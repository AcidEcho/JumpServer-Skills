# Create Organization

## 创建组织

### API

`POST /api/v1/orgs/orgs/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_org.py create-organization ...
```

### 必填

- `--name`

### 可选

- `--comment`

### Payload 规则

- 无备注：`{"name": "<name>"}`
- 带备注：`{"name": "<name>", "comment": "<comment>"}`

### 执行规则

- 无 `--confirm` 只预览 payload，不调用 client。
- 有 `--confirm` 时直接 POST 创建；唯一性冲突由服务端校验返回。
- 创建组织请求不带 `X-JMS-ORG`，不使用 `.env JMS_ORG_ID`。
- 创建成功后不写 `.env JMS_ORG_ID`，不自动切换当前组织。

### 示例

```bash
python3 subskills/create/scripts/jms_create_org.py create-organization --name new
python3 subskills/create/scripts/jms_create_org.py create-organization --name new --comment 备注 --confirm
```
