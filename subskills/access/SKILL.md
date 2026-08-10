---
name: jumpserver-access
description: >
  JumpServer V4.10 current-identity access subskill. Use when users ask to connect through
  JumpServer, obtain one-time SSH or database connection information, execute commands in one SSH
  session, connect to a MySQL/MariaDB database asset, or execute commands through PostgreSQL,
  Redis, MongoDB, SQL Server, Oracle, or ClickHouse terminals. This skill
  creates only current-identity, non-reusable tokens and requires explicit confirmation.
  Do not use for queries about what assets, nodes, accounts, or protocols a user can access;
  those belong to jumpserver-query. 中文触发词：通过 JumpServer 连接、登录这台机器、获取一次性
  SSH 连接信息、SSH 执行命令、连接数据库、执行 SQL、执行 SHOW DATABASES、Redis PING、
  PostgreSQL/MongoDB/SQL Server/Oracle/ClickHouse、获取 connect token 或 connection token、
  先连接再执行远程任务。资产访问范围和授权原因不属于本 Skill。
---

# Access

为当前 API 身份获取授权资产的一次性 SSH/数据库连接信息，在同一个一次性 SSH 会话中执行远程命令，或通过 KoKo SSH 数据库终端执行数据库命令。命令过滤、连接方式 ACL 和目标账号权限由 JumpServer 侧决定。用户有效访问范围和授权原因都属于 Query；Access 不对外提供 `user-assets`、`user-nodes` 或 `user-asset-access`。

若本目录被独立注册为 Skill 根目录，使用 [agents/openai.yaml](agents/openai.yaml)，从本目录 cwd 执行 `python3 scripts/<entry>.py ...`。Access 不依赖 Query，只复用 sibling Common 的认证、组织、API client 和脱敏运行时；Access 与 Query 不得互相导入或加载，因此完整仓库仍需保留。

## 输入 / 输出

| 项 | 内容 |
|---|---|
| 输入 | 当前 API 身份、目标组织、唯一资产 ID/名称/地址、可选账号、显式确认 |
| 输出 | 一次性连接信息、SSH/数据库命令结果或明确阻塞原因；执行入口不返回 token 密码 |

## Entrypoints

| 场景 | 命令 |
|---|---|
| 当前身份一次性 SSH 信息 | `jms_ssh_connect.py connect-info --asset-id/--asset-name/--asset-address ... --confirm` |
| 当前身份 MySQL/MariaDB SQL 执行 | `jms_db_connect.py db-query --asset-id/--asset-name/--asset-address --sql 'SHOW DATABASES;' --confirm` |
| 当前身份多协议一次性连接信息 | `jms_connect.py connect-info --asset-id/--asset-name/--asset-address --protocol <protocol> --confirm` |
| 当前身份 SSH 命令执行 | `jms_ssh_exec.py ssh-exec --asset-id/--asset-name/--asset-address --command <command> --confirm` |
| PostgreSQL/Redis/MongoDB/SQL Server/Oracle/ClickHouse 命令执行 | `jms_db_exec.py db-exec --asset-id/--asset-name/--asset-address --protocol <protocol> --command <command> --confirm` |

SSH token 创建和使用前读取 [SSH 连接生命周期](references/ssh-connection.md)；MySQL/MariaDB SQL 执行读取 [数据库连接与 SQL 执行](references/database-connection.md)；新增多协议连接和执行读取 [KoKo 多协议连接与命令执行](references/koko-execution.md)。

## Rules

| 条件 | 动作 |
|---|---|
| 用户显式指定组织 | 用 `--org-id` 或 `--org-name` 限定本次命令，不写 `.env` |
| `connect-info` 目标资产不唯一 | 阻塞，要求唯一资产 ID |
| 没有唯一 `has_secret=true` 账号 | 阻塞；多个账号时要求 `--account` |
| 没有 SSH 协议或允许的 SSH 连接方式 | 阻塞，不绕过 ACL |
| MySQL/MariaDB SQL 执行 | 从资产授权中选择 `mysql` 或 `mariadb`；两者同时存在时按资产平台自动匹配，仍无法区分才要求 `--protocol`；固定使用 `db_client` 和 `is_reusable=false`；数据库 `client-url` 只取 token ID/value，连接主机和端口从 Smart Endpoint 动态读取 `host/ssh_port`；SQL 不在本地解析或限制 |
| SSH 命令执行 | `jms_ssh_exec.py` 只创建一个 SSH token、认证一次，并在同一个 Paramiko 客户端按顺序执行所有 `--command`；不调用本地 shell |
| 新增数据库协议执行 | `jms_db_exec.py` 只接受 PostgreSQL、Redis、MongoDB、SQL Server、Oracle、ClickHouse；前五种协议固定 `db_client`，ClickHouse 固定 `web_cli`；token 固定 `is_reusable=false`，所有协议统一走 Smart Endpoint 的 KoKo SSH `host/ssh_port` |
| 连接探针 | `db-exec --require-output` 要求返回可验证输出；普通无结果集写入不使用该参数 |
| SQL Server 输入别名 | `serversql`、`server-sql`、`mssql` 归一化为资产协议 `sqlserver`；资产授权必须精确存在 `sqlserver` |
| SQL 权限或命令过滤 | 交给 JumpServer 连接方式 ACL、命令过滤和数据库账号权限；本入口不绕过服务端拒绝 |
| 未传 `--confirm` | 只返回 `connection_token_confirmation_required`，不得 POST |
| token 未激活 | 返回 `pending`，不得请求 `client-url` |
| MySQL/MariaDB token 与 SSH token | token 协议和连接方式不同，不得交叉使用；SSH、MySQL、MariaDB 的实际连接传输统一使用 Smart Endpoint 返回的 KoKo SSH `host/ssh_port` |

## SSH Token 生命周期

- 一次性 token 只允许完成一次 SSH 认证，不等于只允许执行一条命令。
- 多条命令复用同一 SSH 会话；不要为每条命令重新连接。
- 会话关闭、超时或断开后丢弃旧 token，重新调用 `connect-info`。
- token 不写 `.env`、文件、日志或跨回合缓存；不返回原始 `jms_url`。
- 只有成功结果的 `result.connection.password` 可明文返回；其他密文字段、错误和预览继续脱敏。
- `ssh-exec` 直接在同一进程中创建 token、连接、执行、关闭并丢弃凭据，不跨进程传递一次性密码。

## MySQL/MariaDB Token 生命周期

- `db-query` 为目标数据库资产创建一次性、不可复用的 `mysql` 或 `mariadb` + `db_client` token；省略 `--protocol` 时先从资产授权中选择，两者同时存在则按资产平台自动匹配；必须使用当前 API 身份和 `users/self` 资产。
- 认证用户名使用 `JMS-<client-token-id>`；token ID/value 来自数据库 `client-url`。连接主机和端口从 `/api/v1/terminal/endpoints/smart/?asset_id=...&protocol=ssh` 动态读取 `host/ssh_port`，不使用数据库协议对应的 Magnus 端口，不设置固定端口，也不提供本地覆盖参数。
- token 只用于本次通过 KoKo SSH 服务建立的数据库会话认证；脚本在同一交互会话发送一条 SQL 后退出并丢弃凭据，不把 token、密码或原始 URL 写入文件、日志或结果。
- `db-query` 结果只返回 SQL 输出和非敏感连接元数据，不返回 token password。`connect-info` 生成的 SSH token 不能用于 MySQL/MariaDB CLI。

## 边界

| 不适用场景 | 处理 |
|---|---|
| 某用户能访问哪些资产、节点、账号或协议 | 转到 Query 的 `jms_access.py user-assets/user-nodes/user-asset-access` |
| 为什么能访问、命中哪条授权规则 | 转到 `jms_permissions.py` |
| 代替其他用户创建 connection token | 阻塞；`connect-info` 只使用 `users/self` |
| 任意业务对象创建、更新、删除 | 转到 create/update 边界 |
| 绕过 JumpServer 直接猜 KoKo 地址或端口 | 阻塞；只接受 JumpServer Smart Endpoint API 返回的 SSH `host/ssh_port` |
| 只想查询资产/账号/协议或授权原因 | 转到 Query；Access 只负责实际连接或数据库终端执行 |
| 要执行 SQL | 继续走 `db-query`；是否允许执行由 JumpServer 侧策略、ACL 和数据库权限决定 |
| 要在 PostgreSQL、Redis、MongoDB、SQL Server、Oracle 或 ClickHouse 执行命令 | 走 `jms_db_exec.py db-exec`；不回退到 MySQL/MariaDB 入口 |

## 触发验收样例

应触发本 Skill：

- “通过 JumpServer 连接 10.1.1.1。”
- “先拿这台机器的一次性 SSH 信息，再执行部署。”
- “通过 JumpServer 在这台机器上执行 `hostname` 和 `id -u`。”
- “获取 PostgreSQL 的一次性 KoKo 连接信息。”
- “在 Redis 上执行 `PING`，或在 MongoDB 上执行 ping 命令。”
- “连接 serversql、Oracle 或 ClickHouse 并执行版本查询。”
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
- “列出所有 PostgreSQL 资产。”转到 Query 的对象查询入口。
- “为什么这个 Oracle 资产能被 alice 访问？”转到权限解释。

最近邻：出现“实际连接/登录/执行数据库 SQL”时使用 Access；出现“能访问什么”或“为什么能访问”时转到 Query。

## 成功标准

- 已确认请求需要当前身份的一次性 SSH，而不是用户有效访问结果。
- `connect-info` 精确选中一个资产、一个 SSH 协议和一个托管凭据账号。
- POST payload 固定 `is_reusable=false`，且只有显式 `--confirm` 才发送。
- ready 结果可直接用于一次 SSH 认证；pending/阻塞结果不泄露密码或 token value。
- `db-query` 已唯一选中数据库资产、MySQL/MariaDB 协议、`db_client` 和托管账号，使用 `is_reusable=false` token 将 SQL 原文交给 JumpServer；结果不包含 token password。
- `ssh-exec` 只认证一次并复用同一客户端；`db-exec` 按协议选择受控连接方式，并只走 Smart Endpoint 的 KoKo SSH `host/ssh_port`；两者执行完成后关闭连接且结果不包含一次性密码。

## Examples

```bash
python3 subskills/access/scripts/jms_ssh_connect.py connect-info --asset-address 10.1.1.1 --account root --confirm

python3 subskills/access/scripts/jms_db_connect.py db-query \
  --asset-address 10.1.12.224 \
  --sql 'SHOW DATABASES;' \
  --confirm

python3 subskills/access/scripts/jms_ssh_exec.py ssh-exec \
  --asset-name prod-host --command hostname --command 'id -u' --confirm

python3 subskills/access/scripts/jms_db_exec.py db-exec \
  --asset-name demo-postgresql --protocol postgresql \
  --command 'SELECT version();' --confirm
```
