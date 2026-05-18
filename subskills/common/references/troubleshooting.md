# 故障排查

## 快速概览

- 优先按“判断当前是首次全量还是后续轻量 -> 环境 -> 连通性 -> 组织 -> 端点验证”的顺序排查。
- 环境与入口问题看 [runtime.md](runtime.md)；资源与标准流程看 [assets.md](../../query/references/assets.md)；治理和调查能力看 [capabilities.md](../../query/references/capabilities.md)。
- 所有正式入口都在 `subskills/*/scripts/` 下，不使用 SDK 临时脚本路径；这些路径默认以 skill 根目录为当前工作目录。
- 遇到阻塞或参数错误时，优先看返回里的 `reason_code`、`user_message`、`action_hint`、`suggested_commands`，不要只盯顶层 `error`。

## 报错速查

| 报错文本 | 常见原因 | 优先动作 |
|---|---|---|
| `python3: command not found` / 无可用 Python 3 | 本机未安装 Python 3，或命令名不对 | 回到 [runtime.md](runtime.md) 的 Python 3 检查 |
| `No module named requests` / `Automatic dependency installation failed.` | 当前解释器环境缺依赖、pip 不可用、无网络，或自动安装失败 | 优先查看自动安装错误明细；必要时执行 `python3 -m pip install -r requirements.txt` |
| `.env` 缺失，或 `JMS_API_URL is required.` | 本地配置未初始化，或地址变量没配置 | 先执行 `python3 subskills/common/scripts/jms_common.py config-status --json` |
| `API credential is required.` / 认证凭据缺失 | 未提供完整的 AK/SK 或用户名密码 | 补齐 `JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` 或 `JMS_USERNAME/JMS_PASSWORD` 中至少一组 |
| 组织结果不符合预期 | 当前组织来自 `.env JMS_ORG_ID`，或本次命令显式传了组织 | 先执行 `python3 subskills/common/scripts/jms_common.py select-org --org-id <org-id> --confirm` 切换当前组织；只想临时覆盖时给业务命令传 `--org-id` |
| `Unknown capability` | `--capability` 拼写错误，或当前版本未实现 | 先执行 `... capabilities` 查看能力目录 |
| `无法解析 --filters 参数。` / `--filters 必须是 JSON 对象。` | `--filters` 不是合法 JSON 对象 | 优先改用显式参数或重复的 `--filter key=value`；若继续用 JSON，再检查引号、逗号和花括号 |
| `无法解析 --filter 参数。` | `--filter` 不是 `key=value` 形式 | 改成 `--filter name=Default` 这种写法 |
| `Asset permission API is unavailable or not yet confirmed ...` | 当前环境未开放权限接口，或权限不足 | 记录为接口待确认，先做替代性只读验证 |
| `object_does_not_exist` / `404` | ID 错误、组织错误或对象不存在 | 先重新 `list/get/resolve` |
| `python3: can't open file 'subskills/*/scripts/...': [Errno 2] No such file or directory` | 当前工作目录不在 skill 根目录，或调用方使用了错误的相对路径 | 先执行 `pwd` 确认 cwd；若不在 skill 根目录，先切换到 skill 根目录再重试，或改用仓库相对路径 |
| “帮我创建/更新/删除/解锁/授权” 被拒绝 | 该问题超出 common 范围 | 查看根级 [路由与安全边界](../../../references/routing-and-safety.md)，再进入对应子 Skill |

## 统计误判与执行上下文

- 登录、会话等正式入口返回 JSON 时，固定按 `ok -> result -> summary / records` 的顺序读取；不要猜顶层 `results` 或把临时打印结构当成正式契约。
- 只要返回里已有 `summary.total` 或同类总量字段，就优先引用它；`records` 主要用于明细、去重和逐条解释，不用于替代总量。
- 终端输出被截断、长 JSON 只显示部分 `records`、或日志查看器只露出前几百行时，不能据此估算总量。
- 如果命令报找不到 `subskills/*/scripts/...`，先排查 cwd 是否在 skill 根目录；这属于执行上下文问题，不要直接归因为“仓库路径写错”。

## 轻量失败后的升级动作

| 轻量校验失败点 | 升级动作 |
|---|---|
| `config-status --json` 显示 `complete=false` | 回到 [runtime.md](runtime.md) 补环境 |
| `ping` 失败 | 重新执行完整预检，确认 URL、认证凭据（AK/SK 或用户名密码）、TLS、组织 |
| `select-org` 返回候选组织但未确定 | 明确组织后再继续业务命令 |
| `inspect/analyze` 返回空结果 | 先检查时间范围，再检查对象过滤条件 |

## 最小排查流程

```text
判断当前是首次全量失败还是后续轻量失败
  -> 若为轻量失败，先升级到全量校验
  -> 检查 Python 3 与自动依赖安装结果
  -> 执行 config-status --json
  -> 检查 .env / shell 环境变量
  -> jms_common.py ping
  -> 选择组织 select-org
  -> endpoint-inventory / endpoint-verify
  -> 再进入对应 query / create 子 Skill
```

## 常见误用

| 误用 | 正确做法 |
|---|---|
| 默认仍手写 `--filters '{"key":"value"}'` | 优先改用显式参数；高级场景再用 `--filter key=value` |
| 手动改 `.env` 后直接执行业务命令 | 先执行 `config-status --json` 和 `ping` |
| 组织名称不精确 | 先用 `select-org --org-name <name>` 预览候选 |
| 不在 skill 根目录执行正式入口 | 先切换到 skill 根目录，或使用仓库相对路径 |
