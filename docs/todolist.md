# Todo List

> **增量 PRD**：[super-agent-incremental.md](./prd/super-agent-incremental.md)  
> 下列**不在**增量 PRD 内，前提满足后再做。

## 通用 backlog

| 项 | 说明 | 触发条件 |
|----|------|----------|
| PR/CI 真依赖 | GHA Postgres/MCP/Graphiti integration | 需要协作 / PR 门禁 |
| LangGraph Platform | 云部署、托管 checkpoint | 脱离纯本地 dev |

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
