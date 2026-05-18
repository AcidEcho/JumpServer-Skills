---
name: jumpserver-skills
description: >
  JumpServer V4.10 main routing skill. Use when users ask to query JumpServer objects,
  access, permissions, audit logs, reports, inspections, runtime config checks,
  connectivity checks, organization selection, create users, user groups, organizations,
  host/device/database/web assets, zones, gateways, account templates, add accounts or
  account templates to assets, command groups, command filter rules, login ACLs, connect
  method ACLs, asset permissions, login asset ACLs, data masking rules, or reserve update
  workflows. 中文创建触发词：创建用户、创建用户组、创建组织、邀请用户、添加用户到用户组、
  创建标签、创建节点、创建主机资产、创建网络设备资产、创建数据库资产、创建 Web 资产、
  创建网域、创建网关、创建账号模板、批量添加资产账号、绑定账号模板到资产、创建命令组、
  创建命令过滤规则、创建登录控制、创建连接方式过滤器、创建资产授权规则、创建资产连接规则、
  创建数据脱敏规则。
---

# JumpServer Skills

主 Skill 只做路由。具体能力进入一个子 Skill 后再执行。

全局路由与写操作白名单见 [references/routing-and-safety.md](references/routing-and-safety.md)。

## Route

| 需求 | 子 Skill | 入口 |
|------|----------|------|
| 配置检查、预检、组织选择、连通性、端点验证 | [subskills/common/SKILL.md](subskills/common/SKILL.md) | `python3 subskills/common/scripts/jms_common.py ...` |
| 所有查询类：对象、访问范围、权限、审计、报告、巡检、只读运行时数据 | [subskills/query/SKILL.md](subskills/query/SKILL.md) | `python3 subskills/query/scripts/<script>.py ...` |
| 创建类 | [subskills/create/SKILL.md](subskills/create/SKILL.md) | `python3 subskills/create/scripts/jms_create_user.py create-user ...` / `python3 subskills/create/scripts/jms_create_user_group.py create-user-group ...` / `python3 subskills/create/scripts/jms_create_org.py create-organization ...` / `python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org ...` / `python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group ...` / `python3 subskills/create/scripts/jms_create_label.py create-label ...` / `python3 subskills/create/scripts/jms_create_node.py create-node ...` / `python3 subskills/create/scripts/jms_create_asset.py create-host-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-device-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-database-asset ...` / `python3 subskills/create/scripts/jms_create_asset.py create-web-asset ...` / `python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone ...` / `python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway ...` / `python3 subskills/create/scripts/jms_create_account_template.py create-account-template ...` / `python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets ...` / `python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets ...` / `python3 subskills/create/scripts/jms_create_command_acl.py create-command-group ...` / `python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule ...` / `python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl ...` / `python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl ...` / `python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission ...` / `python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl ...` / `python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule ...` |
| 更新类预留 | [subskills/update/SKILL.md](subskills/update/SKILL.md) | 暂无可执行写操作 |

## Common First

配置、组织或连通性不确定时先执行：

```bash
python3 subskills/common/scripts/jms_common.py config-status --json
python3 subskills/common/scripts/jms_common.py ping
```

阻塞或参数错误时，优先看返回里的 `reason_code`、`user_message`、`action_hint`、`suggested_commands`。

## Safety

- 未被 [references/routing-and-safety.md](references/routing-and-safety.md) 明确声明的写操作一律阻塞。
- 本版 JumpServer 业务写操作仅开放：`create-user`、`create-user-group`、`create-organization`、`invite-user-to-org`、`add-user-to-user-group`、`create-label`、`create-node`、`create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset`、`create-zone`、`create-gateway`、`create-account-template`、`add-account-to-assets`、`add-account-template-to-assets`、`create-command-group`、`create-command-filter-rule`、`create-login-acl`、`create-connect-method-acl`、`create-asset-permission`、`create-login-asset-acl`、`create-data-masking-rule`，且必须 `--confirm`。
- 允许本地运行时写入：`config-write --confirm`、`select-org --confirm`。
- dry-run、成功和错误输出中不回显密文字段或密文语义字段，包括 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`、`password`。
- 不猜对象 ID、平台 ID、组织、鉴权信息或筛选条件。
- 不生成临时 SDK Python 脚本或 HTTP 脚本绕过正式入口。

## Respond With

成功时至少回显：已走预检、生效组织、入口脚本、命令摘要、关键结果。
阻塞时至少回显：已走预检、生效组织、阻塞原因、候选对象/组织、下一步安全动作。
