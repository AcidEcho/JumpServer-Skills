# Invite User To Org

## 邀请用户加入某个组织

API：`POST /api/v1/users/users/invite/`

入口：

```bash
python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org ...
```

必填：

- `--user`
- `--org-role`

可选：

- 通过多个 `--user <username-or-email-or-name-or-uuid>` 邀请多个用户。
- 通过多个 `--org-role <role-id-or-name>` 指定多个组织角色。
- `--org-id <org-id>` 指定目标组织；只覆盖本次命令，不写 `.env`。
- `--org-name <name>` 指定目标组织名称；只覆盖本次命令，不写 `.env`。

组织：

- 未传目标组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回 `reason_code=ambiguous_organization_selector`。
- 邀请目标组织不能使用全局组织 ID。
- dry-run 不写 `.env`，不 POST，不解析用户或角色。

解析规则：

- `--user` 支持用户 UUID、username、email、姓名。
- `--confirm` 时，用户标识从全局组织 `00000000-0000-0000-0000-000000000000` 查询 `/api/v1/users/users/` 并解析为用户 UUID。
- 用户不存在时返回 `reason_code=invite_user_not_found`。
- 用户多匹配时返回 `reason_code=invite_user_ambiguous` 与候选用户。
- `--org-role` 支持组织角色 ID 或精确名称。
- 组织角色在目标组织下查询 `/api/v1/rbac/org-roles/`。
- 组织角色不存在时返回 `reason_code=invite_org_role_reference_not_found`。
- 组织角色多匹配时返回 `reason_code=invite_org_role_reference_ambiguous`。

Payload：

```json
{
  "users": [
    "<user-id>"
  ],
  "org_roles": [
    "<org-role-id>"
  ]
}
```

示例：

```bash
python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org --org-name Default --user zhangsan --org-role 组织用户
python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org --org-name Default --user zhangsan --org-role 组织用户 --confirm
python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org --org-id <org-id> --user zhangsan@example.com --user lisi --org-role 组织用户 --confirm
```
