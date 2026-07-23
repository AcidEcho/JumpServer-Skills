# Create User Group

## 用户 ID 解析

创建用户组时，`--user` 只接收用户 ID。如果用户给的是姓名、username 或 email，先走 query 子 Skill 解析：

```bash
python3 subskills/query/scripts/jms_query.py resolve --resource user --name <value>
```

拿到唯一用户 ID 后，再传给创建用户组脚本。

## 创建用户组

### API

`POST /api/v1/users/groups/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_user_group.py create-user-group ...
```

### 必填

- `--name`

### 可选

- `--comment`
- 通过多个 `--user <user-id>` 添加多个用户 ID。
- `--org-id <org-id>` 指定创建所在组织；只覆盖本次命令，不写 `.env`。
- `--org-name <name>` 指定组织名称。

### 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后仅限定本次命令，不写 `.env`。
- `--org-name` 未匹配时返回 `reason_code=organization_not_accessible`、`org_name`、`candidate_orgs`。
- `--org-name` 多匹配时返回 `reason_code=ambiguous_organization`、`org_name`、命中的 `candidate_orgs`。
- 组织名失败时不写 `.env`，不创建；从 `candidate_orgs` 选择准确组织名后，用 `--org-name <selected-name> --confirm` 重试。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回 `reason_code=ambiguous_organization_selector`。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。

### Payload 规则

- 空组：`{"name": "<name>"}`
- 带备注：`{"name": "<name>", "comment": "<comment>"}`
- 带多个用户：`{"name": "<name>", "users": [{"pk": "<user-id-1>"}, {"pk": "<user-id-2>"}]}`

### 执行规则

- 无 `--confirm` 只预览 payload，不调用 client，不做用户 ID 存在性校验。
- 有 `--confirm` 时，逐个校验用户 ID 是否存在，最后 POST 创建；唯一性冲突由服务端校验返回。
- `--user` 不是用户 ID 时返回 `reason_code=create_user_group_user_id_required`，提示先用 query 解析用户 ID。
- 用户 ID 不存在时返回 `reason_code=create_user_group_user_not_found`、`missing_user_id` 与 `available_users`。
- 多个用户 ID 有问题时，一次只返回第一个失败用户 ID，让用户确认后重试。

### 示例

```bash
python3 subskills/create/scripts/jms_create_user_group.py create-user-group --name 运维组
python3 subskills/create/scripts/jms_create_user_group.py create-user-group --name 运维组 --comment 备注 --confirm
python3 subskills/create/scripts/jms_create_user_group.py create-user-group --org-id <org-id> --name 运维组 --confirm
python3 subskills/create/scripts/jms_create_user_group.py create-user-group --org-name Default --name 运维组 --confirm
python3 subskills/create/scripts/jms_create_user_group.py create-user-group --name 运维组 --user 636ee32f-9fbb-42a4-b9f7-3ae85444b74f --user c85d65e8-5909-47d2-b2b3-65f752583197 --confirm
```
