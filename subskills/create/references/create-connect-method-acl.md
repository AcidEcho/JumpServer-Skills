# Create Connect Method ACL

API：`POST /api/v1/acls/connect-method-acls/`

入口：

```bash
python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl ...
```

Payload 规则：

- 以 `--payload` 完整 JSON 为主，结构按 `API.md` 第 22 项。
- 常用显式字段会覆盖 payload：`--name`、`--action`、`--connect-method`、`--is-active`、`--comment`。
- `--connect-method` 可重复传，写入 `connect_methods`。
- 未传 `action` 默认 `reject`。
- `action` 只接受 `accept` 或 `reject`。
- `connect_methods` 不做硬编码枚举；`--confirm` 时查询 `/api/v1/terminal/components/connect-methods/?flat=1&os=all&search=<keyword>`。
- `connect_methods` 最终发送选项的 `value` 字段；`label` 是显示名，用于候选提示。
- `--is-active` 写入布尔 `is_active`。

示例：

```bash
python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl --payload '<json>' --name 禁止客户端连接 --action reject --connect-method ssh_client --confirm
```

组织规则：

- 只能在全局组织下创建。
- 全局组织 ID 固定为 `00000000-0000-0000-0000-000000000000`。
- 显式 `--org-id` / `--org-name` 或 `.env JMS_ORG_ID` 最终都必须解析为全局组织 ID。
- 显式组织只限定本次命令，不写 `.env`。
- 未传组织时使用 `.env JMS_ORG_ID`，但值必须是全局组织 ID。
- dry-run 不写 `.env`，不 POST，不查重；传 `--org-name` 时只预览组织名。
- 无 `--confirm` 默认 dry-run；只有 `--confirm` 才 POST。
