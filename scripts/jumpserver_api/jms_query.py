#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jumpserver_api.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

import argparse

from jumpserver_api.jms_analytics import (
    _apply_common_filters,
    _asset_filter_evidence,
    _exact_first_filter,
    _extract_filter_diagnostics,
    _fetch_command_record_by_id,
    _fetch_command_records,
    _fetch_terminal_session_records,
    _list_request_filters,
    _normalize_job_audit_filters,
    _normalize_login_audit_filters,
    _normalize_operate_audit_filters,
    _normalize_password_change_audit_filters,
    _normalize_terminal_session_filters,
    _normalize_time_filters,
    _normalize_user_filter_payload,
    _resolve_asset,
    _resolve_user,
    explain_asset_permissions,
    resolve_command_storage_context,
    run_capability,
)
from jumpserver_api.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    add_filter_arguments,
    create_client,
    create_discovery,
    ensure_selected_org_context,
    merge_filter_args,
    org_context_output,
    parse_bool,
    run_and_print,
)


ASSET_PATH = "/api/v1/assets/assets/"
NODE_PATH = "/api/v1/assets/nodes/"
PLATFORM_PATH = "/api/v1/assets/platforms/"
ACCOUNT_PATH = "/api/v1/accounts/accounts/"
ACCOUNT_TEMPLATE_PATH = "/api/v1/accounts/account-templates/"
USER_PATH = "/api/v1/users/users/"
GROUP_PATH = "/api/v1/users/groups/"
ORG_PATH = "/api/v1/orgs/orgs/"
LABEL_PATH = "/api/v1/labels/labels/"
ZONE_PATH = "/api/v1/assets/zones/"

ASSET_KIND_PATHS = {
    "": ASSET_PATH,
    "generic": ASSET_PATH,
    "host": "/api/v1/assets/hosts/",
    "database": "/api/v1/assets/databases/",
    "device": "/api/v1/assets/devices/",
    "cloud": "/api/v1/assets/clouds/",
    "web": "/api/v1/assets/webs/",
    "website": "/api/v1/assets/webs/",
    "custom": "/api/v1/assets/customs/",
    "customs": "/api/v1/assets/customs/",
    "directory": "/api/v1/assets/directories/",
    "directories": "/api/v1/assets/directories/",
}

OBJECT_RESOURCE_PATHS = {
    "node": NODE_PATH,
    "platform": PLATFORM_PATH,
    "account": ACCOUNT_PATH,
    "account-template": ACCOUNT_TEMPLATE_PATH,
    "user": USER_PATH,
    "user-group": GROUP_PATH,
    "organization": ORG_PATH,
    "label": LABEL_PATH,
    "zone": ZONE_PATH,
}

LOCAL_MATCH_FIELDS = {
    "asset": ("id", "name", "address"),
    "node": ("id", "name", "value", "full_value"),
    "platform": ("id", "name"),
    "account": ("id", "name", "username"),
    "user": ("id", "name", "username", "email"),
    "user-group": ("id", "name"),
    "organization": ("id", "name"),
    "label": ("id", "name"),
    "zone": ("id", "name"),
}

PERMISSION_RESOURCE_PATHS = {
    "asset-permission": "/api/v1/perms/asset-permissions/",
    "connect-method-acl": "/api/v1/acls/connect-method-acls/",
    "data-masking-rule": "/api/v1/acls/data-masking-rules/",
    "login-asset-acl": "/api/v1/acls/login-asset-acls/",
    "login-acl": "/api/v1/acls/login-acls/",
    "command-filter-acl": "/api/v1/acls/command-filter-acls/",
    "command-group": "/api/v1/acls/command-groups/",
    "org-role": "/api/v1/rbac/org-roles/",
    "system-role": "/api/v1/rbac/system-roles/",
    "role-binding": "/api/v1/rbac/role-bindings/",
    "org-role-binding": "/api/v1/rbac/org-role-bindings/",
    "system-role-binding": "/api/v1/rbac/system-role-bindings/",
}

AUDIT_PATHS = {
    "operate": "/api/v1/audits/operate-logs/",
    "login": "/api/v1/audits/login-logs/",
    "session": "/api/v1/audits/user-sessions/",
    "ftp": "/api/v1/audits/ftp-logs/",
    "password_change": "/api/v1/audits/password-change-logs/",
    "jobs": "/api/v1/audits/job-logs/",
    "command": "/api/v1/terminal/commands/",
    "terminal-session": "/api/v1/terminal/sessions/",
}

TERMINAL_SESSION_PRESETS = {
    "online": {"is_finished": 0, "order": "is_finished,-date_end"},
    "history": {"is_finished": 1, "order": "is_finished,-date_end"},
}

COMMAND_AUDIT_CAPABILITIES = {
    "command-record-query",
    "high-risk-command-audit",
}

OBJECT_LIST_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py object-list --resource organization --name Default --limit 5",
    "python3 scripts/jumpserver_api/jms_query.py object-list --resource asset --kind host --search prod --limit 10",
]
PERMISSION_LIST_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py permission-list --resource asset-permission --name 生产环境授权 --limit 10",
    "python3 scripts/jumpserver_api/jms_query.py permission-list --resource asset-permission --filter users=jingyu.qi --limit 20",
]
ASSET_PERM_USERS_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py asset-perm-users --asset-id <asset-id>",
]
AUDIT_LIST_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type login --days 30 --username 古思清(gusiqing) --status 1 --limit 5",
    "python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type terminal-session --days 7 --user gusiqing --asset demo-host --protocol ssh --limit 20",
    "python3 scripts/jumpserver_api/jms_query.py audit-list --audit-type operate --days 30 --user gusiqing --action 创建 --resource-type 'User session' --limit 20",
]
TERMINAL_SESSION_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py terminal-sessions --view history --days 7 --user gusiqing --limit 10",
    "python3 scripts/jumpserver_api/jms_query.py terminal-sessions --view online --asset demo-host --protocol ssh",
]
JOB_LIST_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py job-list --name 删除Windows用户 --limit 10",
    "python3 scripts/jumpserver_api/jms_query.py job-list --search shell --limit 10",
]
COMMAND_STORAGE_HINT_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py command-storage-hint",
    "python3 scripts/jumpserver_api/jms_query.py command-storage-hint --command-storage-id <storage-id>",
]
AUDIT_ANALYZE_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability session-record-query --days 7 --user gusiqing --limit 20",
    "python3 scripts/jumpserver_api/jms_query.py audit-analyze --capability command-record-query --date-from '2026-03-01 00:00:00' --date-to '2026-03-20 23:59:59' --command-storage-scope all",
]
AUDIT_STRATEGY_FIELDS = {
    "operate": (
        ("user", "server_user_exact"),
        ("action", "server_action_exact"),
        ("resource_type", "server_resource_type_exact"),
    ),
    "login": (
        ("username", "server_username_exact"),
        ("ip", "server_ip_exact"),
        ("type", "server_type_exact"),
        ("city", "server_city_exact"),
        ("mfa", "server_mfa_exact"),
        ("status", "server_status_exact"),
    ),
    "password_change": (
        ("user", "server_user_exact"),
        ("change_by", "server_change_by_exact"),
        ("remote_addr", "server_remote_addr_exact"),
    ),
    "jobs": (
        ("creator__name", "server_creator_name_exact"),
        ("material", "server_material_exact"),
    ),
    "session": (
        ("user", "server_user_exact"),
        ("account", "server_account_exact"),
        ("asset", "server_asset_exact"),
        ("asset_id", "server_asset_id_exact"),
        ("protocol", "server_protocol_exact"),
        ("login_from", "server_login_from_exact"),
        ("remote_addr", "server_remote_addr_exact"),
    ),
    "terminal-session": (
        ("user", "server_user_exact"),
        ("account", "server_account_exact"),
        ("asset", "server_asset_exact"),
        ("asset_id", "server_asset_id_exact"),
        ("protocol", "server_protocol_exact"),
        ("login_from", "server_login_from_exact"),
        ("remote_addr", "server_remote_addr_exact"),
    ),
    "command": (
        ("asset_id", "server_asset_id_exact"),
    ),
}
COMMON_QUERY_FIELDS = ("date_from", "date_to", "days", "search", "limit", "offset")
AUDIT_ALLOWED_FIELDS = {
    "operate": COMMON_QUERY_FIELDS + ("user", "action", "resource_type"),
    "login": COMMON_QUERY_FIELDS + ("username", "ip", "type", "city", "mfa", "status"),
    "password_change": COMMON_QUERY_FIELDS + ("user", "change_by", "remote_addr"),
    "jobs": COMMON_QUERY_FIELDS + ("creator__name", "material"),
    "session": COMMON_QUERY_FIELDS + ("user", "asset", "asset_id", "account", "protocol", "login_from", "remote_addr", "order"),
    "ftp": COMMON_QUERY_FIELDS,
    "command": COMMON_QUERY_FIELDS + ("asset_id", "order", "command_storage_id", "command_storage_scope"),
    "terminal-session": COMMON_QUERY_FIELDS + ("user", "asset", "asset_id", "account", "protocol", "login_from", "remote_addr", "order"),
}


def _asset_list_path(kind: str | None) -> str:
    kind_value = str(kind or "").strip().lower()
    if kind_value not in ASSET_KIND_PATHS:
        raise CLIError("Unsupported asset kind: %s" % kind)
    return ASSET_KIND_PATHS[kind_value]


def _object_list_path(resource: str, kind: str | None) -> str:
    if resource == "asset":
        return _asset_list_path(kind)
    if kind:
        raise CLIError("--kind is only supported when --resource asset.")
    return OBJECT_RESOURCE_PATHS[resource]


def _object_get_path(resource: str) -> str:
    if resource == "asset":
        return ASSET_PATH
    return OBJECT_RESOURCE_PATHS[resource]


def _without_pagination(filters: dict) -> dict:
    payload = dict(filters)
    payload.pop("limit", None)
    payload.pop("offset", None)
    return payload


def _apply_requested_page(records, filters: dict):
    if not isinstance(records, list):
        return records
    if filters.get("limit") in {None, ""} and filters.get("offset") in {None, ""}:
        return records
    try:
        offset = max(int(filters.get("offset") or 0), 0)
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(filters.get("limit")) if filters.get("limit") not in {None, ""} else None
    except (TypeError, ValueError):
        limit = None
    if limit is not None and limit < 0:
        limit = None
    end = offset + limit if limit is not None else None
    return records[offset:end]


def _merge_match_strategy(current: str, addition: str) -> str:
    parts = [item for item in str(current or "").split("+") if item]
    if addition not in parts:
        parts.append(addition)
    return "+".join(parts) if parts else addition


def _requested_server_filter_strategy(audit_type: str, filters: dict[str, object], *, base: str = "server") -> str:
    strategy = str(base or "server")
    if filters.get("search") not in {None, ""}:
        strategy = "server_search" if strategy == "server" else _merge_match_strategy(strategy, "server_search")
    for key, strategy_name in AUDIT_STRATEGY_FIELDS.get(audit_type, ()):
        if filters.get(key) not in {None, ""}:
            strategy = strategy_name if strategy == "server" else _merge_match_strategy(strategy, strategy_name)
    return strategy


def _trim_audit_filters(audit_type: str, filters: dict[str, object]) -> dict[str, object]:
    allowed = set(AUDIT_ALLOWED_FIELDS.get(audit_type, COMMON_QUERY_FIELDS))
    return {key: value for key, value in filters.items() if key in allowed or str(key).startswith("_")}


def _normalize_audit_filters(audit_type: str, filters: dict[str, object]) -> dict[str, object]:
    if audit_type == "operate":
        return _normalize_operate_audit_filters(filters)
    if audit_type == "login":
        return _normalize_login_audit_filters(filters)
    if audit_type == "password_change":
        return _normalize_password_change_audit_filters(filters)
    if audit_type == "jobs":
        return _normalize_job_audit_filters(filters)
    if audit_type in {"session", "terminal-session"}:
        return _normalize_terminal_session_filters(filters)
    return dict(filters)


def _candidate_brief(resource: str, item: dict) -> dict:
    if resource == "asset":
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "address": item.get("address"),
            "platform": (item.get("platform") or {}).get("name") if isinstance(item.get("platform"), dict) else item.get("platform"),
            "nodes_display": item.get("nodes_display"),
        }
    if resource == "node":
        return {
            "id": item.get("id"),
            "name": item.get("name") or item.get("value"),
            "full_value": item.get("full_value"),
            "org_name": item.get("org_name"),
        }
    return {"id": item.get("id"), "name": item.get("name")}


def _ambiguity_hint(resource: str, matched_fields: list[str]) -> str | None:
    if resource == "asset" and "address" in matched_fields:
        return "Address 可能对应多个资产，请改用 id、name 或 platform 继续确认。"
    if resource == "node" and "full_value" in matched_fields:
        return "full_value 应唯一命中；若仍多条，请改用 id。"
    if matched_fields:
        return "当前条件仍命中多个对象，请改用 id 或更精确字段继续缩小范围。"
    return None


def _apply_local_exact_filters(client, *, path: str, resource: str, filters: dict, records):
    if not isinstance(records, list):
        return records, "server", []
    current = [item for item in records if isinstance(item, dict)]
    match_strategy = "server"
    matched_fields = []
    for field in LOCAL_MATCH_FIELDS.get(resource, ()):
        value = filters.get(field)
        if value in {None, ""}:
            continue
        matched_fields.append(field)
        narrowed = _exact_first_filter(current, value, field)
        if narrowed:
            if narrowed != current:
                match_strategy = "local_exact_first"
            current = narrowed
            continue
        broader_filters = _without_pagination(filters)
        broader_filters.pop(field, None)
        broader = client.list_paginated(path, params=broader_filters)
        broader = [item for item in broader if isinstance(item, dict)] if isinstance(broader, list) else []
        current = _exact_first_filter(broader, value, field)
        match_strategy = "local_exact_first_broad_fetch"
    return current, match_strategy, matched_fields


def _permission_detail_matches_user(detail: dict, *, resolved_user: dict) -> bool:
    user_id = str(resolved_user.get("id") or "").strip()
    user_name = str(resolved_user.get("name") or "").strip().lower()
    user_username = str(resolved_user.get("username") or "").strip().lower()
    user_group_ids = {
        str(item.get("id", item)).strip()
        for item in (resolved_user.get("groups") or [])
        if str(item.get("id", item) if isinstance(item, dict) else item).strip()
    }
    expected_values = {value for value in {user_id, user_name, user_username} if value}

    for item in detail.get("users", []) or []:
        if isinstance(item, dict):
            item_id = str(item.get("id") or "").strip()
            item_name = str(item.get("name") or "").strip().lower()
            item_username = str(item.get("username") or "").strip().lower()
            if user_id and item_id == user_id:
                return True
            if user_username and item_username == user_username:
                return True
            if user_name and item_name == user_name:
                return True
            continue
        item_text = str(item or "").strip()
        if item_text and (item_text == user_id or item_text.lower() in expected_values):
            return True

    detail_group_ids = {
        str(item.get("id", item)).strip()
        for item in (detail.get("user_groups") or [])
        if str(item.get("id", item) if isinstance(item, dict) else item).strip()
    }
    return bool(detail_group_ids & user_group_ids)


def _filter_asset_permission_records_by_user(client, records, user_filter, *, discovery=None):
    resolved_user = _resolve_user(str(user_filter or "").strip(), discovery=discovery)
    filtered_records = []
    for item in records:
        permission_id = str(item.get("id") or "").strip() if isinstance(item, dict) else ""
        if not permission_id:
            continue
        detail = client.get("%s%s/" % (_permission_resource_path("asset-permission"), permission_id))
        if _permission_detail_matches_user(detail, resolved_user=resolved_user):
            filtered_records.append(item)
    return filtered_records, resolved_user


def _object_list(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=OBJECT_LIST_EXAMPLES,
    )
    path = _object_list_path(args.resource, args.kind)
    records = client.list_paginated(path, params=filters)
    records, match_strategy, matched_fields = _apply_local_exact_filters(
        client,
        path=path,
        resource=args.resource,
        filters=filters,
        records=records,
    )
    ambiguous = isinstance(records, list) and bool(matched_fields) and len(records) > 1
    return {
        "resource": args.resource,
        "kind": args.kind if args.resource == "asset" else None,
        "match_strategy": match_strategy,
        "summary": {
            "total": len(records) if isinstance(records, list) else None,
            "filters": filters,
            "matched_fields": matched_fields,
            "ambiguous": ambiguous,
            "ambiguity_hint": _ambiguity_hint(args.resource, matched_fields) if ambiguous else None,
            "candidates": [_candidate_brief(args.resource, item) for item in records[:10]] if ambiguous else [],
        },
        "records": records,
        **org_context_output(context),
    }


def _object_get(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    record = client.get("%s%s/" % (_object_get_path(args.resource), args.id))
    return {
        "resource": args.resource,
        "record": record,
        **org_context_output(context),
    }


def _permission_resource_path(resource: str) -> str:
    return PERMISSION_RESOURCE_PATHS[resource]


def _permission_brief(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "is_expired": item.get("is_expired"),
        "from_ticket": item.get("from_ticket"),
        "date_start": item.get("date_start"),
        "date_expired": item.get("date_expired"),
    }


def _add_pagination_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, help="返回条数上限。")
    parser.add_argument("--offset", type=int, help="分页偏移量。")


def _add_time_filter_arguments(parser: argparse.ArgumentParser, *, include_days: bool = True) -> None:
    parser.add_argument("--date-from", dest="date_from", help="开始时间，格式如 `2026-03-23 00:00:00`。")
    parser.add_argument("--date-to", dest="date_to", help="结束时间，格式如 `2026-03-23 23:59:59`。")
    if include_days:
        parser.add_argument("--days", type=int, help="最近 N 天；未显式给时间窗时使用。")


def _add_common_audit_filter_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_direction: bool = False,
    include_keyword: bool = False,
    include_storage: bool = False,
    include_top: bool = False,
) -> None:
    _add_time_filter_arguments(parser)
    parser.add_argument("--user", help="用户名或显示名。")
    parser.add_argument("--user-id", dest="user_id", help="用户 UUID。")
    parser.add_argument("--asset", help="资产名称、地址或关键字。")
    parser.add_argument("--search", help="服务端搜索关键字。")
    parser.add_argument("--status", help="状态过滤，例如 `success`、`failed`。")
    parser.add_argument("--protocol", help="协议过滤，例如 `ssh`。")
    parser.add_argument("--account", help="账号过滤。")
    parser.add_argument("--source-ip", dest="source_ip", help="来源 IP 过滤。")
    _add_pagination_arguments(parser)
    if include_keyword:
        parser.add_argument("--keyword", help="关键字过滤，适用于命令/内容类查询。")
    if include_direction:
        parser.add_argument("--direction", help="传输方向，例如 `upload` 或 `download`。")
    if include_storage:
        parser.add_argument("--command-storage-id", dest="command_storage_id", help="指定 command storage ID。")
        parser.add_argument(
            "--command-storage-scope",
            dest="command_storage_scope",
            choices=["all"],
            help="设为 `all` 时汇总全部可访问 command storage。",
        )
    if include_top:
        parser.add_argument("--top", type=int, help="排行场景返回前 N 条。")


def _add_page_query_time_arguments(parser: argparse.ArgumentParser) -> None:
    _add_time_filter_arguments(parser)
    parser.add_argument("--search", help="页面搜索框的直接搜索关键字。")
    _add_pagination_arguments(parser)


def _permission_list(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset", "user", "user_id", "users", "is_expired"),
        usage_examples=PERMISSION_LIST_EXAMPLES,
    )
    if args.resource != "asset-permission":
        filters.pop("user_id", None)
    path = _permission_resource_path(args.resource)
    records = client.list_paginated(path, params=filters)
    filtered_records = [item for item in records if isinstance(item, dict)] if isinstance(records, list) else records
    match_strategy = "server"
    summary = {
        "filters": filters,
        "total": len(filtered_records) if isinstance(filtered_records, list) else None,
    }

    if isinstance(filtered_records, list) and args.resource == "asset-permission" and filters.get("name"):
        filtered = _exact_first_filter(filtered_records, filters.get("name"), "name")
        if filtered:
            if filtered != filtered_records:
                match_strategy = "local_exact_first"
            filtered_records = filtered
        else:
            fallback_filters = dict(filters)
            fallback_filters.pop("name", None)
            fallback_filters.pop("search", None)
            broader_records = client.list_paginated(path, params=fallback_filters)
            broader_records = [item for item in broader_records if isinstance(item, dict)] if isinstance(broader_records, list) else []
            filtered_records = _exact_first_filter(broader_records, filters.get("name"), "name")
            match_strategy = "local_exact_first_broad_fetch"
        summary["matched_name"] = filters.get("name")

    if isinstance(filtered_records, list) and args.resource == "asset-permission":
        requested_user_filter = next(
            ((field, filters.get(field)) for field in ("users", "user") if filters.get(field) not in {None, ""}),
            None,
        )
        if requested_user_filter is not None:
            field_name, field_value = requested_user_filter
            discovery = create_discovery()
            broader_filters = _without_pagination({key: value for key, value in filters.items() if key not in {"user", "users"}})
            broader_records = client.list_paginated(path, params=broader_filters)
            broader_records = [item for item in broader_records if isinstance(item, dict)] if isinstance(broader_records, list) else []
            locally_filtered_records, resolved_user = _filter_asset_permission_records_by_user(
                client,
                broader_records,
                field_value,
                discovery=discovery,
            )
            filtered_records = _apply_requested_page(locally_filtered_records, filters)
            match_strategy = _merge_match_strategy(match_strategy, "local_detail_user_filter")
            summary["requested_user_filter"] = {"field": field_name, "value": field_value}
            summary["matched_user"] = {
                "id": resolved_user.get("id"),
                "name": resolved_user.get("name"),
                "username": resolved_user.get("username"),
                "email": resolved_user.get("email"),
            }
            summary["local_detail_user_filter_candidate_count"] = len(broader_records)
            summary["local_detail_user_filter_total_before_pagination"] = len(locally_filtered_records)
            if not filtered_records and not summary.get("empty_reason_hint"):
                summary["empty_reason_hint"] = "当前组织下实时可见的 asset-permission 中未发现匹配该用户或其用户组的规则。"

    if isinstance(filtered_records, list) and args.resource == "asset-permission":
        visible_sample = filtered_records
        if filters.get("name") and not filtered_records:
            visible_sample = client.list_paginated(path, params={k: v for k, v in filters.items() if k not in {"name", "search"}})
            visible_sample = [item for item in visible_sample if isinstance(item, dict)] if isinstance(visible_sample, list) else []
            summary["current_visible_total_without_name_filter"] = len(visible_sample)
            if not visible_sample:
                summary["empty_reason_hint"] = "名称链路已尝试服务端过滤与本地 broad fetch，当前组织下仍未发现该规则；若历史工件曾出现该对象，可能已删除、跨组织，或当前账号不可见。"
            else:
                summary["current_visible_candidates"] = [_permission_brief(item) for item in visible_sample[:10]]

        if filters.get("is_expired") is not None:
            wanted = parse_bool(filters.get("is_expired"))
            active_sample = client.list_paginated(path, params={k: v for k, v in filters.items() if k != "is_expired"})
            active_sample = [item for item in active_sample if isinstance(item, dict)] if isinstance(active_sample, list) else []
            summary["requested_is_expired"] = wanted
            summary["returned_expired_count"] = sum(1 for item in filtered_records if parse_bool(item.get("is_expired")))
            summary["returned_active_count"] = sum(1 for item in filtered_records if not parse_bool(item.get("is_expired")))
            summary["current_visible_total_without_is_expired_filter"] = len(active_sample)
            summary["current_visible_expired_count_without_filter"] = sum(1 for item in active_sample if parse_bool(item.get("is_expired")))
            summary["current_visible_active_count_without_filter"] = sum(1 for item in active_sample if not parse_bool(item.get("is_expired")))
            if wanted and not filtered_records:
                summary["empty_reason_hint"] = "当前组织下实时可见的 asset-permission 中没有 is_expired=true 记录；若历史工件曾出现该对象，可能已删除、跨组织，或当前账号不可见。"
                summary["current_visible_candidates"] = [_permission_brief(item) for item in active_sample[:10]]

    summary["total"] = len(filtered_records) if isinstance(filtered_records, list) else summary.get("total")
    return {
        "resource": args.resource,
        "match_strategy": match_strategy,
        "summary": summary,
        "records": filtered_records,
        **org_context_output(context),
    }


def _permission_get(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    record_id = str(args.id or args.permission_id or "").strip()
    if not record_id:
        raise CLIError("Provide --id. --permission-id is kept only for backward compatibility.")
    record = client.get("%s%s/" % (_permission_resource_path(args.resource), record_id))
    return {
        "resource": args.resource,
        "record": record,
        **org_context_output(context),
    }


def _asset_perm_users(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    discovery = create_discovery()
    filters = merge_filter_args(args, explicit_fields=("limit", "offset", "search"), usage_examples=ASSET_PERM_USERS_EXAMPLES)
    records = client.list_paginated("/api/v1/assets/assets/%s/perm-users/" % args.asset_id, params=filters)
    result = {
        "resource": "asset-perm-users",
        "asset_id": args.asset_id,
        "records": records,
        **org_context_output(context),
    }
    if isinstance(records, list) and not records:
        asset = _resolve_asset(args.asset_id, discovery=discovery)
        explanation = explain_asset_permissions(asset, client=client, discovery=discovery)
        if explanation.get("matched_permission_count"):
            result.update(
                {
                    "service_view_mismatch": True,
                    "warning": "Asset permission users API returned no records, but matching asset-permissions were found for this asset.",
                    "permission_explain_summary": {
                        "matched_permission_count": explanation.get("matched_permission_count"),
                        "matched_permissions": [
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "match_source": item.get("match_source"),
                            }
                            for item in explanation.get("matched_permissions", [])
                        ],
                    },
                }
            )
    return result


def _audit_list(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    filters = _trim_audit_filters(
        args.audit_type,
        merge_filter_args(
            args,
            explicit_fields=(
                "date_from",
                "date_to",
                "days",
                "search",
                "user",
                "username",
                "ip",
                "type",
                "city",
                "mfa",
                "status",
                "change_by",
                "remote_addr",
                "creator__name",
                "material",
                "asset",
                "asset_id",
                "account",
                "protocol",
                "login_from",
                "order",
                "action",
                "resource_type",
                "command_storage_id",
                "command_storage_scope",
                "limit",
                "offset",
            ),
            usage_examples=AUDIT_LIST_EXAMPLES,
        ),
    )
    filters = _normalize_time_filters(filters, default_days=7)
    filters = _normalize_audit_filters(args.audit_type, filters)
    filter_strategy = _requested_server_filter_strategy(args.audit_type, filters)
    if args.audit_type == "terminal-session":
        result, meta = _fetch_terminal_session_records(filters)
        filter_strategy = _requested_server_filter_strategy(
            args.audit_type,
            filters,
            base=meta.get("filter_strategy") or filter_strategy,
        )
    elif args.audit_type == "command":
        result = _fetch_command_records(filters)
        filter_strategy = _requested_server_filter_strategy(args.audit_type, filters, base="server+command_storage_context")
    else:
        path = AUDIT_PATHS[args.audit_type]
        result = client.list_paginated(path, params=_list_request_filters(path, filters))
        if isinstance(result, list):
            filtered = _apply_common_filters([item for item in result if isinstance(item, dict)], filters)
            if len(filtered) != len(result):
                filter_strategy = _merge_match_strategy(filter_strategy, "local_common_filters")
            result = filtered
    payload = {
        "audit_type": args.audit_type,
        "filter_strategy": filter_strategy,
        "records": result,
        **org_context_output(context),
    }
    return _attach_filter_diagnostics(payload, filters)


def _audit_get(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    if args.audit_type == "command":
        result = _fetch_command_record_by_id(args.id)
    else:
        result = client.get("%s%s/" % (AUDIT_PATHS[args.audit_type], args.id))
    return {"audit_type": args.audit_type, "record": result, **org_context_output(context)}


def _terminal_sessions(args: argparse.Namespace):
    context = ensure_selected_org_context()
    filters = _normalize_time_filters(
        merge_filter_args(
            args,
            explicit_fields=(
                "date_from",
                "date_to",
                "days",
                "search",
                "user",
                "asset",
                "asset_id",
                "account",
                "protocol",
                "login_from",
                "remote_addr",
                "order",
                "limit",
                "offset",
            ),
            usage_examples=TERMINAL_SESSION_EXAMPLES,
        ),
        default_days=7,
    )
    filters = _normalize_terminal_session_filters(filters)
    preset = TERMINAL_SESSION_PRESETS.get(args.view or "")
    if preset:
        for key, value in preset.items():
            filters.setdefault(key, value)

    filtered, meta = _fetch_terminal_session_records(filters)
    filter_strategy = _requested_server_filter_strategy(
        "terminal-session",
        filters,
        base=meta.get("filter_strategy") or "server",
    )
    payload = {
        "audit_type": "terminal-session",
        "view": args.view or "all",
        "summary": {
            "total": len(filtered),
            "filters": {key: value for key, value in filters.items() if not str(key).startswith("_")},
            "filter_strategy": filter_strategy,
            "resolved_asset": meta.get("resolved_asset"),
        },
        "records": [
            {
                **item,
                "asset_evidence": _asset_filter_evidence(item, expected=filters.get("asset")),
            }
            for item in filtered
        ],
        **org_context_output(context),
    }
    return _attach_filter_diagnostics(payload, filters)


def _job_list(args: argparse.Namespace):
    context = ensure_selected_org_context()
    client = create_client()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=JOB_LIST_EXAMPLES,
    )
    path = "/api/v1/audits/jobs/"
    records = client.list_paginated(path, params=_list_request_filters(path, filters))
    filter_strategy = "server"
    if filters.get("search") not in {None, ""}:
        filter_strategy = "server_search"
    if filters.get("name") not in {None, ""}:
        filter_strategy = "server_name_exact" if filter_strategy == "server" else _merge_match_strategy(filter_strategy, "server_name_exact")
    return {
        "resource": "job-list",
        "summary": {
            "total": len(records) if isinstance(records, list) else 0,
            "filters": filters,
            "filter_strategy": filter_strategy,
        },
        "records": records,
        **org_context_output(context),
    }


def _command_storage_hint(args: argparse.Namespace):
    context = ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        explicit_fields=("command_storage_id", "command_storage_scope"),
        usage_examples=COMMAND_STORAGE_HINT_EXAMPLES,
    )
    return _command_storage_hint_payload(filters, context=context)


def _command_storage_hint_payload(filters: dict, *, context: dict | None = None):
    storage_context = resolve_command_storage_context(filters)
    return {
        "storage_count": storage_context["available_command_storage_count"],
        "default_storage_count": storage_context["default_storage_count"],
        "storages": storage_context["available_command_storages"],
        "warning": storage_context["command_storage_hint"],
        **storage_context,
        **org_context_output(context or ensure_selected_org_context()),
    }


def _attach_filter_diagnostics(result: dict, filters: dict) -> dict:
    diagnostics = _extract_filter_diagnostics(filters)
    if not diagnostics:
        return result
    payload = dict(result)
    payload.setdefault("filter_diagnostics", diagnostics)
    return payload


def _audit_analyze(args: argparse.Namespace):
    context = ensure_selected_org_context()
    filters = _normalize_user_filter_payload(
        merge_filter_args(
            args,
            explicit_fields=(
                "date_from",
                "date_to",
                "days",
                "user",
                "user_id",
                "asset",
                "asset_keywords",
                "search",
                "keyword",
                "direction",
                "status",
                "protocol",
                "account",
                "source_ip",
                "command_storage_id",
                "command_storage_scope",
                "limit",
                "offset",
                "top",
            ),
            usage_examples=AUDIT_ANALYZE_EXAMPLES,
        )
    )
    effective_filters = dict(filters)
    storage_context = None
    if args.capability in COMMAND_AUDIT_CAPABILITIES:
        storage_context = resolve_command_storage_context(effective_filters)
        if not effective_filters.get("command_storage_id"):
            if storage_context.get("selection_required"):
                return _attach_filter_diagnostics(
                    {
                        "blocked": True,
                        "block_reason": "Multiple command storages detected and no default storage is available. Select one command_storage_id before querying command audit capabilities.",
                        "capability": args.capability,
                        **_command_storage_hint_payload(effective_filters, context=context),
                    },
                    effective_filters,
                )
            selected_command_storage_id = storage_context.get("selected_command_storage_id")
            if selected_command_storage_id:
                effective_filters = {**filters, "command_storage_id": selected_command_storage_id}
    result = run_capability(args.capability, effective_filters)
    if args.capability in COMMAND_AUDIT_CAPABILITIES and storage_context is not None:
        result.update(storage_context)
    if "effective_org" not in result:
        result.update(org_context_output(context))
    return _attach_filter_diagnostics(result, effective_filters)


def _audit_capabilities(_: argparse.Namespace):
    from jumpserver_api.jms_capabilities import CAPABILITIES

    return [
        {
            "id": item.capability_id,
            "name": item.name,
            "category": item.category,
            "priority": item.priority,
            "entrypoint": item.entrypoint,
        }
        for item in CAPABILITIES
        if item.entrypoint.startswith("jms_query.py audit-analyze")
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 统一只读查询入口。",
        epilog=(
            "推荐路径:\n"
            "  1. 优先使用显式参数，例如 --name、--days、--user、--limit\n"
            "  2. 高级补充筛选使用重复的 --filter key=value\n"
            "  3. 只有兼容旧命令时再使用 --filters '{\"key\": \"value\"}'"
        ),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    object_resources = [
        "asset",
        "node",
        "platform",
        "account",
        "account-template",
        "user",
        "user-group",
        "organization",
        "label",
        "zone",
    ]
    permission_resources = sorted(PERMISSION_RESOURCE_PATHS)

    object_list = subparsers.add_parser(
        "object-list",
        help="按资源类型列出对象。",
        description="列出资产、节点、平台、账号、用户、组织等对象。",
        epilog="Examples:\n  " + "\n  ".join(OBJECT_LIST_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    object_list.add_argument("--resource", required=True, choices=object_resources)
    object_list.add_argument("--kind", help="仅当 --resource asset 时可选，用于限定资产子类型。")
    object_list.add_argument("--name", help="按名称精确优先匹配。")
    object_list.add_argument("--search", help="服务端搜索关键字。")
    _add_pagination_arguments(object_list)
    add_filter_arguments(object_list)
    object_list.set_defaults(func=_object_list)

    object_get = subparsers.add_parser(
        "object-get",
        help="按 ID 读取单个对象详情。",
        description="按资源类型和 ID 读取单个对象详情。",
        formatter_class=CLIHelpFormatter,
    )
    object_get.add_argument("--resource", required=True, choices=object_resources)
    object_get.add_argument("--id", required=True)
    object_get.set_defaults(func=_object_get)

    permission_list = subparsers.add_parser(
        "permission-list",
        help="列出权限、ACL 或 RBAC 记录。",
        description="读取 asset-permission、ACL、RBAC 等权限相关资源。",
        epilog="Examples:\n  " + "\n  ".join(PERMISSION_LIST_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    permission_list.add_argument("--resource", choices=permission_resources, default="asset-permission")
    permission_list.add_argument("--name", help="按权限名称精确优先匹配。")
    permission_list.add_argument("--search", help="服务端搜索关键字。")
    permission_list.add_argument("--user", help="按用户名或显示名筛选 asset-permission。")
    permission_list.add_argument("--user-id", dest="user_id", help="按用户 UUID 筛选 asset-permission。")
    permission_list.add_argument("--users", help="兼容字段，按用户标识筛选 asset-permission。")
    permission_list.add_argument("--is-expired", dest="is_expired", help="按过期状态筛选，例如 true / false。")
    _add_pagination_arguments(permission_list)
    add_filter_arguments(permission_list)
    permission_list.set_defaults(func=_permission_list)

    permission_get = subparsers.add_parser(
        "permission-get",
        help="按 ID 读取单条权限记录详情。",
        description="按资源类型和 ID 读取权限、ACL 或 RBAC 详情。",
        formatter_class=CLIHelpFormatter,
    )
    permission_get.add_argument("--resource", choices=permission_resources, default="asset-permission")
    permission_get.add_argument("--id")
    permission_get.add_argument("--permission-id")
    permission_get.set_defaults(func=_permission_get)

    asset_perm_users = subparsers.add_parser(
        "asset-perm-users",
        help="查看某资产的授权主体列表。",
        description="读取资产授权用户视图；当服务端视图为空时，会补充权限解释摘要。",
        epilog="Examples:\n  " + "\n  ".join(ASSET_PERM_USERS_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    asset_perm_users.add_argument("--asset-id", required=True)
    _add_pagination_arguments(asset_perm_users)
    add_filter_arguments(asset_perm_users)
    asset_perm_users.set_defaults(func=_asset_perm_users)

    audit_list = subparsers.add_parser(
        "audit-list",
        help="读取登录、会话、命令等审计明细。",
        description="读取指定审计类型的页面同款审计明细；未给时间时默认最近 7 天。",
        epilog="Examples:\n  " + "\n  ".join(AUDIT_LIST_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    audit_list.add_argument("--audit-type", required=True, choices=sorted(AUDIT_PATHS))
    _add_page_query_time_arguments(audit_list)
    audit_list.add_argument("--user", help="页面精确用户过滤；用于 operate、password_change、session、terminal-session。输入用户名或显示名时会解析成页面显示值。")
    audit_list.add_argument("--username", help="登录日志页面用户名精确过滤；最终下发 `name(username)`，仅当 audit-type=login 时生效。")
    audit_list.add_argument("--ip", help="登录日志页面来源 IP 精确过滤，仅当 audit-type=login 时生效。")
    audit_list.add_argument("--type", help="登录日志页面设备类型精确过滤；仅当 audit-type=login 时生效，只支持 `W/T/U`。")
    audit_list.add_argument("--city", help="登录日志页面城市精确过滤，仅当 audit-type=login 时生效。")
    audit_list.add_argument("--mfa", help="登录日志页面 MFA 状态精确过滤；仅当 audit-type=login 时生效，只支持 `0/1/2`。")
    audit_list.add_argument("--status", help="登录日志页面状态精确过滤；仅当 audit-type=login 时生效，只支持 `0/1`。")
    audit_list.add_argument("--change-by", dest="change_by", help="改密日志页面修改者精确过滤；最终下发 `name(username)`，仅当 audit-type=password_change 时生效。")
    audit_list.add_argument("--remote-addr", dest="remote_addr", help="页面远端地址精确过滤；仅当 audit-type=password_change、session 或 terminal-session 时生效。")
    audit_list.add_argument("--creator-name", dest="creator__name", help="作业日志页面创建者精确过滤；最终下发创建者显示名，仅当 audit-type=jobs 时生效。")
    audit_list.add_argument("--material", help="作业日志页面执行内容精确过滤，仅当 audit-type=jobs 时生效。")
    audit_list.add_argument("--asset", help="页面资产精确过滤；用于 session 和 terminal-session，输入名称或地址时会解析成 `name(ip)`。")
    audit_list.add_argument("--asset-id", dest="asset_id", help="资产 UUID 精确过滤，仅当 audit-type=session、terminal-session 或 command 时生效。")
    audit_list.add_argument("--account", help="页面账号精确过滤；用于 session 和 terminal-session，输入名称或用户名时会解析成 `name(username)`。")
    audit_list.add_argument("--protocol", help="页面协议精确过滤；用于 session 和 terminal-session。")
    audit_list.add_argument("--login-from", dest="login_from", help="页面登录来源精确过滤；用于 session 和 terminal-session，只支持 `WT/ST/RT/DT/VT`。")
    audit_list.add_argument("--order", help="页面排序字段；仅当 audit-type=session、terminal-session 或 command 时生效。")
    audit_list.add_argument("--action", help="操作日志页面动作精确过滤；仅当 audit-type=operate 时生效，支持 create/创建 等值。")
    audit_list.add_argument("--resource-type", dest="resource_type", help="操作日志页面资源类型精确过滤，仅当 audit-type=operate 时生效。")
    audit_list.add_argument("--command-storage-id", dest="command_storage_id", help="命令记录页面指定 command storage ID，仅当 audit-type=command 时生效。")
    audit_list.add_argument(
        "--command-storage-scope",
        dest="command_storage_scope",
        choices=["all"],
        help="命令记录页面设为 `all` 时汇总全部可访问 command storage，仅当 audit-type=command 时生效。",
    )
    add_filter_arguments(audit_list)
    audit_list.set_defaults(func=_audit_list)

    audit_get = subparsers.add_parser(
        "audit-get",
        help="按 ID 读取单条审计详情。",
        description=(
            "按审计类型和记录 ID 读取单条详情。"
            "当 audit-type=command 时，--id 必须使用 CLI 返回的稳定命令记录 ID。"
        ),
        formatter_class=CLIHelpFormatter,
    )
    audit_get.add_argument("--audit-type", required=True, choices=sorted(AUDIT_PATHS))
    audit_get.add_argument("--id", required=True, help="记录 ID；command 审计必须传入 CLI 返回的稳定 ID。")
    audit_get.set_defaults(func=_audit_get)

    terminal_sessions = subparsers.add_parser(
        "terminal-sessions",
        help="读取 terminal 在线或历史会话。",
        description="查询 terminal 组件的在线或历史会话，支持页面同款时间窗、搜索和精确字段过滤。",
        epilog="Examples:\n  " + "\n  ".join(TERMINAL_SESSION_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    terminal_sessions.add_argument("--view", choices=["online", "history"])
    _add_page_query_time_arguments(terminal_sessions)
    terminal_sessions.add_argument("--user", help="页面用户精确过滤；输入用户名或显示名时会解析成 `name(username)`。")
    terminal_sessions.add_argument("--account", help="页面账号精确过滤；输入名称或用户名时会解析成 `name(username)`。")
    terminal_sessions.add_argument("--asset", help="页面资产精确过滤；输入名称或地址时会解析成 `name(ip)`。")
    terminal_sessions.add_argument("--protocol", help="页面协议精确过滤。")
    terminal_sessions.add_argument("--login-from", dest="login_from", help="页面登录来源精确过滤；只支持 `WT/ST/RT/DT/VT`。")
    terminal_sessions.add_argument("--remote-addr", dest="remote_addr", help="页面远端地址精确过滤。")
    terminal_sessions.add_argument("--asset-id", dest="asset_id", help="资产 UUID 精确过滤。")
    terminal_sessions.add_argument("--order", help="页面排序字段。")
    add_filter_arguments(terminal_sessions)
    terminal_sessions.set_defaults(func=_terminal_sessions)

    job_list = subparsers.add_parser(
        "job-list",
        help="读取作业列表。",
        description="读取 `/api/v1/audits/jobs/` 作业列表，支持页面搜索和名称精确过滤。",
        epilog="Examples:\n  " + "\n  ".join(JOB_LIST_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    job_list.add_argument("--name", help="页面作业名称精确过滤。")
    job_list.add_argument("--search", help="页面搜索框的直接搜索关键字。")
    _add_pagination_arguments(job_list)
    add_filter_arguments(job_list)
    job_list.set_defaults(func=_job_list)

    command_storage_hint = subparsers.add_parser(
        "command-storage-hint",
        help="查看 command storage 选择上下文。",
        description="用于命令审计前确认默认 storage、可切换 storage 和是否需要显式指定。",
        epilog="Examples:\n  " + "\n  ".join(COMMAND_STORAGE_HINT_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    command_storage_hint.add_argument("--command-storage-id", dest="command_storage_id")
    command_storage_hint.add_argument("--command-storage-scope", dest="command_storage_scope", choices=["all"])
    add_filter_arguments(command_storage_hint)
    command_storage_hint.set_defaults(func=_command_storage_hint)

    audit_analyze = subparsers.add_parser(
        "audit-analyze",
        help="执行 capability 化的审计分析。",
        description="用于会话、命令、传输和异常行为等 capability 化分析。",
        epilog="Examples:\n  " + "\n  ".join(AUDIT_ANALYZE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    audit_analyze.add_argument("--capability", required=True)
    _add_common_audit_filter_arguments(
        audit_analyze,
        include_direction=True,
        include_keyword=True,
        include_storage=True,
        include_top=True,
    )
    audit_analyze.add_argument("--asset-keywords", dest="asset_keywords", help="敏感资产审计使用的资产关键字。")
    add_filter_arguments(audit_analyze)
    audit_analyze.set_defaults(func=_audit_analyze)

    audit_capabilities = subparsers.add_parser(
        "capabilities",
        help="列出可用的 audit-analyze capability。",
        description="输出所有由 jms_query.py audit-analyze 支持的 capability。",
        formatter_class=CLIHelpFormatter,
    )
    audit_capabilities.set_defaults(func=_audit_capabilities)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_and_print(args.func, args)


if __name__ == "__main__":
    raise SystemExit(main())
