# 15 - Final Docs And Architecture Maps

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：这是最终文档收口任务，需要对照已实现代码更新 README、PRD、progress 和 maps，但不再新增运行能力。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

01-14。

## 背景

前 14 张任务完成后，README 和 PRD 中的“计划”部分需要对齐真实代码，`docs/maps/` 需要记录当前架构图和代码导航，`docs/progress.md` 需要最终收口。

## 目标

- 更新项目文档，使 README 成为当前 runtime contract，PRD 保留设计历史，maps 反映真实代码。

## 范围

| Area | Change |
|------|--------|
| `README.md` | 更新当前实现状态、运行方式、配置、测试、架构 |
| `docs/prd/super-agent-runtime-architecture.md` | 标记已实现/未实现/后续项 |
| `docs/maps/` | 新增 runtime graph、module map、state contract map |
| `docs/progress.md` | 完成 15 号任务并更新总数、next step、changelog |
| `docs/prompts/` | 如任务执行中发生重大偏差，补备注，不重写历史 |

## 实施步骤

1. 对照真实代码读取 `src/agent/`、`tests/`、`langgraph.json`、配置文件。
2. 更新 README，只写已经落地的 runtime contract；未落地内容标记 planned。
3. 在 `docs/maps/` 创建 Mermaid 或 Markdown map，反映真实模块和 LangGraph 路径。
4. 检查 `.env_example` 与 README 配置一致。
5. 更新 progress：15 完成、Completed=15、Recommended next task 改为维护/后续路线。

## 验证方案

```bash
uv run pytest
uv run ruff check .
uv run mypy src
rg -n "TODO|planned|not implemented|template" README.md docs
```

如果完整测试不可用，至少运行：

```bash
uv run python -m compileall src tests
rg -n "OPENAI_API_KEY=.*\\S|LANGSMITH_API_KEY=.*\\S|sk-|lsv2_" README.md docs .env_example .env.example
```

## 非范围

- 不新增运行功能。
- 不重构已完成代码。
- 不删除历史 PRD。

## 完成标准

- [ ] README 反映真实当前 runtime contract。
- [ ] `docs/maps/` 有真实架构/模块图。
- [ ] PRD 标注实现状态。
- [ ] progress 全部收口。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] Git commit 已创建，建议消息：`docs: finalize runtime architecture docs`。

## 进度更新

`docs/progress.md` **15** -> implementation complete 后改为 `✅`.

