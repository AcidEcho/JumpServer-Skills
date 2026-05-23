# Create Data Masking Rule

## API

`POST /api/v1/acls/data-masking-rules/`

## 入口

```bash
python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule ...
```

## Payload 规则

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 23 项。
- 常用显式字段会覆盖 payload：`--name`、`--priority`、`--account`、`--user`、`--asset`、`--fields-pattern`、`--masking-method`、`--mask-pattern`、`--is-active`、`--comment`。
- `--account`、`--user`、`--asset` 可重复传。
- 未传 `priority` 默认 `50`。
- 未传 `accounts` 默认 `["@ALL"]`。
- `--user` 写入 `users.type=ids`，`--asset` 写入 `assets.type=ids`。
- `users.type=ids` 时，`--confirm` 会复用现有用户解析能力，把用户 ID、username 或姓名解析成用户 ID。
- `assets.type=ids` 时，`--confirm` 会复用现有资产解析能力，把资产 ID、名称或地址解析成资产 ID。
- `masking_method` 只接受 `fixed_char`、`hide_middle`、`keep_prefix`、`keep_suffix`。
- `fields_pattern` 未传时按 API 默认值 `password` 带入。
- `masking_method=fixed_char` 且未传 `mask_pattern` 时，按 API 默认值 `######` 带入。

## 示例

```bash
python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule --org-name Default --payload '<json>' --name 密码脱敏 --masking-method fixed_char --confirm
```

## 组织规则

- 显式 `--org-id` / `--org-name` 只限定本次命令，不写 `.env`。
- 未传组织时使用 `.env JMS_ORG_ID`。
- 全局组织禁止。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。
- 无 `--confirm` 默认 dry-run；只有 `--confirm` 才解析用户/资产并 POST。
