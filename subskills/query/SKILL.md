---
name: jumpserver-query
description: JumpServer query-only subskill. Use for object lookup, user access scope, permissions, RBAC, ACL, audit logs, terminal sessions, reports, inspections, governance rankings, and read-only runtime data.
---

# Query

所有查询类能力只放在本子 Skill。禁止创建、更新、删除。

## Entrypoints

| 查询类型 | 入口 | 主要命令 |
|----------|------|----------|
| 对象清单/详情/解析 | `python3 subskills/query/scripts/jms_query.py ...` | `object-list`, `object-get`, `resolve` |
| 用户访问范围 | `python3 subskills/query/scripts/jms_access.py ...` | `user-assets`, `user-nodes`, `user-asset-access` |
| 权限/RBAC/ACL | `python3 subskills/query/scripts/jms_permissions.py ...` | `permission-list`, `permission-get`, `asset-perm-users`, `asset-permission-explain` |
| 审计/会话/命令/作业 | `python3 subskills/query/scripts/jms_audit.py ...` | `audit-list`, `audit-get`, `recent-audit`, `terminal-sessions`, `job-list`, `command-storage-hint`, `audit-analyze`, `capabilities` |
| 巡检/治理/排行 | `python3 subskills/query/scripts/jms_inspect.py ...` | `inspect`, `capabilities` |
| 只读运行时数据 | `python3 subskills/query/scripts/jms_runtime_query.py ...` | `settings-category`, `license-detail`, `tickets`, `command-storages`, `replay-storages`, `terminals`, `reports`, `account-automations`, `resolve-platform` |
| HTML 使用报告 | `python3 subskills/query/scripts/jms_report.py ...` | `daily-usage`, `contract-check` |

## Rules

- 配置、预检、组织选择、连通性先走 [../common/SKILL.md](../common/SKILL.md)。
- 查清单优先用脚本参数；复杂过滤用重复 `--filter key=value`。
- `jms_query.py object-list/object-get/resolve` 支持 `--org-id` / `--org-name` 单次命令覆盖组织，不写 `.env`；全局用户解析可显式传全局组织 ID。
- 不使用 `--limit` / `--offset`；脚本内部负责分页和汇总。
- 查询类脚本可以读取 JumpServer API，但不能产生业务写入。
- 命名用户在某时间窗内“登录多少次 / 成功登录多少次 / 失败登录多少次”，不要走 `daily-usage`、`recent-active-users-ranking` 或 Top 榜单；优先用 `jms_audit.py audit-list --audit-type login`，按每个用户的 `summary.total` 回答，再逐个用户列出结果。
- 回答统计问题时，先写 `时间范围 + 组织 + 统计口径`，再给结论。
- 报告类请求先生成并验证 HTML 报告，再补充摘要；示例：帮我分析下 `20260310` 的堡垒机使用情况。

## Statistical Guidelines

- `session_count` 与去重后的 `assets` 是两套口径；前者回答“连了几次 / 有多少会话”，后者回答“连了哪些机器 / 有多少台机器”。
- `top_users`、`top_assets`、ranking 一类排行榜默认可能是 Top N 或部分样本；这是部分榜单，不能替代总量。
- 当用户问“某天连接了哪些机器”时，先从 `records` 按用户分组，再提取并去重资产名称。

## Data Validation

- 若返回里有 `summary.total`，优先把它作为权威总量。
- 不要把单个用户的会话数说成“总会话数”。
- 不要写“从这次已返回记录看”“我逐条数出来的”这类样本口吻。

### 统计与报告类错误（严禁）

- 用 Top N 榜单代替总量。
- 用可见 `records` 条数代替服务端 `summary.total`。
- 把不同组织、时间窗或成功/失败口径混在一起回答。

### 模板报告后的数据总结

- 先报告“报告已生成”，再补充文字摘要。
- 文字摘要必须基于正式入口返回的 `summary`、`records`、校验结果。
- 若只是部分榜单，明确说“这是部分榜单，不能替代总量”。

## Response Checklist

- 已说明预检和生效组织。
- 已说明正式入口。
- 已说明时间范围和统计口径。
- 已使用 `summary.total` 或正式报告结果，不手工数样本。

## Examples

```bash
python3 subskills/query/scripts/jms_query.py object-list --resource user --name openclaw
python3 subskills/query/scripts/jms_access.py user-assets --username example.user
python3 subskills/query/scripts/jms_permissions.py asset-perm-users --asset-id <asset-id>
python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login --days 30 --username example.user
python3 subskills/query/scripts/jms_inspect.py inspect --capability hot-assets-ranking --days 30 --top 10
python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30
python3 subskills/query/scripts/jms_report.py daily-usage --date 20260310
```
