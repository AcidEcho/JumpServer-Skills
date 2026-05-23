# Create Asset Permission

## API

`POST /api/v1/perms/asset-permissions/`

## 入口

```bash
python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission ...
```

## Payload 规则

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 18 项。
- 常用显式字段会覆盖 payload：`--name`、`--asset`、`--node`、`--user`、`--user-group`、`--account`、`--no-account`、`--protocol`、`--action`、`--is-active`、`--date-start`、`--date-expired`、`--comment`。
- `--asset`、`--node`、`--user`、`--user-group`、`--account`、`--protocol`、`--action` 可重复传。
- 未传 `accounts` 默认 `["@ALL"]`。
- 未传 `protocols` 默认 `["all"]`。
- 未传 `actions` 默认全部动作 value：`connect/upload/download/copy/paste/delete/share`。
- `actions` payload 只发送 value；label 只用于显示。
- `protocols=["all"]` 表示所有协议；显式传协议时，`--confirm` 查询协议选项，按 `value` 或 `label` 匹配，payload 发送 `value`。
- `assets` 支持资产 UUID、名称或地址，`--confirm` 时解析成 UUID 字符串。
- `nodes` 支持节点 UUID、名称或 `full_value`，`--confirm` 时解析成 `nodes[].pk`。
- `users` 支持用户 UUID、用户名或姓名，`--confirm` 时解析成 `users[].pk`。
- `user_groups` 支持用户组 UUID 或名称，`--confirm` 时解析成 `user_groups[].pk`。

## 账号规则

- 基础账号模式四选一：所有账号 `@ALL`、指定账号 `@SPEC + 账号名`、排除账号 `!name`、无账号 `[]`。
- 虚拟账号 `@INPUT`、`@USER`、`@ANON` 可单独使用，也可与任一基础模式组合。
- `--no-account` 表示基础账号模式为无账号，可与虚拟账号组合，例如 `--no-account --account @USER`。
- `--no-account` 不能与 `@ALL`、`@SPEC`、`!name` 或普通账号名混用。
- `@ANON` 只做组合校验，资产类型兼容性交给 JumpServer 服务端判断。

## 示例

```bash
python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission --org-name Default --name 生产资产授权 --user alice --asset prod-host --confirm
python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission --org-name Default --name 手动账号授权 --user alice --asset prod-host --no-account --account @INPUT --confirm
python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission --org-name Default --payload '<json>' --confirm
```

## 组织规则

- 显式 `--org-id` / `--org-name` 只限定本次命令，不写 `.env`。
- 未传组织时使用 `.env JMS_ORG_ID`。
- 全局组织禁止。
- dry-run 不写 `.env`，不 POST，不解析对象或协议；传 `--org-name` 时只预览组织名。
- 无 `--confirm` 默认 dry-run；只有 `--confirm` 才解析引用并 POST。
