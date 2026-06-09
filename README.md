# JARVIS

**Streaming Spec 驱动的个人 AI 助手框架**

`10 智能体` · `20+ 工具` · `DAG 并行执行` · `技能自进化` · `知识图谱`

JARVIS 是一个模块化的多智能体 AI 助手，基于 **Streaming Spec** 范式构建 —— 将自然语言意图分解为依赖感知的 DAG 任务图，支持并行执行、运行时约束编辑和技能自我进化。

## 快速开始

### 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 安装

```bash
git clone <repo-url> jarvis && cd jarvis
uv sync
```

### 配置

```bash
# LLM 功能需要设置 API Key（可选，不设置也能以 mock 模式运行）
export OPENAI_API_KEY="sk-..."
# 或
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 启动

```bash
# Web UI
jarvis server --port 8000

# 交互式对话
jarvis chat

# 单次任务
jarvis chat "审查 src/ 目录下的代码"

# Streaming Spec 工作流
jarvis spec create "构建用户管理 REST API"
jarvis spec execute <spec-id>
```

## 核心特性

### Streaming Spec 引擎

自然语言意图 → 可执行 DAG → 并行执行 → 运行时约束编辑 → 技能蒸馏

- 依赖感知的并行执行（`asyncio.gather`）
- 人在回路：执行中可添加约束、编辑步骤、重定向意图
- 拓扑排序、关键路径分析、循环检测

### 多智能体系统

| 智能体 | 领域 | 能力 |
|--------|------|------|
| code-agent | 开发 | 代码审查、生成、Git 操作 |
| data-agent | 数据 | CSV 分析、统计 |
| devops-agent | 运维 | Docker、CI/CD、部署 |
| security-agent | 安全 | 漏洞审计、合规检查 |
| research-agent | 研究 | 市场趋势、分析 |
| knowledge-agent | 知识 | 信息检索、综合 |
| writing-agent | 写作 | 文档、博客 |
| ops-agent | 运营 | 服务器健康、监控 |
| comms-agent | 通信 | 邮件、消息 |
| calendar-agent | 日程 | 会议调度、可用性 |

### 技能自进化

完成的 Streaming Spec → 蒸馏为可复用技能 → 基于执行历史自我改进 → 语义版本管理

### 其他子系统

- **知识图谱** — 实体/关系抽取、语义查询、可视化
- **记忆系统** — 5 种记忆类型，关键词 + 重要度 + 时效性评分
- **质量策展** — 准确性、安全性、幻觉检测
- **可观测性** — OpenTelemetry 风格的分布式追踪 + 指标

## 架构

```
CLI / Web UI
     │
  JarvisApp (编排器)
     │
     ├── SpecEngine ──→ SpecExecutor (DAG 并行)
     ├── AgentRegistry (10 个专业智能体)
     ├── ToolRegistry (20+ 内置工具)
     ├── KnowledgeGraph
     ├── MemoryManager
     ├── SkillRegistry (蒸馏 + 进化)
     ├── Curator (质量审核)
     ├── SessionManager
     └── Observability (追踪 + 指标)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 数据模型 | Pydantic v2 |
| Web | FastAPI + Uvicorn + WebSocket |
| CLI | Typer + Rich |
| LLM | OpenAI / Anthropic（可插拔） |
| 测试 | pytest + pytest-asyncio |
| 构建 | Hatch (PEP 517) + uv |

## 测试

```bash
# 完整测试
.venv/bin/python -m pytest tests/ -q

# 集成测试
.venv/bin/python -m pytest tests/test_integration.py -v
```

## 项目结构

```
src/jarvis/
  app.py                 # 顶层编排
  engine/                # Streaming Spec 引擎 + DAG 执行器
  agents/                # 10 个专业智能体 + 编排器
  tools/                 # 20+ 内置工具
  knowledge/             # 知识图谱
  memory/                # 记忆管理
  skills/                # 技能注册 + 进化
  curator/               # 质量审核
  session/               # 会话管理
  observability/         # 追踪 + 指标
  server/                # FastAPI 服务
  cli/                   # Typer CLI
web/                     # 前端界面
tests/                   # 测试套件
```
