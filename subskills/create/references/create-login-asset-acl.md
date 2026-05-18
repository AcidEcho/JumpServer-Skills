# Create Login Asset ACL

API：`POST /api/v1/acls/login-asset-acls/`

入口：

```bash
python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl ...
```

Payload 规则：

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 19 项。
- 常用显式字段会覆盖 payload：`--name`、`--priority`、`--action`、`--account`、`--user`、`--asset`、`--reviewer`、`--is-active`、`--comment`。
- `--account`、`--user`、`--asset`、`--reviewer` 可重复传。
- 未传 `priority` 默认 `50`。
- 未传 `action` 默认 `reject`。
- `--user` 写入 `users.type=ids`，`--asset` 写入 `assets.type=ids`。
- `users.type=ids` 时，`--confirm` 会复用现有用户解析能力，把用户 ID、username 或姓名解析成用户 ID。
- `assets.type=ids` 时，`--confirm` 会复用现有资产解析能力，把资产 ID、名称或地址解析成资产 ID。
- `reviewers` 支持用户 ID、用户名或姓名，`--confirm` 时解析成 `reviewers[].pk`。
- 本地校验 `accounts`、`rules.ip_group`、`rules.time_period`、`users.attrs`、`assets.attrs`。
- `action` 只接受 `review`、`accept`、`reject`、`notice`、`face_verify`、`face_online`。
- `action` 为 `review` 或 `notice` 时，payload 必须包含 `reviewers`。

示例：

```bash
python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl --org-name Default --payload '<json>' --name 资产连接规则 --action reject --confirm
```

组织规则：

- 显式 `--org-id` / `--org-name` 只限定本次命令，不写 `.env`。
- 未传组织时使用 `.env JMS_ORG_ID`。
- 全局组织禁止。
- dry-run 不写 `.env`，不 POST，不查重；传 `--org-name` 时只预览组织名。
- 无 `--confirm` 默认 dry-run；只有 `--confirm` 才解析用户/资产、查重并 POST。
