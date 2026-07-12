---
name: jumpserver-query
description: JumpServer query-only subskill. Use for object lookup, user access scope, permissions, RBAC, ACL, audit logs, terminal sessions, reports, inspections, governance rankings, and read-only runtime data.
---

# Query

所有查询类能力只放在本子 Skill。禁止创建、更新、删除。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 查询对象、组织、用户/资产/权限标识、审计类型、时间范围、报告类型 |
| 输出 | 正式入口结果、`summary`、`records`、HTML 报告路径、阻塞原因或候选对象 |

## Entrypoints

| 查询类型 | 入口 | 主要命令 |
|---|---|---|
| 对象清单/详情/解析 | `python3 subskills/query/scripts/jms_query.py ...` | `object-list`, `object-get`, `resolve` |
| 用户访问范围 | `python3 subskills/query/scripts/jms_access.py ...` | `user-assets`, `user-nodes`, `user-asset-access` |
| 权限/RBAC/ACL | `python3 subskills/query/scripts/jms_permissions.py ...` | `permission-list`, `permission-get`, `asset-perm-users`, `asset-permission-explain` |
| 审计/会话/命令/作业 | `python3 subskills/query/scripts/jms_audit.py ...` | `audit-list`, `audit-get`, `recent-audit`, `terminal-sessions`, `job-list`, `command-storage-hint`, `audit-analyze`, `capabilities` |
| 巡检/治理/排行 | `python3 subskills/query/scripts/jms_inspect.py ...` | `inspect`, `capabilities` |
| 只读运行时数据 | `python3 subskills/query/scripts/jms_runtime_query.py ...` | `settings-category`, `license-detail`, `tickets`, `command-storages`, `replay-storages`, `terminals`, `reports`, `account-automations`, `resolve-platform` |
| HTML 使用报告 | `python3 subskills/query/scripts/jms_report.py ...` | `daily-usage-prepare`, `daily-usage-render`, `contract-check` |

## Rules

| 条件 | 动作 |
|---|---|
| 配置、预检、组织选择、连通性不确定 | 先走 [../common/SKILL.md](../common/SKILL.md) |
| 查清单 | 优先用脚本参数；复杂过滤用重复 `--filter key=value` |
| 单次命令覆盖组织 | `--org-id` / `--org-name` 不写 `.env` |
| 全局用户解析 | 可显式传全局组织 ID |
| 分页参数 | 不使用 `--limit` / `--offset`；脚本内部负责分页和汇总 |
| 查询类脚本 | 可以读取 JumpServer API，但不能产生业务写入 |
| 统计问题 | 先写 `时间范围 + 组织 + 统计口径`，再给结论 |
| 报告类请求 | 先生成并验证 HTML 报告，再补充摘要；示例：帮我分析下 `20260310` 的堡垒机使用情况 |

## Login Count Routing

| 用户问法 | 入口规则 |
|---|---|
| 命名用户在某时间窗内“登录多少次 / 成功登录多少次 / 失败登录多少次” | 不要走使用报告流程、`recent-active-users-ranking` 或 Top 榜单 |
| 单个或多个命名用户登录次数 | 优先用 `jms_audit.py audit-list --audit-type login` |
| 返回结果 | 按每个用户的 `summary.total` 回答，再逐个用户列出结果 |

## Statistical Guidelines

| 场景 | 规则 |
|---|---|
| `session_count` 与去重后的 `assets` | 两套口径；前者回答“连了几次 / 有多少会话”，后者回答“连了哪些机器 / 有多少台机器” |
| `top_users`、`top_assets`、ranking | 默认可能是 Top N 或部分样本；这是部分榜单，不能替代总量 |
| 当用户问“某天连接了哪些机器”时，先从 `records` 按用户分组 | 再提取并去重资产名称 |

## Data Validation

| 条件 | 动作 |
|---|---|
| 返回里有 `summary.total` | 优先把它作为权威总量 |
| 单个用户结果 | 不要把单个用户的会话数说成“总会话数” |
| 可见 `records` 是样本 | 不要写“从这次已返回记录看”“我逐条数出来的”这类样本口吻 |

### 统计与报告类错误（严禁）

- 用 Top N 榜单代替总量。
- 用可见 `records` 条数代替服务端 `summary.total`。
- 把不同组织、时间窗或成功/失败口径混在一起回答。

### 模板报告后的数据总结

- 使用报告正式流程为 `daily-usage-prepare -> Skill 根据 summary_input 写摘要 JSON -> daily-usage-render`。
- `risk_login_analysis`、`risk_command_analysis`、`risk_transfer_analysis`、`high_risk_operation_analysis`、`risk_action`、`command_summary`、`command_compliance_analysis`、`file_transfer_summary` 必须由 Skill 基于 `summary_input` 总结填入。
- 先完成 render 并报告“报告已生成”，再补充文字摘要。
- 文字摘要必须基于正式入口返回的 `summary_input`、`summary`、`records`、校验结果。
- 若只是部分榜单，明确说“这是部分榜单，不能替代总量”。

## 边界

| 不适用场景 | 处理 |
|---|---|
| 创建、更新、删除业务对象 | 转到 create/update 边界并阻塞 |
| 报告类请求绕过 `jms_report.py` | 阻塞临时拼装 |
| 对象、组织、时间范围不明确 | 返回候选或要求补充 |

## Response Checklist

- 已说明预检和生效组织。
- 已说明正式入口。
- 已说明时间范围和统计口径。
- 已使用 `summary.total` 或正式报告结果，不手工数样本。

## 成功标准

- 查询结果来自正式入口。
- 统计结论有组织、时间范围和口径。
- 报告类请求已生成 HTML 报告或明确阻塞原因。

## Examples

```bash
python3 subskills/query/scripts/jms_query.py object-list --resource user --name openclaw
python3 subskills/query/scripts/jms_access.py user-assets --username example.user
python3 subskills/query/scripts/jms_permissions.py asset-perm-users --asset-id <asset-id>
python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login --days 30 --username example.user
python3 subskills/query/scripts/jms_inspect.py inspect --capability hot-assets-ranking --days 30 --top 10
python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30
python3 subskills/query/scripts/jms_report.py daily-usage-prepare --date 20260310
python3 subskills/query/scripts/jms_report.py daily-usage-render --prepared-path reports/prepared/JumpServer-2026-03-10.prepared.json --summary-file /tmp/jms-summary.json
```
