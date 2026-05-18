# JumpServer Skills

`jumpserver-skills` 是一个面向 JumpServer V4.10 的查询、审计分析与模板化使用报告 skill 仓库，适用于对象查询、权限回看、审计调查、治理巡检、访问分析，以及某一天或某一段时间的堡垒机使用报告。它更像一套可复用的 skill 规则与正式入口封装，而不是要求使用者手动拼接脚本命令的 CLI 教程。

仓库内部会按请求类型自动路由到 `subskills/*/scripts/jms_*.py` 子 Skill 正式入口。默认保持只读，仅允许本地运行时写入 `.env` 配置，仅开放已声明的 `create-user`、`create-user-group`、`create-organization`、`invite-user-to-org`、`add-user-to-user-group`、`create-label`、`create-node`、`create-host-asset`、`create-device-asset`、`create-database-asset`、`create-web-asset`、`create-zone`、`create-gateway`、`create-account-template`、`add-account-to-assets`、`add-account-template-to-assets`、`create-command-group`、`create-command-filter-rule`、`create-login-acl`、`create-connect-method-acl`、`create-asset-permission`、`create-login-asset-acl` 与 `create-data-masking-rule` 写操作。

所有 create dry-run、成功和错误输出都会脱敏密文字段或密文语义字段，包括 `secret`、`passphrase`、`private_key`、`access_key`、`api_key`、`token`、`password`。

[English](./README.en.md)

## 最快上手

1. 把这个 skill 接到你的 agent 或 Codex 环境里。仓库中的 [agents/openai.yaml](./agents/openai.yaml) 可以直接作为接入描述使用。
2. 直接用自然语言初始化配置，例如“帮我生成 `.env`，JumpServer 地址是 `https://jump.example.com`，我用 AK/SK 登录”。
3. 然后继续直接提需求，例如“查某某用户在 Default 组织下有哪些资产”或“看看昨天使用情况”。

第一次使用时，优先推荐走“自然语言对话生成 `.env`”这条路径，通常比手动改模板更快。

## 这个 skill 能做什么

| 能力分组 | 适合处理的请求 | 入口名称 | 说明 |
|---|---|---|---|
| 对象查询 | 资产、账号、用户、用户组、组织、平台、节点、标签、网域查询 | `jms_query.py` | 适合精确查询对象清单或读取单个对象详情 |
| 权限关系 | 授权规则、ACL、RBAC、资产授权给了谁、谁能访问某资产、某条权限详情 | `jms_permissions.py` | 默认区分“授权主体”和“实际可访问者”，不把超级管理员默认混入授权主体 |
| 审计调查 | 登录、会话、命令、文件传输、异常行为、高危命令、失败登录调查 | `jms_audit.py` | 适合日志、记录、明细、详情类请求 |
| 公共预检 | 配置检查、连通性、组织切换、端点验证 | `jms_common.py` | 适合所有业务能力执行前的环境确认 |
| 只读运行时查询 | 对象解析、平台解析、许可证、系统设置、存储、工单、报表原始数据 | `jms_query.py` / `jms_runtime_query.py` | 属于查询类能力，统一放在 query 子 Skill |
| 用户有效访问范围 | 某某用户有哪些资产、某某用户在某组织下有哪些节点、某某用户在某资产下有哪些账号/协议 | `jms_access.py` | 优先返回 effective access 结果，不默认展开授权规则说明；资产/节点清单以 `user-assets` / `user-nodes` 为准 |
| 治理巡检 | 资产治理、账号治理、访问分析、系统巡检、capability 聚合分析 | `jms_inspect.py` | 优先走能力化聚合，而不是让使用者手工拼零散查询 |
| 使用报告 | 日报、使用情况、使用分析、某天发生了什么、某时间段排行或概览 | `jms_report.py` | 这类请求默认输出完整 HTML 报告，而不是只给一句摘要 |
| 创建用户 | 创建 JumpServer 本地用户 | `jms_create_user.py` | 无 `--confirm` 只预览；有 `--confirm` 才创建，创建前查重且密文字段或密文语义字段脱敏 |
| 创建用户组 | 创建 JumpServer 用户组，可加入多个用户 ID | `jms_create_user_group.py` | 无 `--confirm` 只预览；有 `--confirm` 才查重并创建；成员通过多个 `--user <user-id>` 添加 |
| 创建组织 | 创建 JumpServer 组织 | `jms_create_org.py` | 无 `--confirm` 只预览；有 `--confirm` 才查重并创建；请求不带 `X-JMS-ORG` |
| 邀请用户加入组织 | 把全局可见用户邀请到目标组织 | `jms_invite_user.py` | 无 `--confirm` 只预览；有 `--confirm` 才从全局组织解析用户并在目标组织邀请 |
| 添加用户到用户组 | 把目标组织内用户加入目标组织内用户组 | `jms_add_user_to_group.py` | 无 `--confirm` 只预览；有 `--confirm` 才在目标组织解析用户和用户组并添加关系 |
| 创建标签 | 创建 JumpServer 标签 | `jms_create_label.py` | 无 `--confirm` 只预览；有 `--confirm` 才在目标组织查重并创建；全局组织禁止 |
| 创建节点 | 创建 JumpServer 资产节点 | `jms_create_node.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/assets/nodes/`；显式组织只限定本次命令，不写 `.env`；全局组织禁止 |
| 创建主机/网络设备/数据库/Web 资产 | 创建 JumpServer 资产 | `jms_create_asset.py` | 无 `--confirm` 只预览；有 `--confirm` 才解析 `platform/nodes/labels/zone/accounts[].template`、查重并创建；未传协议按平台默认协议补齐；密文字段或密文语义字段脱敏；全局组织禁止 |
| 创建网域/网关机器 | 创建 JumpServer 网域和网关机器 | `jms_create_zone_gateway.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/assets/zones/` 或 `/api/v1/assets/gateways/`；网关支持解析 `platform/zone/nodes/labels`；全局组织禁止 |
| 创建账号模板 | 创建 JumpServer 账号模板 | `jms_create_account_template.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/accounts/account-templates/`；`su_from/platforms` 支持解析；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段或密文语义字段脱敏 |
| 给资产添加账号/账号模板 | 给某个资产或一批资产添加账号，或给资产/节点添加账号模板 | `jms_asset_account_bulk.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/accounts/accounts/bulk/`；显式组织只限定本次命令，不写 `.env`；未传组织使用 `.env JMS_ORG_ID`；全局组织禁止；密文字段或密文语义字段脱敏 |
| 创建命令组/命令过滤规则 | 创建 JumpServer 命令组和命令过滤规则 | `jms_create_command_acl.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/acls/command-groups/` 或 `/api/v1/acls/command-filter-acls/`；全局组织禁止 |
| 创建用户登录控制 | 创建 JumpServer 用户登录控制 | `jms_create_login_acl.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/acls/login-acls/`；只能在全局组织下创建；不写 `.env` |
| 创建连接方式过滤器 | 创建 JumpServer 连接方式过滤器 | `jms_create_connect_method_acl.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/acls/connect-method-acls/`；只能在全局组织下创建；不写 `.env` |
| 创建资产授权规则 | 创建 JumpServer 资产授权规则 | `jms_create_asset_permission.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/perms/asset-permissions/`；全局组织禁止 |
| 创建资产连接规则 | 创建 JumpServer 资产连接规则 | `jms_create_login_asset_acl.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/acls/login-asset-acls/`；全局组织禁止 |
| 创建数据脱敏过滤规则 | 创建 JumpServer 数据脱敏过滤规则 | `jms_create_data_masking_rule.py` | 无 `--confirm` 只预览；有 `--confirm` 才 POST `/api/v1/acls/data-masking-rules/`；`accounts` 只支持 `@ALL/@SPEC`；全局组织禁止 |

## 怎么使用这个 skill

1. 准备环境文件。在仓库根目录创建 `.env`，有两种方式：

手动方式：

```bash
cp .env.example .env
```

对话方式：

如果本地配置不完整，运行时也可以直接通过自然语言对话帮你生成 `.env`。它会按固定顺序收集 `JMS_API_URL`、认证方式、组织、超时和 TLS 配置，回显脱敏摘要后写入本地 `.env`。例如：

- “帮我生成 `.env`，JumpServer 地址是 `https://jump.example.com`，我用 AK/SK 登录。”
- “帮我初始化 JumpServer 配置，我用用户名密码登录，不校验证书。”

2. 把这个 skill 接到你的 agent 或 Codex 环境里使用。仓库中的 [agents/openai.yaml](./agents/openai.yaml) 提供了一个现成的 skill 接入描述，可作为引用或注册该 skill 的入口之一。

3. 直接用自然语言描述需求，不需要手动拼接脚本命令。例如“查某某用户在 Default 组织下有哪些资产”“看看昨天使用情况”“看某条授权规则详情”。

4. 根据返回结果继续补充上下文。如果结果提示 `candidate_orgs`、`switchable_orgs`、候选对象或缺少时间范围，就按提示补充组织、对象名称、平台或时间窗口。组织必须先选时，返回里还会带 `reason_code`、`user_message`、`action_hint`、`suggested_commands` 和 `candidate_org_count`，方便直接按提示继续。

使用时不需要记住具体执行命令。这个 skill 会先做预检，再按路由规则自动选择正式入口，并在需要时提示你补充组织、对象或时间范围。

## 手工 CLI 路径

如果你希望直接手动执行正式入口，推荐按下面的顺序使用参数：

1. 优先使用显式参数，例如 `--org-name`、`--name`、`--days`、`--user`
2. 需要补充少量高级字段时，再重复传入 `--filter key=value`
3. 只有兼容旧命令时，才使用 `--filters '{"key":"value"}'`

推荐写法：

```bash
python3 subskills/common/scripts/jms_common.py select-org --org-name Default
python3 subskills/query/scripts/jms_access.py user-assets --org-name Default --username example.user
python3 subskills/query/scripts/jms_query.py object-list --resource organization --name Default
python3 subskills/query/scripts/jms_audit.py audit-analyze --capability session-record-query --days 7 --user example.user
python3 subskills/query/scripts/jms_inspect.py inspect --capability hot-assets-ranking --days 30 --top 10
python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30
```

兼容写法：

```bash
python3 subskills/query/scripts/jms_query.py object-list --resource organization --filters '{"name":"Default"}'
python3 subskills/query/scripts/jms_audit.py audit-analyze --capability session-record-query --filter user=example.user --filter days=7
```

列表型和分析型命令默认会自动翻页抓取并返回查询范围内的全部结果，不再支持 `--limit/--offset`。

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

- “查一下 `Demo-User` 这个用户的详情。”
- “看看名为 `Demo-Node` 的资产节点里有哪些资产。”
- “帮我看 `Linux` 平台下有哪些可用资产。”
- “查某某用户在 Default 组织下有哪些资产。”
- “看这条授权规则详情，顺便告诉我它影响哪些用户和资产。”
- “谁能访问这台资产？”
- “查最近一周的登录审计。”
- “看某个用户的会话记录和异常中断情况。”
- “帮我排查昨天的高危命令和文件传输审计。”
- “看看某天使用情况。”
- “帮我分析下某天堡垒机器的使用情况。”
- “帮我看昨天登录情况。”
- “想看上周谁登录最多。”
- “过一下 3 月上旬哪些资产最活跃。”
- “看某天登录日志明细。”
- “导出某天命令记录详情。”

这类边界尤其重要：

- `某某用户在 Default 组织下有哪些资产`、`某某用户有哪些节点`、`某某用户在某资产下有哪些账号` 这类结果型问法，属于用户有效访问范围，优先返回资产 / 节点 / 账号范围结果，不回退成授权规则说明。
- `某某用户为什么能访问某资产`、`某条授权规则详情` 这类原因型问法，属于权限关系或访问分析。
- `这台资产授权给了谁`、`谁被授权到这台资产` 默认回答授权主体，不默认把超级管理员算进去；只有用户明确要求“实际可访问者（含超管）”时才补充超级管理员集合。
- `某天登录情况`、`某天会话概览`、`某时间段谁最多` 这类表达，属于报告/使用分析。
- `某天登录日志`、`某天命令记录`、`某条会话详情` 这类表达，属于审计调查。
- `创建用户`、`创建用户组`、`创建组织`、`邀请用户加入组织`、`添加用户到用户组`、`创建标签`、`创建节点`、`创建主机/网络设备/数据库/Web 资产`、`创建网域`、`创建网关机器`、`创建账号模板`、`给资产批量添加账号`、`给资产或节点批量添加账号模板`、`创建命令组`、`创建命令过滤规则`、`创建用户登录控制`、`创建连接方式过滤器`、`创建资产授权规则`、`创建资产连接规则`、`创建数据脱敏过滤规则` 属于 create 子 Skill；创建用户组添加成员时只能传用户 ID。邀请用户加入组织时，用户标识可传 username、email、姓名或 UUID，脚本会从全局组织解析用户 UUID。添加用户到用户组时，用户和用户组都只在目标组织解析。创建标签时 `name/value` 必填，`color/comment` 未传不发送。创建节点时只发送 `org_id/full_value/value`。创建主机/网络设备/数据库/Web 资产以完整 `--payload` JSON 为主，常用显式字段可覆盖；`--confirm` 时解析 `platform/nodes/labels/zone/accounts[].template`，未传协议按平台默认协议补齐，密文字段或密文语义字段脱敏。创建网域只发送 `name/assets/comment`；创建网关机器以完整 `--payload` 为主。创建账号模板以完整 `--payload` JSON 为主，常用显式字段可覆盖，密文字段或密文语义字段脱敏。给资产批量添加账号以完整 `--payload` JSON 为主，资产支持 ID、名称或地址，密文字段或密文语义字段脱敏。给资产或节点批量添加账号模板以完整 `--payload` JSON 为主，账号模板支持 ID 或名称，资产支持 ID、名称或地址，节点支持 ID、名称或 full_value。创建命令组只发送 `type/ignore_case/name/content/comment`，且 `name/type/content` 必填。创建命令过滤规则以完整 `--payload` JSON 为主，常用显式字段 `--name`、`--priority`、`--action`、`--account`、`--command-group`、`--is-active` 可覆盖。创建用户登录控制以完整 `--payload` JSON 为主，常用显式字段 `--name`、`--priority`、`--action`、`--reviewer`、`--is-active`、`--comment` 可覆盖，`action` 为 `review` 或 `notice` 时需要 `reviewers`。创建连接方式过滤器以完整 `--payload` JSON 为主，常用显式字段 `--name`、`--action`、`--connect-method`、`--is-active`、`--comment` 可覆盖，`connect_methods` 不做硬编码枚举，`--confirm` 时查询连接方式选项接口并发送选项 `value` 字段，`label` 只作为显示名。创建资产授权规则以完整 `--payload` JSON 为主，`assets/nodes/users/user_groups` 会在 `--confirm` 时复用现有解析能力转成 UUID 或 `pk`，显式协议按 `label/value` 解析并发送 `value`，账号默认 `@ALL`，动作默认全部 value。创建资产连接规则和数据脱敏过滤规则以完整 `--payload` JSON 为主，`users.type=ids` / `assets.type=ids` 会在 `--confirm` 时复用现有用户/资产解析能力转成 ID。创建节点、主机/网络设备/数据库/Web 资产、网域、网关机器、账号模板、给资产批量添加账号、给资产或节点批量添加账号模板、命令组、命令过滤规则、资产授权规则、资产连接规则、数据脱敏过滤规则显式 `--org-id` / `--org-name` 复用组织解析且只限定本次命令，不写 `.env`，未传组织时使用 `.env JMS_ORG_ID`，全局组织禁止。创建用户登录控制和连接方式过滤器只能在全局组织下创建，显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`，且不写 `.env`。

## 使用报告与时间范围规则

只要请求的核心对象是某一天或某一段时间内的 JumpServer 使用数据分析，就会优先走模板化报告流程。这包括：

- 使用报告、日报、周报、月报
- 使用情况、使用分析、使用统计、使用汇总、使用概览
- 审计分析、某天发生了什么
- 某天登录 / 会话 / 命令 / 传输情况
- 某时间段的排行、TOP、谁最多、哪些资产最活跃

这类请求默认直接产出完整 HTML 报告，不先回退成自由文本摘要。只有当用户明确说“不要生成报告，直接分析”“先简单说下”“只给我结论”“不用模板”时，才允许跳过模板直接给简短分析。

日期表达速查：

- `某天` 只是占位说法，用户不需要真的输入“某天”。常见自然语言表达包括：
  - `昨天`
  - `20260310`
  - `2026-03-10`
  - `2026/03/10`
  - `3月10号`
  - `3 月 10 日`
  - `2026年3月10日`
- `某时间段` 也只是占位说法。常见自然语言表达包括：
  - `上周`
  - `本月`
  - `3月上旬`
  - `2026-03-10 到 2026-03-24`
  - `2026/03/10 到 2026/03/24`
  - `3月10号到3月24号`
- 用户自然语言会先被归一化，再进入正式入口。正式入口最终统一落到 `--date`、`--period` 或 `--date-from/--date-to`。

时间表达会先归一化为明确时间窗：

- “昨天” -> 前一天 `00:00:00 ~ 23:59:59`
- `20260310` -> `2026-03-10 00:00:00 ~ 23:59:59`
- `2026-03-10` / `2026/03/10` / `3月10号` / `3 月 10 日` / `2026年3月10日` -> 同一天 `00:00:00 ~ 23:59:59`
- “上周” -> 上一个自然周，周一 `00:00:00 ~ 周日 23:59:59`
- “本月” -> 本月 1 日 `00:00:00` 到当前日期或月末 `23:59:59`

常见归一化结果示例：

- `帮我分析下20260310的堡垒机使用情况` -> `date_from=2026-03-10 00:00:00`，`date_to=2026-03-10 23:59:59`
- `帮我分析下3月10号的堡垒机器使用情况` -> `date_from=当日 00:00:00`，`date_to=当日 23:59:59`
- `帮我分析下上周的堡垒机使用情况` -> `period=上周`，最终归一化为上周周一 `00:00:00` 到周日 `23:59:59`
- `帮我分析下2026-03-10到2026-03-24的堡垒机使用情况` -> 最终归一化为 `date_from=2026-03-10 00:00:00`，`date_to=2026-03-24 23:59:59`

报告固定输出到 `reports/JumpServer-YYYY-MM-DD.html`。如果请求里涉及命令审计字段，报告会按既定规则处理可访问的 command storage 汇总，不需要使用者手动选择内部取数逻辑。
报告成功时，默认先回显“报告已生成”，并附上报告文件路径、文件存在性/大小、模板路径、字段元数据路径、时间范围、组织和 `validation_summary`；简短摘要只能作为补充，不能替代这些报告产物信息。

## 组织选择与阻塞规则

- 当前组织保存在 `.env` 的 `JMS_ORG_ID`；业务命令未显式传组织时使用这个当前组织。
- 报告类 `daily-usage` 未显式传组织时，默认使用全局组织 `00000000-0000-0000-0000-000000000000`，且不写 `.env JMS_ORG_ID`。
- 报告类 `daily-usage` 显式传 `--org-id` 或 `--org-name` 且匹配成功时，按该组织生成报告，并写入 `.env JMS_ORG_ID`。
- 普通查询显式指定组织时，先解析成组织 ID，再按该组织执行；命令级 `--org-id` / `--org-name` 只限定本次命令，不写回 `.env`。
- create 子 Skill 例外：创建用户/用户组传 `--org-name <name> --confirm` 时，唯一匹配后会写入 `.env JMS_ORG_ID`，再执行创建；未匹配或多匹配时返回 `candidate_orgs`。邀请用户加入组织、添加用户到用户组、创建标签、创建节点、创建主机/网络设备/数据库/Web 资产、创建网域、创建网关机器、创建账号模板、给资产批量添加账号、给资产或节点批量添加账号模板、创建命令组、创建命令过滤规则、创建资产授权规则、创建资产连接规则、创建数据脱敏过滤规则的目标组织只限定本次命令，不写 `.env`；创建标签、节点、主机/网络设备/数据库/Web 资产、网域、网关机器、账号模板、给资产批量添加账号、给资产或节点批量添加账号模板、命令组、命令过滤规则、资产授权规则、资产连接规则、数据脱敏过滤规则未传组织时使用 `.env JMS_ORG_ID`，且禁止全局组织。创建用户登录控制和连接方式过滤器只能在全局组织下创建；显式组织或 `.env JMS_ORG_ID` 最终都必须是全局组织 ID `00000000-0000-0000-0000-000000000000`，且不写 `.env`。创建组织不带 `X-JMS-ORG`，创建成功后不切换 `.env JMS_ORG_ID`。
- 切换当前组织使用 `select-org --org-id <org-id> --confirm` 或 `select-org --org-name <org-name> --confirm`，确认后写入 `.env JMS_ORG_ID`。
- 多组织且没有当前组织时，先返回 `candidate_orgs` 并阻塞，要求选择组织。
- 如果当前组织是 A、目标对象在 B，不会自动跨组织继续执行。

出现下面这些情况时，skill 会先阻塞，而不是继续猜测执行：

- 配置或鉴权不完整
- 对象名称重名或平台不明确
- 查询结果跨组织
- 多组织且没有当前组织可用
- 用户试图绕过正式入口或跳过预检

## 文档地图

| 文件 | 用途 |
|---|---|
| [SKILL.md](./SKILL.md) | skill 的顶部路由规则、组织优先级与响应约束 |
| [agents/openai.yaml](./agents/openai.yaml) | skill 接入描述与默认提示词入口 |
| [references/routing-and-safety.md](./references/routing-and-safety.md) | 全仓库路由、正式入口边界、允许写操作白名单和全局阻塞规则 |
| [subskills/query/references/routing-playbook.md](./subskills/query/references/routing-playbook.md) | 普通路由、典型触发词、阻塞规则与反例 |
| [subskills/query/references/report-template-playbook.md](./subskills/query/references/report-template-playbook.md) | 模板化报告流程、组织优先级、时间范围与报告规则 |
| [subskills/common/references/runtime.md](./subskills/common/references/runtime.md) | 预检流程、环境变量模型、组织选择与运行时约束 |
| [subskills/query/references/capabilities.md](./subskills/query/references/capabilities.md) | capability 能力目录与能力说明 |
| [subskills/query/references/assets.md](./subskills/query/references/assets.md) | 资产、账号、用户、节点、平台等对象查询说明 |
| [subskills/create/references/index.md](./subskills/create/references/index.md) | create 子 skill 已支持命令与参考文档索引 |
| [subskills/query/references/permissions.md](./subskills/query/references/permissions.md) | 权限、ACL、RBAC 与授权关系查询说明 |
| [subskills/query/references/audit.md](./subskills/query/references/audit.md) | 登录、会话、命令、文件传输等审计说明 |
| [subskills/query/references/diagnose.md](./subskills/query/references/diagnose.md) | 连通性、对象解析、访问分析、系统巡检与治理说明 |
| [subskills/common/references/safety-rules.md](./subskills/common/references/safety-rules.md) | common 本地写入边界 |
| [subskills/common/references/troubleshooting.md](./subskills/common/references/troubleshooting.md) | common 预检、组织和连通性排障 |

## 不支持范围

- 创建类写操作只开放白名单入口：`jms_create_user.py create-user`、`jms_create_user_group.py create-user-group`、`jms_create_org.py create-organization`、`jms_invite_user.py invite-user-to-org`、`jms_add_user_to_group.py add-user-to-user-group`、`jms_create_label.py create-label`、`jms_create_node.py create-node`、`jms_create_asset.py create-host-asset`、`jms_create_asset.py create-device-asset`、`jms_create_asset.py create-database-asset`、`jms_create_asset.py create-web-asset`、`jms_create_zone_gateway.py create-zone`、`jms_create_zone_gateway.py create-gateway`、`jms_create_account_template.py create-account-template`、`jms_asset_account_bulk.py add-account-to-assets`、`jms_asset_account_bulk.py add-account-template-to-assets`、`jms_create_command_acl.py create-command-group`、`jms_create_command_acl.py create-command-filter-rule`、`jms_create_login_acl.py create-login-acl`、`jms_create_connect_method_acl.py create-connect-method-acl`、`jms_create_asset_permission.py create-asset-permission`、`jms_create_login_asset_acl.py create-login-asset-acl`、`jms_create_data_masking_rule.py create-data-masking-rule`。未列入白名单的对象创建一律不开放。
- 所有对象更新、删除、解锁一律不开放。
- 权限类仅开放白名单中的创建入口：`create-command-filter-rule`、`create-login-acl`、`create-connect-method-acl`、`create-asset-permission`、`create-login-asset-acl`、`create-data-masking-rule`。除此之外，权限创建、更新、追加关系、移除关系、删除一律不开放。
- 跳过预检直接执行业务动作。
- 临时 SDK/HTTP 脚本绕过正式入口。
- 报告类请求绕过 `jms_report.py` 正式入口，改用现场临时拼装逻辑。
- 在对象不明确、组织不明确或跨组织场景下继续猜测执行。
