# 诊断与访问分析

## 快速概览

- 主入口：`python3 scripts/jumpserver_api/jms_diagnose.py <subcommand> ...`
- 适合连通性检查、对象解析、用户有效访问范围分析、最近审计预检、系统设置巡检、许可证读取、工单列表、终端组件/命令存储/录像存储查询、报表读取、账号自动化概览、核心端点 inventory 与按路径验证。
- `select-org` 是显式组织选择入口；未选组织时，除 `config-status`、`config-write`、`ping`、`select-org` 外，其余子命令都会先阻塞。
- 当当前组织已生效时，`ping`、`select-org` 以及主要查询结果会额外回显仍可切换的组织列表，便于继续按其他组织范围查询。
- 统计与巡检类聚合请求优先用 `inspect --capability ...`；需要直连读取某类设置或系统对象时，再用专用子命令。
- 推荐优先使用显式参数；低频字段再用 `--filter key=value`。

## 常用子命令

| 子命令 | 何时用 | 关键参数 | 关键输出 |
|---|---|---|---|
| `config-status` | 查看本地运行时配置是否完整 | 无 | `complete`、认证方式、`missing_fields`、`invalid_fields` |
| `config-write` | 把准备好的运行时配置写入 `.env` | `--payload` + `--confirm` | 脱敏后的当前配置摘要 |
| `ping` | 验证环境与 API client 连通性 | 无 | 当前用户、当前组织、可切换组织 |
| `select-org` | 查看当前环境组织或显式写入 `JMS_ORG_ID` | 可选 `--org-id` / `--org-name` | `candidate_orgs`、`effective_org`、`switchable_orgs` |
| `resolve` | 把自然语言名称解析成对象 | `--resource` + `--name` 或 `--id` | 规范对象 |
| `resolve-platform` | 解析平台名称或分类 | `--value` | `status`、`resolved`、候选平台 |
| `user-assets` | 查用户当前可访问资产 | `--user-id` 或 `--username` | `asset_count`、`assets` |
| `user-nodes` | 查用户当前可访问节点 | `--user-id` 或 `--username` | `node_count`、`nodes` |
| `user-asset-access` | 查用户在某资产下的账号与协议 | 一个用户定位 + 一个资产定位 | `permed_accounts`、`permed_protocols` |
| `asset-permission-explain` | 从资产视角解释命中的授权规则 | `--asset-id` 或 `--asset-name` | `matched_permissions`、`match_source` |
| `recent-audit` | 快速看最近审计 | `--audit-type` + 页面同款参数 | 最近事件列表，包含 `data_sources` 与 `filter_strategies` 摘要 |
| `settings-category` | 按设置分类读取系统配置 | `--category`，可选 `--id` | 原始设置项与分类摘要 |
| `license-detail` | 查看许可证详情 | 无 | 许可证原始详情 |
| `tickets` | 查看工单列表 | `--search --applicant --state --type` | 工单记录 |
| `command-storages` | 查看命令存储列表 | 可选 `--name` / `--search` | 命令存储记录 |
| `replay-storages` | 查看录像存储列表 | 可选 `--name` / `--search` | 录像存储记录 |
| `terminals` | 查看终端组件列表 | 可选 `--name` / `--search` | 终端组件记录 |
| `reports` | 读取报表与 dashboard | `--report-type` | 报表原始返回与摘要 |
| `account-automations` | 汇总账号备份、改密、风险、检测任务 | 可选 `--days --limit --offset` | 自动化概览 |
| `endpoint-inventory` | 查看核心端点 inventory / OPTIONS 缓存 | 可选 `--refresh` | 端点清单与方法能力 |
| `endpoint-verify` | 对单个端点做 GET/OPTIONS 验证 | `--path` | `method`、`path`、原始 payload |
| `inspect` | 查询治理、统计、巡检能力单元 | `--capability` | 能力摘要、排行、样本 |
| `capabilities` | 列出所有 `inspect` 能力 | 无 | 能力目录 |

## 有效访问范围

这组命令直接读取 JumpServer effective access 接口：

- `user-assets` 从 `/api/v1/perms/users/{user_id}/assets/` 获取用户当前可访问资产。
- `user-nodes` 从 `/api/v1/perms/users/{user_id}/nodes/` 获取用户当前可访问节点。
- `user-assets`、`user-nodes`、`user-asset-access` 都支持额外传 `--org-id` 或 `--org-name`，只在当前命令内临时限定查询组织，不会写回 `.env`。
- 结果里会保留 `effective_org`、`switchable_orgs`、`data_source` 等上下文字段，便于排查“结果查到哪里去了”。

## `recent-audit` 页面同款参数面

`recent-audit` 只支持 `operate`、`login`、`session`、`command` 四类：

- `operate`：`--search --user --action --resource-type`
- `login`：`--search --username --ip --type --city --mfa --status`
- `session`：`--search --user --account --asset --protocol --login-from --remote-addr --asset-id --order`
- `command`：`--search --command-storage-id --command-storage-scope --asset-id --order`

补充规则：

- 查询型时间参数和 `jms_query.py` 保持一致：`--days` 只是输入快捷方式，最终会换算成 `date_from/date_to`。
- `session` 优先读取 `/api/v1/terminal/sessions/`；只有 terminal 侧没有命中时，才回退到 `/api/v1/audits/user-sessions/`。
- `--search` 可和精确字段同时下发；结果摘要会带 `filter_strategies`，用于判断本次过滤来源。

## 报表与 dashboard

`reports` 读取系统报表和 dashboard，重点区分两类：

- 原生 `days` 报表族：`account-statistic`、`account-automation`、`asset-statistic`、`asset-activity`、`users`、`user-change-password`
- dashboard 族：`pam-dashboard`、`change-secret-dashboard`

使用规则：

- 报表和 dashboard 保留原生 `days`，不走查询型 `date_from/date_to` 时间窗换算。
- `change-secret-dashboard` 需要同时带 `days` 和 `--daily-success-and-failure-metrics` 这类页面开关。
- `pam-dashboard` 走页面布尔开关，不强行生成 `date_from/date_to`。

## 高频示例

预检与组织：

```bash
python3 scripts/jumpserver_api/jms_diagnose.py config-status --json
python3 scripts/jumpserver_api/jms_diagnose.py ping
python3 scripts/jumpserver_api/jms_diagnose.py select-org
python3 scripts/jumpserver_api/jms_diagnose.py select-org --org-name Default
```

对象解析与有效访问范围：

```bash
python3 scripts/jumpserver_api/jms_diagnose.py resolve --resource account --name root
python3 scripts/jumpserver_api/jms_diagnose.py resolve-platform --value Unix
python3 scripts/jumpserver_api/jms_diagnose.py user-assets --org-name Default --username jingyu.qi
python3 scripts/jumpserver_api/jms_diagnose.py user-nodes --user-id 4f8b763f-5c21-4b77-903c-37a7838968ae
python3 scripts/jumpserver_api/jms_diagnose.py user-asset-access --user-id 4f8b763f-5c21-4b77-903c-37a7838968ae --asset-id 84d763b2-08bb-4d39-8fab-993714857642
```

最近审计与工单：

```bash
python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type login --days 30 --username 古思清(gusiqing) --status 1 --limit 5
python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type session --user gusiqing --account root --asset demo-host --login-from WT --limit 10
python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type operate --days 30 --user gusiqing --action 创建 --resource-type 'User session' --limit 20
python3 scripts/jumpserver_api/jms_diagnose.py tickets --applicant gusiqing --state closed --type command_confirm --limit 10
```

设置、报表与巡检：

```bash
python3 scripts/jumpserver_api/jms_diagnose.py settings-category --category security_auth --id <setting-id>
python3 scripts/jumpserver_api/jms_diagnose.py license-detail
python3 scripts/jumpserver_api/jms_diagnose.py reports --report-type account-statistic --days 30
python3 scripts/jumpserver_api/jms_diagnose.py reports --report-type pam-dashboard --total-long-time-no-login-accounts --total-weak-password-accounts
python3 scripts/jumpserver_api/jms_diagnose.py inspect --capability hot-assets-ranking --days 30 --top 10 --limit 10
python3 scripts/jumpserver_api/jms_diagnose.py inspect --capability system-settings-overview
```

端点验证：

```bash
python3 scripts/jumpserver_api/jms_diagnose.py endpoint-inventory --refresh
python3 scripts/jumpserver_api/jms_diagnose.py endpoint-verify --path /api/v1/settings/setting/ --method GET
python3 scripts/jumpserver_api/jms_diagnose.py capabilities
```
