# 审计与调查

## 快速概览

- 主入口：`python3 scripts/jumpserver_api/jms_query.py <subcommand> ...`
- 常用子命令：`audit-list`、`audit-get`、`terminal-sessions`、`job-list`、`command-storage-hint`、`audit-analyze`、`capabilities`。
- 页面型查询优先使用显式参数；低频页面字段再用 `--filter key=value`。
- `audit-list` 和 `terminal-sessions` 未显式传 `limit/offset` 时会按当前时间窗拉全量；传了分页参数就按分页结果返回。
- 查询型接口未显式给时间窗时默认最近 7 天；`--days` 只是输入快捷方式，不是最终下发给服务端的查询主参数。
- 命令审计在多 `command storage` 环境下，普通查询优先沿用默认 storage；报告或汇总分析场景可显式传 `--command-storage-scope all` 汇总全部可访问 storage。

## 页面同款直接查询

| 场景 | 推荐入口 | 当前显式参数 | 说明 |
|---|---|---|---|
| 操作日志 | `audit-list --audit-type operate` | `--search --user --action --resource-type` | `--search` 是页面搜索框；`--user` 会解析为页面显示值 `name(username)` |
| 登录日志 | `audit-list --audit-type login` | `--search --username --ip --type --city --mfa --status` | `--username` 下发页面精确字段；`type` 只支持 `W/T/U` |
| 改密日志 | `audit-list --audit-type password_change` | `--search --user --change-by --remote-addr` | `--user` 与 `--change-by` 都会解析为 `name(username)` |
| 作业日志 | `audit-list --audit-type jobs` | `--search --creator-name --material` | `--creator-name` 解析后下发创建者显示名 |
| 会话记录页面 | `audit-list --audit-type terminal-session` / `terminal-sessions` | `--search --user --account --asset --protocol --login-from --remote-addr --asset-id --order` | `terminal-sessions` 继续保留 `--view online/history` |
| 审计侧会话 | `audit-list --audit-type session` | `--search --user --account --asset --protocol --login-from --remote-addr --asset-id --order` | 适合审计侧会话口径；需要页面同款在线/历史视图时优先 `terminal-sessions` |
| 命令记录页面 | `audit-list --audit-type command` | `--search --command-storage-id --command-storage-scope --asset-id --order` | 这一轮只显式化已确认页面字段；低频字段继续走 `--filter` |
| 文件传输日志 | `audit-list --audit-type ftp` | 时间、分页、`--search` | 页面型显式参数只保留已确认字段 |
| 作业列表 | `job-list` | `--search --name --limit --offset` | 对应 `/api/v1/audits/jobs/` 页面 |

补充规则：

- 用户类字段优先接受 `username`、`name`、`name(username)`，唯一匹配后再转换成页面需要的显示值。
- 账号类字段会转换成 `name(username)`；资产类字段会转换成 `name(ip)`。
- `--search` 可与精确字段同时存在，最终按服务端 AND 语义组合。
- 页面型命令不要把 `audit-list --audit-type login --user`、`terminal-sessions --source-ip`、泛化 `--keyword`、泛化 `--direction` 当成首选写法。

## 查询型时间语义

- 查询型接口中的 `--days` 会先换算成本地时间窗，再统一生成 `date_from/date_to` 请求参数；最终请求不再携带 `days`。
- 显式传了 `--date-from/--date-to` 时，以显式时间窗为准。
- `date_from=YYYY-MM-DD` 会补成本地当天 `00:00:00.000`。
- `date_to=YYYY-MM-DD` 会补成本地当天 `23:59:59.999`。
- 无时区字符串先按 skill 运行环境时区解释，再统一序列化为页面同款 UTC `...Z`。
- 报表和 dashboard 不在这套规则里，仍保留原生 `days`。

## `audit-analyze --capability` 适用场景

| 能力 | 适用问题 |
|---|---|
| `command-record-query` | 按用户 / 资产 / 命令关键字排查命令 |
| `high-risk-command-audit` | 排查高危命令、拒绝命令 |
| `session-record-query` | 查会话明细、协议、状态 |
| `file-transfer-log-query` | 查文件上传 / 下载记录 |
| `abnormal-hours-login-query` | 查异常时间段登录 |
| `abnormal-source-ip-login-query` | 查异常来源 IP 登录 |
| `failed-login-statistics` | 统计失败登录排行 |
| `privileged-account-usage-audit` | 审计特权账号使用情况 |
| `session-behavior-statistics` | 汇总会话行为统计 |
| `frequent-operation-user-ranking` | 统计高频操作用户排行 |
| `suspicious-operation-summary` | 跨命令、登录、会话、传输汇总可疑行为 |
| `user-session-analysis` / `asset-session-analysis` | 从用户或资产维度分析会话行为 |

某用户某天连接过哪些机器：

- 先解析用户，再优先 `audit-analyze --capability session-record-query`
- 若用户已经被解析成 UUID，固定传 `filters.user_id`；`filters.user` 只保留显示名或用户名文本
- 返回时区分 `session_count` 与去重后的 `assets`
- 不要先用 `audit-list --audit-type session` 作为“是否有会话”的唯一依据

## 高频示例

最近登录审计：

```bash
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type login --limit 5
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type login --days 30 --username 古思清(gusiqing) --status 1 --limit 5
```

最近操作日志：

```bash
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type operate --days 30 --user gusiqing --action 创建 --resource-type 'User session' --limit 20
```

改密日志与作业日志：

```bash
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type password_change --days 30 --user 杨天宏(tianhong.yang) --change-by 古思清(gusiqing) --remote-addr 121.225.130.254 --limit 20
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type jobs --days 30 --creator-name 古思清 --material 'shell:ls' --limit 20
```

会话记录与作业列表：

```bash
python3 scripts/jumpserver_api/jms_query.py terminal-sessions --view history --days 7 --user gusiqing --login-from WT --limit 10
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type terminal-session --days 7 --asset demo-host --protocol ssh --limit 20
python3 scripts/jumpserver_api/jms_query.py job-list --name 删除Windows用户 --limit 10
```

某用户某天连接过哪些机器：

```bash
python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability session-record-query --user 齐经宇 --date-from '2026-03-23 00:00:00' --date-to '2026-03-23 23:59:59' --limit 200
```

高危命令审计：

```bash
python3 scripts/jumpserver_api/jms_query.py command-storage-hint
python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability high-risk-command-audit --date-from '2026-03-01 00:00:00' --date-to '2026-03-20 23:59:59' --command-storage-id '<storage-id>'
```

文件传输与命令记录分析：

```bash
python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability file-transfer-log-query --direction upload --date-from '2026-03-01 00:00:00' --date-to '2026-03-20 23:59:59'
python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability command-record-query --date-from '2026-03-01 00:00:00' --date-to '2026-03-20 23:59:59' --command-storage-scope all
```

## 统计口径与常见误区

- `session_count` 与去重后的 `assets` 是两套口径；前者回答“连了几次 / 有多少会话”，后者回答“连了哪些机器 / 有多少台机器”。
- `top_users`、`top_assets`、ranking 一类排行榜默认可能是 Top N 或部分样本，排行榜不等于总量。
- 若返回里有 `summary.total`，先把它当作权威总量；只有在榜单明确覆盖全量时，才允许用榜单求和去交叉验证。
- 若榜单只是部分数据，必须明确写“根据已返回榜单/样本数据”，不能直接写成整体总数或全体用户数。
- 当用户问“某天连接了哪些机器”时，必须从 `records` 中按用户提取并去重资产名称，不用 `top_assets` 代替明细。
- 不要把单个用户的会话数说成总会话数，也不要把单个资产的访问次数说成总访问量。

## 排障提示

- `command` 审计记录里的 `id` 是 skill 生成的稳定 ID，后端原始瞬时行 ID 会保存在 `source_row_id` 里，仅用于排障观察。
- 页面型查询结果里可能带 `data_source`、`filter_strategy` 或其他诊断字段，用于对照本次实际命中的端点和过滤方式。
- 如果目标会话或命令发生在更早时间，请显式传 `--days` 或 `--date-from/--date-to`，不要直接把空结果解读成“没有记录”。
