---
name: jumpserver-create
description: >
  Create JumpServer objects and rules. Use when users ask to create users, user groups,
  organizations, invitations, user-group relations, labels, nodes, host/device/database/web
  assets, zones, gateways, account templates, asset-account bulk bindings, command groups,
  command filter rules, login ACLs, connect method filters, asset permissions, login asset
  ACLs, or data masking rules. Requires --confirm for writes and supports dry-run previews.
  中文触发词：创建用户、创建用户组、创建组织、邀请用户、添加用户到用户组、创建标签、
  创建节点、创建主机资产、创建网络设备资产、创建数据库资产、创建 Web 资产、创建网域、
  创建网关、创建账号模板、批量添加资产账号、绑定账号模板到资产、创建命令组、
  创建命令过滤规则、创建登录控制、创建连接方式过滤器、创建资产授权规则、创建资产连接规则、
  创建数据脱敏规则。
---

# Create

JumpServer create 子 Skill 只允许使用正式入口脚本创建对象，不允许临时拼 HTTP/SDK 绕过预检。

若本目录被独立注册为 Skill 根目录，使用 [agents/openai.yaml](agents/openai.yaml)，并从本目录 cwd 执行 `python3 scripts/<entry>.py ...`；完整仓库要求见 [子 Skill 独立注册](../../references/subskill-registration.md)。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 创建对象类型、组织、必填字段、引用对象、可选 `--payload` |
| 输出 | dry-run payload、引用解析结果、服务端创建结果或冲突错误、候选对象 |

## 正式入口

完整命令、脚本入口和详细规则见 [references/index.md](references/index.md)。

`create-user`、`create-user-group`、`create-organization`、`invite-user-to-org`、`add-user-to-user-group`、`create-label`、`create-node`、`create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset`、`create-zone`、`create-gateway`、`create-account-template`、`add-account-to-assets`、`add-account-template-to-assets`、`create-command-group`、`create-command-filter-rule`、`create-login-acl`、`create-connect-method-acl`、`create-asset-permission`、`create-login-asset-acl`、`create-data-masking-rule`。

## 流程

```text
识别创建类型 -> 选择正式入口 -> 无 --confirm 只预览 -> --confirm 后解析必要引用 -> POST -> 服务端原子校验唯一性
```

## 安全规则

| 场景 | 规则 |
|---|---|
| 无 `--confirm` | 只预览 payload，不 POST，不解析在线对象，不写 `.env` |
| 有 `--confirm` | 解析必要引用并真实创建；唯一性由 JumpServer 服务端校验 |
| `--org-id` / `--org-name` | 只覆盖本次命令；两者不能同时传 |
| 未传组织 | 使用 `.env JMS_ORG_ID` 当前组织 |
| `--org-name` 未匹配或多匹配 | 返回 `candidate_orgs`，不写 `.env`，不创建 |
| `create-user`、`create-user-group` 的 `--org-name --confirm` | 唯一匹配后仅限本次命令，不写 `.env` |
| `create-organization` | 请求不带 `X-JMS-ORG`，成功后不切换 `.env JMS_ORG_ID` |
| `create-login-acl`、`create-connect-method-acl` | 只能在全局组织 ID `00000000-0000-0000-0000-000000000000` 下创建，且不写 `.env` |
| 其他业务 create 命令 | 禁止使用全局组织 |
| 输出 | dry-run 和成功/错误输出中不回显 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`、`password` |

## 引用解析与服务端约束

| 对象 | 规则 |
|---|---|
| 用户、邀请用户、添加用户到用户组 | 用户、角色、用户组按对应参考文档的组织范围解析 |
| 主机/网络设备/数据库/Web 资产 | `--confirm` 时解析平台、节点、标签、网域、账号模板 |
| 网关、账号模板、资产授权、ACL 类命令 | `--confirm` 时解析平台、节点、标签、用户、资产、审批人等引用 |
| 服务端唯一性冲突 | 保留服务端状态码和错误详情，不额外查询对象列表 |
| 引用解析失败 | 阻止创建并返回候选对象 |

## 边界

| 不适用场景 | 处理 |
|---|---|
| `API.md` 已存在但未在 [references/index.md](references/index.md) 登记的创建接口 | 暂不开放 |
| 更新、删除、解锁 | 不属于 create 子 Skill |
| 跳过预检或绕过正式入口 | 阻塞 |

## 成功标准

- 已返回 dry-run payload 或真实创建结果。
- 已说明生效组织和入口脚本。
- 写操作必须有 `--confirm`。
- 密文字段或密文语义字段已脱敏。
