# Create User

## 创建用户

### API

`POST /api/v1/users/users/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_user.py create-user ...
```

### 必填

- `--username`
- `--name`
- `--email`
- 默认 `--password-strategy custom` 时必须传 `--password`

### 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- 可传 `--org-id <org-id>` 指定创建所在组织；只覆盖本次命令，不写 `.env`。
- 可传 `--org-name <name>` 指定组织名称；`--confirm` 时查询当前 AK/SK 可访问组织。
- `--org-name --confirm` 唯一匹配后仅限定本次命令，不写 `.env`。
- `--org-name` 未匹配时返回 `reason_code=organization_not_accessible`、`org_name`、`candidate_orgs`。
- `--org-name` 多匹配时返回 `reason_code=ambiguous_organization`、`org_name`、命中的 `candidate_orgs`。
- 组织名失败时不写 `.env`，不创建；从 `candidate_orgs` 选择准确组织名后，用 `--org-name <selected-name> --confirm` 重试。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回 `reason_code=ambiguous_organization_selector`。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。

### 默认 Payload

- `password_strategy=custom`
- `need_update_password=true`
- `mfa_level=0`
- `source=local`
- `is_active=true`
- `system_roles=["00000000-0000-0000-0000-000000000003"]`
- `org_roles=["00000000-0000-0000-0000-000000000007"]`

### 角色与用户组

- `--system-role`、`--org-role`、`--group` 可传 ID 或精确名称。
- `--confirm` 时才在线解析系统角色、组织角色、用户组；dry-run 只预览 payload。
- 解析顺序固定：`system_roles` -> `org_roles` -> `groups`。
- 某类解析失败时只返回当前失败类型的查询列表，让用户确认后重试；不会一次返回后续类型。
- 系统角色失败返回 `failed_reference_type=system_roles` 与 `available_system_roles`。
- 组织角色失败返回 `failed_reference_type=org_roles` 与 `available_org_roles`。
- 用户组失败返回 `failed_reference_type=groups` 与 `available_groups`。
- 只读查询复用 common discovery endpoint；创建 POST 仍由 create 子 skill 执行。

唯一性冲突由服务端原子校验返回；Skill 保留服务端状态码与错误详情，不额外查询重复用户候选。

### 未传不发送

- `date_expired`
- `phone`
- `comment`
- `groups`

### 示例

```bash
python3 subskills/create/scripts/jms_create_user.py create-user --username zhangsan --name 张三 --email zhangsan@example.com --password '<password>'
python3 subskills/create/scripts/jms_create_user.py create-user --username zhangsan --name 张三 --email zhangsan@example.com --password '<password>' --confirm
python3 subskills/create/scripts/jms_create_user.py create-user --org-id <org-id> --username zhangsan --name 张三 --email zhangsan@example.com --password '<password>' --confirm
python3 subskills/create/scripts/jms_create_user.py create-user --org-name Default --username zhangsan --name 张三 --email zhangsan@example.com --password '<password>' --confirm
python3 subskills/create/scripts/jms_create_user.py create-user --username zhangsan --name 张三 --email zhangsan@example.com --password '<password>' --system-role 用户 --org-role 组织用户 --group 运维组 --confirm
```
