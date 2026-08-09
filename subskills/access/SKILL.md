---
name: jumpserver-access
description: >
  JumpServer V4.10 current-identity access subskill. Use when users ask to connect through
  JumpServer, obtain one-time SSH connection information, connect to a MySQL/MariaDB database asset,
  or execute SQL through a database client terminal. This skill
  creates only current-identity, non-reusable tokens and requires explicit confirmation.
  Do not use for queries about what assets, nodes, accounts, or protocols a user can access;
  those belong to jumpserver-query. 中文触发词：通过 JumpServer 连接、登录这台机器、获取一次性
  SSH 连接信息、连接 MySQL/MariaDB、执行 SQL、执行 SHOW DATABASES、获取 connect token 或
  connection token、先连接再执行远程任务。资产访问范围和授权原因不属于本 Skill。
---

# Access

为当前 API 身份获取授权资产的一次性 SSH 连接信息，或通过 `db_client` 连接 MySQL/MariaDB 资产执行 SQL。SQL 原文直接交给 JumpServer，命令过滤、连接方式 ACL 和数据库账号权限由 JumpServer 侧决定。用户有效访问范围和授权原因都属于 Query；Access 不对外提供 `user-assets`、`user-nodes` 或 `user-asset-access`。

若本目录被独立注册为 Skill 根目录，使用 [agents/openai.yaml](agents/openai.yaml)，从本目录 cwd 执行 `python3 scripts/jms_ssh_connect.py connect-info ...` 或 `python3 scripts/jms_db_connect.py db-query ...`。Access 不依赖 Query，只复用 sibling Common 的认证、组织、API client 和脱敏运行时；Access 与 Query 不得互相导入或加载，因此完整仓库仍需保留。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 当前 API 身份、目标组织、唯一资产 ID/名称/地址、可选账号、显式确认 |
| 输出 | SSH 连接信息、数据库 SQL 输出或明确阻塞原因；数据库连接不返回 token 密码 |

## Entrypoints

| 场景 | 命令 |
|---|---|
| 当前身份一次性 SSH 信息 | `jms_ssh_connect.py connect-info --asset-id/--asset-name/--asset-address ... --confirm` |
| 当前身份 MySQL/MariaDB SQL 执行 | `jms_db_connect.py db-query --asset-id/--asset-name/--asset-address --sql 'SHOW DATABASES;' --confirm` |

SSH token 创建和使用前读取 [SSH 连接生命周期](references/ssh-connection.md)；MySQL/MariaDB SQL 执行读取 [数据库连接与 SQL 执行](references/database-connection.md)。

## Rules

| 条件 | 动作 |
|---|---|
| 用户显式指定组织 | 用 `--org-id` 或 `--org-name` 限定本次命令，不写 `.env` |
| `connect-info` 目标资产不唯一 | 阻塞，要求唯一资产 ID |
| 没有唯一 `has_secret=true` 账号 | 阻塞；多个账号时要求 `--account` |
| 没有 SSH 协议或允许的 SSH 连接方式 | 阻塞，不绕过 ACL |
| MySQL/MariaDB SQL 执行 | 从资产授权中选择 `mysql` 或 `mariadb`；两者同时存在时按资产平台自动匹配，仍无法区分才要求 `--protocol`；固定使用 `db_client` 和 `is_reusable=false`，连接主机和端口只取 `client-url.endpoint`；SQL 不在本地解析或限制 |
| SQL 权限或命令过滤 | 交给 JumpServer 连接方式 ACL、命令过滤和数据库账号权限；本入口不绕过服务端拒绝 |
| 未传 `--confirm` | 只返回 `connection_token_confirmation_required`，不得 POST |
| token 未激活 | 返回 `pending`，不得请求 `client-url` |
| MySQL/MariaDB token 与 SSH token | 分别使用选中的数据库协议/`db_client` 与 `ssh` 连接方式；不得交叉使用 |

## SSH Token 生命周期

- 一次性 token 只允许完成一次 SSH 认证，不等于只允许执行一条命令。
- 多条命令复用同一 SSH 会话；不要为每条命令重新连接。
- 会话关闭、超时或断开后丢弃旧 token，重新调用 `connect-info`。
- token 不写 `.env`、文件、日志或跨回合缓存；不返回原始 `jms_url`。
- 只有成功结果的 `result.connection.password` 可明文返回；其他密文字段、错误和预览继续脱敏。

## MySQL/MariaDB Token 生命周期

- `db-query` 为目标数据库资产创建一次性、不可复用的 `mysql` 或 `mariadb` + `db_client` token；省略 `--protocol` 时先从资产授权中选择，两者同时存在则按资产平台自动匹配；必须使用当前 API 身份和 `users/self` 资产。
- 认证用户名使用 `JMS-<client-token-id>`；连接主机和端口都直接取 `client-url` 的 `endpoint.host/endpoint.port`，不设置固定端口，也不提供本地覆盖参数。
- token 只用于本次数据库 SSH 认证；脚本在同一交互会话发送一条 SQL 后退出并丢弃凭据，不把 token、密码或原始 URL 写入文件、日志或结果。
- `db-query` 结果只返回 SQL 输出和非敏感连接元数据，不返回 token password。`connect-info` 生成的 SSH token 不能用于 MySQL/MariaDB CLI。

## 边界

| 不适用场景 | 处理 |
|---|---|
| 某用户能访问哪些资产、节点、账号或协议 | 转到 Query 的 `jms_access.py user-assets/user-nodes/user-asset-access` |
| 为什么能访问、命中哪条授权规则 | 转到 `jms_permissions.py` |
| 代替其他用户创建 connection token | 阻塞；`connect-info` 只使用 `users/self` |
| 任意业务对象创建、更新、删除 | 转到 create/update 边界 |
| 绕过 JumpServer 直接猜 KoKo 地址或端口 | 阻塞；只接受 `client-url` 结果 |
| 只想查询资产/账号/协议或授权原因 | 转到 Query；Access 只负责实际连接或数据库终端执行 |
| 要执行 SQL | 继续走 `db-query`；是否允许执行由 JumpServer 侧策略、ACL 和数据库权限决定 |

## 触发验收样例

应触发本 Skill：

- “通过 JumpServer 连接 10.1.1.1。”
- “先拿这台机器的一次性 SSH 信息，再执行部署。”
- “获取当前身份登录 prod-host 所需的一次性 SSH 参数。”
- “通过 JumpServer 连接 10.1.12.224，执行 `SHOW DATABASES;`。”
- “在这台 MySQL 或 MariaDB 上执行一条 `SELECT` 或更新语句。”
- “修改 MySQL 或 MariaDB 表结构或写入数据。”仍走 `db-query`；是否允许由 JumpServer 侧命令过滤、连接 ACL 和数据库账号权限决定。

不应触发本 Skill：

- “查 alice 在 Default 组织能访问哪些资产。”转到 Query 的有效访问入口。
- “为什么 alice 能访问这台机器？”转到权限解释。
- “查看 Linux 平台的 SSH 协议配置。”转到对象或平台配置查询。
- “创建一台主机资产。”转到 create。
- “查 alice 能访问哪些数据库资产。”转到 Query 的有效访问入口。

最近邻：出现“实际连接/登录/执行数据库 SQL”时使用 Access；出现“能访问什么”或“为什么能访问”时转到 Query。

## 成功标准

- 已确认请求需要当前身份的一次性 SSH，而不是用户有效访问结果。
- `connect-info` 精确选中一个资产、一个 SSH 协议和一个托管凭据账号。
- POST payload 固定 `is_reusable=false`，且只有显式 `--confirm` 才发送。
- ready 结果可直接用于一次 SSH 认证；pending/阻塞结果不泄露密码或 token value。
- `db-query` 已唯一选中数据库资产、MySQL/MariaDB 协议、`db_client` 和托管账号，使用 `is_reusable=false` token 将 SQL 原文交给 JumpServer；结果不包含 token password。

## Examples

```bash
python3 subskills/access/scripts/jms_ssh_connect.py connect-info --asset-address 10.1.1.1 --account root --confirm

python3 subskills/access/scripts/jms_db_connect.py db-query \
  --asset-address 10.1.12.224 \
  --sql 'SHOW DATABASES;' \
  --confirm
```
