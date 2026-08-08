---
name: jumpserver-access
description: >
  JumpServer V4.10 current-identity SSH connect-info subskill. Use only when users ask to
  connect, SSH, or log in through JumpServer, obtain the current API identity's one-time
  SSH connection information, create a non-reusable connection/connect token, obtain an
  SSH command, or prepare an authorized remote task. Do not use for
  queries about what assets, nodes, accounts, or protocols a user can access; those
  belong to jumpserver-query. 中文触发词：通过 JumpServer 连接、登录这台机器、获取一次性
  SSH 连接信息、获取 connect token 或 connection token、先连接再部署。
---

# Access

为当前 API 身份获取授权资产的一次性 SSH 连接信息。用户有效访问范围和授权原因都属于 Query；Access 不对外提供 `user-assets`、`user-nodes` 或 `user-asset-access`。

若本目录被独立注册为 Skill 根目录，使用 [agents/openai.yaml](agents/openai.yaml)，从本目录 cwd 执行 `python3 scripts/jms_ssh_connect.py connect-info ...`。Access 不依赖 Query，只复用 sibling Common 的认证、组织、API client 和脱敏运行时；Access 与 Query 不得互相导入或加载，因此完整仓库仍需保留。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 当前 API 身份、目标组织、唯一资产 ID/名称/地址、可选账号、显式确认 |
| 输出 | 一次性 SSH 主机、端口、用户名、密码和命令，或明确阻塞原因 |

## Entrypoints

| 场景 | 命令 |
|---|---|
| 当前身份一次性 SSH 信息 | `jms_ssh_connect.py connect-info --asset-id/--asset-name/--asset-address ... --confirm` |

SSH token 创建和使用前必须读取 [SSH 连接生命周期](references/ssh-connection.md)。

## Rules

| 条件 | 动作 |
|---|---|
| 用户显式指定组织 | 用 `--org-id` 或 `--org-name` 限定本次命令，不写 `.env` |
| `connect-info` 目标资产不唯一 | 阻塞，要求唯一资产 ID |
| 没有唯一 `has_secret=true` 账号 | 阻塞；多个账号时要求 `--account` |
| 没有 SSH 协议或允许的 SSH 连接方式 | 阻塞，不绕过 ACL |
| 未传 `--confirm` | 只返回 `connection_token_confirmation_required`，不得 POST |
| token 未激活 | 返回 `pending`，不得请求 `client-url` |

## SSH Token 生命周期

- 一次性 token 只允许完成一次 SSH 认证，不等于只允许执行一条命令。
- 多条命令复用同一 SSH 会话；不要为每条命令重新连接。
- 会话关闭、超时或断开后丢弃旧 token，重新调用 `connect-info`。
- token 不写 `.env`、文件、日志或跨回合缓存；不返回原始 `jms_url`。
- 只有成功结果的 `result.connection.password` 可明文返回；其他密文字段、错误和预览继续脱敏。

## 边界

| 不适用场景 | 处理 |
|---|---|
| 某用户能访问哪些资产、节点、账号或协议 | 转到 Query 的 `jms_access.py user-assets/user-nodes/user-asset-access` |
| 为什么能访问、命中哪条授权规则 | 转到 `jms_permissions.py` |
| 代替其他用户创建 connection token | 阻塞；`connect-info` 只使用 `users/self` |
| 任意业务对象创建、更新、删除 | 转到 create/update 边界 |
| 绕过 JumpServer 直接猜 KoKo 地址或端口 | 阻塞；只接受 `client-url` 结果 |

## 触发验收样例

应触发本 Skill：

- “通过 JumpServer 连接 10.1.1.1。”
- “先拿这台机器的一次性 SSH 信息，再执行部署。”
- “获取当前身份登录 prod-host 所需的一次性 SSH 参数。”

不应触发本 Skill：

- “查 alice 在 Default 组织能访问哪些资产。”转到 Query 的有效访问入口。
- “为什么 alice 能访问这台机器？”转到权限解释。
- “查看 Linux 平台的 SSH 协议配置。”转到对象或平台配置查询。
- “创建一台主机资产。”转到 create。

最近邻：出现“连接、登录、一次性 SSH 信息”时使用 Access；出现“能访问什么”或“为什么能访问”时转到 Query。

## 成功标准

- 已确认请求需要当前身份的一次性 SSH，而不是用户有效访问结果。
- `connect-info` 精确选中一个资产、一个 SSH 协议和一个托管凭据账号。
- POST payload 固定 `is_reusable=false`，且只有显式 `--confirm` 才发送。
- ready 结果可直接用于一次 SSH 认证；pending/阻塞结果不泄露密码或 token value。

## Examples

```bash
python3 subskills/access/scripts/jms_ssh_connect.py connect-info --asset-address 10.1.1.1 --account root --confirm
```
