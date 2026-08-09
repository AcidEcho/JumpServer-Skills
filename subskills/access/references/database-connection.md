# MySQL/MariaDB 数据库连接与 SQL 执行

## 适用场景

- 用户要通过 JumpServer 连接已授权 MySQL 或 MariaDB 资产。
- 用户要通过数据库终端执行 SQL；语句类型、数量和关键字不在本地限制。

## 正式入口

```bash
python3 subskills/access/scripts/jms_db_connect.py db-query \
  --asset-address 10.1.12.224 \
  --sql 'SHOW DATABASES;' \
  --confirm
```

资产选择器 `--asset-id`、`--asset-name`、`--asset-address` 必须且只能提供一个。`--account` 接受账号 ID、alias、名称或用户名；只有一个可用托管凭据账号时可省略。

## API 与会话流程

1. 从 `/api/v1/perms/users/self/assets/` 查询当前身份可访问资产。
2. 精确选择目标数据库资产，读取其 `permed_protocols` 和 `permed_accounts`。
3. 从资产授权协议中选择 `mysql` 或 `mariadb`；两者同时存在时按资产平台名称/slug 自动匹配，平台信息仍无法区分时才要求通过 `--protocol` 明确选择。
4. 从 `/api/v1/terminal/components/connect-methods/?os=linux` 选择所选数据库协议下的 `db_client`。
5. 未传 `--confirm` 时只返回确认提示，不创建 token。
6. 确认后 POST `/api/v1/authentication/connection-token/`，固定使用：

```json
{
  "asset": "<asset-id>",
  "account": "<account-alias>",
  "protocol": "<mysql-or-mariadb>",
  "connect_method": "db_client",
  "connect_options": {},
  "is_reusable": false
}
```

7. 读取并解码 `client-url`，得到数据库连接 token；不把原始 `jms_url` 写入文件或输出。
8. 与 `jms_ssh_connect.py` 一致，直接使用 `client-url` 解码结果中的 `endpoint.host/endpoint.port` 建立连接；不写死端口，也不提供本地自定义主机/端口参数。
9. 在同一交互会话发送 `--sql` 原文，读取输出后发送 `\\q` 关闭会话。

内部连接形态为 `JMS-<client-token-id>@<endpoint-host>:<endpoint-port>`，主机、端口、token ID 和密码都来自本次 `client-url`。脚本只在内存中使用密码，不在 JSON 结果中回显；SSH `connect-info` token 不能替代数据库 token。

## 安全边界

- 只使用当前 API 身份的 `users/self` 资产，不代替其他用户签发 token。
- token 固定 `is_reusable=false`，不会持久化 token、密码或原始 URL。
- 不在本地解析、改写或限制 SQL；JumpServer 连接方式 ACL、命令过滤规则和数据库账号权限是唯一 SQL 阻断来源。
- `--confirm` 是创建 token 和执行查询的必要确认门槛。
- 账号、资产、组织或协议不唯一时先阻塞，不猜 ID。
- SQL 输出不返回 token password；错误和 pending 输出继续脱敏。

## 常见阻塞

| reason code | 检查项 |
|---|---|
| `database_connection_asset_selection_required` | 组织、资产名称/地址是否唯一 |
| `database_connection_account_selection_required` | 是否存在唯一 `has_secret=true` 账号 |
| `database_connection_protocol_unavailable` | 资产是否启用 MySQL/MariaDB 协议，当前用户是否有权限 |
| `database_connection_protocol_selection_required` | 资产同时启用 MySQL 和 MariaDB，且平台信息无法区分，需通过 `--protocol` 明确选择 |
| `database_connection_method_unavailable` | Magnus、所选数据库协议的 `db_client` 和连接方式 ACL |
| `database_connection_failed` | db_client SSH 主机/端口、Magnus 状态和网络 |

## 生命周期

- 一次 token 只允许一次数据库 SSH 认证；本入口按 `--sql` 原文发送，不在本地限制语句数量。
- 会话关闭、超时或断开后丢弃旧 token，重新调用 `db-query`。
- 数据库 token 与 `connect-info` 的 SSH token 协议、连接方式和目标终端不同，不复用、不互换。
