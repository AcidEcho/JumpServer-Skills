# 路由与安全边界

## 全局路由

主 Skill 只做路由，具体请求进入对应子 Skill：

| 请求类型 | 子 Skill | 正式入口 |
|---|---|---|
| 配置、预检、组织选择、连通性、端点验证 | `subskills/common/` | `python3 subskills/common/scripts/jms_common.py ...` |
| 当前身份一次性 SSH 连接信息 | `subskills/access/` | `python3 subskills/access/scripts/jms_ssh_connect.py connect-info ...` |
| 当前身份 MySQL/MariaDB SQL 执行 | `subskills/access/` | `python3 subskills/access/scripts/jms_db_connect.py db-query ...` |
| 用户有效访问范围、对象、权限、审计、报告、巡检、只读运行时数据 | `subskills/query/` | `python3 subskills/query/scripts/jms_access.py user-assets/user-nodes/user-asset-access ...` 或其他 Query 正式入口 |
| 创建用户、用户组、组织、邀请、标签、节点、资产、网域、网关、账号模板、账号绑定、ACL、资产授权、数据脱敏规则 | `subskills/create/` | 完整命令索引见 `subskills/create/references/index.md`；写入规则见下方“允许写操作”表 |
| 更新类 | `subskills/update/` | 本版无可执行写操作 |

## 正式入口边界

- 只使用 `subskills/*/scripts/` 下声明的正式入口。
- 不生成临时 SDK Python 脚本或 HTTP 脚本绕过正式入口。
- 配置、组织或连通性不确定时，先走 `jms_common.py config-status --json` 和 `jms_common.py ping`。
- 对象 ID、平台 ID、组织、鉴权信息或筛选条件不明确时，先查询或解析，不猜测。
- dry-run、成功和错误输出中默认不回显密文字段或密文语义字段，包括 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`、`password`。唯一例外是 `connect-info` ready 成功结果的 `result.connection.password`；错误、pending 和其他路径仍须脱敏。

## 允许写操作

| 写操作 | 正式入口 | 要求 |
|---|---|---|
| 本地配置写入 | `jms_common.py config-write --confirm`；损坏恢复追加 `--recover-invalid-env` | 只写 `.env` / `.env.lock`；恢复额外使用 `.env.recovery-*.bak` 和 `.env.recovery-*.stage` |
| 当前组织切换 | `jms_common.py select-org --confirm` | 只写 `.env JMS_ORG_ID` |
| 当前身份一次性 SSH connection token | `jms_ssh_connect.py connect-info --confirm` | 只使用 `users/self`；资产、SSH 协议、托管凭据账号必须唯一；固定 `is_reusable=false`；不返回原始 `jms_url`，不持久化 token 或密码 |
| 当前身份 MySQL/MariaDB SQL 执行 connection token | `jms_db_connect.py db-query --confirm` | 只使用 `users/self` 数据库资产；从资产授权中唯一选择 `mysql` 或 `mariadb` 协议，固定 `db_client` + `is_reusable=false`；SQL 不在本地解析、改写或阻塞，由 JumpServer 命令过滤、连接 ACL 和数据库权限决定；不返回或持久化 token password；主机和端口只取 `client-url.endpoint` |
| 创建用户 | `jms_create_user.py create-user --confirm` | 密文字段或密文语义字段脱敏；唯一性冲突由服务端校验返回 |
| 创建用户组 | `jms_create_user_group.py create-user-group --confirm` | 成员只接受用户 ID；唯一性冲突由服务端校验返回 |
| 创建组织 | `jms_create_org.py create-organization --confirm` | 请求不带 `X-JMS-ORG`，成功后不切换当前组织 |
| 邀请用户加入组织 | `jms_invite_user.py invite-user-to-org --confirm` | 用户从全局组织解析，角色在目标组织解析 |
| 添加用户到用户组 | `jms_add_user_to_group.py add-user-to-user-group --confirm` | 用户和用户组都在目标组织解析 |
| 创建标签 | `jms_create_label.py create-label --confirm` | 只在目标组织创建；全局组织禁止；唯一性冲突由服务端校验返回 |
| 创建节点 | `jms_create_node.py create-node --confirm` | 只发送 `org_id/full_value/value`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建主机/网络设备/数据库/Web 资产 | `jms_create_asset.py create-host-asset/create-device-asset/create-database-asset/create-web-asset --confirm` | 以完整 `--payload` 为主；`platform/nodes/labels/zone/accounts[].template` 支持解析；未传 `protocols` 时按平台默认协议补齐；密文字段或密文语义字段脱敏；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建网域 | `jms_create_zone_gateway.py create-zone --confirm` | 只发送 `name/assets/comment`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建网关机器 | `jms_create_zone_gateway.py create-gateway --confirm` | 以完整 `--payload` 为主；`platform/zone/nodes/labels` 支持解析；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建账号模板 | `jms_create_account_template.py create-account-template --confirm` | 以完整 `--payload` 为主；`su_from/platforms` 支持解析；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段或密文语义字段脱敏 |
| 给资产批量添加账号 | `jms_asset_account_bulk.py add-account-to-assets --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段或密文语义字段脱敏 |
| 给资产或节点批量添加账号模板 | `jms_asset_account_bulk.py add-account-template-to-assets --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建命令组 | `jms_create_command_acl.py create-command-group --confirm` | 只发送 `type/ignore_case/name/content/comment`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建命令过滤规则 | `jms_create_command_acl.py create-command-filter-rule --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建用户登录控制 | `jms_create_login_acl.py create-login-acl --confirm` | 以完整 `--payload` 为主；显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`；不写 `.env` |
| 创建连接方式过滤器 | `jms_create_connect_method_acl.py create-connect-method-acl --confirm` | 以完整 `--payload` 为主；显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`；不写 `.env` |
| 创建资产授权规则 | `jms_create_asset_permission.py create-asset-permission --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建资产连接规则 | `jms_create_login_asset_acl.py create-login-asset-acl --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建数据脱敏过滤规则 | `jms_create_data_masking_rule.py create-data-masking-rule --confirm` | 以完整 `--payload` 为主；`accounts` 只支持 `@ALL/@SPEC`；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |

## 全局阻塞规则

| 场景 | 阻塞规则 |
|---|---|
| 未被上表声明的写操作 | 一律阻塞 |
| 代替其他用户创建 token、创建可复用 token、绕过审批/Face Verify/ACL | 不开放 |
| 数据库 token 复用 SSH token，或绕过 `client-url.endpoint` 猜测主机/端口 | 不开放；按 Access 数据库连接 reference 使用 `JMS-<client-token-id>@<endpoint-host>:<endpoint-port>` |
| 绕过 JumpServer 数据库命令过滤、连接 ACL 或服务端拒绝 | 不开放；`db-query` 只负责透传 SQL，不提供本地绕过能力 |
| 对象更新、删除、解锁 | 不开放 |
| 资产、账号、节点、网域、网关、账号模板等对象创建 | 只开放上表列出的 create 入口 |
| 授权类创建 | 只开放上表列出的命令过滤规则、登录控制、连接方式过滤器、资产授权规则、资产连接规则和数据脱敏过滤规则创建 |
| 授权更新、追加、移除、删除 | 不开放 |
| 多个候选对象、名称歧义、组织不明确或跨组织风险未确认 | 阻塞并要求先确认 |
| 跳过预检、绕过正式入口或现场拼临时脚本 | 阻塞 |
