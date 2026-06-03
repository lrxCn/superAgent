# 13 - Memory Write Policies

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：记忆写入涉及长期状态、敏感信息过滤、Graphiti/checkpoint 双层契约和失败降级。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

04、05、12。

## 背景

短期状态通过 checkpoint + PostgreSQL 保持会话连续性；长期事实、实体和关系写入 Graphiti。写入失败不能阻断最终回答。

## 目标

- 实现记忆写入策略、过滤、状态记录和失败降级。

## 范围

| Area | Change |
|------|--------|
| `src/agent/memory/policy.py` | 写入候选提取、敏感过滤、稳定性判断 |
| `src/agent/nodes/memory_write.py` | checkpoint/Graphiti 写入协调和结果记录 |
| `tests/unit_tests/` | stored/skipped/error、敏感信息过滤、Graphiti 失败降级 |

## 实施步骤

1. 定义 `MemoryWriteResult`：status、target、reason、error、stored_count。
2. 只写入稳定、有价值、非敏感或已获允许的信息。
3. 长期记忆写入 Graphiti 时保留来源、时间、置信信息。
4. Graphiti 不可用时记录 error/skipped，不阻断 final answer。
5. 与 reflection/evaluation 结果结合，避免写入已判定不可靠的信息。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不实现复杂实体解析模型。
- 不做真实 Graphiti 数据清理。
- 不改变 checkpoint 初始化逻辑。

## 完成标准

- [ ] 记忆写入结果结构化记录。
- [ ] 敏感信息不会写入长期记忆。
- [ ] Graphiti 写入失败不阻断最终回答。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 13 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add memory write policies`。

## 进度更新

`docs/progress.md` **13** -> implementation complete 后改为 `✅`.

