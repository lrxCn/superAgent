# 05 - Graphiti Long-Term Memory Client

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：该任务建立长期记忆边界、Graphiti 客户端和本地 Docker/OrbStack 运行文档，涉及外部服务降级。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

02。

## 背景

长期记忆使用本地 Graphiti，默认走 Graphiti MCP Server Docker Compose 的 FalkorDB 后端。Graphiti 不可用时主流程必须降级到无长期记忆。

## 目标

- 封装长期记忆 client 接口和 Graphiti 本地连接配置，提供 mock fallback。

## 范围

| Area | Change |
|------|--------|
| `src/agent/memory/graphiti.py` | 定义长期记忆读写协议、Graphiti client、mock client |
| `docs/` | 增加本地 Graphiti/OrbStack 启动说明或链接到 maps/runbook |
| `.env_example` / `.env.example` | 同步 `GRAPHITI_BACKEND`、`GRAPHITI_MCP_URL`、`FALKORDB_URL` |
| `tests/unit_tests/` | 覆盖 Graphiti 不可用、读写成功、读写失败降级 |

## 实施步骤

1. 调研并选择 Graphiti MCP/local client 的最小接入方式。
2. 封装 `LongTermMemoryClient` 或等价协议，不让业务节点直接依赖 Graphiti SDK 细节。
3. 默认配置为 `GRAPHITI_BACKEND=falkordb`。
4. 实现健康检查或连接探测，但不得在 import 时强连服务。
5. 写 mock 测试，真实 Graphiti 只作为可选 smoke。

## 验证方案

```bash
uv run pytest tests/unit_tests
uv run ruff check src tests
uv run mypy src
```

可选真实链路：

```bash
docker compose ps
uv run pytest tests/integration_tests -m graphiti
```

## 非范围

- 不实现 memory write policy。
- 不实现实体抽取或事实过滤。
- 不强制本任务完成真实 Docker 服务启动。

## 完成标准

- [ ] Graphiti client 接口和 mock fallback 可用。
- [ ] Graphiti 不可用不阻断主流程。
- [ ] 配置文档与 README/PRD 一致。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 05 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add graphiti memory client`。

## 进度更新

`docs/progress.md` **05** -> implementation complete 后改为 `✅`.

