---
name: jumpserver-skills
description: JumpServer V4.10 查询、诊断与使用分析 skill。Use when users ask to query objects, permissions, effective access, page-style audit logs, reports or dashboards, or generate a daily usage HTML report for a specific day or time range such as 使用报告、日报、某天使用情况、某段时间使用分析、daily usage report, usage analysis, or JumpServer usage overview.
---

# JumpServer Skills

只使用正式 CLI 入口：

- `python3 scripts/jumpserver_api/jms_query.py ...`
- `python3 scripts/jumpserver_api/jms_diagnose.py ...`
- `python3 scripts/jumpserver_api/jms_report.py ...`

这是查询、诊断与使用分析 skill。允许本地运行时写入 `config-write --confirm` 和 `select-org --confirm`。不执行 JumpServer 业务写操作。

## Execution Skeleton

1. 先做预检：`config-status --json` -> 必要时 `config-write --confirm` -> `ping`。
2. 按路由和组织优先级只选择 1 个正式入口执行普通查询。
3. 某天或某时间段的使用报告 / 使用分析优先走 `python3 scripts/jumpserver_api/jms_report.py daily-usage ...`。
4. 组织、对象、平台或时间窗不明确时先阻塞或解析，不猜。
5. 只做读取、诊断、审计、治理分析；不做 JumpServer 业务写操作。

## Quick Examples

优先使用当前显式参数；低频页面字段再用重复的 `--filter key=value`。

```bash
python3 scripts/jumpserver_api/jms_diagnose.py select-org --org-name Default
python3 scripts/jumpserver_api/jms_diagnose.py user-assets --org-name Default --username gusiqing
python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type login --days 30 --username 古思清(gusiqing) --status 1 --limit 5
python3 scripts/jumpserver_api/jms_query.py terminal-sessions --view history --days 7 --user gusiqing --login-from WT --limit 10
python3 scripts/jumpserver_api/jms_diagnose.py tickets --applicant gusiqing --state closed --type command_confirm --limit 10
python3 scripts/jumpserver_api/jms_query.py job-list --name 删除Windows用户 --limit 10
python3 scripts/jumpserver_api/jms_diagnose.py reports --report-type account-statistic --days 30
python3 scripts/jumpserver_api/jms_report.py daily-usage --period 上周 --org-name Default
```

阻塞或参数错误时，优先看返回里的 `reason_code`、`user_message`、`action_hint`、`suggested_commands`，不要只看顶层 `error`。

## Route First

按下面顺序判路由。上面的规则优先于下面的规则。

1. 如果用户请求的核心对象是某一天或某一段时间内的 JumpServer 使用数据分析，优先命中 HTML 模板工作流。这包括：使用报告、日报、使用情况、使用分析、审计分析、某天发生了什么、分析 `20260310`、看下 `3 月 10 号` 使用情况、帮我分析下某天堡垒机器的使用情况、帮我分析下 `20260310` 的堡垒机使用情况、帮我分析下 `3月10号` 的堡垒机器使用情况、帮我分析下 `2026-03-10到2026-03-24` 的堡垒机使用情况、帮我分析下 `上周` 的堡垒机使用情况，以及类似的“时间范围内使用情况 / 概览 / 排行 / TOP”表达。
动作：优先使用 `python3 scripts/jumpserver_api/jms_report.py daily-usage ...`，并由它加载 [template/bastion-daily-usage-template.html](template/bastion-daily-usage-template.html) 和 [references/metadata/daily_usage_report_template_fields.json](references/metadata/daily_usage_report_template_fields.json) 这份运行时元数据；先把“昨天 / 20260310 / 3月10号 / 上周 / 本月”等时间表达归一化为明确时间窗，再生成并验证完整 HTML 报告；模板细节见 [references/report-template-playbook.md](references/report-template-playbook.md)。

2. 如果用户要配置 JumpServer、检查依赖、检查配置、检查连通性、切换组织、查看许可证、系统设置、工单、存储、终端或读取报表，先走 `jms_diagnose.py`。
动作：优先 `config-status`、`ping`、`select-org`、`settings-category`、`tickets`、`reports`、`inspect`。

3. 如果用户要查某某用户当前能访问哪些资产、节点，或在某资产下有哪些账号 / 协议，归为“用户有效访问范围”，先走 `jms_diagnose.py`。
动作：显式给了组织就按用户指定组织执行；结果型问法优先 `user-assets` / `user-nodes` / `user-asset-access`，先返回有效访问范围结果，不回退成授权规则说明。

4. 如果用户要看授权规则、ACL、RBAC、为什么某人能访问某资产、某条权限详情，走权限读取与解释路径。
动作：`资产授权给了谁` 优先 `jms_query.py asset-perm-users`；`为什么会被授权 / 节点授权是否覆盖它 / 权限详情` 优先 `jms_diagnose.py asset-permission-explain` 加 `permission-list/get`。

5. 如果用户要查页面同款审计明细、会话、命令、文件传输或作业列表，走 `jms_query.py`。
动作：直接查明细优先 `audit-list`、`terminal-sessions`、`job-list`；做汇总分析再用 `audit-analyze --capability ...`。

6. 如果用户要做治理巡检、聚合排行、账号治理、资产治理或系统巡检，走 `jms_diagnose.py inspect --capability ...`。
动作：优先 capability，不手工拼多条零散查询。

普通路由细节、更多命中说法和反例见 [references/routing-playbook.md](references/routing-playbook.md)。

## Template Overrides

按下面顺序处理模板例外。上面的规则优先于下面的规则。

1. 如果用户明确说“不要生成报告，直接分析”“先简单说下”“只给我结论”“不用模板”，才允许跳过模板，直接给简短分析。
2. 除上述明确例外外，只要是某一天或某一段时间的 JumpServer 使用情况 / 使用分析 / 审计分析，或者表达为某时间段的登录 / 会话 / 命令 / 传输情况、排行、TOP，就必须先走模板工作流。
3. “分析”不等于自由文本优先。带时间范围的使用分析、情况概览或排行类问题，默认先产出完整 HTML 报告；摘要只能作为补充，不能替代报告。
4. 只要 `daily-usage` 成功返回，就必须先告诉用户“报告已生成”，并回显报告文件路径、文件存在性/大小、模板路径、元数据路径、时间范围、组织和 `validation_summary`；不允许后台生成 HTML 却只给文字摘要。

### 模板报告后的数据总结

- 当正式入口已成功生成 HTML 报告，若还要补充文字摘要，必须基于正式工具输出里的 `result.summary`、`records` 或其他结构化结果字段，不基于猜测。
- 优先读取 `result.summary` 这类总量字段；只有在它不足以回答问题时，才继续展开 `records` 或其他明细。
- 不要只看 HTML 静态内容下结论；HTML 是展示结果，统计口径仍以工具返回的数据为准。
- 若 `top_users`、`top_assets` 或其他 ranking 是 Top N / 被 `top` 截断 / 只返回部分榜单，必须明确说明“这只是部分榜单，不能替代总量”。
- 若榜单明确覆盖全量分布，才允许把 `summary.total` 与榜单求和做一致性校验；否则只能保守描述“根据已返回榜单/样本数据”。

## Page-Style Query Rules

- `--search` 表示页面搜索框的直接搜索，不是用户名专用，也不是精确字段的别名。
- 操作日志页面同款精确过滤优先用 `--user --action --resource-type`。
- 登录日志页面同款精确过滤优先用 `--username --ip --type --city --mfa --status`。
- 改密日志页面同款精确过滤优先用 `--user --change-by --remote-addr`。
- 作业日志页面同款精确过滤优先用 `--creator-name --material`。
- 会话页面同款精确过滤优先用 `--user --account --asset --protocol --login-from --remote-addr`；需要时再加 `--asset-id --order`。
- 工单页面优先用 `--applicant --state --type`；作业列表优先用 `--name`。
- 页面型命令不把 `audit-list --audit-type login --user`、`terminal-sessions --source-ip`、`tickets --name` 当成首选写法。
- 查询型接口中的 `--days` 只是输入快捷方式，最终会换算成明确的 `date_from/date_to`；纯日期会补到当天起止，再序列化成页面同款 UTC `...Z`。报表和 dashboard 保留原生 `days`，不强行换算成时间窗。
- `--filter key=value` 继续保留，但只作为低频页面字段的兜底入口。

## Organization Priority

按下面顺序处理组织。上面的规则优先于下面的规则。

1. 用户显式给组织：按用户指定组织执行。
2. 报告或使用分析模板请求且用户未指定组织，或明确指定“所有组织”“全局组织”：默认执行 `python3 scripts/jumpserver_api/jms_diagnose.py select-org --org-id 00000000-0000-0000-0000-000000000000 --confirm`。
3. 如果全局组织 `00000000-0000-0000-0000-000000000000` 的显式选择验证失败：直接阻塞并返回 `candidate_orgs`；不要回退到自动规则。
4. 非报告类请求且未指定组织：沿用保留组织逻辑。只有可访问组织集合恰好是 `{0002}` 或 `{0002,0004}` 时，才自动写入 `0002`。
5. 查询类请求在未确定组织且存在多个可访问组织时：先返回 `candidate_orgs` 并要求用户选择查询组织。
6. 当前 `JMS_ORG_ID` 已不可访问：先重新 `select-org`，不要继续业务命令。

## Standard Flow

收到请求先做：

```text
自动检查依赖 -> config-status --json -> 必要时 config-write --confirm -> ping -> 按路由和组织优先级选择正式入口
```

执行规则：

- 配置或环境不确定时，先执行 `python3 scripts/jumpserver_api/jms_diagnose.py config-status --json`。
- 名称不唯一、平台不明确、对象跨组织时，先解析或阻塞，不要猜。
- “某某用户在某组织下有哪些资产 / 节点 / 账号” 这类请求先解析组织；优先在单次命令内用 `--org-id` / `--org-name` 限定组织。
- 审计类问题没有 `date_from/date_to` 时，默认最近 7 天；想查更大范围时优先要求明确时间窗。
- “某用户某天连接过哪些机器 / 某天会话数” 这类问题，优先返回两套口径：`session_count` 与去重后的 `assets`；机器列表用去重资产，不要把会话条数直接说成机器数。
- 模板化使用报告/使用分析请求必须先走 `python3 scripts/jumpserver_api/jms_report.py daily-usage ...`；普通查询优先只选 1 个正式入口。

## Statistical Guidelines

- 先看权威总量字段：`summary.total`、`summary.total_sessions`、`summary.total_users`、`summary.total_assets`；再看 `top_users`、`top_assets`、`ranking` 一类榜单字段。
- 用户问“某天连接了哪些机器”时，优先从 `records` 推导“用户 -> 去重资产列表”；不要只看 `top_assets` 就回答机器清单。
- `session_count`、去重后的 `assets`、活跃用户数、被访问资产数是不同统计口径，回答时要分别标注来源，不要互相替代。
- 若 `top_users`、`top_assets` 或 ranking 明显是 Top N、被 `top` 截断、或语义上只是排行，禁止把其求和后直接当总数。
- 只有在榜单明确覆盖全量分布时，才允许用 `len(top_users)` 推导活跃用户数，或用 `len(top_assets)` 推导被访问资产数；否则只能说“已返回榜单中的用户数/资产数”。
- 不要把单个用户的会话数、单个资产的访问次数，或榜单第一名的计数，当成整体总量。
- 继续保留两套口径回答：会话问题看 `session_count` 或总会话字段，机器问题看去重后的 `assets`；不要把会话条数直接说成机器数。

## Guardrails

- 不生成临时 SDK Python 脚本或 HTTP 脚本。
- 不猜对象 ID、平台 ID、组织、鉴权信息或筛选条件。
- 不创建、更新、删除、解锁对象，也不追加或移除权限关系。
- 权限问题只做读取和解释，不做权限写入。
- 对“某某用户在某组织下有哪些资产”不要直接返回授权规则说明，也不要把“有哪些资产”自动翻译成“解释访问依据”。
- 只有正式入口在精确时间窗和正确组织下实际返回 `0` 条时，才能说“没有记录”。
- 未经验证，不要猜测“页面选错日期”“时区差异”“数据同步延迟”等原因。
- 模板化报告请求必须优先使用 `python3 scripts/jumpserver_api/jms_report.py daily-usage ...`；不要现场写临时拼装逻辑。
- 模板化报告请求只使用字段元数据里声明的来源，不用 Markdown 模板替代 HTML 模板。

### 统计与报告类错误（严禁）

- 不要把单个用户的会话数说成“总会话数”。
- 不要把单个资产的被访问次数说成“总资产数”或“总访问量”。
- 不要只看 `top_users[0]`、`top_assets[0]` 或榜单第一名，就下“只有 X 位用户 / 只有 Y 台机器 / 总共 Z 次会话”的结论。
- 不要忽略 `top_users`、`top_assets` 或 ranking 列表中除第一个外的其他条目。
- 只有在 `top_users` 明确覆盖全量时，才能把 `len(top_users)` 当作活跃用户数；否则只能说“已返回榜单中的用户数”。
- 只有在 `top_assets` 明确覆盖全量时，才能把 `len(top_assets)` 当作被访问资产数；否则只能说“已返回榜单中的资产数”。
- 当用户问“某天连接了哪些机器”时，不要用 `top_assets` 替代 `records`；必须从 `records` 推导用户与资产的去重关系。

## Respond With

成功时至少回显：

- 已走预检
- 选中的正式入口或模板路径
- `effective_org`
- `switchable_orgs`（当当前组织已生效且仍有其他可切换组织时）
- 执行命令摘要
- 用户有效访问范围：`asset_count` + `assets`，或 `node_count` + `nodes`，或 `permed_accounts` + `permed_protocols`
- 其他普通查询：结果摘要
- 模板报告：完整 HTML 报告，且已经通过生成后自检

模板报告成功时还至少回显：

- 明确说明“报告已生成”
- 正式入口：`python3 scripts/jumpserver_api/jms_report.py daily-usage ...`
- 报告文件路径
- 文件存在性与大小：`output_exists`、`output_size_bytes`、`output_size_human`
- 模板路径：`template/bastion-daily-usage-template.html`
- 字段元数据路径：`references/metadata/daily_usage_report_template_fields.json`
- `queried_command_storage_ids`
- `queried_command_storage_count`
- `report_date`
- `date_from`
- `date_to`
- `validation_summary`

阻塞时至少回显：

- 已走预检
- `effective_org`
- 阻塞原因
- `candidate_orgs` 或 `candidate_objects`
- 下一步安全动作

## Data Validation

### 全量可验证场景

- 若返回了 `summary.total` 或同类总量字段，且 `top_users`、`top_assets` 或其他分布列表明确覆盖全量，必须交叉验证用户之和、资产之和与总量一致。
- 若三者不一致，先说明差异和各自口径，再分别列出；不要强行合并成一个数字。
- 报告“X 位用户，共 Y 次会话”这类结论前，先确认 X 来自全量用户分布或全量 `records`，Y 来自总量字段或全量求和，而不是某个单条记录。

### 部分榜单场景

- 若 `top_users`、`top_assets` 或 ranking 只是 Top N、被 `top` 截断、或语义上明显只是排行，必须明确说明“这是部分榜单，不能替代总量”。
- 这类场景下不要把榜单求和写成总会话数，不要把 `len(top_users)` 写成全部活跃用户数，也不要把 `len(top_assets)` 写成全部被访问资产数。
- 结论措辞必须降级为“根据已返回榜单/样本数据”或“已返回的 Top 用户/资产中”，不能直接给全局判断。

### 会话-用户一致性检查

- 不要把某个用户的会话数说成总会话数；例如榜首用户有 `23` 次会话，不等于系统里总共只有 `23` 次会话。
- 只有在用户列表明确覆盖全量时，才能把用户计数求和后和总量对齐；否则只能说“已返回榜单中的若干用户共贡献了 X 次会话”。

### 用户-资产连接矩阵

- 当用户问“某天连接了哪些机器”时，先从 `records` 按用户分组，再提取每个用户对应的去重资产名称。
- 报告格式优先写成“用户 -> 机器列表”，不要直接把 `top_assets` 当作某个用户的连接矩阵。
- 只有在缺少 `records` 且工具明确只返回部分榜单时，才能保守表述“根据已返回榜单/样本数据”，不要伪造全量结论。

## Reference Loading Guide

- 查对象、资产、账号、用户、节点、平台与组织时，读 [references/assets.md](references/assets.md)。
- 查授权主体、ACL、RBAC、权限详情、资产授权解释时，读 [references/permissions.md](references/permissions.md)。
- 查页面同款登录、会话、命令、文件传输、作业与审计分析时，读 [references/audit.md](references/audit.md)。
- 查预检、配置、组织、select-org、config-write、连通性时，读 [references/runtime.md](references/runtime.md)。
- 查 resolve、effective access、settings、license、tickets、reports、inspect 时，读 [references/diagnose.md](references/diagnose.md)。
- 查报告模板、日报、某天/某时间段使用分析与报告口径时，读 [references/report-template-playbook.md](references/report-template-playbook.md)。
- 查 capability 目录、优先级和 capability 选择时，读 [references/capabilities.md](references/capabilities.md)。
- 查阻塞、参数报错、依赖失败、空结果与排障建议时，读 [references/troubleshooting.md](references/troubleshooting.md)。
- 查安全边界和禁止动作时，读 [references/safety-rules.md](references/safety-rules.md)。
- 查旧能力迁移、设计映射或历史能力拆分时，读 [references/migration-map.md](references/migration-map.md)。
- 查自然语言对象映射、资源归一化与歧义处理时，读 [references/object-map.md](references/object-map.md)。

## References

- [普通路由与阻塞规则](references/routing-playbook.md)
- [报告模板工作流](references/report-template-playbook.md)
- [运行入口与环境](references/runtime.md)
- [审计与调查](references/audit.md)
- [诊断与访问分析](references/diagnose.md)
- [安全规则](references/safety-rules.md)

## Response Checklist

- [ ] 我是否先确认了数字来自 `summary`、全量 `records`，还是 Top N / 部分榜单？
- [ ] 如果拿榜单做推断，我是否先确认它覆盖全量，而不是默认把 Top N 当成总量？
- [ ] 如果存在 `summary.total` 和完整分布，我是否做了用户之和、资产之和、总量的交叉验证？
- [ ] 我是否避免了把单个用户会话数、单个资产访问次数、或榜单第一名的 count 说成总数？
- [ ] 如果回答“某天连接了哪些机器”，我是否从 `records` 去重推导，而不是只看 `top_assets`？
- [ ] 当只能看到部分数据时，我是否明确写出“根据已返回榜单/样本数据”这类保守措辞？
