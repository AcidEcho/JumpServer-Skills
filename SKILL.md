---
name: jumpserver-skills
description: >
  JumpServer V4.10 main routing skill. Use for JumpServer queries, access scope,
  permissions, audit logs, reports, inspections, runtime config checks, connectivity,
  organization selection, allowed create workflows, and reserved update requests.
  中文创建触发词：创建用户、创建用户组、创建组织、邀请用户、添加用户到用户组、创建标签、
  创建节点、创建主机资产、创建网络设备资产、创建数据库资产、创建 Web 资产、创建网域、
  创建网关、创建账号模板、批量添加资产账号、绑定账号模板到资产、创建命令组、
  创建命令过滤规则、创建登录控制、创建连接方式过滤器、创建资产授权规则、创建资产连接规则、
  创建数据脱敏规则。
---

# JumpServer Skills

主 Skill 只做路由。具体能力进入子 Skill 后再执行。全局路由与写操作白名单见 [references/routing-and-safety.md](references/routing-and-safety.md)。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 用户自然语言需求、对象名/ID、组织、时间范围、过滤条件、创建参数 |
| 输出 | 目标子 Skill、正式入口、预检建议、阻塞原因或可执行命令摘要 |

## Route

| 请求类型 | 子 Skill | 入口索引 / 命令摘要 |
|---|---|---|
| 配置检查、预检、组织选择、连通性、端点验证 | [subskills/common/SKILL.md](subskills/common/SKILL.md) | `jms_common.py config-status` / `ping` / `select-org` / `endpoint-verify` |
| 对象、访问范围、权限、审计、报告、巡检、只读运行时数据 | [subskills/query/SKILL.md](subskills/query/SKILL.md) | `jms_query.py` / `jms_access.py` / `jms_permissions.py` / `jms_audit.py` / `jms_inspect.py` / `jms_runtime_query.py` / `jms_report.py` |
| 创建类 | [subskills/create/SKILL.md](subskills/create/SKILL.md) | 完整索引见 [subskills/create/references/index.md](subskills/create/references/index.md) |
| 更新类预留 | [subskills/update/SKILL.md](subskills/update/SKILL.md) | 本版无可执行业务更新 |

## Create Command 白名单

完整白名单与每条入口的写入规则以 [references/routing-and-safety.md](references/routing-and-safety.md) 的"允许写操作"表为唯一来源；create 子 skill 的命令-脚本映射见 [subskills/create/references/index.md](subskills/create/references/index.md)。当前开放命令：`create-user`、`create-user-group`、`create-organization`、`invite-user-to-org`、`add-user-to-user-group`、`create-label`、`create-node`、`create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset`、`create-zone`、`create-gateway`、`create-account-template`、`add-account-to-assets`、`add-account-template-to-assets`、`create-command-group`、`create-command-filter-rule`、`create-login-acl`、`create-connect-method-acl`、`create-asset-permission`、`create-login-asset-acl`、`create-data-masking-rule`。

## 路由流程

```text
识别请求类型 -> 配置/组织不确定先 common -> 进入目标子 Skill -> 使用正式入口 -> 返回结果或阻塞原因
```

## Safety

| 条件 | 动作 |
|---|---|
| 未被白名单声明的业务写操作 | 阻塞 |
| 已开放 create 写操作 | 必须追加 `--confirm` 才真实写入 |
| 本地运行时写入 | 只允许 `config-write --confirm`、`select-org --confirm` |
| dry-run、成功、错误输出 | 不回显 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`、`password` |
| 对象 ID、平台 ID、组织、鉴权信息或筛选条件不明确 | 先查询或解析，不猜 |
| 用户要求临时 SDK/Python/HTTP 绕过正式入口 | 阻塞 |

## 边界

| 不适用场景 | 处理 |
|---|---|
| 直接执行 JumpServer 业务更新、删除、解锁 | 路由到 update 预留说明并阻塞 |
| 报告类请求要求绕过 `jms_report.py` 正式入口 | 阻塞临时拼装 |
| 跨组织对象不明确 | 返回候选或要求用户明确组织 |

## 成功标准

- 已说明预检和生效组织。
- 已说明目标子 Skill 和正式入口。
- 已说明写操作是否需要 `--confirm`。
- 阻塞时返回原因、候选对象/组织和下一步安全动作。
