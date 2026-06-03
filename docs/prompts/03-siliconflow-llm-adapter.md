# 03 - SiliconFlow LLM Adapter

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：该任务实现单一 OpenAI-compatible provider 封装和 mock 测试，范围明确但涉及配置与错误处理。

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

第一阶段只支持硅基流动，使用 OpenAI-compatible API 形态和 commonAgent 迁移变量名。业务节点不能散落读取环境变量，必须通过 adapter 调用。

## 目标

- 实现集中式 SiliconFlow LLM adapter，并提供 fake/mock LLM 用于测试。

## 范围

| Area | Change |
|------|--------|
| `src/agent/config.py` | 支持 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME`、`LLM_TIMEOUT_SECONDS`、`LLM_MAX_TOKENS` |
| `src/agent/llm.py` | 实现 SiliconFlow/OpenAI-compatible client factory 和 fake client |
| `.env_example` / `.env.example` | 同步非敏感默认值 |
| `tests/unit_tests/` | 覆盖默认值、缺失 key 行为、fake LLM、调用参数 |

## 实施步骤

1. 选择项目已安装或适合新增的 OpenAI-compatible 客户端依赖；若新增依赖，同步 `pyproject.toml`。
2. 封装 `LLMClient` 或等价协议，业务节点只依赖协议。
3. 默认 base URL 为 `https://api.siliconflow.cn/v1`，模型为 `Pro/moonshotai/Kimi-K2.6`。
4. 单元测试不得要求真实 API key。
5. 确保异常被转换成可由节点记录的结构化错误。

## 验证方案

```bash
uv run pytest tests/unit_tests
uv run ruff check src tests
uv run mypy src
```

如果没有真实 key，不运行真实链路；fake 测试必须通过。

## 非范围

- 不实现 direct answer 业务节点。
- 不实现 router、tool、planner 或 reflection。
- 不支持多 provider adapter。

## 完成标准

- [ ] LLM adapter 可用 fake client 测试。
- [ ] 配置默认值与 README/PRD 一致。
- [ ] 不泄漏真实 key。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 03 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add siliconflow llm adapter`。

## 进度更新

`docs/progress.md` **03** -> implementation complete 后改为 `✅`.

