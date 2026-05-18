# JumpServer Skills

`jumpserver-skills` is a skill repository for JumpServer V4.10 that focuses on query workflows, audit investigation, and template-based usage reports. It is designed for object lookup, permission readback, audit investigation, governance inspection, access analysis, and bastion usage reports for a specific day or time range. It is closer to a reusable skill package with formal entrypoints than to a CLI tutorial that expects users to manually compose script commands.

Inside the repository, requests are automatically routed to the `subskills/*/scripts/jms_*.py` child-skill entrypoints. The repository stays read-only by default, only allowing local runtime writes to `.env` configuration, and it only supports the declared `create-user`, `create-user-group`, `create-organization`, `invite-user-to-org`, `add-user-to-user-group`, `create-label`, `create-node`, `create-host-asset`, `create-device-asset`, `create-database-asset`, `create-web-asset`, `create-zone`, `create-gateway`, `create-account-template`, `add-account-to-assets`, `add-account-template-to-assets`, `create-command-group`, `create-command-filter-rule`, `create-login-acl`, `create-connect-method-acl`, `create-asset-permission`, `create-login-asset-acl`, and `create-data-masking-rule` write operations.

All create dry-run, success, and error output redacts secret fields or secret-like fields, including `secret`, `passphrase`, `private_key`, `access_key`, `api_key`, `token`, and `password`.

[中文](./README.md)

## Quick Start

1. Connect this skill to your agent or Codex environment. The repository file [agents/openai.yaml](./agents/openai.yaml) can be used directly as the integration description.
2. Initialize the configuration in natural language, for example: "Help me generate `.env`. My JumpServer URL is `https://jump.example.com`, and I log in with AK/SK."
3. Then continue with direct requests such as "Which assets can this user access in the Default organization?" or "Show me yesterday's usage."

For first-time use, the natural-language `.env` generation path is usually the fastest option.

## What This Skill Can Do

| Capability Group | Suitable Requests | Entrypoint | Notes |
|---|---|---|---|
| Object queries | queries for assets, accounts, users, user groups, orgs, platforms, nodes, labels, and domains | `jms_query.py` | Best for exact object lists or reading a single object in detail |
| Permission relationships | permission rules, ACL, RBAC, who can access an asset, details of a permission rule | `jms_permissions.py` | Read and explain only; no permission writes |
| Audit investigation | login, session, command, file transfer, abnormal behavior, high-risk commands, failed login investigations | `jms_audit.py` | Best for logs, records, details, and event-level requests |
| Shared preflight | config checks, connectivity, org switching, endpoint verification | `jms_common.py` | Best before any business query or write operation |
| Read-only runtime queries | object resolution, platform resolution, license, system settings, storage, tickets, raw reports | `jms_query.py` / `jms_runtime_query.py` | Query-only capabilities under the query subskill |
| User effective access scope | which assets or nodes a user can access, or which accounts/protocols a user can use on an asset | `jms_access.py` | Returns effective access scope first instead of defaulting to permission-rule explanations |
| Governance inspection | asset governance, account governance, access analysis, system inspection, capability-based aggregate analysis | `jms_inspect.py` | Prefer capability aggregation instead of forcing users to stitch together scattered queries |
| Usage reports | daily reports, usage situation, usage analysis, what happened on a day, rankings or overviews for a time range | `jms_report.py` | These requests produce a complete HTML report instead of a one-line summary |
| Create user | create JumpServer local users | `jms_create_user.py` | Dry-run without `--confirm`; create only with `--confirm`, duplicate check, and redacted secret or secret-like fields |
| Create user group | create JumpServer user groups, optionally with multiple user IDs | `jms_create_user_group.py` | Dry-run without `--confirm`; create only with `--confirm`; add members with multiple `--user <user-id>` arguments |
| Create organization | create JumpServer organizations | `jms_create_org.py` | Dry-run without `--confirm`; create only with `--confirm`; request sends no `X-JMS-ORG` |
| Invite user to organization | invite globally visible users into a target organization | `jms_invite_user.py` | Dry-run without `--confirm`; create only with `--confirm`; users are resolved from the global organization |
| Add user to user group | add target-organization users into target-organization user groups | `jms_add_user_to_group.py` | Dry-run without `--confirm`; create only with `--confirm`; users and groups are resolved inside the target organization |
| Create label | create JumpServer labels | `jms_create_label.py` | Dry-run without `--confirm`; create only with `--confirm` after duplicate check in the target organization; Global organization is blocked |
| Create node | create JumpServer asset nodes | `jms_create_node.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/assets/nodes/`; explicit organization is command-scoped and does not write `.env`; Global organization is blocked |
| Create host/device/database/web asset | create JumpServer assets | `jms_create_asset.py` | Dry-run without `--confirm`; create only with `--confirm` after resolving `platform/nodes/labels/zone/accounts[].template`; default protocols come from the platform; secret or secret-like fields are redacted; Global organization is blocked |
| Create zone/gateway | create JumpServer zones and gateway machines | `jms_create_zone_gateway.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/assets/zones/` or `/api/v1/assets/gateways/`; gateways resolve `platform/zone/nodes/labels`; Global organization is blocked |
| Create account template | create JumpServer account templates | `jms_create_account_template.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/accounts/account-templates/`; `su_from/platforms` are resolved on confirm; explicit organization is command-scoped and does not write `.env`; `.env JMS_ORG_ID` is used when no organization is passed; Global organization is blocked; secret or secret-like fields are redacted |
| Add account/template to assets | add accounts to one or more assets, or add account templates to assets/nodes | `jms_asset_account_bulk.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/accounts/accounts/bulk/`; explicit organization is command-scoped and does not write `.env`; `.env JMS_ORG_ID` is used when no organization is passed; Global organization is blocked; secret or secret-like fields are redacted |
| Create command group/filter rule | create JumpServer command groups and command filter rules | `jms_create_command_acl.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/acls/command-groups/` or `/api/v1/acls/command-filter-acls/`; Global organization is blocked |
| Create login ACL | create JumpServer login ACLs | `jms_create_login_acl.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/acls/login-acls/`; only Global organization is allowed; does not write `.env` |
| Create connect method filter | create JumpServer connect method filters | `jms_create_connect_method_acl.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/acls/connect-method-acls/`; only Global organization is allowed; does not write `.env` |
| Create asset permission | create JumpServer asset permission rules | `jms_create_asset_permission.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/perms/asset-permissions/`; Global organization is blocked |
| Create login asset ACL | create JumpServer login asset ACLs | `jms_create_login_asset_acl.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/acls/login-asset-acls/`; Global organization is blocked |
| Create data masking rule | create JumpServer data masking rules | `jms_create_data_masking_rule.py` | Dry-run without `--confirm`; create only with `--confirm` by POSTing `/api/v1/acls/data-masking-rules/`; `accounts` only supports `@ALL/@SPEC`; Global organization is blocked |

## How To Use This Skill

1. Prepare the environment file. Create `.env` in the repository root. There are two ways to do it:

Manual method:

```bash
cp .env.example .env
```

Conversation method:

If local configuration is incomplete, the runtime can also generate `.env` directly through natural-language conversation. It collects `JMS_API_URL`, authentication mode, organization, timeout, and TLS settings in a fixed order, then writes the local `.env` after showing a masked summary. For example:

- "Help me generate `.env`. My JumpServer URL is `https://jump.example.com`, and I log in with AK/SK."
- "Help me initialize JumpServer config. I log in with username and password, and I do not want certificate verification."

2. Connect this skill to your agent or Codex environment. The repository file [agents/openai.yaml](./agents/openai.yaml) provides a ready-to-use skill integration description and can serve as one of the entrypoints for referencing or registering the skill.

3. Describe requests directly in natural language instead of manually assembling script commands. For example: "Which assets can this user access in the Default organization?", "Show me yesterday's usage", or "Show the details of this permission rule."

4. Add context based on the returned result. If the result shows `candidate_orgs`, `switchable_orgs`, candidate objects, or a missing time range, follow the prompt and provide the organization, object name, platform, or time window. When organization selection is mandatory, the response also includes `reason_code`, `user_message`, `action_hint`, `suggested_commands`, and `candidate_org_count` so the next step is explicit.

You do not need to remember specific execution commands. This skill performs preflight first, then routes to the formal entrypoint automatically, and prompts for organization, object, or time-range details only when needed.

## Manual CLI Path

If you want to run the formal entrypoints manually, use parameters in this order:

1. Prefer explicit arguments such as `--org-name`, `--name`, `--days`, and `--user`
2. Use repeated `--filter key=value` only for a few advanced fields
3. Keep `--filters '{"key":"value"}'` only for backward compatibility

Recommended style:

```bash
python3 subskills/common/scripts/jms_common.py select-org --org-name Default
python3 subskills/query/scripts/jms_access.py user-assets --org-name Default --username example.user
python3 subskills/query/scripts/jms_query.py object-list --resource organization --name Default
python3 subskills/query/scripts/jms_audit.py audit-analyze --capability session-record-query --days 7 --user example.user
python3 subskills/query/scripts/jms_inspect.py inspect --capability hot-assets-ranking --days 30 --top 10
python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30
```

Compatibility style:

```bash
python3 subskills/query/scripts/jms_query.py object-list --resource organization --filters '{"name":"Default"}'
python3 subskills/query/scripts/jms_audit.py audit-analyze --capability session-record-query --filter user=example.user --filter days=7
```

List and analysis commands now auto-paginate and return the full result set for the requested range, so `--limit/--offset` are no longer supported.

## Environment Variables

The repository root provides [`.env.example`](./.env.example) as a template. In actual use, prepare the `.env` file in the repository root. You can copy the template and edit it, or create it manually by following the template.

If you do not want to edit it manually, you can also generate `.env` through natural-language conversation. When missing or incomplete configuration is detected, the skill collects the required fields in order and writes the configuration to the local `.env` through the formal entrypoint.

If you want to provide everything up front, these are usually enough:

- `JMS_API_URL`
- one complete credential pair: `JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET` or `JMS_USERNAME/JMS_PASSWORD`
- `JMS_ORG_ID`, which can be left empty at first and later written by `select-org --confirm`
- `JMS_TIMEOUT`, which falls back to the default if omitted
- `JMS_VERIFY_TLS`, which defaults to `false` if omitted

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
- If `.env` is missing or incomplete, you can fill it through natural-language conversation, and the runtime will generate or overwrite the local `.env` after confirmation.
- Before first use, make sure the URL, authentication method, organization, timeout, and TLS settings are complete.
- If you switch the JumpServer instance, account, organization, or `.env` content, rerun full preflight.

## Typical Request Examples

- "Show me the details for the user `Demo-User`."
- "Show me which assets are under the node named `Demo-Node`."
- "Show me which assets are available on the `Linux` platform."
- "Which assets can this user access in the Default organization?"
- "Show me the details of this permission rule, and tell me which users and assets it affects."
- "Who can access this asset?"
- "Query the login audit for the last week."
- "Show me a user's session records and abnormal interruption details."
- "Help me investigate yesterday's high-risk commands and file-transfer audit."
- "Show me usage for a specific day."
- "Show me yesterday's login activity."
- "I want to know who logged in the most last week."
- "Check which assets were most active in early March."
- "Show me the detailed login logs for a specific day."
- "Export detailed command records for a specific day."

These boundaries are especially important:

- Expressions like `which assets can this user access in the Default organization`, `which nodes can this user access`, or `which accounts can this user use on this asset` belong to user effective access scope and should return scope results first.
- Expressions like `why can this user access this asset` or `details of this permission rule` belong to permission explanation or access analysis.
- Expressions like `login status for a day`, `session overview for a day`, or `who had the most activity in a time range` belong to reports or usage analysis.
- Expressions like `login logs for a day`, `command records for a day`, or `details of a specific session` belong to audit investigation.
- Creating users, user groups, organizations, organization invitations, user-group membership relations, labels, nodes, host/device/database/web assets, zones, gateway machines, account templates, asset-account bulk bindings, command groups, command filter rules, login ACLs, connect method filters, asset permissions, login asset ACLs, and data masking rules belongs to the create subskill. User-group members must be user IDs; resolve names, usernames, or emails first with `jms_query.py resolve --resource user --name <value>`. For labels, `name/value` are required, and `color/comment` are omitted when not supplied. For nodes, only `org_id/full_value/value` is sent. Host/device/database/web assets primarily use full `--payload` JSON with common explicit overrides; on `--confirm`, they resolve `platform/nodes/labels/zone/accounts[].template`, fill default protocols from the platform when omitted, and redact secret or secret-like fields. For zones, only `name/assets/comment` is sent. Gateway machines primarily use full `--payload` JSON. Account templates primarily use full `--payload` JSON, support common explicit overrides, and redact secret or secret-like fields. Asset-account bulk bindings primarily use full `--payload` JSON; assets, nodes, and account templates must be IDs, and account secrets are redacted. Command groups send only `type/ignore_case/name/content/comment`, and `name/type/content` are required. Command filter rules primarily use full `--payload` JSON, with `--name`, `--priority`, `--action`, `--account`, `--command-group`, and `--is-active` as common explicit overrides. Login ACLs primarily use full `--payload` JSON, with `--name`, `--priority`, `--action`, and `--is-active` as common explicit overrides; `review` and `notice` actions require `reviewers`. Connect method filters primarily use full `--payload` JSON, with `--name`, `--action`, `--connect-method`, `--is-active`, and `--comment` as common explicit overrides. Asset permissions primarily use full `--payload` JSON; `assets/nodes/users/user_groups` are resolved on `--confirm`, explicit protocols are matched by `label/value` and sent as `value`, accounts default to `@ALL`, and actions default to all action values. Login asset ACLs and data masking rules primarily use full `--payload` JSON; `users.type=ids` and `assets.type=ids` are resolved to IDs on `--confirm` by reusing existing user/asset resolution. Explicit `--org-id` / `--org-name` for nodes, host/device/database/web assets, zones, gateways, account templates, asset-account bulk bindings, command groups, command filter rules, asset permissions, login asset ACLs, and data masking rules reuses organization resolution and does not write `.env`; when no organization is passed, `.env JMS_ORG_ID` is used; Global organization is blocked. Login ACLs and connect method filters can only be created in the Global organization; explicit organization or `.env JMS_ORG_ID` must ultimately be the Global organization ID `00000000-0000-0000-0000-000000000000`, and `.env` is not written.

## Usage Reports and Time-Range Rules

As long as the core request is JumpServer usage-data analysis for a specific day or time range, the workflow prioritizes the template-based report flow. This includes:

- usage reports, daily reports, weekly reports, and monthly reports
- usage situation, usage analysis, usage statistics, usage summary, and usage overview
- audit analysis and "what happened on a day"
- login, session, command, or transfer activity for a specific day
- rankings, TOP lists, "who had the most", or "which assets were most active" for a time range

These requests generate a complete HTML report by default instead of falling back to a free-text summary first. Only when the user explicitly says "do not generate a report", "just analyze it", "give me a quick summary", "only give me the conclusion", or "do not use the template" may the workflow skip the template and return a short analysis.

Time expressions are normalized into explicit time windows first:

- "yesterday" -> previous day `00:00:00 ~ 23:59:59`
- `20260310` -> `2026-03-10 00:00:00 ~ 23:59:59`
- `2026-03-10` / `2026/03/10` / `March 10` style expressions -> that day `00:00:00 ~ 23:59:59`
- "last week" -> previous natural week, Monday `00:00:00 ~ Sunday 23:59:59`
- "this month" -> the first day of the current month `00:00:00` to the current date or month end `23:59:59`

Quick reading guide:

- `a specific day` is only a placeholder concept; users can say `yesterday`, `20260310`, `2026-03-10`, `2026/03/10`, or `March 10`.
- `a time range` is also a placeholder concept; users can say `last week`, `this month`, or a concrete range such as `2026-03-10 to 2026-03-24`.
- Natural-language time expressions are normalized first, and the formal entrypoint ultimately uses `--date`, `--period`, or `--date-from/--date-to`.

Reports are always written to `reports/JumpServer-YYYY-MM-DD.html`. If the request includes command-audit fields, the report applies the predefined command-storage aggregation rules automatically, so users do not need to choose internal collection logic manually.

## Organization Selection and Blocking Rules

- The current organization is stored in `.env` as `JMS_ORG_ID`; business commands use it when no organization is passed explicitly.
- `daily-usage` reports default to the Global organization `00000000-0000-0000-0000-000000000000` when no organization is passed, and do not write `.env JMS_ORG_ID`.
- When `daily-usage` receives `--org-id` or a uniquely matched `--org-name`, it uses that organization for the report and writes `.env JMS_ORG_ID`.
- For ordinary queries, explicitly specified organizations are resolved to an organization ID and only affect the current command.
- Create subskill exception: when creating a user or user group with `--org-name <name> --confirm`, a unique match writes `.env JMS_ORG_ID` before creation; no match or multiple matches returns `candidate_orgs`. Organization invitations, user-group membership additions, label creation, node creation, host/device/database/web asset creation, zone creation, gateway creation, account template creation, asset-account bulk bindings, command group creation, command filter rule creation, asset permission creation, login asset ACL creation, and data masking rule creation use the explicit organization only for the current command and do not write `.env`; label, node, host/device/database/web asset, zone, gateway, account template, asset-account bulk binding, command group, command filter rule, asset permission, login asset ACL, and data masking rule creation use `.env JMS_ORG_ID` when no organization is passed and block the Global organization. Login ACLs and connect method filters can only be created in the Global organization; explicit organization or `.env JMS_ORG_ID` must ultimately be the Global organization ID `00000000-0000-0000-0000-000000000000`, and `.env` is not written. Creating an organization sends no `X-JMS-ORG` and does not switch `.env JMS_ORG_ID` after success.
- Use `select-org --org-id <org-id> --confirm` or `select-org --org-name <org-name> --confirm` to switch the current organization and write `.env JMS_ORG_ID`.
- If multiple organizations are accessible and no current organization is selected, the skill returns `candidate_orgs` and blocks until one is selected.
- If the current organization is A and the target object is in B, the workflow does not continue automatically across organizations.

In the following cases, the skill blocks instead of continuing by guesswork:

- configuration or authentication is incomplete
- the object name is duplicated or the platform is unclear
- query results cross organizations
- no current organization is selected while multiple organizations are accessible
- the user tries to bypass the formal entrypoint or skip preflight

## Document Map

| File | Purpose |
|---|---|
| [SKILL.md](./SKILL.md) | top-level routing rules, organization priority, and response constraints |
| [agents/openai.yaml](./agents/openai.yaml) | skill integration description and default prompt entry |
| [references/routing-and-safety.md](./references/routing-and-safety.md) | repository-wide routing, formal entrypoint boundaries, allowed write operations, and global blocking rules |
| [subskills/query/references/routing-playbook.md](./subskills/query/references/routing-playbook.md) | ordinary routing, typical trigger words, blocking rules, and counterexamples |
| [subskills/query/references/report-template-playbook.md](./subskills/query/references/report-template-playbook.md) | template report workflow, organization priority, time-range handling, and report rules |
| [subskills/common/references/runtime.md](./subskills/common/references/runtime.md) | preflight flow, environment variable model, organization selection, and runtime constraints |
| [subskills/query/references/capabilities.md](./subskills/query/references/capabilities.md) | capability catalog and capability descriptions |
| [subskills/query/references/assets.md](./subskills/query/references/assets.md) | query guidance for assets, accounts, users, nodes, platforms, and related objects |
| [subskills/create/references/index.md](./subskills/create/references/index.md) | supported create commands and reference index for the create subskill |
| [subskills/query/references/permissions.md](./subskills/query/references/permissions.md) | query guidance for permissions, ACL, RBAC, and authorization relationships |
| [subskills/query/references/audit.md](./subskills/query/references/audit.md) | audit guidance for login, session, command, file-transfer, and related data |
| [subskills/query/references/diagnose.md](./subskills/query/references/diagnose.md) | connectivity, object resolution, access analysis, system inspection, and governance guidance |
| [subskills/common/references/safety-rules.md](./subskills/common/references/safety-rules.md) | common local-write boundaries |
| [subskills/common/references/troubleshooting.md](./subskills/common/references/troubleshooting.md) | common preflight, organization, and connectivity troubleshooting |

## Unsupported Scope

- Create-class write operations are limited to the allowlisted entrypoints: `jms_create_user.py create-user`, `jms_create_user_group.py create-user-group`, `jms_create_org.py create-organization`, `jms_invite_user.py invite-user-to-org`, `jms_add_user_to_group.py add-user-to-user-group`, `jms_create_label.py create-label`, `jms_create_node.py create-node`, `jms_create_asset.py create-host-asset`, `jms_create_asset.py create-device-asset`, `jms_create_asset.py create-database-asset`, `jms_create_asset.py create-web-asset`, `jms_create_zone_gateway.py create-zone`, `jms_create_zone_gateway.py create-gateway`, `jms_create_account_template.py create-account-template`, `jms_asset_account_bulk.py add-account-to-assets`, `jms_asset_account_bulk.py add-account-template-to-assets`, `jms_create_command_acl.py create-command-group`, `jms_create_command_acl.py create-command-filter-rule`, `jms_create_login_acl.py create-login-acl`, `jms_create_connect_method_acl.py create-connect-method-acl`, `jms_create_asset_permission.py create-asset-permission`, `jms_create_login_asset_acl.py create-login-asset-acl`, and `jms_create_data_masking_rule.py create-data-masking-rule`. Object creation not listed in this allowlist is not supported.
- Updating, deleting, or unlocking any object is not supported.
- Permission writes are limited to the allowlisted create entrypoints: `create-command-filter-rule`, `create-login-acl`, `create-connect-method-acl`, `create-asset-permission`, `create-login-asset-acl`, and `create-data-masking-rule`. Other permission creation, updates, relationship appends, relationship removals, and deletion are not supported.
- Running business actions while skipping preflight.
- Using temporary SDK or HTTP scripts to bypass the formal entrypoints.
- Bypassing the formal `jms_report.py` entrypoint for report requests and replacing it with ad hoc inline logic.
- Continuing execution by guessing when objects are unclear, organizations are unclear, or the request crosses organizations.
