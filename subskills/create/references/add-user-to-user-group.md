# Add User To User Group

## 添加用户到用户组

### API

`POST /api/v1/users/users-groups-relations/`

### 入口

```bash
python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group ...
```

### 必填

- `--user`
- `--user-group`

### 可选

- 通过多个 `--user <username-or-email-or-name-or-uuid>` 添加多个用户。
- `--org-id <org-id>` 指定目标组织；只覆盖本次命令，不写 `.env`。
- `--org-name <name>` 指定目标组织名称；只覆盖本次命令，不写 `.env`。

### 组织规则

- 未传目标组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回 `reason_code=ambiguous_organization_selector`。
- 目标组织不能使用全局组织 ID。
- dry-run 不写 `.env`，不 POST，不解析用户或用户组。

### 解析规则

- `--user` 支持用户 UUID、username、email、姓名。
- `--confirm` 时，用户只在目标组织下查询 `/api/v1/users/users/` 并解析为用户 UUID。
- 用户不存在时返回 `reason_code=add_user_group_user_not_found`。
- 用户多匹配时返回 `reason_code=add_user_group_user_ambiguous` 与候选用户。
- `--user-group` 支持用户组 ID 或精确名称。
- 用户组只在目标组织下查询 `/api/v1/users/groups/`。
- 用户组不存在时返回 `reason_code=add_user_group_group_not_found`。
- 用户组多匹配时返回 `reason_code=add_user_group_group_ambiguous`。

### Payload

```json
[
  {
    "user": "<user-id>",
    "usergroup": "<user-group-id>"
  }
]
```

### 示例

```bash
python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group --org-name Default --user zhangsan --user-group 运维组
python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group --org-name Default --user zhangsan --user-group 运维组 --confirm
python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group --org-id <org-id> --user zhangsan@example.com --user lisi --user-group 运维组 --confirm
```
