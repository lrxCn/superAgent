# Todo List

> **增量 PRD**：[super-agent-incremental.md](./prd/super-agent-incremental.md)  
> 下列**不在**增量 PRD 内，前提满足后再做。

## 通用 backlog

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
