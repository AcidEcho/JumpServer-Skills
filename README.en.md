# JumpServer Skills

`jumpserver-skills` is a natural-language operations skill repository for JumpServer V4.10. It supports object lookup, permission readback, audit investigation, governance inspection, access analysis, current-identity SSH/MySQL/MariaDB connections, template-based usage reports, and controlled object creation. Users do not need to manually compose script commands. Persistent business writes remain limited to allowlisted create entrypoints; Access may create only a short-lived, non-reusable connection token after explicit confirmation, and create output redacts secret fields automatically.

[中文](./README.md)

## Quick Start

1. Connect this skill to your agent or Codex environment. The repository file [agents/openai.yaml](./agents/openai.yaml) can be used directly as the integration description.
2. Initialize configuration in natural language, for example: "Help me generate `.env`. The JumpServer URL is `https://jump.example.com`, and I log in with AK/SK."
3. Continue with direct requests, for example: "Which assets can this user access in the Default organization?" or "Show me yesterday's usage."

For first-time use, the natural-language `.env` generation path is usually faster than manually editing a template.

## What This Skill Can Do

| Capability Group | You Can Ask | Automatic Entrypoint | Output and Safety Boundary |
|---|---|---|---|
| Environment preflight and organization selection | “Check whether the configuration works”, “test connectivity”, “switch to the Default organization” | `jms_common.py` | Confirms `.env`, authentication, organization, and endpoint first; local writes are limited to `.env`, `.env.lock`, and `.env.recovery-*` recovery files |
| Object lookup | "Find this asset/user/account/node/label", "show details for this platform" | `jms_query.py` / `jms_runtime_query.py` | Returns object lists, details, or candidates; asks the user to confirm when an object is ambiguous |
| User effective access | "Which assets/nodes/accounts/protocols can this user access?" | Query: `subskills/query/scripts/jms_access.py user-assets/user-nodes/user-asset-access` | Returns effective access and never creates a connection token |
| Current-identity one-time SSH | "Connect to this host through JumpServer" | Access: `subskills/access/scripts/jms_ssh_connect.py connect-info` | Requires a unique asset/managed account and explicit `--confirm`, with a non-reusable token |
| Current-identity MySQL/MariaDB SQL execution | "Connect to 10.1.12.224 and run SHOW DATABASES" | Access: `subskills/access/scripts/jms_db_connect.py db-query` | Selects one permitted `mysql` or `mariadb` protocol and uses a one-time `db_client` token; forwards SQL to JumpServer policy and never returns the token password |
| Permission relationship readback | "Who is this asset authorized to?", "why can this user access it?", "show details for this permission rule" | `jms_permissions.py` | Keeps authorization subjects, actual access users, and super-admin impact separate |
| Audit investigation | "Who failed to log in yesterday?", "query a user's sessions/commands/file transfers", "analyze high-risk commands" | `jms_audit.py` | Queries logs, records, details, or aggregate results under an explicit organization and time window |
| Governance inspection and access analysis | "Run asset governance inspection", "show component load", "analyze password-change failures", "show access rankings/abnormal behavior" | `jms_inspect.py` / `jms_audit.py` | Uses built-in capability aggregation instead of making users stitch together scattered queries |
| Usage reports | "Generate a daily report", "analyze bastion usage on 2026-03-10", "show a usage overview for this time range" | `jms_report.py` | Generates a complete HTML report by default and returns the report path, time window, organization, and validation summary |
| Controlled creation | "Create a user/org/label/node/asset/zone/gateway/account template/permission rule/ACL/masking rule" | [create entrypoint index](./subskills/create/references/index.md) | Only allowlisted create entrypoints are open; without `--confirm` only previews, with `--confirm` creates; secret fields are redacted |

Create capabilities currently cover 23 allowlisted commands, including users and organizations, labels and nodes, host/network device/database/web assets, zones and gateways, account templates and bulk account binding, command groups and command filter rules, login control, connect method filters, asset permission rules, login asset rules, and data masking rules. For complete commands, scripts, and field documentation, see the [create entrypoint index](./subskills/create/references/index.md).

## How To Use This Skill

1. Prepare an environment file. Create `.env` in the repository root in one of two ways:

Manual method:

```bash
cp .env.example .env
```

Conversation method:

If the local configuration is incomplete, the runtime can generate `.env` through natural-language conversation. It collects `JMS_API_URL`, authentication mode, organization, timeout, and TLS settings in a fixed order, echoes a redacted summary, and writes the local `.env`. For example:

```text
Help me generate `.env`. The JumpServer URL is `https://jump.example.com`, and I log in with AK/SK.
```
```text
Help me initialize JumpServer config. I log in with username and password, and I do not verify certificates.
```

2. Connect this skill to your agent or Codex environment. [agents/openai.yaml](./agents/openai.yaml) provides a ready-to-use skill integration description that can be used as a reference or registration entrypoint.

If the host can register only one subskill, use `subskills/common|access|query|create|update/agents/openai.yaml`. Access is an optional standalone entrypoint. See [standalone subskill registration](./references/subskill-registration.md) for cwd and full-repository requirements.

3. Describe requests directly in natural language. You do not need to manually compose script commands. For example: "Which assets can this user access in the Default organization?", "Show me yesterday's usage", or "Show details for this permission rule."

4. Add context based on returned prompts. If the result contains `candidate_orgs`, `switchable_orgs`, candidate objects, or a missing time range, provide the organization, object name, platform, or time window as prompted. When organization selection is required, the response also includes `reason_code`, `user_message`, `action_hint`, `suggested_commands`, and `candidate_org_count` so the next step is clear.

You do not need to remember specific commands. This skill runs preflight first, automatically chooses the formal entrypoint according to routing rules, and asks for organization, object, or time-range details only when needed.

## Environment Variables

The repository root provides [`.env.example`](./.env.example) as a template. In actual use, prepare a `.env` file in the repository root. You can copy the template and edit it, or create it manually based on the template.

If you do not want to edit it manually, you can generate `.env` through natural-language conversation. When missing or incomplete configuration is detected, the skill collects the required fields in order and writes the configuration to the local `.env` through the formal entrypoint.

If you want to provide everything up front, these are usually enough:

- `JMS_API_URL`
- one complete authentication pair: `JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` or `JMS_USERNAME/JMS_PASSWORD`
- `JMS_ORG_ID`, which can be left empty first and later written by `select-org --confirm`
- `JMS_TIMEOUT`, which uses the default when omitted
- `JMS_VERIFY_TLS`, which defaults to `false` when omitted

| Variable | Required | Notes |
|---|---|---|
| `JMS_API_URL` | required | JumpServer API / access URL |
| `JMS_ACCESS_KEY_ID` | paired with `JMS_ACCESS_KEY_SECRET`, or use username/password instead | API Access Key ID |
| `JMS_ACCESS_KEY_SECRET` | paired with `JMS_ACCESS_KEY_ID`, or use username/password instead | API Access Key Secret |
| `JMS_USERNAME` | paired with `JMS_PASSWORD`, or use AK/SK instead | JumpServer login username |
| `JMS_PASSWORD` | paired with `JMS_USERNAME`, or use AK/SK instead | JumpServer login password |
| `JMS_ORG_ID` | optional | current organization ID, writable by `select-org --confirm` |
| `JMS_TIMEOUT` | optional | request timeout in seconds |
| `JMS_VERIFY_TLS` | optional | whether to verify certificates, default `false` |

Environment variable rules:

- `JMS_API_URL` must be provided.
- At least one complete authentication pair must be provided: `JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` or `JMS_USERNAME/JMS_PASSWORD`.
- `.env` is loaded automatically by the runtime.
- If `.env` is missing or incomplete, it can be completed through natural-language conversation; after confirmation, the runtime generates or overwrites the local `.env`.
- Before first use, make sure the URL, authentication method, organization, timeout, and TLS settings are complete.
- If you switch the JumpServer instance, account, organization, or `.env` content, rerun full preflight.

## Typical Request Examples

| Scenario | You Can Ask | Automatic Route |
|---|---|---|
| Object lookup | "Show details for user `Demo-User`", "show which assets are under node `Demo-Node`", "show available assets on the `Linux` platform" | `jms_query.py` |
| User effective access scope | "Which assets can this user access in the Default organization?", "which nodes can this user access?", "which accounts and protocols can this user use on this asset?" | Query: `subskills/query/scripts/jms_access.py user-assets/user-nodes/user-asset-access` |
| Current-identity one-time SSH | "Connect to 10.1.1.1 through JumpServer", "get SSH information for this host before deployment" | Access: `subskills/access/scripts/jms_ssh_connect.py connect-info --confirm` |
| Current-identity MySQL/MariaDB SQL execution | "Connect to 10.1.12.224 and run `SHOW DATABASES;` or an update statement" | Access: `subskills/access/scripts/jms_db_connect.py db-query --confirm` |
| Permission relationship readback | "Who is this asset authorized to?", "why can this user access this asset?", "show details for this permission rule" | `jms_permissions.py` |
| Audit investigation | "Query login audit for the last week", "show a user's session records and abnormal interruptions", "export command records for a specific day" | `jms_audit.py` |
| Usage reports | "Show me yesterday's usage", "show who logged in most last week", "check which assets were most active in early March" | `jms_report.py` |
| Governance inspection | "Run an asset governance inspection", "show component CPU/memory load", "analyze password-change failures over the last 30 days" | `jms_inspect.py` |
| Controlled creation | "Create a user", "create a node", "create a host asset", "create an asset permission rule", "create a data masking rule" | create subskill, see the [create index](./subskills/create/references/index.md) |

Ambiguous request wording is handled by these rules:

| Wording Pattern | Classification |
|---|---|
| "Which assets / nodes / accounts / protocols can this user access?" | User effective access scope, returning result lists |
| "Connect to this host / log in through JumpServer / get one-time SSH information" | Current API identity SSH connection; never issues a token for another user |
| "Connect to this database / run SHOW DATABASES / run SQL" | Current API identity MySQL/MariaDB `db_client`; never reuses an SSH token; JumpServer controls SQL permission |
| "Why can this user access it? / permission rule details / authorization basis" | Permission relationship readback, explaining authorization sources |
| "Who is this asset authorized to? / who is authorized to this asset?" | Answers authorization subjects by default and does not include super admins by default |
| "Login situation on a day / session overview / who had the most / which were most active" | Usage report or usage analysis |
| "Login logs on a day / command records / session details / file transfer details" | Audit investigation |

## Usage Reports and Time-Range Rules

If the core request is JumpServer overall usage, overview, summary, ranking, or distribution for a specific day or time range, the template-based report flow is preferred. The template is skipped only when the user explicitly says "do not generate a report", "analyze directly", "give me a quick summary", "only give me the conclusion", or "do not use the template".

| Expression Type | Route |
|---|---|
| Usage report, daily report, weekly report, monthly report, usage situation, usage analysis, usage statistics, usage overview | `jms_report.py daily-usage-prepare` -> Skill summary -> `jms_report.py daily-usage-render` |
| What happened on a day, login/session/command/transfer activity on a day, TOP list or ranking for a time range | `jms_report.py daily-usage-prepare` -> Skill summary -> `jms_report.py daily-usage-render` |
| Login logs, session details, command records, file transfer details, single audit record | `jms_audit.py` |
| Explicit "do not generate a report / only give conclusions / do not use the template" | May skip the HTML report and return a short analysis |

Natural-language time is normalized before entering the formal entrypoint:

| User Time Expression | Normalized Result |
|---|---|
| `yesterday` | previous day `00:00:00 ~ 23:59:59` |
| `20260310`, `2026-03-10`, `2026/03/10`, `March 10`, `March 10, 2026` | same day `00:00:00 ~ 23:59:59` |
| `last week` | previous natural week, Monday `00:00:00 ~ Sunday 23:59:59` |
| `this month` | first day of this month `00:00:00` to current date or month end `23:59:59` |
| `2026-03-10 to 2026-03-24`, `March 10 to March 24` | start day `00:00:00` to end day `23:59:59` |

The formal entrypoint ultimately uses `--date`, `--period`, or `--date-from/--date-to`. The Skill writes its analysis from `summary_input` and carries the prepare response's `report_binding` unchanged into the summary JSON. Reports are written to `reports/JumpServer-YYYY-MM-DD-<context-id>-<run-id>.html`; on success, the response first says "report generated", then returns the report path, file existence/size, template path, field metadata path, time range, organization, and `validation_summary`. A short summary can only supplement these report artifacts, not replace them.

## Organization Selection and Blocking Rules

The current organization is stored in `.env` as `JMS_ORG_ID`. When a business request does not specify an organization, it usually uses the current organization. Reports and some create commands have special rules.

| Scenario | Organization Handling | Writes `.env JMS_ORG_ID` |
|---|---|---|
| Manually switch current organization | `select-org --org-id <org-id> --confirm` or `select-org --org-name <name> --confirm` | yes |
| Ordinary query with explicit organization | Resolve the organization ID first, then run under that organization | no, command-scoped only |
| Ordinary query without explicit organization | Use `.env JMS_ORG_ID` | no additional write |
| Usage report without explicit organization | Default to Global organization `00000000-0000-0000-0000-000000000000` | no |
| Usage report with explicit organization and successful match | Generate the report under the specified organization | no, report-scoped only |
| Create command | Follow the [write-operation allowlist](./references/routing-and-safety.md) and [create index](./subskills/create/references/index.md) | depends on the command |

Create organization rules are not repeated in full in this README. The boundaries to remember are: most create commands treat explicit organization as command-scoped; when no organization is passed, some commands use `.env JMS_ORG_ID`; create commands that need a target organization usually block Global organization; `create-login-acl` and `create-connect-method-acl` must run in Global organization; `create-organization` sends no `X-JMS-ORG` and does not switch the current organization after success.

In these cases, the skill blocks instead of continuing by guessing:

| Blocking Reason | Handling |
|---|---|
| Configuration or authentication is incomplete | Complete `.env` or run preflight first |
| Object name is duplicated, platform is unclear, or organization is unclear | Return candidates and ask the user to confirm |
| Query results cross organizations, or the current organization differs from the target object's organization | Require an explicit target organization |
| SSH target asset, protocol, or managed-credential account is not unique | Return candidates or block without creating a connection token |
| Database token/port shape is wrong, or the user asks to bypass JumpServer SQL policy | Block and follow the Access database connection reference |
| Multiple organizations are available and no current organization is selected | Return `candidate_orgs` and require organization selection first |
| User tries to bypass formal entrypoints, skip preflight, or assemble temporary scripts | Block and require formal entrypoints |

## Document Map

| What You Want To Know | Read This | Purpose |
|---|---|---|
| How to integrate this skill | [SKILL.md](./SKILL.md), [agents/openai.yaml](./agents/openai.yaml) | Top-level routing, default prompt, response constraints |
| Safety boundaries and allowlist | [references/routing-and-safety.md](./references/routing-and-safety.md) | Formal entrypoint boundaries, allowed write operations, global blocking rules |
| How query, effective-access, permission, audit, and inspection routing works | [intent-routing.md](./subskills/query/references/intent-routing.md), [routing-playbook.md](./subskills/query/references/routing-playbook.md), [capabilities.md](./subskills/query/references/capabilities.md) | Query intent classification, trigger words, capability catalog, blocking rules, counterexamples |
| How Access one-time SSH creation and use works | [ssh-connection.md](./subskills/access/references/ssh-connection.md) | `connect-info`, `users/self`, confirmation gate, API flow, token lifecycle, and safety boundaries |
| How Access connects to MySQL/MariaDB and runs SQL | [database-connection.md](./subskills/access/references/database-connection.md) | `db-query`, protocol selection, `db_client`, `client-url` endpoint, JumpServer SQL policy, and token lifecycle |
| Component load and password-change failure analysis | [component-load-and-password-report.md](./subskills/query/references/component-load-and-password-report.md) | Metric fields, load thresholds, failure classification, and statistical scope |
| How usage reports are generated | [subskills/query/references/report-template-playbook.md](./subskills/query/references/report-template-playbook.md) | Template report flow, time ranges, organization priority |
| Object lookup, permission, and audit details | [assets.md](./subskills/query/references/assets.md), [permissions.md](./subskills/query/references/permissions.md), [audit.md](./subskills/query/references/audit.md), [diagnose.md](./subskills/query/references/diagnose.md) | Asset/account/user/node lookup, authorization relationships, log audit, governance diagnosis |
| What create can create | [subskills/create/references/index.md](./subskills/create/references/index.md) | Create commands, entrypoint scripts, field-document index |
| Runtime, preflight, and troubleshooting | [runtime.md](./subskills/common/references/runtime.md), [safety-rules.md](./subskills/common/references/safety-rules.md), [troubleshooting.md](./subskills/common/references/troubleshooting.md) | `.env`, organization selection, local-write boundary, common failure handling |
| Standalone registration and extension | [subskill-registration.md](./references/subskill-registration.md), [ADD-SUBSKILL-GUIDE.md](./ADD-SUBSKILL-GUIDE.md) | Single-subskill integration, capability/command/domain extension, and acceptance checks |

## Unsupported Scope

The following requests are not executed:

- Persistent server-side writes are only open to allowlisted create entrypoints; Access `connect-info --confirm` and `db-query --confirm` may also create an `is_reusable=false` short-lived token for the current identity. Object updates, deletion, unlocking, and non-allowlisted permission creation, changes, or removal are not executed; database SQL permission is delegated to JumpServer policy and database privileges. For the complete scope, see [`references/routing-and-safety.md`](./references/routing-and-safety.md).
- Skipping preflight, bypassing formal entrypoints, or using temporary SDK/HTTP scripts for business actions.
- Continuing by guessing when objects, organizations, or cross-organization relationships are unclear.
- Bypassing `jms_report.py` for report requests and replacing it with ad hoc assembly logic.
