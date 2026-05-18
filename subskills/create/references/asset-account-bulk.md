# Asset Account Bulk

API：`POST /api/v1/accounts/accounts/bulk/`

入口：

```bash
python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets ...
python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets ...
```

## 给资产批量添加账号

对应 `API.md` 第 15 项。

Payload 规则：

- v1 以 `--payload` 完整 JSON 为主。
- 常用显式字段可覆盖 payload：`--name`、`--username`、`--secret-type`、`--secret`、`--passphrase`、`--privileged`、`--secret-reset`、`--push-now`、`--on-invalid`、`--is-active`、`--asset`、`--comment`。
- `assets` 支持资产 ID、名称或地址；`--confirm` 时在目标组织内解析，规则复用 query/discovery。
- `on_invalid` 可为 `skip`、`update`、`error`。
- `secret_type` 可为 `ssh_key`、`password`、`token`、`access_key`、`api_key`。
- `secret_type=ssh_key` 时可传 `passphrase`。

示例：

```bash
python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets --org-name Default --payload '<json>' --confirm
```

## 给资产或节点批量添加账号模板

对应 `API.md` 第 16 项。

Payload 规则：

- v1 以 `--payload` 完整 JSON 为主。
- 常用显式字段可覆盖 payload：`--template`、`--asset`、`--node`、`--privileged`、`--secret-type`、`--secret-reset`、`--push-now`、`--on-invalid`、`--is-active`。
- `secret_type` 必填，可为 `ssh_key`、`password`、`token`、`access_key`、`api_key`。
- `template` 支持账号模板 ID 或名称；`--confirm` 时在目标组织内解析。
- `assets` 支持资产 ID、名称或地址；`nodes` 支持节点 ID、名称或 full_value。
- `on_invalid` 可为 `skip`、`update`、`error`。

示例：

```bash
python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets --org-name Default --secret-type password --payload '<json>' --confirm
```

## Secret 脱敏

- 不回显明文 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`。
- dry-run 输出 payload 时，上述字段统一显示为脱敏值。
- `--confirm` 成功或失败回显时，也不能暴露密文字段。

## 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传。
- 显式 `--org-id` / `--org-name` 只限定本次命令，不写 `.env`。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织执行，但不写 `.env JMS_ORG_ID`。
- dry-run 不写 `.env`，不 POST，不查重；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下执行。
