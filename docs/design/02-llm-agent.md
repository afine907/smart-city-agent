# 第2章 LLM Agent 层

## 设计思路

### 为什么不用 RL？

| 维度 | RL | LLM |
|------|-----|-----|
| 训练 | 需要 100K+ episodes | 零训练，prompt only |
| 可解释性 | 黑盒 | 自然语言推理（CoT） |
| 泛化 | 受限于训练分布 | 能处理未见过的异常 |
| 维护 | 分布偏移需重训 | 更新 prompt 即可 |
| 成本 | GPU 基础设施 | API 调用 |

### Tool Use 模式

LLM 不直接控制信号灯，而是通过 Tool Use 模式：
1. LLM 观察编码后的交通状态
2. LLM 输出决策 + 推理过程
3. 系统解析决策并执行

这不是让 LLM "训练" 控制策略，而是让 LLM "推理" 出最佳决策。

## Prompt 设计

### System Prompt

```python
SYSTEM_PROMPT = """你是一个城市交通信号灯AI控制系统。

## 角色
你负责控制 {intersection_id} 路口的信号灯。你有 20 年交通工程经验。

## 决策原则
1. **安全第一**: 确保行人和车辆安全
2. **效率优先**: 最小化总等待时间
3. **公平性**: 不要让任何一个方向等待过久
4. **协调性**: 与邻居路口配合，创造绿波带
5. **应急响应**: 紧急车辆永远优先

## 信号灯阶段
- NS_GREEN (0): 南北方向绿灯 (10-60秒)
- NS_YELLOW (1): 南北方向黄灯 (3秒)
- EW_GREEN (2): 东西方向绿灯 (10-60秒)
- EW_YELLOW (3): 东西方向黄灯 (3秒)

## 可用动作
- switch_phase: 切换到指定相位
- extend_green: 延长当前绿灯
- emergency: 紧急模式（全红+紧急通道）

## 输出格式
你必须输出严格的 JSON 格式：
{
    "action": "switch_phase" | "extend_green" | "emergency",
    "phase": "NS_GREEN" | "EW_GREEN",
    "duration": <秒数, 10-60>,
    "reasoning": "<你的决策推理过程>",
    "confidence": <0.0-1.0>,
    "coordination_message": "<给邻居路口的消息, 可选>"
}
"""
```

### User Prompt（每步）

```python
def build_user_prompt(state: dict) -> str:
    return f"""当前路口状态：
- 东向排队: {state['east']['queue']} 辆, 平均等待: {state['east']['avg_wait']:.0f}s
- 西向排队: {state['west']['queue']} 辆, 平均等待: {state['west']['avg_wait']:.0f}s
- 南向排队: {state['south']['queue']} 辆, 平均等待: {state['south']['avg_wait']:.0f}s
- 北向排队: {state['north']['queue']} 辆, 平均等待: {state['north']['avg_wait']:.0f}s
- 当前相位: {state['current_phase']} (已持续 {state['phase_duration']:.0f}s)

请给出决策。"""
```

## CoT 推理

LLM 的 Chain-of-Thought 推理过程是核心价值：

```
观察：
- 南北方向：北向排队 23 辆，南向排队 18 辆，等待时间长
- 东西方向：东向排队 5 辆，西向排队 4 辆，等待时间短
- 当前相位：南北绿灯，已持续 45 秒

分析：
- 南北方向车流量明显高于东西方向（23+18 vs 5+4）
- 南北绿灯已持续 45 秒，北方向仍有 23 辆车排队
- 东西方向车很少，切换不会造成太大影响

决策：延长南北绿灯 15 秒
理由：南北方向仍有大量排队车辆，延长绿灯可以消化更多车流
置信度：0.85
```

这个推理过程：
- 可以展示在 Dashboard 上（可解释性）
- 可以用于调试和优化 prompt
- 可以作为论文的 qualitative analysis

## 响应解析

```python
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class LLMDecision:
    action: str          # switch_phase | extend_green | emergency
    phase: str           # NS_GREEN | EW_GREEN
    duration: int        # 10-60 秒
    reasoning: str       # 推理过程
    confidence: float    # 0.0-1.0
    coordination_msg: Optional[str] = None

class ResponseParser:
    VALID_ACTIONS = {"switch_phase", "extend_green", "emergency"}
    VALID_PHASES = {"NS_GREEN", "EW_GREEN", "NS_YELLOW", "EW_YELLOW"}
    
    @staticmethod
    def parse(response: str) -> Optional[LLMDecision]:
        try:
            # 提取 JSON（处理 markdown 代码块）
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            data = json.loads(response.strip())
            
            # 验证
            if data["action"] not in ResponseParser.VALID_ACTIONS:
                return None
            if data["phase"] not in ResponseParser.VALID_PHASES:
                return None
            
            # 钳位 duration
            data["duration"] = max(10, min(60, data.get("duration", 30)))
            
            return LLMDecision(
                action=data["action"],
                phase=data["phase"],
                duration=data["duration"],
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 0.5),
                coordination_msg=data.get("coordination_message"),
            )
        except (json.JSONDecodeError, KeyError, IndexError):
            return None
    
    @staticmethod
    def fallback(reason: str) -> LLMDecision:
        """LLM 失败时的规则回退。"""
        return LLMDecision(
            action="extend_green",
            phase="NS_GREEN",
            duration=15,
            reasoning=f"LLM 响应无效，使用规则回退: {reason}",
            confidence=0.5,
        )
```

## 多模型支持

```python
class LLMClient:
    """统一的 LLM 客户端，支持多个 provider。"""
    
    def __init__(self, provider: str = "openai", model: str = "gpt-4o"):
        self.provider = provider
        self.model = model
    
    def decide(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        if self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        elif self.provider == "qwen":
            return self._call_qwen(system_prompt, user_prompt)
        elif self.provider == "ollama":
            return self._call_ollama(system_prompt, user_prompt)
    
    def _call_openai(self, system: str, user: str) -> LLMDecision:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,  # 低温度，决策稳定
            max_tokens=500,
        )
        return ResponseParser.parse(response.choices[0].message.content)
```

## 降级策略

```
LLM Decision → Cache Hit → Rule-based → Safe Default
```

```python
class FallbackController:
    """带降级的控制器。"""
    
    def __init__(self, llm_client, cache, rule_engine):
        self.llm = llm_client
        self.cache = cache
        self.rules = rule_engine
    
    def decide(self, state: dict) -> LLMDecision:
        # 1. 尝试缓存
        cached = self.cache.get(state)
        if cached:
            return cached
        
        # 2. 尝试 LLM
        try:
            decision = self.llm.decide(SYSTEM_PROMPT, build_user_prompt(state))
            if decision and decision.confidence > 0.6:
                self.cache.set(state, decision)
                return decision
        except Exception as e:
            pass  # LLM 失败，继续降级
        
        # 3. 规则引擎
        return self.rules.decide(state)
```

## 成本优化

### 分层调用策略

| 层级 | 场景 | 模型 | 成本 |
|------|------|------|------|
| Tier 0 | 规则可处理 | 无 | 免费 |
| Tier 1 | 常规决策 | GPT-4o-mini | ~$0.001/次 |
| Tier 2 | 复杂协调 | GPT-4o | ~$0.01/次 |
| Tier 3 | 缓存命中 | 无 | 免费 |

### 预估成本

```
9 路口城市，每 5 秒一次决策，运行 1 小时：
- 总决策次数: 9 × 720 = 6,480
- 规则处理 (~30%): 1,944 次 = $0
- 缓存命中 (~40%): 2,592 次 = $0
- GPT-4o-mini (~25%): 1,620 次 ≈ $0.05
- GPT-4o (~5%): 324 次 ≈ $1.00

总计: ~$1.05/小时
```
