# Quant Core (量化分析核心层)

> 目录名保留为 `mcp-server/` 以兼容现有路径引用。实际为 Python 量化分析库，不是独立的 MCP Server 进程。

## 当前架构

```
OpenClaw Agent
  └─ exec tool → quant.py (CLI wrapper)
       └─ import from mcp-server/ (as library)
            ├── data_sources/   数据源 (腾讯/新浪/东财/同花顺)
            ├── analysis/       分析引擎 (评分/技术指标/资金流)
            └── config.py       配置
```

## 集成方式

**exec-based Skill** (非 MCP plugin):
- OpenClaw Agent 通过 `exec` 工具调用 `quant.py <tool> [args]`
- `quant.py` 作为 CLI wrapper 导入本目录的 Python 模块
- 输出结构化 JSON，agent 解读后生成报告

## 工具列表

见 `../skills/trading-quant/SKILL.md` 完整工具清单。
