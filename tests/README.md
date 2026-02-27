# 交易蜘蛛单元测试框架

## 测试框架

- **框架**: pytest 8.x
- **覆盖率**: pytest-cov
- **Mock**: pytest-mock / unittest.mock
- **异步测试**: pytest-asyncio

## 安装依赖

```bash
cd /Users/study/.openclaw/workspace-trading
./mcp-server/.venv/bin/pip install pytest pytest-cov pytest-mock pytest-asyncio
```

## 运行测试

```bash
# 运行所有测试
./mcp-server/.venv/bin/python -m pytest tests/ -v

# 运行特定模块测试
./mcp-server/.venv/bin/python -m pytest tests/test_capital_flow.py -v

# 运行并生成覆盖率报告
./mcp-server/.venv/bin/python -m pytest tests/ --cov=mcp-server --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

## 测试目录结构

```
tests/
├── conftest.py              # pytest 配置和共享 fixture
├── README.md                # 本文档
├── requirements-test.txt    # 测试依赖
├── data_sources/            # 数据源层测试
│   ├── test_tencent.py
│   ├── test_ths.py
│   ├── test_eastmoney.py
│   └── test_capital_flow_manager.py
├── analysis/                # 分析层测试
│   ├── test_technical.py
│   ├── test_capital_flow.py
│   └── test_scoring.py
└── scripts/                 # 脚本测试
    └── test_quant.py
```

## 测试规范

### 1. 命名规范
- 测试文件：`test_<module>.py`
- 测试函数：`test_<function>_<scenario>()`
- 测试类：`Test<Module>`

### 2. 测试类型
- **单元测试**: 测试单个函数/方法
- **集成测试**: 测试模块间交互
- **端到端测试**: 测试完整流程

### 3. Mock 使用原则
- 外部 API 调用必须 Mock
- 数据库/文件系统操作必须 Mock
- 耗时操作 (>1 秒) 建议 Mock

### 4. 断言规范
- 使用 `assert` 语句
- 复杂断言使用 pytest 的 `pytest.approx()`
- 异常测试使用 `pytest.raises()`

## CI/CD 集成

### GitHub Actions (待实现)

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r tests/requirements-test.txt
      - name: Run tests
        run: pytest tests/ --cov=mcp-server --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 测试覆盖率目标

| 模块 | 覆盖率目标 | 优先级 |
|------|-----------|--------|
| `mcp-server/analysis/scoring.py` | >90% | P0 |
| `mcp-server/analysis/capital_flow.py` | >90% | P0 |
| `mcp-server/data_sources/capital_flow_manager.py` | >85% | P0 |
| `mcp-server/data_sources/tencent.py` | >80% | P1 |
| `skills/trading-quant/scripts/quant.py` | >70% | P1 |

## 代码审查流程

1. **PR 提交前**: 本地运行所有测试通过
2. **PR 提交时**: GitHub Actions 自动运行测试
3. **代码审查**: 检查测试覆盖率和测试质量
4. **合并条件**: 所有测试通过 + 覆盖率达标

---

*最后更新：2026-02-27 | 交易蜘蛛测试团队*
