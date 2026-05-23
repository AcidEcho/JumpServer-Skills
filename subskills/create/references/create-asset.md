# Create Assets

## API

- 主机：`POST /api/v1/assets/hosts/`
- 网络设备：`POST /api/v1/assets/devices/`
- 数据库：`POST /api/v1/assets/database/`
- Web 资产：`POST /api/v1/assets/webs/`

## 入口

```bash
python3 subskills/create/scripts/jms_create_asset.py create-host-asset ...
python3 subskills/create/scripts/jms_create_asset.py create-device-asset ...
python3 subskills/create/scripts/jms_create_asset.py create-database-asset ...
python3 subskills/create/scripts/jms_create_asset.py create-web-asset ...
```

## Payload 规则

- v1 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 8-11 项。
- 常用显式字段会覆盖 payload：`--name`、`--address`、`--platform`、`--platform-pk`、`--node`、`--label`、`--zone`、`--protocol name:port`、`--account-template`、`--account-json`、`--is-active`、`--comment`。
- `--confirm` 时解析 `platform/nodes/labels/zone/accounts[].template`，最终发送平台 ID、对象 UUID 或 `pk`。
- `zone` 可选；未传 `--zone` 且 payload 中没有 `zone` 时不发送网域字段，显式传入时才解析并带入。
- 未传 `protocols` 时，dry-run 不联网；`--confirm` 后按平台默认协议补齐。
- `accounts` 可不传；传入时支持内联账号和账号模板。内联账号 `secret_type` 只支持 `password/ssh_key`，密文字段输出脱敏。
- 数据库资产支持 `--db-name`、`--use-ssl/--no-use-ssl`、`--allow-invalid-cert/--no-allow-invalid-cert`；未传 `db_name` 时按平台默认库名补齐。
- Web 资产支持 `--autofill no|basic|script`、选择器字段和 `--script-json`；`autofill=script` 时必须有 `script`。

## 示例

```bash
python3 subskills/create/scripts/jms_create_asset.py create-host-asset --org-name Default --name Linux --address 1.1.1.1 --platform Linux --node /Default --confirm
python3 subskills/create/scripts/jms_create_asset.py create-database-asset --org-name Default --payload '<json>' --confirm
```

## 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传。
- 显式组织只限定本次命令，不写 `.env`。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- dry-run 不写 `.env`，不 POST，不解析对象；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建。
