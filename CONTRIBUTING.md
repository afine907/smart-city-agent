# Contributing to LLM Traffic Timing Assistant

感谢您对本项目的关注！我们欢迎各种形式的贡献。

## 🚀 快速开始

### 环境准备

```bash
# 克隆仓库
git clone https://github.com/afine907/smart-city-agent.git
cd smart-city-agent

# 安装依赖
pip install -e ".[llm,dev]"

# 运行测试
python -m pytest tests/ -v
```

### 开发工具

- **代码风格**: Ruff (linting + formatting)
- **类型检查**: mypy
- **测试**: pytest + pytest-cov
- **构建**: hatchling

## 📝 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### 类型 (type)

- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整（不影响功能）
- `refactor`: 重构（既不修复 bug 也不添加功能）
- `perf`: 性能优化
- `test`: 添加或修改测试
- `chore`: 构建过程或辅助工具的变动

### 示例

```
feat(api): add traffic statistics endpoint
fix(signal): correct phase transition timing
test(crew): add coordination test coverage
docs: update README with new CLI commands
```

## 🔧 开发流程

### 1. 创建分支

```bash
git checkout -b feat/your-feature-name
```

### 2. 编写代码

- 遵循现有代码风格
- 添加类型注解
- 编写文档字符串

### 3. 运行检查

```bash
# Lint
ruff check src/ tests/

# 类型检查
mypy src/traffic_agent/

# 测试
python -m pytest tests/ -v --cov=traffic_agent
```

### 4. 提交代码

```bash
git add .
git commit -m "feat(module): your feature description"
```

### 5. 创建 Pull Request

- 填写 PR 模板
- 关联相关 Issue
- 等待 CI 检查通过

## 🧪 测试指南

### 运行测试

```bash
# 所有测试
python -m pytest tests/ -v

# 特定模块
python -m pytest tests/test_signal_controller.py -v

# 带覆盖率
python -m pytest tests/ --cov=traffic_agent --cov-report=html
```

### 编写测试

- 每个新功能都应有对应测试
- 测试文件命名: `test_<module>.py`
- 测试函数命名: `test_<behavior>`
- 使用 pytest fixtures 复用设置

### 测试结构

```python
class TestFeatureName:
    """Test feature description."""

    def test_basic_behavior(self):
        """Test basic expected behavior."""
        # Arrange
        # Act
        # Assert

    def test_edge_case(self):
        """Test edge case handling."""
        pass
```

## 📚 文档指南

### 代码文档

- 所有公共 API 必须有文档字符串
- 使用 Google 风格文档字符串
- 包含类型注解

```python
def process_data(data: dict[str, Any], threshold: float = 0.5) -> Result:
    """
    Process input data and return results.

    Args:
        data: Input data dictionary
        threshold: Processing threshold (0.0 to 1.0)

    Returns:
        Processed result object

    Raises:
        ValueError: If data is invalid
    """
    pass
```

### README 更新

- 新功能需要更新 README
- 包含使用示例
- 保持中英文版本同步

## 🐛 报告 Bug

### 使用 Issue 模板

请使用 Bug Report 模板，包含：

1. **环境信息**
   - Python 版本
   - 操作系统
   - 依赖版本

2. **重现步骤**
   - 详细的操作步骤
   - 输入数据
   - 预期行为
   - 实际行为

3. **错误日志**
   - 完整的错误堆栈
   - 相关日志

## 💡 功能建议

### 使用 Feature Request 模板

请包含：

1. **问题描述**: 您遇到的问题
2. **解决方案**: 您期望的解决方案
3. **替代方案**: 您考虑过的其他方案
4. **上下文**: 相关的背景信息

## 📋 Issue 标签

- `bug`: Bug 报告
- `enhancement`: 功能增强
- `documentation`: 文档相关
- `good first issue`: 适合新手
- `help wanted`: 需要帮助

## 🎯 开发重点

### 当前优先级

1. **测试覆盖率**: 提升到 85%+
2. **性能优化**: 减少 LLM 调用延迟
3. **文档完善**: API 文档和教程
4. **功能增强**: 交通预测和可视化

### 技术债务

查看 `ITERATION_PLAN.md` 了解当前的技术债务和改进计划。

## 📞 联系方式

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: 1049905106@qq.com

## 📄 许可证

贡献的代码将使用与项目相同的 MIT 许可证。

---

再次感谢您的贡献！🎉
