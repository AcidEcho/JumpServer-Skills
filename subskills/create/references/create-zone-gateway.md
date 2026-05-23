# Create Zone And Gateway

## 创建网域

### API

`POST /api/v1/assets/zones/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone ...
```

### Payload 规则

- 只发送 `name/assets/comment`。
- `name` 必填。
- `assets` 来自重复 `--asset <asset-id>` 或 payload 数组。
- `comment` 未传不发送。

### 示例

```bash
python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone --org-name Default --name 网域名称 --asset <asset-id> --confirm
```

## 创建网关机器

### API

`POST /api/v1/assets/gateways/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway ...
```

### Payload 规则

- v1 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 14 项。
- 常用显式字段会覆盖 payload：`--name`、`--address`、`--zone`、`--platform`、`--platform-pk`、`--node`、`--label`、`--protocol name:port`。
- 必填核心字段：`name/address/platform.pk/zone/nodes/protocols/accounts`。
- `--confirm` 时 `platform/zone/nodes/labels` 支持 ID、名称或值解析，最终发送 ID 或 `pk`。
- 本地校验 `accounts[]`：每项必须有 `name/username/secret_type/secret`，`secret_type` 只支持 `password/ssh_key`。
- 返回 dry-run 时会脱敏 `accounts[].secret`。

### 示例

```bash
python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway --org-name Default --payload '<json>' --confirm
```

## 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传。
- 显式组织只限定本次命令，不写 `.env`。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建。
