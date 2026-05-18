---
name: jumpserver-common
description: JumpServer shared runtime helper skill for configuration check, preflight, connectivity, organization selection, and endpoint verification. Use before any query/create/update skill when runtime state is unknown.
---

# Common

公共入口：

```bash
python3 subskills/common/scripts/jms_common.py <command> ...
```

支持：

- `config-status`
- `config-write`
- `ping`
- `select-org`
- `endpoint-inventory`
- `endpoint-verify`

规则：

- 所有业务 skill 执行前，如配置、组织、连通性不确定，先走这里。
- `select-org` 不带 `--confirm` 只预览；带 `--confirm` 写入 `.env JMS_ORG_ID`。
- 这里不放对象、访问、权限、审计、报表、巡检等业务查询；这些都在 `subskills/query/`。
- 写 `.env` 只允许 `config-write --confirm` 和 `select-org --confirm`。
- 切组织只允许 `select-org --confirm`。
- 多组织且无法自动确定时，返回 `candidate_orgs` 后阻塞。

示例：

```bash
python3 subskills/common/scripts/jms_common.py config-status --json
python3 subskills/common/scripts/jms_common.py ping
python3 subskills/common/scripts/jms_common.py select-org --org-name Default
python3 subskills/common/scripts/jms_common.py endpoint-verify --path /api/v1/settings/setting/ --method GET
```
