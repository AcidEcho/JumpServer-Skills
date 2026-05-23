# Create Node

## 创建节点

### API

`POST /api/v1/assets/nodes/`

### 入口

```bash
python3 subskills/create/scripts/jms_create_node.py create-node ...
```

### 必填

- `--full-value`
- `--value`

### 可选

- `--org-id <org-id>` 指定目标组织；只限定本次命令，不写 `.env`。
- `--org-name <name>` 指定目标组织名称；只限定本次命令，不写 `.env`。

### 组织规则

- 未传组织时使用 `.env JMS_ORG_ID` 当前组织。
- `--org-id` 与 `--org-name` 不能同时传；同时传会返回组织选择冲突。
- `--org-name --confirm` 会查询当前 AK/SK 可访问组织；唯一匹配后按该组织创建，但不写 `.env JMS_ORG_ID`。
- `--org-name` 未匹配或多匹配时返回 `candidate_orgs`，不写 `.env`，不创建；从候选里选择准确组织后重试。
- dry-run 不写 `.env`，不 POST；传 `--org-name` 时只预览组织名。
- 全局组织禁止；不能在 `00000000-0000-0000-0000-000000000000` 下创建节点。

### Payload 规则

- 只发送 `org_id/full_value/value`。
- `org_id` 来自显式 `--org-id`、显式 `--org-name` 解析结果，或未传组织时的 `.env JMS_ORG_ID`。
- `full_value` 是节点完整路径，例如 `/Default/Linux/新节点2`。
- `value` 是节点名称，例如 `新节点2`。

### 执行规则

- 无 `--confirm` 只预览 payload，不调用 client，不 POST。
- 有 `--confirm` 才 POST 创建节点。
- 创建节点不写 `.env`。

### 示例

```bash
python3 subskills/create/scripts/jms_create_node.py create-node --org-name Default --full-value /Default/Linux/新节点2 --value 新节点2 --confirm
```
