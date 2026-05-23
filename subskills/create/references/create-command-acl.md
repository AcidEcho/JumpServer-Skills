# Create Command ACL

## 创建命令组

### API

`POST /api/v1/acls/command-groups/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_command_acl.py create-command-group ...
```

### Payload 规则

- 只发送 `type/ignore_case/name/content/comment`。
- `name`、`type`、`content` 必填。
- `type` 只接受 `command` 或 `regex`。
- `ignore_case` 未传时不发送。
- `comment` 未传时不发送。

### 示例

```bash
python3 subskills/create/scripts/jms_create_command_acl.py create-command-group --org-name Default --name 禁止rm --type command --content rm --confirm
```

## 创建命令过滤规则

### API

`POST /api/v1/acls/command-filter-acls/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule ...
```

### Payload 规则

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 20 项。
- 常用显式字段会覆盖 payload：`--name`、`--priority`、`--action`、`--account`、`--user`、`--asset`、`--command-group`、`--reviewer`、`--is-active`、`--comment`。
- 未传 `priority` 默认 `50`；未传 `action` 默认 `reject`；未传 `accounts` 默认 `["@ALL"]`。
- `--account` 可重复传，写入 `accounts`。
- `--user` / `--user-id` 可重复传，写入 `users.type=ids`；`--confirm` 时解析为用户 UUID。
- `--asset` / `--asset-id` 可重复传，写入 `assets.type=ids`；`--confirm` 时解析为资产 UUID。
- `--command-group` 可重复传，写入 `command_groups`。
- `--reviewer` 可重复传，写入 `reviewers[].pk`；`--confirm` 时解析为用户 UUID。
- `--is-active` 写入布尔 `is_active`。
- `action` 支持 `review`、`accept`、`reject`、`warning`、`notice`、`notify_and_warn`。
- `action` 为 `review`、`notice`、`notify_and_warn` 时必须传 `reviewers`。
- `users/assets.type` 只接受 `all`、`ids`、`attrs`；`ids` 必须非空，`attrs` 必须为数组。
- dry-run 不联网解析；正式 `--confirm` 才解析用户、资产和 reviewer 引用。

### 示例

```bash
python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule --org-name Default --name 高危命令拦截 --user alice --asset server1 --command-group <command-group-id> --confirm
```

## 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传。
- 显式组织只限定本次命令，不写 `.env`。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建。
