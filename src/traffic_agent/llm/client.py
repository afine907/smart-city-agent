"""
LLM Client — Unified interface for LLM API calls.

Supports OpenAI, Qwen, LongCat, and other OpenAI-compatible APIs.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


def load_env():
    """Load .env file if present."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


@dataclass
class LLMConfig:
    """LLM configuration."""
    # Model selection
    fast_model: str = "LongCat-Flash-Chat"        # Routine decisions
    smart_model: str = "LongCat-Flash-Thinking-2601"  # Complex coordination
    
    # API settings
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    timeout: float = 10.0
    max_retries: int = 3
    
    # Cost tracking
    cost_per_1k_input: float = 0.00015
    cost_per_1k_output: float = 0.0006
    
    def __post_init__(self):
        load_env()  # Load .env first
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY", "")
        if self.api_base is None:
            self.api_base = os.getenv("OPENAI_API_BASE", "https://api.longcat.chat/openai")


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0


class LLMClient:
    """
    Unified LLM client with cost tracking and fallback.
    
    Usage:
        client = LLMClient(config)
        response = client.chat("你是一个交通工程师...", "当前路况数据...")
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._total_cost = 0.0
        self._total_calls = 0

        # Create reusable OpenAI client
        import openai
        self._client = openai.OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.api_base,
            timeout=self.config.timeout,
        )
    
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Send a chat completion request.
        
        Args:
            system_prompt: System message
            user_message: User message
            model: Model to use (default: fast_model)
            temperature: Sampling temperature
            max_tokens: Max response tokens
        
        Returns:
            LLMResponse with content and metadata
        """
        model = model or self.config.fast_model
        start_time = time.time()

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            content = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            latency = (time.time() - start_time) * 1000

            cost = self._calculate_cost(tokens_in, tokens_out, model)
            self._total_cost += cost
            self._total_calls += 1

            return LLMResponse(
                content=content,
                model=model,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                latency_ms=latency,
                cost=cost,
            )
            
        except Exception as e:
            # Fallback: return error response
            return LLMResponse(
                content=json.dumps({
                    "action": "extend_green",
                    "phase": "NS_GREEN",
                    "duration": 15,
                    "reasoning": f"LLM调用失败: {str(e)}，使用默认决策",
                    "confidence": 0.3,
                }),
                model=model or "fallback",
                latency_ms=(time.time() - start_time) * 1000,
            )
    
    def _calculate_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate API call cost using CostTracker pricing."""
        from traffic_agent.optimization.cost_tracker import MODEL_COSTS

        costs = MODEL_COSTS.get(model, {"input": 0.0001, "output": 0.0002})
        return (tokens_in * costs["input"] + tokens_out * costs["output"]) / 1000
    
    def get_stats(self) -> Dict[str, Any]:
        """Return usage statistics."""
        return {
            "total_calls": self._total_calls,
            "total_cost": self._total_cost,
            "avg_cost_per_call": self._total_cost / max(1, self._total_calls),
        }
