# SuperAgent Runtime Architecture PRD

> 来源材料：[docs/总体架构.md](../总体架构.md) 与 [docs/agent-runtime-architecture-visual.html](../agent-runtime-architecture-visual.html)。
> 本文保留设计历史与决策记录。**当前运行时代码契约以 [README.md](../../README.md) 与 [docs/maps/](../maps/) 为准。**

## Implementation Status (2026-06-03)

Tasks 01–15 from `docs/prompts/` are complete. Summary:

| PRD area | Status | Code / notes |
|----------|--------|----------------|
| State schema + graph skeleton | **Implemented** | `state.py`, `graph.py` |
| SiliconFlow LLM adapter | **Implemented** | `llm.py` |
| Checkpoint + PostgreSQL | **Implemented** | `memory/checkpoint.py`; optional at compile |
| Graphiti long-term memory | **Implemented (write)** | `memory/graphiti.py`, `memory/policy.py`; `load_memory` read still stub |
| Context budget + compression | **Implemented** | `context_budget.py` |
| Intent / complexity router | **Implemented** | `router.py` |
| Direct answer path | **Implemented** | `nodes/direct.py` |
| MCP + ReAct loop | **Implemented** | `tools/mcp.py`, `nodes/react.py`; example filesystem MCP only |
| Plan-and-Execute | **Implemented** | `planning.py`, `nodes/planner.py` |
| Parallel multi-agent | **Implemented (mock workers)** | `workers/*`, `nodes/orchestrator.py` |
| Reflection / evaluator / revise | **Implemented** | `reflection.py` |
| Memory write policies | **Implemented** | `memory/policy.py`, `nodes/memory_write.py` |
| Observability / path metrics | **Implemented** | `observability.py` |
| LangGraph Platform deploy | **Not planned (phase 1)** | Local `langgraph dev` only |
| Production MCP servers | **Follow-up** | Backend-provided servers; client adapter ready |
| Production worker agents | **Follow-up** | Mock registry replaced per role |
| UI / multi-tenant | **Not planned (phase 1)** | Per PRD non-goals |

Architecture maps: [docs/maps/README.md](../maps/README.md).

---

## 1. 背景

当前仓库基于 LangGraph Python 模板初始化，现有 `src/agent/graph.py` 仍是单节点示例图。`docs/总体架构.md` 给出了目标 Agent Runtime 的高层流程：从用户输入开始，经过记忆加载、上下文预算、意图路由、ReAct 工具循环、Plan-and-Execute、多 Agent 编排、反思评估、记忆写入，最终输出结果。

SuperAgent 的目标不是只做一个固定问答机器人，而是沉淀一套可逐步演进的 Agent Runtime 骨架。它需要能按任务复杂度选择执行路径，在长上下文、工具调用、任务拆分、专业 Agent 分工、质量检查和记忆沉淀之间形成清晰的控制面。

## 2. 产品目标

SuperAgent 要提供一个基于 LangGraph 的通用 Agent Runtime，支持以下能力：

1. 接收用户目标与上下文，并形成结构化运行状态。
2. 加载短期、长期、实体等记忆，为当前任务补充背景。
3. 对上下文长度进行预算检查，必要时执行压缩、摘要和重要性过滤。
4. 判断任务类型与复杂度，并路由到直接回答、ReAct 工具循环、Plan-and-Execute 或 Multi-Agent 编排路径。
5. 对需要工具的任务执行可观察、可限制步数、可降级的 ReAct 循环。
6. 对复杂目标进行计划拆分、依赖校验、步骤执行和中间结果记录。
7. 对需要专业分工或并行处理的任务编排不同 Worker Agent。
8. 在最终输出前按策略执行质量检查、修正或降级。
9. 将有价值的事实、偏好、实体和任务结果写入记忆层。

## 3. 非目标

本 PRD 不要求一次性实现完整生产系统，后续应按任务卡拆成可验证的小步。

非目标包括：

1. 不在第一阶段实现完整 UI、账号系统或多租户管理。
2. 不在第一阶段考虑 LangGraph Platform 部署，只支持本地 `langgraph dev` 运行与调试。
3. 不默认实现复杂权限体系，只保留权限与安全检查扩展点。
4. 不把所有 Agent 类型一次性实现到生产质量，可先做最小可运行 Worker。
5. 不在第一阶段支持多 LLM provider，只支持硅基流动。
6. 不绕过 LangGraph 的状态图模型去写不可观察的脚本式执行流。

## 4. 第一阶段确认决策

| Decision | Choice |
|----------|--------|
| Runtime target | 只做本地 LangGraph dev，不考虑 LangGraph Platform 部署 |
| LLM provider | 只支持硅基流动，使用其 OpenAI-compatible API 形态接入 |
| 短期记忆 | LangGraph checkpoint + PostgreSQL |
| 长期记忆 | 本地部署 Graphiti |
| 工具协议 | 支持外部工具，第一阶段以 MCP 协议接入 |
| 首批工具 | MCP server 由后续后端工程提供；SuperAgent 只实现 MCP client/adapter 能力，第一阶段可选一个公开或本地 demo MCP server 做示例 |
| Multi-Agent | 第一阶段支持并行 Worker 编排 |
| Reflection | 部分开启，只对复杂、高风险、工具/计划/多 Agent 路径或显式要求质量检查的任务启用 |
| 环境变量命名 | 保留从 commonAgent 迁移过来的命名，并补充 SuperAgent 新增配置 |

## 4.1 第一阶段默认参数

| Area | Default |
|------|---------|
| LangSmith project | `SUPER_AGENT` |
| LangSmith endpoint | `https://api.smith.langchain.com` |
| LLM base URL | `https://api.siliconflow.cn/v1` |
| LLM model | `Pro/moonshotai/Kimi-K2.6` |
| LLM timeout | 60 seconds |
| LLM max tokens | 4096 |
| ReAct max steps | 8 |
| Plan max steps | 12 |
| Worker max concurrency | 4 |
| Worker timeout | 120 seconds |
| Tool timeout | 30 seconds |
| Reflection max rounds | 1 |
| Reflection enabled paths | tool、plan、multi-agent、高风险、低置信路由、用户显式要求检查 |
| MCP connection | SuperAgent 作为 MCP client 连接后端提供的 MCP server；server 启动方式指 MCP server 进程/URL/传输配置，不是 SuperAgent 对外暴露业务接口 |
| Example MCP server | 官方 filesystem MCP server：`npx -y @modelcontextprotocol/server-filesystem ./docs`，仅用于第一阶段连通性示例 |
| PostgreSQL checkpoint | 使用 `langgraph-checkpoint-postgres` + `psycopg[binary,pool]`；运行时使用 `AsyncPostgresSaver.from_conn_string(DATABASE_URL)`，首次启动或 `CHECKPOINT_SETUP=true` 时调用 `await checkpointer.setup()` |
| Graphiti deployment | 本地 Docker/OrbStack 部署；默认采用 Graphiti MCP Server Docker Compose 的 FalkorDB 后端，后续需要 Neo4j 时再切换 |
| Worker cancellation | 并行 Worker 使用超时驱动取消；超时或异常的 Worker 标为 `failed`，不阻断其他 Worker，聚合阶段输出 partial |
| Reflection threshold | `route_confidence < 0.72`、工具/计划/多 Agent 路径、fallback 前、用户显式要求检查或高风险关键词命中时开启 |

## 5. 当前事实与目标差距

> **Historical.** At PRD authoring time the repo was a LangGraph template. As of task 15 completion, the “目标状态” column below is largely met; remaining gaps are called out in the Implementation Status table and README “Implemented vs planned”.

| Area | 当前事实 (2026-06-03) | 目标状态 |
|------|----------|----------|
| Runtime | 多路径 LangGraph 状态图 (`graph.py`) | 多路径 Agent Runtime 状态图 |
| State | 显式 `AgentState` 字段 + observability | 包含输入、上下文、记忆、路由决策、计划、工具结果、评估结果和输出 |
| Router | `router.py` 结构化路由 | 基于任务类型、复杂度和约束选择执行路径 |
| Tools | MCP client + ReAct；示例 filesystem server | 通过 MCP 接入外部工具，并有工具注册、参数校验、执行、观察结果写入和错误处理 |
| Planning | plan/validate/execute/observe 循环 | 支持 plan/validate/execute/observe/done |
| Multi-Agent | 并行 mock Worker 编排 | 支持 researcher/coder/reviewer/memory_manager 等 Worker 并行编排 |
| Reflection | 部分开启的 gate/evaluator/revise | 支持部分开启的 evaluator、revise、max rounds 和 fallback |
| Memory | checkpoint + Graphiti 写入；`load_memory` 读仍为占位 | 短期记忆使用 checkpoint + PostgreSQL，长期记忆使用本地 Graphiti |
| Observability | `runtime_events` / `path_metrics` | 对关键决策、路径、错误、降级和质量检查可追踪 |

## 6. 目标用户与使用场景

### 6.1 目标用户

1. Agent 工程开发者：需要一个可调试、可测试、可扩展的 LangGraph Agent Runtime 骨架。
2. 产品/业务构建者：希望用同一套 Agent Runtime 支持问答、工具执行、复杂任务拆分和专业 Agent 协作。
3. 后续自动化开发 Agent：需要从 PRD、任务卡和进度文档中理解边界并逐步实现。

### 6.2 核心场景

1. 简单问答：用户提出无需工具和复杂规划的问题，系统直接回答，并按需写入记忆。
2. 工具增强任务：用户请求需要外部信息、文件、代码、搜索或 API，系统进入 ReAct 工具循环。
3. 复杂目标执行：用户提出多步骤目标，系统先拆计划，再逐步执行并聚合结果。
4. 专业分工任务：任务需要研究、编码、审查、记忆管理等角色协作，系统交给 Multi-Agent 编排。
5. 长上下文任务：上下文超过预算时，系统压缩历史、保留关键事实，再继续执行。
6. 质量敏感输出：最终答案需要事实、完整性、约束或格式检查，系统执行反思评估和修正。

## 7. 目标运行流

```mermaid
flowchart TD
  START([START]) --> intake["intake_input<br/>接收用户目标与上下文"]

  intake --> load_memory["load_memory<br/>加载短期/长期/实体记忆"]
  load_memory --> context_budget["context_budget_check<br/>检查上下文窗口"]

  context_budget -->|上下文过长| compress_memory["compress_memory<br/>滑动窗口 + 摘要 + 重要性过滤"]
  context_budget -->|上下文正常| intent_router["intent_router<br/>判断任务类型与复杂度"]
  compress_memory --> intent_router

  intent_router -->|简单问答| direct_answer["direct_answer<br/>直接回复"]
  intent_router -->|需要工具/外部信息| react_loop["react_agent<br/>ReAct 推理循环"]
  intent_router -->|复杂目标| planner["planner<br/>Plan-and-Execute 任务拆分"]
  intent_router -->|专业分工/并行任务| orchestrator["multi_agent_orchestrator<br/>多 Agent 编排"]

  direct_answer --> reflection_gate["reflection_gate<br/>是否需要质量检查"]

  react_loop --> tool_router["tool_router<br/>选择工具"]
  tool_router --> tool_exec["tool_executor<br/>执行工具并校验参数"]
  tool_exec --> observation["observation<br/>写入工具结果"]
  observation --> react_continue{"是否继续 ReAct?"}
  react_continue -->|继续| react_loop
  react_continue -->|完成| reflection_gate
  react_continue -->|超过 max_steps| fallback["fallback_handler<br/>降级/澄清/返回部分结果"]

  planner --> plan_validate["plan_validate<br/>校验子任务/依赖/验收标准"]
  plan_validate --> execute_plan["execute_plan<br/>执行计划步骤"]
  execute_plan --> step_router{"步骤类型"}
  step_router -->|普通 LLM 步骤| llm_step["llm_step_executor"]
  step_router -->|工具步骤| tool_router
  step_router -->|需要专业 Agent| orchestrator

  llm_step --> step_observe["step_observe<br/>记录中间结论"]
  step_observe --> plan_done{"计划完成?"}
  observation --> plan_done
  plan_done -->|未完成| execute_plan
  plan_done -->|完成| reflection_gate

  orchestrator --> agent_router["agent_router<br/>选择 Worker Agent"]
  agent_router --> researcher["researcher_agent"]
  agent_router --> coder["coder_agent"]
  agent_router --> reviewer["reviewer_agent"]
  agent_router --> memory_manager["memory_manager_agent"]

  researcher --> agent_result["agent_result_aggregate<br/>聚合子 Agent 结果"]
  coder --> agent_result
  reviewer --> agent_result
  memory_manager --> agent_result

  agent_result --> multi_done{"多 Agent 任务完成?"}
  multi_done -->|未完成/需切换| orchestrator
  multi_done -->|完成| reflection_gate

  reflection_gate -->|不需要反思| memory_write["memory_write<br/>写入长期/实体记忆"]
  reflection_gate -->|需要反思| evaluator["evaluator<br/>事实/完整性/约束/格式检查"]

  evaluator --> eval_pass{"PASS?"}
  eval_pass -->|通过| memory_write
  eval_pass -->|未通过且未超过轮次| revise["revise<br/>按评估意见修正"]
  eval_pass -->|超过 max_reflection_rounds| fallback

  revise --> reflection_gate

  fallback --> memory_write
  memory_write --> final_answer["final_answer<br/>输出最终结果"]
  final_answer --> END([END])
```

## 8. 功能需求

### 8.1 输入接收与状态初始化

系统应将用户输入、会话上下文、运行配置和调用元数据整理为统一状态。该状态应能被 LangGraph 节点读写，并支撑后续记忆、路由、工具、计划和评估流程。

最低要求：

1. 支持用户消息与可选上下文。
2. 支持运行配置，例如最大工具步数、最大反思轮次、是否启用记忆、是否启用评估。
3. 记录运行 ID、线程 ID 或等价追踪字段，便于调试和测试。

### 8.2 LLM Provider

第一阶段只支持硅基流动。实现应通过硅基流动的 OpenAI-compatible API 形态接入模型，但不要把多 provider adapter 作为第一阶段目标。

最低要求：

1. 保留 commonAgent 迁移过来的 OpenAI-compatible 环境变量命名，例如 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME`。
2. `.env_example` 中给出硅基流动所需配置项和安全占位值，不写真实 key。
3. LLM adapter 应集中封装，避免业务节点直接散落读取环境变量。
4. 测试中必须支持 fake/mock LLM，避免单元测试依赖真实硅基流动接口。

### 8.3 记忆读取

系统应在主要执行路径前读取相关记忆。第一阶段记忆分为两层：短期记忆使用 LangGraph checkpoint + PostgreSQL，长期记忆使用本地部署 Graphiti。短期记忆服务线程/会话恢复，长期记忆服务用户事实、实体关系、偏好和跨会话知识。

最低要求：

1. 记忆读取失败不得中断主流程，应记录错误并继续执行。
2. 记忆结果必须有来源标识，避免与用户当前输入混淆。
3. checkpoint 读写应保留 thread/session 维度。
4. PostgreSQL 连接配置应沿用 commonAgent 迁移的命名风格，并补齐缺失项。
5. Graphiti 本地服务不可用时，应允许降级到无长期记忆路径。
6. 支持在测试中使用内存或 mock 实现。

### 8.4 上下文预算与压缩

系统应在进入模型推理前检查上下文预算。当上下文过长时，执行压缩策略。

最低要求：

1. 计算或估算当前输入、历史、记忆、工具结果的上下文占用。
2. 超限时执行滑动窗口、摘要或重要性过滤。
3. 压缩后保留用户当前目标、硬约束、最近交互和高价值事实。
4. 压缩行为应可测试、可追踪。

### 8.5 意图与复杂度路由

系统应根据任务类型、复杂度和约束选择执行路径。

路由结果至少包括：

1. `direct_answer`：简单问答或无需工具任务。
2. `react_agent`：需要工具或外部信息。
3. `planner`：多步骤复杂目标。
4. `multi_agent_orchestrator`：需要专业分工或并行处理。
5. `fallback`：输入不足、风险过高或无法安全执行。

路由结果应包含理由、置信度和可观察字段，便于后续测试与调优。

### 8.6 Direct Answer

对简单请求，系统应直接生成回答，并进入反思门或记忆写入。

最低要求：

1. 不应无意义进入工具循环。
2. 应遵守用户约束、语言和格式要求。
3. 对可能需要最新信息、外部信息或高风险判断的问题，应路由到工具或 fallback，而不是直接猜测。

### 8.7 ReAct 工具循环

对需要工具的任务，系统应执行 ReAct 风格循环：选择工具、校验参数、执行工具、记录观察、判断是否继续。第一阶段外部工具通过 MCP 协议接入，具体工具由实现阶段选择最小可用集合，优先覆盖搜索、文件或知识检索、代码辅助等对 Agent Runtime 骨架有验证价值的工具。

最低要求：

1. 有 MCP server 配置、工具发现、工具注册与工具 schema。
2. 工具调用前校验参数。
3. 工具执行失败时写入 observation，并决定重试、换工具或 fallback。
4. 支持 `max_steps` 限制。
5. 每一步工具选择、输入、输出摘要和错误都可追踪。
6. MCP 连接失败时不得阻断简单问答路径，应只影响工具相关路径。
7. 工具结果写入 observation 时应做大小限制和敏感信息过滤。
8. 在后端正式 MCP server 交付前，示例 MCP server 固定使用官方 filesystem server：`npx -y @modelcontextprotocol/server-filesystem ./docs`。

### 8.8 Plan-and-Execute

对复杂目标，系统应先生成计划，再校验计划，再按步骤执行。

最低要求：

1. 计划包含子任务、依赖、预期产出和验收标准。
2. 计划校验失败时可要求修正或 fallback。
3. 步骤类型可分为普通 LLM 步骤、工具步骤、专业 Agent 步骤。
4. 每个步骤都写入中间观察结果。
5. 最终聚合时应说明完成情况、未完成项和风险。

### 8.9 Multi-Agent 编排

对需要分工的任务，系统应通过 orchestrator 选择 Worker Agent 并聚合结果。第一阶段应支持并行 Worker 编排，而不是只做串行执行。并行实现必须保留依赖关系、超时控制、错误隔离和结果聚合规则。

首批 Worker 建议包括：

1. `researcher_agent`：资料检索、信息整理、事实归纳。
2. `coder_agent`：代码实现、局部重构、测试补充。
3. `reviewer_agent`：审查输出质量、风险、测试缺口。
4. `memory_manager_agent`：提取可写入长期记忆的事实或偏好。

最低要求：

1. Worker 输入输出结构统一。
2. Orchestrator 能根据任务状态选择一组可并行 Worker，并在依赖未满足时延后执行。
3. 聚合结果必须保留来源和置信信息。
4. Worker 失败不应导致不可解释崩溃，应进入 fallback 或局部降级。
5. 并行 Worker 必须有超时、取消或局部失败处理策略。
6. 聚合阶段应能区分 completed、partial、failed 和 skipped。
7. 取消语义按工程可实现优先：Worker 超时或异常即标记为 `failed`，不强制终止已不可中断的底层 LLM/API 调用，但聚合阶段不等待超过 `WORKER_TIMEOUT_SECONDS` 的结果。

### 8.10 Reflection 与 Evaluator

系统应在需要时对输出执行质量检查。第一阶段采用“部分开启”策略：简单、低风险、无工具的直接回答默认不强制评估；复杂目标、工具路径、计划路径、多 Agent 路径、高风险主题、用户显式要求质量检查或路由置信度低的任务应进入 reflection gate。检查范围包括事实正确性、完整性、约束遵守、格式和安全边界。

最低要求：

1. `reflection_gate` 判断是否需要评估。
2. `evaluator` 输出 PASS/FAIL、问题列表和修正建议。
3. 未通过且未超过最大轮次时进入 `revise`。
4. 超过最大轮次时进入 fallback，输出部分结果和风险说明。
5. 评估链路可关闭，以支持低成本路径和单元测试。
6. reflection gate 应输出是否开启评估的理由，避免质量检查策略不可解释。
7. 第一阶段低置信阈值固定为 `route_confidence < 0.72`；高风险先用关键词/类别规则实现，覆盖安全、法律、医疗、金融、生产变更、删除数据、凭证/权限等任务。

### 8.11 Fallback

系统应在工具失败、路由不确定、计划不可执行、反思多次失败或输入不足时进入 fallback。

fallback 输出类型包括：

1. 请求用户澄清。
2. 返回部分结果并说明缺口。
3. 降级到无工具回答。
4. 明确拒绝无法安全执行的请求。

### 8.12 记忆写入

系统应在最终输出前后抽取值得长期保存的信息，并写入记忆层。短期状态应通过 checkpoint + PostgreSQL 保持会话连续性；长期事实、实体和关系写入本地 Graphiti。

最低要求：

1. 只写入稳定、有价值、非敏感或已获允许的信息。
2. 写入失败不得阻断最终回答。
3. 记忆写入结果应可观察，例如 stored/skipped/error。
4. 支持关闭记忆写入。
5. Graphiti 写入应保留来源、时间和置信信息。
6. checkpoint 写入应与 LangGraph thread/session 契约一致。

## 9. 状态与数据契约

后续实现应定义清晰的 State schema。建议最小字段如下：

| Field | Purpose |
|-------|---------|
| `messages` | 用户输入、系统消息和模型消息 |
| `runtime_config` | max steps、reflection rounds、feature flags |
| `memory_context` | 读取到的短期/长期/实体记忆 |
| `context_budget` | token 估算、是否压缩、压缩摘要 |
| `intent_decision` | 路由目标、理由、置信度 |
| `plan` | 子任务、依赖、验收标准 |
| `current_step` | 当前计划步骤 |
| `mcp_sessions` | MCP server 连接状态、可用工具摘要 |
| `tool_calls` | 工具调用历史 |
| `observations` | 工具和步骤结果 |
| `agent_results` | Worker Agent 输出 |
| `evaluation` | 反思评估结果 |
| `fallback_reason` | 降级原因 |
| `memory_write_result` | 记忆写入状态 |
| `final_answer` | 最终输出 |

所有跨节点共享字段都应有测试覆盖，避免隐式字典字段漂移。

## 10. 配置与环境变量

配置应支持本地 `langgraph dev`、测试和后续演进。第一阶段保留从 commonAgent 迁移过来的环境变量命名，并在此基础上补充 SuperAgent 新增配置。不要为了新项目整洁而破坏已有 `.env` 的兼容命名。

建议配置分组：

1. LLM：硅基流动 API key、base URL、模型名、timeout、max tokens；命名优先保留 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME` 等 OpenAI-compatible 变量。
2. LangSmith：tracing 开关、project、endpoint、API key。
3. Runtime：max tool steps、max reflection rounds、router mode。
4. Short-term memory：checkpoint 开关、PostgreSQL DSN、thread/session 配置。
5. Long-term memory：Graphiti 本地服务 URL、写入开关、读写限制。
6. MCP tools：MCP server 配置、工具启用开关、工具超时、安全策略。
7. Server：LangGraph dev/server 相关配置。

第一阶段默认值：

```dotenv
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=SUPER_AGENT
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL_NAME=Pro/moonshotai/Kimi-K2.6
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=4096

REACT_MAX_STEPS=8
PLAN_MAX_STEPS=12
WORKER_MAX_CONCURRENCY=4
WORKER_TIMEOUT_SECONDS=120
TOOL_TIMEOUT_SECONDS=30
REFLECTION_MAX_ROUNDS=1

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true

MCP_EXAMPLE_SERVER_COMMAND=npx
MCP_EXAMPLE_SERVER_ARGS=-y @modelcontextprotocol/server-filesystem ./docs
MCP_TOOL_TIMEOUT_SECONDS=30

GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

`OPENAI_API_KEY` 和 `LANGSMITH_API_KEY` 只允许放在本地 `.env`，不得写入 PRD、README、`.env_example` 或任务卡。

约束：

1. `.env` 不提交。
2. `.env_example` 只保留 key 与安全默认值，不包含真实密钥。
3. 新增环境变量必须同步 `.env_example` 和文档。
4. 如果 commonAgent 迁移变量与 SuperAgent 目标语义冲突，应在文档中标注兼容别名与最终推荐名，不直接删除旧变量。
5. 用户提供的真实 key 只用于本地 `.env` 验证，不进入 git。

## 11. 可观察性与调试

系统应优先保证关键控制面可观察。

必须追踪的事件：

1. 输入接收与运行 ID。
2. 记忆读取结果摘要。
3. 上下文预算与压缩决策。
4. 路由决策、理由和置信度。
5. MCP server 连接、工具发现、工具调用、参数校验、观察结果和错误。
6. 计划生成、校验、步骤执行和完成状态。
7. 并行 Worker Agent 选择、启动、完成、失败、输出和聚合。
8. Reflection gate 决策、Evaluator PASS/FAIL 与 revise 轮次。
9. fallback 原因。
10. 记忆写入状态。

## 12. 测试要求

后续任务拆分应优先补测试护栏，再扩大实现。

建议测试层级：

1. 单元测试：router、context budget、plan validate、tool schema、evaluator gate、memory write policy。
2. 图级测试：LangGraph 不同路径的最小输入输出。
3. 契约测试：State schema 字段、MCP 工具调用记录、fallback 输出结构。
4. Mock 集成测试：无真实外部服务时模拟硅基流动 LLM、MCP 工具、PostgreSQL checkpoint 和 Graphiti。
5. 并行测试：Worker 并发执行、局部失败、超时和聚合。
6. 可选真实链路测试：在配置真实硅基流动 API key、PostgreSQL、Graphiti 和 MCP server 后跑 smoke test。

基础验证命令建议：

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
```

## 13. 验收标准

整体架构完成后，应满足：

1. `langgraph dev` 可以启动目标图。
2. 简单问答路径不进入工具或计划节点。
3. 硅基流动作为唯一真实 LLM provider 可被本地 dev 环境调用。
4. 短期记忆可以通过 checkpoint + PostgreSQL 维持 thread/session 状态。
5. 长期记忆可以在本地 Graphiti 可用时读写，Graphiti 不可用时可降级。
6. 工具任务可以通过 MCP 完成至少一个 mock 或本地 MCP 工具调用循环。
7. 复杂任务可以生成、校验并执行一个多步骤计划。
8. Multi-Agent 路径可以并行选择多个 Worker，并聚合 completed/partial/failed/skipped 结果。
9. Reflection 只在配置或策略要求的路径开启，并能在 FAIL 后 revise，受最大轮次限制。
10. fallback 在超限、失败或输入不足时给出可解释结果。
11. 记忆读写可以使用 mock backend，并记录读写状态。
12. 关键路径有单元测试和图级测试。
13. `.env` 被忽略，`.env_example` 与新增配置保持同步，并保留 commonAgent 迁移命名。
14. README、progress、prompts 和 PRD 在后续任务完成时同步更新。

## 14. 建议拆分方向

后续使用 `$requirement-planner` 拆分时，建议按以下顺序拆成任务卡：

1. 文档治理与当前模板基线：README、progress、docs order、现状说明。
2. State schema 与基础图骨架：统一状态、配置、最小节点。
3. 硅基流动 LLM adapter：OpenAI-compatible 封装、mock LLM、配置校验。
4. 短期记忆 checkpoint + PostgreSQL：thread/session 状态、mock fallback。
5. 长期记忆 Graphiti：本地服务 client、读写策略、降级路径。
6. 上下文预算与压缩：budget、compress、记忆上下文裁剪。
7. 意图/复杂度路由：direct/react/planner/multi-agent/fallback 决策。
8. Direct Answer：可测试的简单回答路径。
9. MCP 工具系统与 ReAct 循环：MCP server 配置、工具发现、mock 工具、max steps、observation。
10. Plan-and-Execute：计划 schema、校验、步骤执行。
11. 并行 Multi-Agent orchestrator：Worker 契约、并行执行、超时和聚合。
12. Reflection/evaluator/revise：部分开启策略、质量检查与修正轮次。
13. Memory write 与策略：短期 checkpoint 写入、Graphiti 长期写入、过滤策略。
14. 可观察性与 tracing：路径事件、MCP、并行 Worker、LangSmith 对齐。
15. 最终文档与运行收口：README、maps、progress、PRD 状态更新。

## 15. 已确认问题

1. 第一阶段只做本地 `langgraph dev`。
2. 首批真实 LLM provider 只支持硅基流动。
3. 短期记忆使用 checkpoint + PostgreSQL。
4. 长期记忆使用本地部署 Graphiti。
5. 工具系统支持外部工具，并通过 MCP 协议接入。
6. 第一阶段 Multi-Agent 支持并行 Worker 编排。
7. Reflection 部分开启，不默认覆盖所有路径。
8. 保留从 commonAgent 迁移过来的环境变量命名。
9. 示例 MCP server 固定使用官方 filesystem MCP server：`npx -y @modelcontextprotocol/server-filesystem ./docs`。
10. PostgreSQL checkpoint 使用 `langgraph-checkpoint-postgres`，通过 `AsyncPostgresSaver.from_conn_string(DATABASE_URL)` 接入，并用 `setup()` 初始化表。
11. Graphiti 本地部署默认采用 Graphiti MCP Server Docker Compose 的 FalkorDB 后端，运行在 OrbStack/Docker。
12. 并行 Worker 超时按 failed 处理，聚合输出 partial，不等待超过 `WORKER_TIMEOUT_SECONDS` 的结果。
13. Reflection 低置信阈值为 `route_confidence < 0.72`，高风险先用关键词/类别规则实现。

## 16. 参考资料

1. LangGraph Postgres checkpointer：`langgraph-checkpoint-postgres` 提供 `PostgresSaver` / `AsyncPostgresSaver`，首次使用需要调用 `setup()` 创建表。
2. Graphiti MCP Server：官方文档说明 Docker Compose 可同时启动数据库和 MCP server，默认支持 FalkorDB，也支持 Neo4j；FalkorDB 方案暴露 MCP endpoint 和 health check。
3. Filesystem MCP Server：官方 filesystem server 通过 `npx -y @modelcontextprotocol/server-filesystem <allowed-dir>` 启动，且只允许访问启动参数指定的目录。
