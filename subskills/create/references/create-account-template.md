# Create Account Template

## API

`POST /api/v1/accounts/account-templates/`

## 入口

```bash
python3 subskills/create/scripts/jms_create_account_template.py create-account-template ...
```

## Payload 规则

- v1 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 17 项。
- 常用显式字段可覆盖 payload：`--name`、`--username`、`--secret-type`、`--secret-strategy`、`--privileged`、`--auto-push`、`--platform`、`--su-from`、`--comment`。
- `secret_type` 可为 `password`、`ssh_key`、`token`、`access_key`、`api_key`。
- `secret_strategy` 可为 `specific` 或 `random`；`specific` 使用传入密文，`random` 可配合 `password_rules`。
- `auto_push=true` 时需要 `platforms`；`--confirm` 时平台支持 ID、名称或 slug 解析，payload 最终发送 `{"pk": <platform-id>}`。
- `su_from` 可传账号模板 ID 或名称；`--confirm` 时查询 `su-from-account-templates` 候选并解析为 ID。
- dry-run 不解析 `su_from/platforms`，只展示待发送预览。

## Secret 脱敏

- 不回显明文 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`。
- dry-run 输出 payload 时，上述字段统一显示为脱敏值。
- `--confirm` 成功或失败回显时，也不能暴露密文字段。

## 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传。
- 显式 `--org-id` / `--org-name` 只限定本次命令，不写 `.env`。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建。

## 示例

Dry-run 预览，不 POST：

```bash
python3 subskills/create/scripts/jms_create_account_template.py create-account-template --org-name Default --payload '<json>'
```

确认创建，才执行 POST：

```bash
python3 subskills/create/scripts/jms_create_account_template.py create-account-template --org-name Default --payload '<json>' --confirm
```
