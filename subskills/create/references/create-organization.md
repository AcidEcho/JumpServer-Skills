# Create Organization

## 创建组织

API：`POST /api/v1/orgs/orgs/`

入口：

```bash
python3 subskills/create/scripts/jms_create_org.py create-organization ...
```

必填：

- `--name`

可选：

- `--comment`

Payload 规则：

- 无备注：`{"name": "<name>"}`
- 带备注：`{"name": "<name>", "comment": "<comment>"}`

执行规则：

- 无 `--confirm` 只预览 payload，不调用 client，不做在线查重。
- 有 `--confirm` 时，先按可访问组织列表查重组织名称，再 POST 创建。
- 创建组织请求不带 `X-JMS-ORG`，不使用 `.env JMS_ORG_ID`。
- 创建成功后不写 `.env JMS_ORG_ID`，不自动切换当前组织。
- 组织名称重复时返回 `reason_code=organization_already_exists` 与 `duplicate_organizations`，每条包含 `id`、`name`、`comment`。

示例：

```bash
python3 subskills/create/scripts/jms_create_org.py create-organization --name new
python3 subskills/create/scripts/jms_create_org.py create-organization --name new --comment 备注 --confirm
```
