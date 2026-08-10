# KoKo 多协议连接与命令执行

## 适用范围

新增入口覆盖当前 API 身份的三类动作：

| 场景 | 正式入口 |
|---|---|
| 获取 SSH 或数据库 KoKo 终端的一次性连接信息 | `jms_connect.py connect-info` |
| 在一个一次性 SSH 认证会话中顺序执行远程命令 | `jms_ssh_exec.py ssh-exec` |
| 通过 KoKo SSH 数据库终端执行 PostgreSQL、Redis、MongoDB、SQL Server、Oracle 或 ClickHouse 命令 | `jms_db_exec.py db-exec` |

原 `jms_ssh_connect.py connect-info` 和 MySQL/MariaDB `jms_db_connect.py db-query` 保持兼容，不由新增入口替换。

## 共同解析流程

1. 只查询 `/api/v1/perms/users/self/assets/`，不代替其他用户签发 token。
2. 资产 ID、名称或地址必须精确且唯一；账号必须唯一且 `has_secret=true`。
3. 请求协议必须精确存在于资产 `permed_protocols`。`serversql`、`server-sql`、`mssql` 只作为用户输入别名归一化为资产协议 `sqlserver`，不会修改或猜测资产协议。
4. SSH 使用资产允许的 `ssh_guide` 或 `ssh_client`；PostgreSQL、Redis、MongoDB、SQL Server、Oracle 固定使用所选协议下的 `db_client`；ClickHouse 固定使用所选协议下的 `web_cli`。
5. 未传 `--confirm` 时只返回确认信息，不创建 token、不连接 KoKo、不执行命令。
6. token POST 固定 `is_reusable=false`。token 未激活时返回 `pending`，不读取 `client-url`。
7. token ID、一次性密码和原始 `jms_url` 只在当前进程内存中使用，不写 `.env`、文件、日志或跨回合缓存。

## KoKo SSH 端点

数据库连接不使用 Magnus 固定端口，也不接受本地主机或端口覆盖。正式入口调用：

```text
GET /api/v1/terminal/endpoints/smart/?asset_id=<asset-id>&protocol=ssh
```

只使用响应中的 `host` 和 `ssh_port`，以 `JMS-<client-token-id>` 和本次一次性密码建立 Paramiko SSH 会话。Smart Endpoint 缺少有效主机或端口时，在执行前阻塞。

SSH `connect-info` 和 `ssh-exec` 使用 SSH token 的 `client-url` Endpoint；数据库 `connect-info` 和 `db-exec` 始终使用上述 Smart Endpoint 的 KoKo SSH 端点。

## SSH 执行

```bash
python3 subskills/access/scripts/jms_ssh_exec.py ssh-exec \
  --asset-name prod-host \
  --command hostname \
  --command 'id -u' \
  --confirm
```

`--command` 可重复传入。脚本只认证一次，在同一个 Paramiko `SSHClient` 中按顺序调用远程 `exec_command`，返回每条命令的 stdout、stderr 和退出码；最后关闭连接并丢弃凭据。命令不会交给本地 shell。远程写入影响仍由命令本身、目标账号权限、JumpServer ACL 和命令过滤规则决定。

## 数据库协议

```bash
python3 subskills/access/scripts/jms_db_exec.py db-exec \
  --asset-name demo-postgresql \
  --protocol postgresql \
  --command 'SELECT version();' \
  --require-output \
  --confirm
```

所有数据库协议都通过 KoKo SSH `host/ssh_port` 进入交互终端，不安装或调用本地数据库驱动。多次 `--command` 复用一个 SSH 交互会话。

| 协议 | 命令封装 | 会话退出 |
|---|---|---|
| PostgreSQL | 原命令后发送换行 | `\q` |
| Redis | 原命令后发送换行 | `quit` |
| MongoDB | 原命令后发送换行 | `quit()` |
| SQL Server | 批次末尾没有独立 `GO` 时自动追加 | `EXIT` |
| Oracle | 缺少 `;` 或 `/` 终止符时追加 `;` | `exit` |
| ClickHouse | 原命令后发送换行 | `exit` |

## 输出与阻塞

- `jms_connect.py connect-info` 的 ready 结果仅允许 `result.connection.password` 明文用于当次连接；其他密文路径仍脱敏。
- `ssh-exec` 和 `db-exec` 不返回一次性密码、token value 或原始 URL，只返回执行结果及非敏感连接元数据。
- 资产、账号、协议或组织不唯一时阻塞，不猜 ID。
- PostgreSQL/Redis/MongoDB/SQL Server/Oracle 缺少 `db_client`，或 ClickHouse 同时缺少 API 返回的 `db_client`/`web_cli` 时停止。Smart Endpoint 无效、审批未完成、ACL 拒绝或终端连接失败时也停止，不使用固定端口或其他协议绕过。
- `--require-output` 适合 `PING`、版本查询等连接探针；普通无结果集 SQL 不要使用，避免把成功的 DDL/DML 误判为失败。
