# Todo List

> **增量 PRD**：[super-agent-incremental.md](./prd/super-agent-incremental.md)  
> 下列**不在**增量 PRD 内，前提满足后再做。

## 质量与调试 backlog

| 项 | 说明 | 触发条件 / 备注 |
|----|------|-----------------|
| MiniMax 直答质量 + 兜底失效 | `.env` 使用 `MiniMaxAI/MiniMax-M2.5` 时，简单寒暄（如「你能做什么」）可 hallucinate 成无关 JSON；`reflection_gate` 对 `direct_answer` 原设计为 `direct_low_risk` 跳过 evaluator，坏答案直达用户。trace `019e96f4-89f0-7fd3-9c06-dd9a62e71a37` | 换模型（如 Kimi）或关闭直答 reflection 豁免 + 语义 judge / regenerate 方案落地后再验 |
| 从 checkpoint 重放 reflection 段 | 希望从 LLM（`direct_answer`）结束后用旧 state 只重跑 `reflection_gate → evaluator → …`；Studio/`langgraph dev` 默认**内存 checkpointer**，该 thread（`019e96f4-89de-7510-9b29-626b298d3f68`）**不在 Postgres**（库里仅有 integration test thread） | 需：`create_graph_with_checkpointer` 路径跑 invoke，或 trace JSON 重建 state + `update_state(as_node="direct_answer")` 脚本；评估器若调真 LLM 耗时长，应支持 `--evaluator rule` / FakeLLM |


| 项 | 说明 | 触发条件 |
|----|------|----------|
| PR/CI 真依赖 | GHA Postgres/MCP/Graphiti integration | 需要协作 / PR 门禁 |
| LangGraph Platform | 云部署、托管 checkpoint | 脱离纯本地 dev |
| Graphiti Neo4j 后端评估 | 当前本地先用 FalkorDB；后续评估是否切 Neo4j 以获得更好的图数据管理、Cypher 调试和生产运维能力 | 任务 17/18 memory read-write loop 跑通后 |

## 后端生产 MCP

G5 先用公开 MCP stand-in；下列等后端就绪。

**待后端确认**

- 传输：stdio / HTTP / SSE
- 鉴权方式
- 工具清单与 schema
- dev/staging 地址或启动命令

**后端就绪后**

- [ ] 配置切到后端 MCP（替换 stand-in）
- [ ] staging `list_tools` + `call_tool` smoke
- [ ] 更新 `.env_example` / README

**完成标准**：至少 1 个后端 MCP 本地 `list_tools` + `call_tool` 成功。
