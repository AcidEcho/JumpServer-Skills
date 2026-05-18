# Create Label

## 创建标签

API：`POST /api/v1/labels/labels/`

入口：

```bash
python3 subskills/create/scripts/jms_create_label.py create-label ...
```

必填：

- `--name`
- `--value`

可选：

- `--color`
- `--comment`
- `--org-id <org-id>` 指定目标组织；只限定本次命令，不写 `.env`。
- `--org-name <name>` 指定目标组织名称；只限定本次命令，不写 `.env`。

组织：

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回组织选择冲突。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- `--org-name` 未匹配或多匹配时返回 `candidate_orgs`，不写 `.env`，不创建；从候选里选择准确组织后重试。
- dry-run 不写 `.env`，不 POST，不查重；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建标签。

Payload 规则：

- 只发送 `color/name/value/comment`。
- `name`、`value` 必填。
- `color` 未传不发送。
- `comment` 未传不发送。

执行规则：

- 无 `--confirm` 只预览 payload，不调用 client，不做在线查重。
- 有 `--confirm` 时，先在目标组织查重标签，再 POST 创建。
- 标签重复时阻塞创建，返回重复标签候选；用户确认后换 `name/value` 重试。

示例：

```bash
python3 subskills/create/scripts/jms_create_label.py create-label --name env --value prod
python3 subskills/create/scripts/jms_create_label.py create-label --name env --value prod --color '#689f7d' --comment 生产环境 --confirm
python3 subskills/create/scripts/jms_create_label.py create-label --org-id <org-id> --name env --value prod --confirm
python3 subskills/create/scripts/jms_create_label.py create-label --org-name Default --name env --value prod --confirm
```
