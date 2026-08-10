# 当前身份一次性 SSH 连接

## 适用场景

- 用户要通过 JumpServer SSH 登录已授权资产。
- 后续自动化任务需要当前 API 身份的一次性 SSH 连接参数。
- 用户问“连接这台机器”“通过 JumpServer 登录”“获取 SSH 连接信息”。

不适用于代替其他用户签发 token，也不用于查询用户有效访问范围或解释授权来源；这两类请求转到 Query。

## 正式入口

```bash
python3 subskills/access/scripts/jms_ssh_connect.py connect-info \
  --asset-address 10.1.1.1 \
  --account root \
  --confirm
```

需要在同一进程内直接执行远程命令时，使用 `jms_ssh_exec.py ssh-exec`；多协议连接与执行细节见 [KoKo 多协议连接与命令执行](koko-execution.md)。原 `jms_ssh_connect.py connect-info` 保持兼容。

资产选择器 `--asset-id`、`--asset-name`、`--asset-address` 必须且只能提供一个。`--account` 接受账号 ID、alias、名称或用户名；只有一个可用托管凭据账号时可省略。

## API 流程

1. 从 `/api/v1/perms/users/self/assets/` 查询当前身份可访问资产。
2. 精确选择唯一资产，并读取 `/api/v1/perms/users/self/assets/{asset_id}/`。
3. 从 `permed_protocols` 唯一选择 SSH，从 `permed_accounts` 唯一选择 `has_secret=true` 账号。
4. 从 `/api/v1/terminal/components/connect-methods/?os=linux` 选择 `ssh_guide`，不可用时再选择 `ssh_client`。
5. 未传 `--confirm` 时返回 `connection_token_confirmation_required`，此时不得 POST。
6. 确认后 POST `/api/v1/authentication/connection-token/`：

```json
{
  "asset": "<asset-id>",
  "account": "<account-alias>",
  "protocol": "ssh",
  "connect_method": "ssh_guide",
  "connect_options": {},
  "is_reusable": false
}
```

7. token 未激活时返回 `pending`，不请求 `client-url`。
8. token 激活后读取 `/api/v1/authentication/connection-token/{id}/client-url/`，解码 `jms://<base64-json>`。
9. 使用解码结果中的 Endpoint 主机和端口、`JMS-<token-id>` 用户名与一次性密码；不猜 KoKo 地址或端口。

## 安全约束

- `is_reusable` 必须为 `false`。
- 不返回原始 `jms_url`，因为它编码了连接凭据。
- 不把 token、密码写入 `.env`、文件、日志、命令行参数或跨回合缓存。
- 只有成功结果的 `result.connection.password` 允许明文；错误、pending、其他 token/secret 字段继续脱敏。
- 审批、Face Verify、ACL 拒绝或连接方式禁用时停止，不自动绕过。

## 生命周期

- 一次性含义是“一次 SSH 认证”，不是“一条远程命令”。
- 认证成功后，在同一个 SSH 会话中执行多条命令。
- SSH 会话关闭、超时或断开后，旧 token 不可重试；重新调用 `connect-info`。
- 不假设 SSH 进程可跨 agent 回合保持。

## 结果状态

| 状态 | 含义 | 下一步 |
|---|---|---|
| `connection_token_confirmation_required` | 已选中资产/账号/协议，尚未创建 token | 人工确认后追加 `--confirm` |
| `pending` | token 已创建但需审批或身份验证 | 完成对应流程后重新获取连接信息 |
| `ready` | 已得到一次性 SSH 参数 | 立即发起一次 SSH 认证并复用该会话 |

## 常见阻塞

| reason code | 检查项 |
|---|---|
| `connection_asset_selection_required` | 生效组织、资产重名、资产 ID/地址是否准确 |
| `connection_account_selection_required` | 是否存在唯一 `has_secret=true` 账号，是否需要 `--account` |
| `connection_protocol_unavailable` | 资产平台是否启用 SSH，当前授权是否包含 SSH |
| `connection_method_unavailable` | KoKo 状态、终端组件设置、连接方式 ACL |
| `connection_client_url_invalid` | JumpServer 版本、API 返回格式、Endpoint 配置 |
