# 路由与安全边界

## 全局路由

主 Skill 只做路由，具体请求进入对应子 Skill：

| 请求类型 | 子 Skill | 正式入口 |
|---|---|---|
| 配置、预检、组织选择、连通性、端点验证 | `subskills/common/` | `python3 subskills/common/scripts/jms_common.py ...` |
| 对象、访问范围、权限、审计、报告、巡检、只读运行时数据 | `subskills/query/` | `python3 subskills/query/scripts/<script>.py ...` |
| 创建用户、用户组、组织、邀请用户加入组织、添加用户到用户组、标签、节点、主机/网络设备/数据库/Web 资产、网域、网关机器、账号模板、给资产添加账号或账号模板、命令组、命令过滤规则、用户登录控制、连接方式过滤器、资产授权规则、资产连接规则、数据脱敏过滤规则 | `subskills/create/` | `python3 subskills/create/scripts/jms_create_user.py create-user ...` / `python3 subskills/create/scripts/jms_create_user_group.py create-user-group ...` / `python3 subskills/create/scripts/jms_create_org.py create-organization ...` / `python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org ...` / `python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group ...` / `python3 subskills/create/scripts/jms_create_label.py create-label ...` / `python3 subskills/create/scripts/jms_create_node.py create-node ...` / `python3 subskills/create/scripts/jms_create_asset.py create-host-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-device-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-database-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-web-asset ...` / `python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone ...` / `python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway ...` / `python3 subskills/create/scripts/jms_create_account_template.py create-account-template ...` / `python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets ...` / `python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets ...` / `python3 subskills/create/scripts/jms_create_command_acl.py create-command-group ...` / `python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule ...` / `python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl ...` / `python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl ...` / `python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission ...` / `python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl ...` / `python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule ...` |
| 更新类 | `subskills/update/` | 本版无可执行写操作 |

## 正式入口边界

- 只使用 `subskills/*/scripts/` 下声明的正式入口。
- 不生成临时 SDK Python 脚本或 HTTP 脚本绕过正式入口。
- 配置、组织或连通性不确定时，先走 `jms_common.py config-status --json` 和 `jms_common.py ping`。
- 对象 ID、平台 ID、组织、鉴权信息或筛选条件不明确时，先查询或解析，不猜测。

## 允许写操作

| 写操作 | 正式入口 | 要求 |
|---|---|---|
| 本地配置写入 | `jms_common.py config-write --confirm` | 只写本地 `.env` |
| 当前组织切换 | `jms_common.py select-org --confirm` | 只写 `.env JMS_ORG_ID` |
| 创建用户 | `jms_create_user.py create-user --confirm` | 先查重，密码脱敏 |
| 创建用户组 | `jms_create_user_group.py create-user-group --confirm` | 先查重，成员只接受用户 ID |
| 创建组织 | `jms_create_org.py create-organization --confirm` | 请求不带 `X-JMS-ORG`，成功后不切换当前组织 |
| 邀请用户加入组织 | `jms_invite_user.py invite-user-to-org --confirm` | 用户从全局组织解析，角色在目标组织解析 |
| 添加用户到用户组 | `jms_add_user_to_group.py add-user-to-user-group --confirm` | 用户和用户组都在目标组织解析 |
| 创建标签 | `jms_create_label.py create-label --confirm` | 先查重，只在目标组织创建；全局组织禁止 |
| 创建节点 | `jms_create_node.py create-node --confirm` | 只发送 `org_id/full_value/value`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建主机/网络设备/数据库/Web 资产 | `jms_create_asset.py create-host-asset/create-device-asset/create-database-asset/create-web-asset --confirm` | 以完整 `--payload` 为主；`platform/nodes/labels/zone/accounts[].template` 支持解析；未传 `protocols` 时按平台默认协议补齐；密文字段脱敏；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建网域 | `jms_create_zone_gateway.py create-zone --confirm` | 只发送 `name/assets/comment`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建网关机器 | `jms_create_zone_gateway.py create-gateway --confirm` | 以完整 `--payload` 为主；`platform/zone/nodes/labels` 支持解析；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建账号模板 | `jms_create_account_template.py create-account-template --confirm` | 以完整 `--payload` 为主；`su_from/platforms` 支持解析；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段脱敏 |
| 给资产批量添加账号 | `jms_asset_account_bulk.py add-account-to-assets --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段脱敏 |
| 给资产或节点批量添加账号模板 | `jms_asset_account_bulk.py add-account-template-to-assets --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建命令组 | `jms_create_command_acl.py create-command-group --confirm` | 只发送 `type/ignore_case/name/content/comment`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建命令过滤规则 | `jms_create_command_acl.py create-command-filter-rule --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建用户登录控制 | `jms_create_login_acl.py create-login-acl --confirm` | 以完整 `--payload` 为主；显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`；不写 `.env` |
| 创建连接方式过滤器 | `jms_create_connect_method_acl.py create-connect-method-acl --confirm` | 以完整 `--payload` 为主；显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`；不写 `.env` |
| 创建资产授权规则 | `jms_create_asset_permission.py create-asset-permission --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建资产连接规则 | `jms_create_login_asset_acl.py create-login-asset-acl --confirm` | 以完整 `--payload` 为主；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |
| 创建数据脱敏过滤规则 | `jms_create_data_masking_rule.py create-data-masking-rule --confirm` | 以完整 `--payload` 为主；`accounts` 只支持 `@ALL/@SPEC`；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止 |

## 全局阻塞规则

- 未被上表声明的写操作一律阻塞。
- 除 `create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset` 外，资产创建不开放；资产、平台、权限关系等对象的更新、删除、解锁不开放；账号仅开放 `add-account-to-assets` 与 `add-account-template-to-assets`，节点仅开放 `create-node`，网域仅开放 `create-zone`，网关机器仅开放 `create-gateway`，账号模板仅开放 `create-account-template`，命令组仅开放 `create-command-group`，命令过滤规则仅开放 `create-command-filter-rule`，用户登录控制仅开放 `create-login-acl`，连接方式过滤器仅开放 `create-connect-method-acl`，资产授权规则仅开放 `create-asset-permission`，资产连接规则仅开放 `create-login-asset-acl`，数据脱敏过滤规则仅开放 `create-data-masking-rule`。
- 除命令过滤规则、用户登录控制、连接方式过滤器、资产授权规则、资产连接规则、数据脱敏过滤规则外，授权创建、更新、追加、移除、删除不开放。
- 多个候选对象、名称歧义、组织不明确或跨组织风险未确认时阻塞。
- 用户要求跳过预检、绕过正式入口或现场拼临时脚本时阻塞。
