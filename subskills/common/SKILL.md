---
name: jumpserver-common
description: JumpServer shared runtime helper skill for config checks, preflight, connectivity, organization selection, and endpoint verification. Use before access/query/create/update when runtime state is unknown.
---

# Common

common 子 Skill 只负责配置、预检、组织选择、连通性和端点验证；不处理业务查询或业务写入。

若本目录被独立注册为 Skill 根目录，使用 [agents/openai.yaml](agents/openai.yaml)，并从本目录 cwd 执行 `python3 scripts/jms_common.py ...`；完整仓库要求见 [子 Skill 独立注册](../../references/subskill-registration.md)。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | JumpServer 地址、认证信息、组织选择、端点路径、连通性检查需求 |
| 输出 | 配置状态、当前组织、候选组织、连通性结果、端点验证结果 |

## 何时先走 Common

| 条件 | 动作 |
|---|---|
| 配置不完整或不确定 | `config-status --json` |
| 需要写入本地运行时配置 | `config-write --confirm` |
| 需要验证 JumpServer 可访问 | `ping` |
| 组织不明确或需要切换 | `select-org`，确认后加 `--confirm` |
| 不确定接口是否存在 | `endpoint-verify` 或 `endpoint-inventory` |

## 命令速查

| 命令 | 作用 | 写入 |
|---|---|---|
| `config-status` | 查看配置和非密摘要 | 否 |
| `config-write` | 写 `.env` 配置；`--recover-invalid-env` 可备份并恢复损坏文件 | 仅 `--confirm` |
| `ping` | 验证认证和连通性 | 否 |
| `select-org` | 选择当前组织 | 仅 `--confirm` |
| `endpoint-inventory` | 查看端点清单 | 否 |
| `endpoint-verify` | 验证端点方法 | 否 |

## 写入边界

| 允许 | 禁止 |
|---|---|
| `config-write --confirm` 写本地 `.env` 和 `.env.lock`；恢复时写 `.env.recovery-*.bak` / `.env.recovery-*.stage` | 写 JumpServer 业务对象 |
| `select-org --confirm` 写 `.env JMS_ORG_ID` | 创建、更新、删除业务数据 |

## 示例

```bash
python3 subskills/common/scripts/jms_common.py config-status --json
python3 subskills/common/scripts/jms_common.py ping
python3 subskills/common/scripts/jms_common.py select-org --org-name Default
python3 subskills/common/scripts/jms_common.py endpoint-verify --path /api/v1/settings/setting/ --method GET
```

## 成功标准

- 已返回 `reason_code`、`user_message`、`action_hint` 或明确结果。
- 多组织且无法自动确定时，返回 `candidate_orgs` 后阻塞。
- 写 `.env` 前必须看到 `--confirm`。
- `--recover-invalid-env --confirm` 只处理无法解析的普通 `.env`，且要求完整新配置。
