# Create Login ACL

API：`POST /api/v1/acls/login-acls/`

入口：

```bash
python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl ...
```

Payload 规则：

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 7 项。
- 常用显式字段会覆盖 payload：`--name`、`--priority`、`--action`、`--reviewer`、`--is-active`、`--comment`。
- 未传 `priority` 默认 `50`。
- 未传 `action` 默认 `reject`。
- `--reviewer` 可重复传，支持用户 ID、用户名或姓名；`--confirm` 时解析后写入 `reviewers[].pk`。
- `action` 只接受 `review`、`accept`、`reject`、`notice`。
- `action` 为 `review` 或 `notice` 时，payload 必须包含 `reviewers`。
- `--is-active` 写入布尔 `is_active`。

示例：

```bash
python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl --payload '<json>' --name 登录审批 --action review --confirm
```

组织规则：

- 只能在全局组织下创建。
- 全局组织 ID 固定为 `00000000-0000-0000-0000-000000000000`。
- 显式 `--org-id` / `--org-name` 或 `.env JMS_ORG_ID` 最终都必须解析为全局组织 ID。
- 显式组织只限定本次命令，不写 `.env`。
- 未传组织时使用 `.env JMS_ORG_ID`，但值必须是全局组织 ID。
- dry-run 不写 `.env`，不 POST，不查重；传 `--org-name` 时只预览组织名。
- 无 `--confirm` 默认 dry-run；只有 `--confirm` 才 POST。
