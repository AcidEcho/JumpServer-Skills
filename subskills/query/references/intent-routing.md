# 查询意图路由

本文件用于 `jumpserver-query` 触发后的二次分类。先识别用户要的是事实对象、有效访问结果、权限原因、审计明细、整体报告、治理聚合还是只读运行时数据，再选择一个正式入口。

## 路由表

| 用户核心意图 | 识别信号 | 正式入口 | 深入参考 |
|---|---|---|---|
| 对象查询 | 查资产、用户、账号、节点、平台、标签、网域的清单/详情/ID | `jms_query.py object-list/object-get/resolve` | [assets.md](assets.md)、[object-map.md](object-map.md) |
| 有效访问范围 | 某用户现在能访问哪些资产/节点/账号/协议 | Query：`python3 subskills/query/scripts/jms_access.py user-assets/user-nodes/user-asset-access` | [诊断与访问分析](diagnose.md) |
| 当前身份 SSH 连接 | 连接这台机器、通过 JumpServer 登录、获取一次性 SSH 信息、先连接再执行远程任务 | 独立 Access：`python3 subskills/access/scripts/jms_ssh_connect.py connect-info --confirm` | [SSH 连接生命周期](../../access/references/ssh-connection.md) |
| 当前身份 MySQL/MariaDB SQL 执行 | 连接数据库、执行 `SHOW DATABASES`、执行 SQL | 独立 Access：`python3 subskills/access/scripts/jms_db_connect.py db-query --confirm` | [数据库连接与 SQL 执行](../../access/references/database-connection.md) |
| 权限解释 | 为什么能访问、命中哪些授权规则、资产授权给谁、RBAC/ACL | `jms_permissions.py` | [permissions.md](permissions.md) |
| 审计调查 | 登录、会话、命令、文件传输、作业的明细、单人次数或取证 | `jms_audit.py` | [audit.md](audit.md) |
| 使用报告 | 某天/时间段整体使用情况、日报/周报/月报、总体排行与分布 | `jms_report.py daily-usage-prepare` -> Skill 总结 -> `daily-usage-render` | [report-template-playbook.md](report-template-playbook.md) |
| 治理与聚合 | 风险排行、配置巡检、组件负载、改密失败分析、治理统计 | `jms_inspect.py inspect` | [capabilities.md](capabilities.md)、[component-load-and-password-report.md](component-load-and-password-report.md) |
| 只读运行时数据 | 设置、许可证、工单、存储、原生报表、平台解析 | `jms_runtime_query.py` | [diagnose.md](diagnose.md) |

## 相邻意图区分

| 容易混淆的问法 | 固定判断 |
|---|---|
| “用户能访问什么” vs “为什么能访问” | 前者走有效访问；后者走权限解释 |
| “查询资产 SSH 配置” vs “立即通过 JumpServer 连接” | 前者走对象/平台配置查询；后者走当前身份 `connect-info` |
| “昨天整体使用情况” vs “昨天某用户登录明细” | 前者走 HTML 使用报告；后者走审计 |
| “查看组件列表” vs “组件是否高负载” | 前者走 `terminal-component-query` 或 `terminals`；后者走 `component-load-overview` |
| “查看改密日志” vs “分析改密失败原因和占比” | 前者走审计列表；后者走 `change-password-failure-report` |
| “查看原生 dashboard” vs “生成使用报告” | 前者走 `jms_runtime_query.py reports`；后者走 `jms_report.py` |
| “系统连接是否正常” vs “读取系统配置” | 前者先走 common；后者走只读运行时数据 |

## 执行规则

1. 先固定组织、时间窗和统计口径。
2. 默认只选择一个正式入口；只有该入口返回的下一步明确需要另一入口时才继续。
3. 对象不唯一时先 `resolve`，不把模糊名称直接传给分析命令。
4. 报告、审计明细、原生报表三类结果不可互相替代。
5. 深层 reference 按上表按需读取，不默认加载全部查询文档。
6. 当前身份 SSH 请求只路由到 Access；Query 不执行 `connect-info`，也不导入 Access。
7. 当前身份 MySQL/MariaDB 查询请求同样只路由到 Access；Query 不创建数据库 connection token，也不执行 `db-query`。

## 路由验收样例

应该路由到治理巡检：

- “看看 Koko、Lion 当前 CPU 和内存负载，有没有高负载组件。”
- “统计最近 30 天改密失败率和主要错误类型。”
- “检查 MFA 和认证源配置。”

不应该路由到治理巡检：

- “列出所有 Koko 组件。”应走只读运行时查询或组件列表 capability。
- “查 alice 昨天的改密日志明细。”应走审计调查。
- “生成昨天的 JumpServer 使用日报。”应走 HTML 使用报告。

最近邻判断：用户说“昨天改密情况”时先确认要明细还是失败聚合；明确出现“失败率、错误类型、失败资产排行”则走 `change-password-failure-report`。

以下请求不在 Query 执行，应转到 Access：

- “通过 JumpServer 连接 10.1.1.1。”
- “先拿这台机器的一次性 SSH 信息，再执行部署。”
- “在 10.1.12.224 上执行 `SHOW DATABASES;`。”

以下请求仍留在 Query：

- “为什么 alice 能访问这台机器？”应走权限解释。
- “查看 Linux 平台的 SSH 协议配置。”应走对象或平台配置查询。
- “查某用户能访问哪些数据库资产。”应走有效访问范围入口。
