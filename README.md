# JumpServer Skills

`jumpserver-skills` 是一个面向 JumpServer V4.10 的自然语言运维 skill 仓库，适用于对象查询、权限回看、审计调查、治理巡检、访问分析、模板化使用报告，以及受控的对象创建场景。使用者无需手动拼接脚本命令；除白名单 create 入口外，其余服务端能力保持非破坏性读取，create 输出会自动脱敏密文字段。

[English](./README.en.md)

## 最快上手

1. 把这个 skill 接到你的 agent 或 Codex 环境里。仓库中的 [agents/openai.yaml](./agents/openai.yaml) 可以直接作为接入描述使用。
2. 直接用自然语言初始化配置，例如“帮我生成 `.env`，JumpServer 地址是 `https://jump.example.com`，我用 AK/SK 登录”。
3. 然后继续直接提需求，例如“查某某用户在 Default 组织下有哪些资产”或“看看昨天使用情况”。

第一次使用时，优先推荐走“自然语言对话生成 `.env`”这条路径，通常比手动改模板更快。

## 这个 skill 能做什么

| 能力分组 | 你可以这样问 | 自动路由入口 | 返回与安全边界 |
|---|---|---|---|
| 环境预检与组织选择 | “检查配置是否可用”“测试连通性”“切到 Default 组织” | `jms_common.py` | 先确认 `.env`、认证、组织和端点；本地写入仅限 `.env`，包含当前组织选择 |
| 对象查询 | “查这个资产/用户/账号/节点/标签”“看某个平台详情” | `jms_query.py` / `jms_runtime_query.py` | 返回对象清单、详情或候选项；对象不唯一时先让使用者确认 |
| 用户有效访问范围 | “某用户能访问哪些资产/节点”“某资产下他能用哪些账号和协议” | `jms_access.py` | 优先返回 effective access 结果，不默认展开授权规则推导 |
| 权限关系回看 | “这个资产授权给了谁”“为什么这个用户能访问”“看某条授权规则详情” | `jms_permissions.py` | 区分授权主体、实际可访问者和超级管理员影响，不混淆口径 |
| 审计调查 | “昨天谁登录失败了”“查某用户会话/命令/文件传输”“分析高危命令” | `jms_audit.py` | 按明确组织和时间窗查询日志、记录、明细或聚合结果 |
| 治理巡检与访问分析 | “做资产治理巡检”“分析账号风险”“看访问排行/异常行为” | `jms_inspect.py` / `jms_audit.py` | 使用内置 capability 聚合分析，不要求使用者手工拼零散查询 |
| 使用报告 | “生成日报”“分析 2026-03-10 的堡垒机使用情况”“看某段时间使用概览” | `jms_report.py` | 默认生成完整 HTML 报告，并回显报告路径、时间窗、组织和校验摘要 |
| 受控创建 | “创建用户/组织/标签/节点/资产/网域/网关/账号模板/授权规则/ACL/脱敏规则” | [create 入口索引](./subskills/create/references/index.md) | 仅开放白名单 create 入口；无 `--confirm` 只预览，有 `--confirm` 才创建；密文字段脱敏 |

创建类能力当前覆盖 23 个白名单命令，包含用户与组织、标签与节点、主机/网络设备/数据库/Web 资产、网域与网关、账号模板与账号批量绑定、命令组与命令过滤规则、登录控制、连接方式过滤器、资产授权规则、资产连接规则和数据脱敏过滤规则。完整命令、脚本和字段说明见 [create 入口索引](./subskills/create/references/index.md)。

## 怎么使用这个 skill

1. 准备环境文件。在仓库根目录创建 `.env`，有两种方式：

手动方式：

```bash
cp .env.example .env
```

对话方式：

如果本地配置不完整，运行时也可以直接通过自然语言对话帮你生成 `.env`。它会按固定顺序收集 `JMS_API_URL`、认证方式、组织、超时和 TLS 配置，回显脱敏摘要后写入本地 `.env`。例如：

```bash
“帮我生成 `.env`，JumpServer 地址是 `https://jump.example.com`，我用 AK/SK 登录。
```
```bash
帮我初始化 JumpServer 配置，我用用户名密码登录，不校验证书。
```

2. 把这个 skill 接到你的 agent 或 Codex 环境里使用。仓库中的 [agents/openai.yaml](./agents/openai.yaml) 提供了一个现成的 skill 接入描述，可作为引用或注册该 skill 的入口之一。

3. 直接用自然语言描述需求，不需要手动拼接脚本命令。例如“查某某用户在 Default 组织下有哪些资产”“看看昨天使用情况”“看某条授权规则详情”。

4. 根据返回结果继续补充上下文。如果结果提示 `candidate_orgs`、`switchable_orgs`、候选对象或缺少时间范围，就按提示补充组织、对象名称、平台或时间窗口。组织必须先选时，返回里还会带 `reason_code`、`user_message`、`action_hint`、`suggested_commands` 和 `candidate_org_count`，方便直接按提示继续。

使用时不需要记住具体执行命令。这个 skill 会先做预检，再按路由规则自动选择正式入口，并在需要时提示你补充组织、对象或时间范围。

## 环境变量

仓库根目录下提供了 [`.env.example`](./.env.example) 作为模板。实际使用时，需要在仓库根目录准备 `.env` 文件；可以直接复制模板后修改，也可以参考模板手动新建。

如果不想手动编辑，也可以直接通过自然语言对话生成 `.env`。当检测到配置缺失或不完整时，skill 会按顺序收集必要字段，并通过正式入口把配置写入本地 `.env`。

如果你想一次把信息说清，通常准备下面这些就够了：

- `JMS_API_URL`
- 一组完整认证方式：`JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` 或 `JMS_USERNAME/JMS_PASSWORD`
- `JMS_ORG_ID` 可先留空，之后用 `select-org --confirm` 写入
- `JMS_TIMEOUT`，不填则使用默认值
- `JMS_VERIFY_TLS`，不填时默认 `false`

| 变量 | 是否必需 | 说明 |
|---|---|---|
| `JMS_API_URL` | 必需 | JumpServer API / 访问地址 |
| `JMS_ACCESS_KEY_ID` | 与 `JMS_ACCESS_KEY_SECRET` 成组，或改用用户名密码 | API Access Key ID |
| `JMS_ACCESS_KEY_SECRET` | 与 `JMS_ACCESS_KEY_ID` 成组，或改用用户名密码 | API Access Key Secret |
| `JMS_USERNAME` | 与 `JMS_PASSWORD` 成组，或改用 AK/SK | JumpServer 登录用户名 |
| `JMS_PASSWORD` | 与 `JMS_USERNAME` 成组，或改用 AK/SK | JumpServer 登录密码 |
| `JMS_ORG_ID` | 可选 | 当前组织 ID，可由 `select-org --confirm` 写入 |
| `JMS_TIMEOUT` | 可选 | 请求超时秒数 |
| `JMS_VERIFY_TLS` | 可选 | 是否校验证书，默认 `false` |

环境变量规则：

- 必须提供 `JMS_API_URL`。
- 认证方式至少完整提供一组：`JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` 或 `JMS_USERNAME/JMS_PASSWORD`。
- `.env` 会被运行时自动加载。
- 如果 `.env` 缺失或不完整，可以直接通过自然语言对话补齐，运行时会在确认后生成或覆盖本地 `.env`。
- 首次使用前，需要确保地址、认证方式、组织、超时和 TLS 配置齐全。
- 如果切换了 JumpServer、账号、组织或 `.env` 内容，应重新执行完整预检。

## 典型请求示例

| 场景 | 可以这样问 | 自动路由 |
|---|---|---|
| 对象查询 | “查一下 `Demo-User` 这个用户的详情”“看看 `Demo-Node` 节点里有哪些资产”“帮我看 `Linux` 平台下有哪些可用资产” | `jms_query.py` |
| 用户有效访问范围 | “某某用户在 Default 组织下有哪些资产”“某某用户有哪些节点”“某某用户在某资产下有哪些账号和协议” | `jms_access.py` |
| 权限关系回看 | “这台资产授权给了谁”“某某用户为什么能访问某资产”“看这条授权规则详情” | `jms_permissions.py` |
| 审计调查 | “查最近一周的登录审计”“看某个用户的会话记录和异常中断情况”“导出某天命令记录详情” | `jms_audit.py` |
| 使用报告 | “看看昨天使用情况”“想看上周谁登录最多”“过一下 3 月上旬哪些资产最活跃” | `jms_report.py` |
| 治理巡检 | “做一次资产治理巡检”“分析账号风险”“看最近访问异常” | `jms_inspect.py` |
| 受控创建 | “创建用户”“创建节点”“创建主机资产”“创建资产授权规则”“创建数据脱敏规则” | create 子 Skill，入口见 [create 索引](./subskills/create/references/index.md) |

容易混淆的问法按下面规则处理：

| 问法特征 | 归类 |
|---|---|
| “能访问哪些资产 / 节点 / 账号 / 协议” | 用户有效访问范围，返回结果清单 |
| “为什么能访问 / 授权规则详情 / 权限依据” | 权限关系回看，解释授权来源 |
| “这台资产授权给了谁 / 谁被授权到这台资产” | 默认回答授权主体，不默认把超级管理员算进去 |
| “某天登录情况 / 会话概览 / 谁最多 / 哪些最活跃” | 使用报告或使用分析 |
| “某天登录日志 / 命令记录 / 会话详情 / 文件传输明细” | 审计调查 |

## 使用报告与时间范围规则

只要核心是某一天或某一段时间内的 JumpServer 整体使用情况、概览、汇总、排行或分布，就优先走模板化报告流程。只有用户明确说“不要生成报告，直接分析”“先简单说下”“只给我结论”“不用模板”时，才跳过模板。

| 表达类型 | 路由 |
|---|---|
| 使用报告、日报、周报、月报、使用情况、使用分析、使用统计、使用概览 | `jms_report.py daily-usage-prepare` -> Skill 总结 -> `jms_report.py daily-usage-render` |
| 某天发生了什么、某天登录/会话/命令/传输情况、某时间段 TOP 或排行 | `jms_report.py daily-usage-prepare` -> Skill 总结 -> `jms_report.py daily-usage-render` |
| 登录日志、会话详情、命令记录、文件传输明细、单条审计记录 | `jms_audit.py` |
| 明确要求“不生成报告 / 只给结论 / 不用模板” | 可跳过 HTML 报告，直接做简短分析 |

自然语言时间会先归一化，再进入正式入口：

| 用户时间表达 | 归一化结果 |
|---|---|
| `昨天` | 前一天 `00:00:00 ~ 23:59:59` |
| `20260310`、`2026-03-10`、`2026/03/10`、`3月10号`、`2026年3月10日` | 同一天 `00:00:00 ~ 23:59:59` |
| `上周` | 上一个自然周，周一 `00:00:00 ~ 周日 23:59:59` |
| `本月` | 本月 1 日 `00:00:00` 到当前日期或月末 `23:59:59` |
| `2026-03-10 到 2026-03-24`、`3月10号到3月24号` | 起始日 `00:00:00` 到结束日 `23:59:59` |

正式入口最终统一使用 `--date`、`--period` 或 `--date-from/--date-to` 进入 prepare，内部归一化为 `date_from` 和 `date_to`。报告分析字段由 Skill 基于 `summary_input` 总结后写入摘要 JSON，再通过 render 生成 `reports/JumpServer-YYYY-MM-DD.html`；成功时先回显“报告已生成”，再给出报告路径、文件存在性/大小、模板路径、字段元数据路径、时间范围、组织和 `validation_summary`。简短摘要只能作为补充，不能替代报告产物信息。

## 组织选择与阻塞规则

当前组织保存在 `.env` 的 `JMS_ORG_ID`。业务请求没有显式组织时，通常使用当前组织；报告和部分 create 命令有专门规则。

| 场景 | 组织处理 | 是否写 `.env JMS_ORG_ID` |
|---|---|---|
| 手动切换当前组织 | `select-org --org-id <org-id> --confirm` 或 `select-org --org-name <name> --confirm` | 写入 |
| 普通查询显式指定组织 | 先解析组织 ID，再按该组织执行 | 不写入，仅限定本次命令 |
| 普通查询未指定组织 | 使用 `.env JMS_ORG_ID` | 不额外写入 |
| 使用报告未指定组织 | 默认使用全局组织 `00000000-0000-0000-0000-000000000000` | 不写入 |
| 使用报告显式指定组织且匹配成功 | 按指定组织生成报告 | 写入 |
| create 命令 | 以 [写操作白名单](./references/routing-and-safety.md) 和 [create 索引](./subskills/create/references/index.md) 为准 | 按具体命令决定 |

create 的组织规则不在 README 重复展开。需要记住的边界是：多数 create 命令的显式组织只限定本次命令；未传组织时部分命令使用 `.env JMS_ORG_ID`；需要目标组织的 create 通常禁止全局组织；`create-login-acl` 和 `create-connect-method-acl` 必须在全局组织；`create-organization` 不带 `X-JMS-ORG`，成功后不切换当前组织。

出现下面情况时，skill 会先阻塞，而不是继续猜测执行：

| 阻塞原因 | 处理方式 |
|---|---|
| 配置或鉴权不完整 | 先补齐 `.env` 或执行预检 |
| 对象名称重名、平台不明确、组织不明确 | 返回候选项，要求使用者确认 |
| 查询结果跨组织，或当前组织与目标对象所在组织不一致 | 要求明确目标组织 |
| 多组织且没有当前组织可用 | 返回 `candidate_orgs`，要求先选择组织 |
| 用户试图绕过正式入口、跳过预检或现场拼临时脚本 | 阻塞，要求使用正式入口 |

## 文档地图

| 你想了解 | 看这里 | 用途 |
|---|---|---|
| 接入这个 skill | [SKILL.md](./SKILL.md)、[agents/openai.yaml](./agents/openai.yaml) | 顶层路由、默认提示词、响应约束 |
| 安全边界和白名单 | [references/routing-and-safety.md](./references/routing-and-safety.md) | 正式入口边界、允许写操作、全局阻塞规则 |
| 查询、访问、权限、审计、巡检怎么路由 | [subskills/query/references/routing-playbook.md](./subskills/query/references/routing-playbook.md)、[capabilities.md](./subskills/query/references/capabilities.md) | 触发词、能力目录、阻塞规则与反例 |
| 使用报告怎么生成 | [subskills/query/references/report-template-playbook.md](./subskills/query/references/report-template-playbook.md) | 模板化报告流程、时间范围、组织优先级 |
| 对象查询和权限审计细节 | [assets.md](./subskills/query/references/assets.md)、[permissions.md](./subskills/query/references/permissions.md)、[audit.md](./subskills/query/references/audit.md)、[diagnose.md](./subskills/query/references/diagnose.md) | 资产/账号/用户/节点查询、授权关系、日志审计、治理诊断 |
| create 能创建什么 | [subskills/create/references/index.md](./subskills/create/references/index.md) | create 命令、入口脚本、字段文档索引 |
| 运行时、预检和排障 | [runtime.md](./subskills/common/references/runtime.md)、[safety-rules.md](./subskills/common/references/safety-rules.md)、[troubleshooting.md](./subskills/common/references/troubleshooting.md) | `.env`、组织选择、本地写入边界、常见失败处理 |

## 不支持范围

以下请求不会执行：

- 服务端写操作只开放白名单 create 入口；对象更新、删除、解锁及未开放的权限创建、变更、移除一律不执行，完整范围以 [`references/routing-and-safety.md`](./references/routing-and-safety.md) 为准。
- 跳过预检、绕过正式入口，或临时拼 SDK/HTTP 脚本执行业务动作。
- 对象、组织或跨组织关系不明确时继续猜测执行。
- 报告类请求绕过 `jms_report.py`，改用临时拼装逻辑。
