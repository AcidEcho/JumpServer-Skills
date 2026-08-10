# 能力映射与缺口清单

## 当前结构摘要

- 维持主 Skill + 子 Skill 的分域心智模型：`common / access / query / create / update`。
- 把底层执行统一收口到 `subskills/*/scripts/`，不让请求入口散落在顶层或依赖临时 SDK 包装。
- 把“查询类能力”组织成 `capability` 能力单元，便于技能路由、意图识别和跨环境复用。
- 把运行时、能力元数据、统计聚合、对象查询、权限回看分层拆开，避免把 CLI 入口、业务逻辑和底层请求耦合在一起。
- `SKILL.md` 负责顶层路由和响应风格；`references/routing-and-safety.md` 负责全仓库路由、写操作白名单和全局阻塞规则；`README.md` 负责整体使用说明；各 `subskills/*/references/*.md` 负责本子 Skill 的分域规则和能力清单；`subskills/query/references/metadata/*.json` 负责查询能力元数据。

## 目录与职责

| 目录 / 文件 | 当前职责 | 说明 |
|---|---|---|
| `subskills/common/scripts/jumpserver_common/` | 环境加载、组织上下文、客户端构建、公共 CLI 行为 | 所有正式入口共享 |
| `subskills/query/scripts/jms_query.py` | 资产、平台、节点、账号、账号模板、用户、用户组、组织、标签、网域查询 | 按对象域集中只读查询 |
| `subskills/query/scripts/jms_access.py` | 用户资产、节点、账号、协议有效访问范围 | Query 正式实现源；保留 `user-assets`、`user-nodes`、`user-asset-access`，不创建 connection token |
| `subskills/access/scripts/jms_ssh_connect.py` | 当前身份一次性 SSH 连接信息 | Access 只提供 `connect-info`；与 Query 零代码依赖，双方只共享 Common |
| `subskills/access/scripts/jms_db_connect.py` | 当前身份通过 MySQL/MariaDB `db_client` 执行 SQL | Access 数据库入口；从资产授权中唯一选择 `mysql` 或 `mariadb` 协议，创建不可复用 token；数据库 `client-url` 只取 token ID/value，连接主机和端口从 Smart Endpoint 动态读取 SSH `host/ssh_port`；SQL 限制由 JumpServer 侧负责；与 Query 零代码依赖 |
| `subskills/access/scripts/jms_connect.py` | 当前身份 SSH/多数据库一次性连接信息 | 新增独立入口；数据库支持 PostgreSQL、Redis、MongoDB、SQL Server、Oracle、ClickHouse，统一使用 Smart Endpoint 的 KoKo SSH `host/ssh_port` |
| `subskills/access/scripts/jms_ssh_exec.py` | 当前身份同进程 SSH 命令执行 | 一次 token、一次认证、单客户端顺序执行，不通过本地 shell，不跨进程传递凭据 |
| `subskills/access/scripts/jms_db_exec.py` | 当前身份新增数据库协议命令执行 | PostgreSQL/Redis/MongoDB/SQL Server/Oracle 固定 `db_client`；ClickHouse 固定 `web_cli`；固定 `is_reusable=false`；多命令复用一个 KoKo SSH 交互会话，按协议封装和退出 |
| `subskills/access/scripts/jms_koko_connection.py` | Access 新增入口共享连接核心 | 集中当前身份资产/账号/协议解析、Smart Endpoint、一次性 token 和 client-url 生命周期 |
| `subskills/query/scripts/jms_permissions.py` | 授权规则、ACL、RBAC 与资产授权用户查询 | 不承担授权写入 |
| `subskills/query/scripts/jms_audit.py` | 审计列表、详情、terminal 会话、命令存储提示、能力分析 | 统一承接调查类意图 |
| `subskills/common/scripts/jms_common.py` | 配置检查、预检、连通性、组织选择、端点验证 | 所有业务 skill 的公共前置能力 |
| `subskills/query/scripts/jms_inspect.py` | 治理、排行、巡检与统计聚合 | 统一承接治理分析能力 |
| `subskills/query/scripts/jms_runtime_query.py` | 设置、许可证、工单、存储、报表原始数据、平台解析 | 运行时只读查询也归入 query 子 Skill |
| `subskills/create/scripts/jms_create_user.py` | 创建用户入口 | 本版开放 `create-user` |
| `subskills/create/scripts/jms_create_user_group.py` | 创建用户组入口 | 本版开放 `create-user-group` |
| `subskills/create/scripts/jms_create_org.py` | 创建组织入口 | 本版开放 `create-organization` |
| `subskills/create/scripts/jms_invite_user.py` | 邀请用户加入组织入口 | 本版开放 `invite-user-to-org` |
| `subskills/create/scripts/jms_add_user_to_group.py` | 添加用户到用户组入口 | 本版开放 `add-user-to-user-group` |
| `subskills/create/scripts/jms_create_label.py` | 创建标签入口 | 本版开放 `create-label` |
| `subskills/create/scripts/jms_create_node.py` | 创建节点入口 | 本版开放 `create-node` |
| `subskills/create/scripts/jms_create_asset.py` | 创建主机、网络设备、数据库与 Web 资产入口 | 本版开放 `create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset` |
| `subskills/create/scripts/jms_create_zone_gateway.py` | 创建网域与网关机器入口 | 本版开放 `create-zone`、`create-gateway` |
| `subskills/create/scripts/jms_create_account_template.py` | 创建账号模板入口 | 本版开放 `create-account-template` |
| `subskills/create/scripts/jms_asset_account_bulk.py` | 给资产批量添加账号或账号模板入口 | 本版开放 `add-account-to-assets`、`add-account-template-to-assets` |
| `subskills/create/scripts/jms_create_command_acl.py` | 创建命令组与命令过滤规则入口 | 本版开放 `create-command-group`、`create-command-filter-rule` |
| `subskills/create/scripts/jms_create_login_acl.py` | 创建用户登录控制入口 | 本版开放 `create-login-acl` |
| `subskills/create/scripts/jms_create_connect_method_acl.py` | 创建连接方式过滤器入口 | 本版开放 `create-connect-method-acl` |
| `subskills/create/scripts/jms_create_asset_permission.py` | 创建资产授权规则入口 | 本版开放 `create-asset-permission` |
| `subskills/create/scripts/jms_create_login_asset_acl.py` | 创建资产连接规则入口 | 本版开放 `create-login-asset-acl` |
| `subskills/create/scripts/jms_create_data_masking_rule.py` | 创建数据脱敏过滤规则入口 | 本版开放 `create-data-masking-rule` |
| `subskills/update/` | 更新类预留 | 本版无可执行更新命令 |
| `subskills/query/scripts/*_core.py` / `jms_runtime_queries.py` / `jms_reporting.py` | 查询类核心实现 | 避免在 CLI 入口里复制逻辑 |

## 能力域 -> 当前能力 -> 脚本实现 -> 触发描述

| 能力域 | 当前能力 / 子命令 | 脚本实现 | 触发描述 |
|---|---|---|---|
| 资产列表、精确查询 | `asset-list-query`、`jms_query.py object-list/object-get` | `jms_inspect.py inspect`、`jms_query.py` | 适用于按名称、地址、节点、平台、启用状态查询资产清单或读取单个资产详情 |
| 账号列表、账号与资产关系 | `account-list-query`、`account-asset-bindings`、`jms_query.py object-list --resource account` | `jms_inspect.py inspect`、`jms_query.py` | 适用于按账号名、资产、特权属性、模板线索查看资产账号与绑定关系 |
| 用户、用户组、组织查询 | `jms_query.py object-list/object-get` | `jms_query.py` | 适用于读取 JumpServer 用户、用户组和组织对象 |
| 账号模板、标签、网域查询 | `jms_query.py object-list/object-get` | `jms_query.py` | 适用于读取账号模板、标签、网域对象，以及配合治理查询回看原始对象 |
| 平台、节点、资产查询 | `jms_query.py object-list/object-get` | `jms_query.py` | 适用于平台、节点、资产对象的只读查询和详情回看 |
| 授权查询 | `jms_permissions.py permission-list/permission-get`、`asset-perm-users` | `jms_permissions.py` | 适用于查看资产授权规则、ACL、RBAC、主体范围、资源范围和资产当前授权用户 |
| 命令审计 | `command-record-query`、`high-risk-command-audit`、`jms_audit.py audit-list --audit-type command` | `jms_audit.py audit-analyze`、`jms_audit.py` | 适用于按用户、资产、关键字、时间范围调查命令执行和高危命令 |
| 会话审计 | `session-record-query`、`session-behavior-statistics`、`user-session-analysis`、`asset-session-analysis`、`jms_audit.py terminal-sessions` | `jms_audit.py audit-analyze`、`jms_audit.py` | 适用于查看登录会话、terminal 会话、在线会话、历史会话、会话时长、异常中断、用户/资产维度会话行为 |
| 文件传输审计 | `file-transfer-log-query`、`file-transfer-risk-audit` | `jms_audit.py audit-analyze` | 适用于排查上传/下载记录、风险文件、异常传输方向和高频主体 |
| 登录安全调查 | `abnormal-hours-login-query`、`abnormal-source-ip-login-query`、`failed-login-statistics` | `jms_audit.py audit-analyze` | 适用于异常时间段、异常来源 IP、失败登录排行调查 |
| 特权与共享账号治理 | `privileged-account-usage-audit`、`high-privilege-account-list`、`privileged-account-activity`、`shared-account-usage` | `jms_audit.py audit-analyze`、`jms_inspect.py inspect` | 适用于特权账号使用审计、高权限账号盘点、特权账号活跃情况和共享账号治理 |
| 资产活跃与热度分析 | `asset-activity-overview`、`asset-login-ranking`、`hot-assets-ranking`、`cold-assets-ranking`、`asset-login-trend` | `jms_inspect.py inspect` | 适用于查看热门资产、冷门资产、最近活跃资产和登录趋势 |
| 账号活跃分析 | `account-activity-overview`、`long-time-unused-accounts`、`frequent-operation-user-ranking` | `jms_inspect.py inspect`、`jms_audit.py audit-analyze` | 适用于查看账号使用热度、长期未使用账号、高频操作用户和最近活跃线索 |
| 资产治理 | `uncategorized-assets-query`、`assets-without-valid-account-template`、`duplicate-asset-name-query`、`offline-disabled-assets-statistics`、`long-time-unlogged-assets`、`long-time-unused-assets`、`node-asset-distribution` | `jms_inspect.py inspect` | 适用于资产分类治理、模板治理、离线禁用统计、未使用资产和节点分布分析 |
| 账号治理 | `account-list-query`、`expired-account-query`、`accounts-without-template`、`account-asset-bindings`、`account-template-list` | `jms_inspect.py inspect` | 适用于账号清单查询、失效账号排查、未绑定模板账号治理、账号-资产绑定关系查看和模板清单查看 |
| 对象解析与访问分析 | `resolve`、`resolve-platform`、`user-assets`、`user-nodes`、`user-asset-access` | `jms_query.py`、`jms_runtime_query.py`、`subskills/query/scripts/jms_access.py` | 适用于名称歧义消解、平台解析、用户有效访问范围分析 |
| 系统设置与配置巡检 | `system-settings-overview`、`security-policy-check`、`login-auth-config-check`、`mfa-config-check`、`auth-source-config-check`、`notification-config-check`、`ticket-approval-config-check`、`audit-retention-check`、`terminal-access-policy-check`、`settings-category`、`license-detail` | `jms_inspect.py inspect`、`jms_runtime_query.py` | 适用于查看系统总览、安全策略、认证源、MFA、通知、审批、审计保留、终端接入配置和许可证详情 |
| 工单、终端组件与存储查询 | `tickets`、`terminals`、`command-storages`、`replay-storages` | `jms_runtime_query.py` | 适用于直接读取工单、终端组件、命令存储、录像存储原始记录 |
| 报表与账号自动化查询 | `reports`、`report-query`、`account-automation-overview` | `jms_runtime_query.py`、`jms_inspect.py inspect` | 适用于读取报表接口、dashboard 数据以及账号备份/改密/风险/检测任务概览 |
| 组件负载与改密失败分析 | `component-load-overview`、`change-password-failure-report` | `jms_inspect.py inspect` | 适用于组件 CPU/内存/磁盘/会话负载巡检，以及按时间窗统计改密失败率、错误类型和失败对象排行 |
| 组织与授权关系统计 | `org-resource-overview`、`role-binding-overview`、`endpoint-inventory`、`endpoint-verify` | `jms_inspect.py inspect`、`jms_common.py` | 适用于组织资源盘点、节点数量、RBAC 绑定关系、核心端点 inventory 与按路径验证 |
| 可疑行为聚合调查 | `suspicious-operation-summary` | `jms_audit.py audit-analyze` | 适用于跨命令、登录、会话、文件传输多接口汇总可疑行为 |
| 各 create 写操作（用户/用户组/组织/邀请/标签/节点/资产/网域/网关/账号模板/账号绑定/各类 ACL/资产授权/数据脱敏规则） | 见 [`subskills/create/references/index.md`](../subskills/create/references/index.md) | 同上 | 命令、入口脚本与每条命令的字段语义见 create 子 skill 的 reference 索引；写操作白名单与组织限制以 [`references/routing-and-safety.md`](routing-and-safety.md) 为唯一来源，本表不再重复 |

## 缺口清单

| 项目 | 当前状态 | 说明 |
|---|---|---|
| 对象创建、更新、删除、解锁 | 部分提供 | 本版只开放 [`references/routing-and-safety.md`](routing-and-safety.md) 中"允许写操作"白名单里的 23 个 create 命令；其他对象写操作不提供 |
| 授权追加、移除、删除 | 不提供 | 本仓库仅开放命令过滤规则、用户登录控制、连接方式过滤器、资产授权规则、资产连接规则、数据脱敏过滤规则创建，不承担其他权限写操作 |
| 资产账号失效状态统一查询 | 待确认 | inventory 未给出统一可依赖的失效字段语义；当前 `expired-account-query` 以 JumpServer 用户账号维度输出 |
| `/api/v1/perms/asset-permissions/` 在所有环境的可用性 | 待环境验证 | `permissions`、`user-assets`、`user-nodes`、`user-asset-access` 依赖该接口或其等价接口 |
| 设置项键名跨环境差异 | 已做降级处理 | 巡检能力统一保留原始键值，必要时提示人工复核 |
| “高风险资产” 的统一标签来源 | 待确认 | 当前以资产名称、地址、关键字过滤为主，不臆造平台未提供的风险标签字段 |

## README 一致性维护策略

- 保持当前 README 的章节骨架，不把它改写成开发设计文档。
- 使用场景与命令示例继续保持示例驱动写法。
- 把实现差异压缩到技术栈、目录说明和扩展维护小节，不让实现细节成为主叙事。
- 能力扩展通过 `subskills/query/references/capabilities.md` 和 `references/migration-map.md` 补充，不打断主 README 的使用者阅读路径。
- README 与 references 中的 create 写流程描述以 [`references/routing-and-safety.md`](routing-and-safety.md) 的"允许写操作"白名单与 [`subskills/create/references/index.md`](../subskills/create/references/index.md) 的命令-脚本映射为唯一来源，其它文档只链接、不重复枚举。

## SKILL / README / references 分工

| 文件 | 负责内容 | 不负责内容 |
|---|---|---|
| `SKILL.md` | 何时适用、如何路由、输出模板 | 细颗粒度 API 映射和实现细节 |
| `references/routing-and-safety.md` | 全仓库路由、正式入口边界、允许写操作白名单、全局阻塞规则 | 子 Skill 内部实现细节 |
| `README.md` | 整体定位、目录结构、使用方式、常见场景、维护约定 | 每个能力的逐条元数据 |
| `subskills/*/references/*.md` | 对应子 Skill 的分域规则、能力目录、映射关系、排障路径、验证结论 | 运行时公共实现细节 |
| `subskills/query/references/metadata/capabilities.json` | 查询能力单元的结构化事实定义 | 面向使用者的叙述性教程 |

## 为什么当前结构更容易维护

- 入口按子 Skill 分域：每类请求有独立正式 CLI 入口。
- 公共逻辑集中：运行时、请求签名、组织选择不在多个脚本里复制。
- 查询能力模块化：统计类、审计类、巡检类都通过 handler + metadata 组合扩展。
- 文档与代码一一对应：`capability_id -> handler -> endpoint -> reference` 关系是显式的。
- 对 inventory 未确认的接口保持克制：统一标记“待确认”，不把猜测写进交付物。
- 查询对象域保持只读，减少了重复 payload 构造、diff、确认和写后回读维护成本；需要创建时只走白名单 create 入口。
