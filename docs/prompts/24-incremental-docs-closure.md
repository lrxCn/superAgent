# 24 - Incremental Docs Closure

## 建议执行模型

- 模型：GPT-5
- Reasoning：low
- 原因：文档对齐为主，少改运行时逻辑。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 **16–23** 全部完成。
3. 只更新文档/maps；不顺手改逻辑。
4. 用户要求 commit 时再提交。

## 依赖

16–23。

## 背景

G9：README 曾把 stub 标 Implemented；链接需与增量 PRD / todolist 一致。

## 目标

- README、module-map、增量 PRD 验收勾选与代码一致。
- 无断链；stub 边界清晰。

## 范围

| Area | Change |
|------|--------|
| `README.md` | 档位表：骨架 / 本地可用 |
| `docs/maps/module-map.md` | 更新 stub 边界 |
| `docs/prd/super-agent-incremental.md` | §5 验收勾选 |

## 验证方案

```bash
# 链接与引用检查
rg -n "production-mcp|phase2-production|docs/todos/" README.md docs/
uv run ruff check .
```

## Agent 验收

人工可读检查 + 上述 rg 无死链；增量 PRD §5 与 progress 16–23 状态一致。

## 非范围

- 新功能

## 完成标准

- [ ] 文档 honest、无断链，档位：**本地可用**
- [ ] progress 24 更新；增量队列关闭

## 进度更新

`docs/progress.md` **24** → 验收后 `✅`。
