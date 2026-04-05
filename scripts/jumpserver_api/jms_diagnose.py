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
    _extract_account,
    _extract_asset,
    _extract_datetime,
    _extract_duration,
    _extract_protocol,
    _extract_source_ip,
    _extract_status,
    _extract_user,
    _fetch_command_records,
    _fetch_session_records,
    _login_records,
    _normalize_login_audit_filters,
    _normalize_operate_audit_filters,
    _normalize_terminal_session_filters,
    _normalize_ticket_filters,
    _normalize_time_filters,
    _operate_audit_server_filters,
    _resolve_asset,
    _resolve_user,
    build_node_lookup,
    explain_asset_permissions,
    match_permission_to_asset,
    run_capability,
)
from jumpserver_api.jms_capabilities import CAPABILITIES
from jumpserver_api.jms_runtime import (
    build_org_selection_required_payload,
    CLIError,
    CLIHelpFormatter,
    DEFAULT_PAGE_SIZE,
    ORG_SELECTION_NEXT_STEP,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    current_runtime_values,
    ensure_selected_org_context,
    get_config_status,
    list_accessible_orgs,
    org_context_output,
    merge_filter_args,
    parse_json_arg,
    persist_selected_org,
    require_confirmation,
    resolve_effective_org_context,
    resolve_platform_reference,
    run_and_print,
    user_profile,
    write_local_env_config,
)


SELECT_ORG_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
MISSING_ENDPOINT_PATH_REASON_CODE = "missing_endpoint_path"
UNSUPPORTED_VERIFICATION_METHOD_REASON_CODE = "unsupported_verification_method"

SELECT_ORG_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_diagnose.py select-org",
    "python3 scripts/jumpserver_api/jms_diagnose.py select-org --org-name Default",
]
RECENT_AUDIT_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type login --days 30 --username 古思清(gusiqing) --status 1 --limit 5",
    "python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type session --user gusiqing --date-from '2026-03-23 00:00:00' --date-to '2026-03-23 23:59:59' --protocol ssh --limit 10",
    "python3 scripts/jumpserver_api/jms_diagnose.py recent-audit --audit-type operate --days 30 --user gusiqing --action 创建 --resource-type 'User session' --limit 20",
]
REPORTS_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_diagnose.py reports --report-type account-statistic --days 30",
]
INSPECT_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_diagnose.py inspect --capability hot-assets-ranking --days 30 --top 10 --limit 10",
    "python3 scripts/jumpserver_api/jms_diagnose.py inspect --capability system-settings-overview",
]
RECENT_AUDIT_STRATEGY_FIELDS = {
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
    "session": (
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


def _config_status(_: argparse.Namespace):
    return get_config_status()


def _config_write(args: argparse.Namespace):
    require_confirmation(args)
    payload = parse_json_arg(
        args.payload,
        source="--payload",
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py config-write --payload '{\"JMS_API_URL\": \"https://jump.example.com\"}' --confirm",
        ],
    )
    return write_local_env_config(payload)


def _ping(_: argparse.Namespace):
    client = create_client()
    health = client.health_check()
    profile = user_profile(client)
    org_context = resolve_effective_org_context()
    current = client.get("/api/v1/orgs/orgs/current/")
    config_status = get_config_status()
    return {
        "health": health,
        "profile": profile,
        "candidate_orgs": org_context.get("candidate_orgs"),
        "current_org": current,
        "auth_mode": config_status.get("auth_mode"),
        "config_status": config_status,
        **org_context_output(org_context),
    }


def _add_pagination_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, help="返回条数上限。")
    parser.add_argument("--offset", type=int, help="分页偏移量。")


def _add_time_filter_arguments(parser: argparse.ArgumentParser, *, include_days: bool = True) -> None:
    parser.add_argument("--date-from", dest="date_from", help="开始时间，格式如 `2026-03-23 00:00:00`。")
    parser.add_argument("--date-to", dest="date_to", help="结束时间，格式如 `2026-03-23 23:59:59`。")
    if include_days:
        parser.add_argument("--days", type=int, help="最近 N 天；未显式给时间窗时使用。")


def _add_page_query_time_arguments(parser: argparse.ArgumentParser) -> None:
    _add_time_filter_arguments(parser)
    parser.add_argument("--search", help="页面搜索框的直接搜索关键字。")
    _add_pagination_arguments(parser)


def _add_enabled_flag_argument(parser: argparse.ArgumentParser, flag_name: str, *, dest: str, help_text: str) -> None:
    parser.add_argument(flag_name, dest=dest, action="store_const", const=1, default=None, help=help_text)


def _merge_match_strategy(current: str, addition: str) -> str:
    parts = [item for item in str(current or "").split("+") if item]
    if addition not in parts:
        parts.append(addition)
    return "+".join(parts) if parts else addition


def _requested_server_filter_strategy(audit_type: str, filters: dict[str, object], *, base: str = "server") -> str:
    strategy = str(base or "server")
    if filters.get("search") not in {None, ""}:
        strategy = "server_search" if strategy == "server" else _merge_match_strategy(strategy, "server_search")
    for key, strategy_name in RECENT_AUDIT_STRATEGY_FIELDS.get(audit_type, ()):
        if filters.get(key) not in {None, ""}:
            strategy = strategy_name if strategy == "server" else _merge_match_strategy(strategy, strategy_name)
    return strategy


def _add_lookup_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="按名称精确优先匹配。")
    parser.add_argument("--search", help="服务端搜索关键字。")
    _add_pagination_arguments(parser)


def _select_org(args: argparse.Namespace):
    candidates = list_accessible_orgs()
    current_context = resolve_effective_org_context(auto_select=False)
    provided_selectors = [
        name
        for name, value in {"org_id": getattr(args, "org_id", None), "org_name": getattr(args, "org_name", None)}.items()
        if str(value or "").strip()
    ]
    if len(provided_selectors) > 1:
        raise CLIError(
            "组织选择参数冲突。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="`select-org` 只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                provided=provided_selectors,
            ),
        )
    if not args.org_id and not getattr(args, "org_name", None):
        if current_context.get("selection_required"):
            return build_org_selection_required_payload(current_context)
        return {
            "selection_required": False,
            "candidate_orgs": candidates,
            "next_step": ORG_SELECTION_NEXT_STEP,
            **org_context_output(current_context),
        }
    target_org_id = str(getattr(args, "org_id", None) or "").strip()
    target_org_name = str(getattr(args, "org_name", None) or "").strip()
    if target_org_id:
        matches = [item for item in candidates if str(item.get("id") or "").strip() == target_org_id]
    else:
        matches = _exact_first_filter([item for item in candidates if isinstance(item, dict)], target_org_name, "name")
    if not matches:
        raise CLIError(
            "指定的组织当前不可访问。",
            payload=build_cli_guidance_payload(
                SELECT_ORG_REASON_CODE,
                user_message="当前账号下找不到你指定的组织，请先从 `candidate_orgs` 里确认可访问组织。",
                action_hint="可以先执行不带参数的 `select-org` 查看候选组织，再改用 `--org-id` 或精确的 `--org-name`。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                org_id=target_org_id or None,
                org_name=target_org_name or None,
                candidate_orgs=candidates,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "给定的组织名称匹配到多个候选组织。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称或直接使用 `--org-id`。",
                action_hint="优先从返回的 `candidate_orgs` 中复制准确的 org_id 再执行。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                org_name=target_org_name or None,
                candidate_orgs=matches[:10],
            ),
        )
    selected = matches[0]
    selected_org_id = str(selected.get("id") or "").strip()
    preview_scope = "%s (%s)" % (
        str(selected.get("name") or "").strip() or "Unknown",
        str(selected.get("id") or "").strip() or "<unknown-org-id>",
    )
    preview_context = {
        **current_context,
        "effective_org": {**selected, "source": "user_selected"},
        "switchable_orgs": [item for item in candidates if str(item.get("id") or "") != selected_org_id],
        "switchable_org_count": len([item for item in candidates if str(item.get("id") or "") != selected_org_id]),
        "org_context_hint": (
            "当前预览的查询范围将切换为组织 %s；确认写入后才能按该组织继续查询。"
            % preview_scope
        ),
    }
    if not args.confirm:
        return {
            "selection_required": False,
            "next_step": "python3 scripts/jumpserver_api/jms_diagnose.py select-org --org-id %s --confirm" % selected_org_id,
            **org_context_output(preview_context),
        }
    require_confirmation(args)
    persisted = persist_selected_org(selected_org_id)
    confirmed_context = {
        **preview_context,
        "org_context_hint": (
            "当前查询范围固定为组织 %s；如需切换查询范围，请先切换组织。"
            % preview_scope
            if preview_context["switchable_org_count"]
            else None
        ),
    }
    return {
        "selection_required": False,
        "current_nonsecret": persisted["current_nonsecret"],
        "env_file_path": persisted["env_file_path"],
        **org_context_output(confirmed_context),
    }


def _resolve(args: argparse.Namespace):
    ensure_selected_org_context()
    client = create_client()
    discovery = create_discovery()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py resolve --resource organization --name Default",
            "python3 scripts/jumpserver_api/jms_diagnose.py resolve --resource user --name gusiqing --limit 5",
        ],
    )
    if args.resource == "asset":
        items = discovery.list_assets()
        field_names = ("id", "name", "address")
    elif args.resource == "node":
        items = discovery.list_nodes()
        field_names = ("id", "name", "value", "full_value")
    elif args.resource == "user":
        items = discovery.list_users()
        field_names = ("id", "name", "username", "email")
    elif args.resource == "user-group":
        items = discovery.list_user_groups()
        field_names = ("id", "name")
    elif args.resource == "organization":
        items = client.list_paginated("/api/v1/orgs/orgs/")
        field_names = ("id", "name")
    elif args.resource == "account":
        items = client.list_paginated("/api/v1/accounts/accounts/")
        field_names = ("id", "name", "username")
    elif args.resource == "platform":
        items = [item.to_dict() for item in discovery.list_platforms()]
        field_names = ("id", "name", "slug", "category")
    elif args.resource == "permission":
        items = client.list_paginated("/api/v1/perms/asset-permissions/")
        field_names = ("id", "name")
    else:
        raise CLIError("Unsupported resolve resource: %s" % args.resource)

    if args.id:
        matches = [item for item in items if str(item.get("id")) == args.id]
    else:
        wanted = str(args.name or filters.get("name") or "").strip()
        matches = _exact_first_filter([item for item in items if isinstance(item, dict)], wanted, *field_names)
    return {"resource": args.resource, "matches": matches[: int(filters.get("limit") or 50)]}


def _resolve_platform(args: argparse.Namespace):
    ensure_selected_org_context()
    return resolve_platform_reference(args.value)


def _require_exactly_one_selector(*, values: dict[str, str | None], message: str) -> None:
    provided = [name for name, value in values.items() if str(value or "").strip()]
    if len(provided) != 1:
        raise CLIError(message, payload={"provided": provided})


def _validate_user_selector(args: argparse.Namespace) -> None:
    _require_exactly_one_selector(
        values={"user_id": args.user_id, "username": args.username},
        message="Provide exactly one of --user-id or --username.",
    )


def _validate_asset_selector(args: argparse.Namespace) -> None:
    _require_exactly_one_selector(
        values={"asset_id": args.asset_id, "asset_name": args.asset_name},
        message="Provide exactly one of --asset-id or --asset-name.",
    )


def _validate_org_override_selector(args: argparse.Namespace) -> None:
    provided = [
        name
        for name, value in {
            "org_id": getattr(args, "org_id", None),
            "org_name": getattr(args, "org_name", None),
        }.items()
        if str(value or "").strip()
    ]
    if len(provided) > 1:
        raise CLIError(
            "Provide at most one of --org-id or --org-name.",
            payload={"provided": provided},
        )


def _build_command_org_context(selected_org: dict, accessible_orgs: list[dict]) -> dict:
    effective_org = {**selected_org, "source": "command_explicit"}
    effective_org_id = str(effective_org.get("id") or "").strip()
    switchable_orgs = [
        item for item in accessible_orgs if str(item.get("id") or "").strip() and str(item.get("id") or "").strip() != effective_org_id
    ]
    org_scope = "%s (%s)" % (
        str(effective_org.get("name") or "").strip() or "Unknown",
        effective_org_id or "<unknown-org-id>",
    )
    return {
        "accessible_orgs": accessible_orgs,
        "candidate_orgs": accessible_orgs,
        "effective_org": effective_org,
        "multiple_accessible_orgs": len(accessible_orgs) > 1,
        "selection_required": False,
        "reserved_org_auto_select_eligible": False,
        "selected_org_accessible": True,
        "switchable_orgs": switchable_orgs,
        "switchable_org_count": len(switchable_orgs),
        "org_context_hint": "当前查询范围固定为组织 %s；本次命令仅临时按该组织执行，不会写回本地配置。" % org_scope,
    }


def _resolve_command_query_scope(args: argparse.Namespace) -> dict:
    org_id = str(getattr(args, "org_id", None) or "").strip()
    org_name = str(getattr(args, "org_name", None) or "").strip()
    if not org_id and not org_name:
        org_context = ensure_selected_org_context()
        return {
            "client": create_client(),
            "discovery": create_discovery(),
            "org_context": org_context,
        }

    accessible_orgs = list_accessible_orgs()
    if org_id:
        matches = [item for item in accessible_orgs if str(item.get("id") or "").strip() == org_id]
    else:
        matches = _exact_first_filter([item for item in accessible_orgs if isinstance(item, dict)], org_name, "name")
    if not matches:
        raise CLIError(
            "Organization %s is not accessible in the current environment."
            % (org_id or org_name),
            payload={
                "org_id": org_id or None,
                "org_name": org_name or None,
                "candidate_orgs": accessible_orgs,
            },
        )
    if len(matches) > 1:
        raise CLIError(
            "Multiple organizations matched the provided identifier.",
            payload={
                "org_id": org_id or None,
                "org_name": org_name or None,
                "candidate_orgs": matches[:10],
            },
        )
    org_context = _build_command_org_context(dict(matches[0]), accessible_orgs)
    effective_org_id = str((org_context.get("effective_org") or {}).get("id") or "").strip()
    return {
        "client": create_client(org_id=effective_org_id),
        "discovery": create_discovery(org_id=effective_org_id),
        "org_context": org_context,
    }


def _normalize_effective_access_payload(payload, *, resource: str):
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        return records, len(records)
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        records = [item for item in (payload.get("results") or []) if isinstance(item, dict)]
        try:
            total = int(payload.get("count"))
        except (TypeError, ValueError):
            total = len(records)
        return records, max(total, len(records))
    raise CLIError(
        "Effective %s API returned an unexpected payload." % resource,
        payload={"resource": resource, "payload_type": type(payload).__name__},
    )


def _append_unique_effective_records(target, new_records, *, seen_ids):
    for item in new_records:
        record_id = str(item.get("id") or "").strip() if isinstance(item, dict) else ""
        if record_id:
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
        target.append(item)


def _fetch_effective_access_records(client, path: str, *, resource: str, params=None):
    payload = client.get(path, params=params)
    records, reported_total = _normalize_effective_access_payload(payload, resource=resource)
    collected = []
    seen_ids = set()
    _append_unique_effective_records(collected, records, seen_ids=seen_ids)
    warnings = []
    next_ref = payload.get("next") if isinstance(payload, dict) else None
    while next_ref:
        page_payload = client.get(next_ref)
        page_records, _ = _normalize_effective_access_payload(page_payload, resource=resource)
        if not page_records:
            break
        _append_unique_effective_records(collected, page_records, seen_ids=seen_ids)
        next_ref = page_payload.get("next") if isinstance(page_payload, dict) else None
    return collected, len(collected), reported_total, warnings


def _effective_user_access(user, *, client=None, org_context=None):
    active_client = client or create_client()
    user_id = str(user.get("id") or "")
    assets_path = "/api/v1/perms/users/%s/assets/" % user_id
    nodes_path = "/api/v1/perms/users/%s/nodes/" % user_id
    asset_params = {"all": 1, "asset": "", "node": "", "offset": 0, "limit": DEFAULT_PAGE_SIZE, "display": 1, "draw": 1}
    node_params = {"all": 1}
    assets, asset_count, reported_asset_count, asset_warnings = _fetch_effective_access_records(
        active_client,
        assets_path,
        resource="assets",
        params=asset_params,
    )
    nodes, node_count, reported_node_count, node_warnings = _fetch_effective_access_records(
        active_client,
        nodes_path,
        resource="nodes",
        params=node_params,
    )
    warnings = [*asset_warnings, *node_warnings]
    result = {
        "asset_count": asset_count,
        "node_count": node_count,
        "assets": assets,
        "nodes": nodes,
        "matched_permissions": [],
        "data_source": {
            "assets_endpoint": assets_path,
            "assets_params": asset_params,
            "nodes_endpoint": nodes_path,
            "nodes_params": node_params,
        },
        "warnings": warnings,
    }
    if org_context is not None:
        result.update(org_context_output(org_context))
    return result


def _user_assets(args: argparse.Namespace):
    _validate_user_selector(args)
    _validate_org_override_selector(args)

    query_scope = _resolve_command_query_scope(args)
    user = _resolve_user(args.user_id, args.username, discovery=query_scope["discovery"])
    return {
        "user": user,
        **_effective_user_access(
            user,
            client=query_scope["client"],
            org_context=query_scope["org_context"],
        ),
    }


def _user_nodes(args: argparse.Namespace):
    _validate_user_selector(args)
    result = _user_assets(args)
    return {
        "user": result["user"],
        "node_count": result["node_count"],
        "nodes": result["nodes"],
        "matched_permissions": result["matched_permissions"],
        "data_source": result["data_source"],
        "warnings": result["warnings"],
        "effective_org": result.get("effective_org"),
        "switchable_orgs": result.get("switchable_orgs") or [],
        "switchable_org_count": int(result.get("switchable_org_count") or 0),
        "org_context_hint": result.get("org_context_hint"),
    }

def _user_asset_access(args: argparse.Namespace):
    _validate_user_selector(args)
    _validate_asset_selector(args)
    _validate_org_override_selector(args)
    from jumpserver_api.jms_analytics import _list_permissions

    query_scope = _resolve_command_query_scope(args)
    client = query_scope["client"]
    discovery = query_scope["discovery"]
    user = _resolve_user(args.user_id, args.username, discovery=discovery)
    user_group_ids = {str(item.get("id", item)) for item in user.get("groups", [])}
    asset = _resolve_asset(args.asset_id, args.asset_name, discovery=discovery)
    node_lookup = build_node_lookup(discovery=discovery)
    permed_accounts = set()
    permed_protocols = set()
    matched_permissions = []
    for item in _list_permissions(client=client):
        permission_id = str(item.get("id") or "").strip()
        if not permission_id:
            continue
        detail = client.get("/api/v1/perms/asset-permissions/%s/" % permission_id)
        user_ids = {str(obj.get("id", obj)) for obj in detail.get("users", [])}
        group_ids = {str(obj.get("id", obj)) for obj in detail.get("user_groups", [])}
        if str(user.get("id")) not in user_ids and not (group_ids & user_group_ids):
            continue
        match = match_permission_to_asset(detail, asset, node_lookup=node_lookup)
        if not match:
            continue
        matched_permissions.append(
            {
                "id": detail.get("id"),
                "name": detail.get("name"),
                "match_source": match["match_source"],
                "match_evidence": match["match_evidence"],
            }
        )
        for account in detail.get("accounts", []):
            if isinstance(account, dict):
                permed_accounts.add(str(account.get("name") or account.get("username") or account.get("id")))
            else:
                permed_accounts.add(str(account))
        for protocol in detail.get("protocols", []):
            if isinstance(protocol, dict):
                permed_protocols.add(str(protocol.get("name") or protocol.get("value") or protocol.get("label")))
            else:
                permed_protocols.add(str(protocol))
    return {
        "user": user,
        "asset": asset,
        "permed_accounts": sorted(permed_accounts),
        "permed_protocols": sorted(permed_protocols),
        "matched_permissions": matched_permissions,
        **org_context_output(query_scope["org_context"]),
    }


def _asset_permission_explain(args: argparse.Namespace):
    _validate_asset_selector(args)
    _validate_org_override_selector(args)
    query_scope = _resolve_command_query_scope(args)
    asset = _resolve_asset(args.asset_id, args.asset_name, discovery=query_scope["discovery"])
    explanation = explain_asset_permissions(
        asset,
        client=query_scope["client"],
        discovery=query_scope["discovery"],
    )
    return {**explanation, **org_context_output(query_scope["org_context"])}


def _format_recent_audit_record(audit_type: str, item: dict, *, filters: dict | None = None) -> dict:
    active_filters = dict(filters or {})
    asset_filter = active_filters.get("asset")
    record = {
        "id": item.get("id"),
        "user": _extract_user(item) or None,
        "asset": _extract_asset(item) or None,
        "account": _extract_account(item) or None,
        "protocol": _extract_protocol(item) or None,
        "source_ip": _extract_source_ip(item) or None,
        "status": _extract_status(item) or None,
        "timestamp": _extract_datetime(item),
        "duration_seconds": _extract_duration(item),
        "data_source": item.get("_data_source") or None,
        "filter_strategy": item.get("_filter_strategy") or None,
        "asset_evidence": _asset_filter_evidence(item, expected=asset_filter),
        "raw": item,
    }
    if audit_type == "command":
        record["command"] = str(item.get("input") or item.get("command") or "").strip() or None
    elif audit_type == "login":
        record["reason"] = str(item.get("reason") or item.get("detail") or "").strip() or None
    elif audit_type == "operate":
        record["action"] = str(item.get("operate") or item.get("action") or item.get("type") or "").strip() or None
    return record



def _recent_audit(args: argparse.Namespace):
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
                "username",
                "ip",
                "type",
                "city",
                "mfa",
                "status",
                "asset",
                "asset_id",
                "protocol",
                "account",
                "login_from",
                "remote_addr",
                "order",
                "action",
                "resource_type",
                "command_storage_id",
                "command_storage_scope",
                "limit",
                "offset",
            ),
            usage_examples=RECENT_AUDIT_EXAMPLES,
        ),
        default_days=7,
    )
    if args.audit_type == "operate":
        filters = _normalize_operate_audit_filters(filters)
    elif args.audit_type == "login":
        filters = _normalize_login_audit_filters(filters)
    elif args.audit_type == "session":
        filters = _normalize_terminal_session_filters(filters)
    handlers = {
        "login": _login_records,
        "session": _fetch_session_records,
        "command": _fetch_command_records,
    }
    filter_strategy = _requested_server_filter_strategy(args.audit_type, filters)
    if args.audit_type == "operate":
        client = create_client()
        server_filters = _operate_audit_server_filters(filters)
        result = client.list_paginated("/api/v1/audits/operate-logs/", params=server_filters)
        records = _apply_common_filters([item for item in result if isinstance(item, dict)], filters)
        if len(records) != len(result):
            filter_strategy = _merge_match_strategy(filter_strategy, "local_common_filters")
    else:
        records = handlers[args.audit_type](filters)
        if args.audit_type == "session":
            filter_strategy = _requested_server_filter_strategy(
                args.audit_type,
                filters,
                base=next(
                    (
                        str(item.get("_filter_strategy") or "").strip()
                        for item in records
                        if isinstance(item, dict) and str(item.get("_filter_strategy") or "").strip()
                    ),
                    "server",
                ),
            )
        elif args.audit_type == "command":
            filter_strategy = _requested_server_filter_strategy(args.audit_type, filters, base="server+command_storage_context")
    limit = int(filters.get("limit") or 20)
    formatted = [_format_recent_audit_record(args.audit_type, item, filters=filters) for item in records[:limit]]
    result = {
        "audit_type": args.audit_type,
        "summary": {
            "total": len(records),
            "returned": len(formatted),
            "filters": {key: value for key, value in filters.items() if not str(key).startswith("_")},
            "filter_strategy": filter_strategy,
            "data_sources": sorted({item.get("_data_source") for item in records if isinstance(item, dict) and item.get("_data_source")}),
            "filter_strategies": sorted({item.get("_filter_strategy") for item in records if isinstance(item, dict) and item.get("_filter_strategy")}),
        },
        "records": formatted,
        **org_context_output(context),
    }
    if args.audit_type == "command":
        from jumpserver_api.jms_analytics import resolve_command_storage_context

        result.update(resolve_command_storage_context(filters))
    return result


def _settings_category(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        default={"category": args.category},
        explicit_fields=("category", "id"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py settings-category --category security_auth",
        ],
    )
    return run_capability("setting-category-query", filters)


def _license_detail(_: argparse.Namespace):
    ensure_selected_org_context()
    return run_capability("license-detail-query", {})


def _tickets(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = _normalize_ticket_filters(
        merge_filter_args(
        args,
        explicit_fields=("search", "applicant_username_name", "state", "type", "limit", "offset"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py tickets --limit 10",
        ],
        ),
    )
    return run_capability("ticket-list-query", filters)


def _command_storages(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py command-storages --limit 10",
        ],
    )
    return run_capability("command-storage-query", filters)


def _replay_storages(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py replay-storages --limit 10",
        ],
    )
    return run_capability("replay-storage-query", filters)


def _terminals(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "limit", "offset"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py terminals --limit 10",
        ],
    )
    return run_capability("terminal-component-query", filters)


def _reports(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        default={"report_type": args.report_type},
        explicit_fields=(
            "report_type",
            "days",
            "date_from",
            "date_to",
            "limit",
            "offset",
            "top",
            "daily_success_and_failure_metrics",
            "total_long_time_no_login_accounts",
            "total_new_found_accounts",
            "total_groups_changed_accounts",
            "total_sudoers_changed_accounts",
            "total_authorized_keys_changed_accounts",
            "total_account_deleted_accounts",
            "total_password_expired_accounts",
            "total_long_time_password_accounts",
            "total_weak_password_accounts",
            "total_leaked_password_accounts",
            "total_repeated_password_accounts",
        ),
        usage_examples=REPORTS_EXAMPLES,
    )
    return run_capability("report-query", filters)


def _account_automations(args: argparse.Namespace):
    ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        explicit_fields=("days", "date_from", "date_to", "limit", "offset", "top", "search"),
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py account-automations --days 30 --limit 10",
        ],
    )
    return run_capability("account-automation-overview", filters)


def _endpoint_inventory(args: argparse.Namespace):
    ensure_selected_org_context()
    discovery = create_discovery()
    return discovery.core_inventory_payload(refresh=args.refresh)


def _endpoint_verify(args: argparse.Namespace):
    ensure_selected_org_context()
    client = create_client()
    filters = merge_filter_args(
        args,
        usage_examples=[
            "python3 scripts/jumpserver_api/jms_diagnose.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
        ],
    )
    path = str(args.path or filters.get("path") or "").strip()
    if not path:
        raise CLIError(
            "缺少待验证的端点路径。",
            payload=build_cli_guidance_payload(
                MISSING_ENDPOINT_PATH_REASON_CODE,
                user_message="请通过 `--path` 指定要验证的 API 路径。",
                action_hint="例如 `--path /api/v1/settings/setting/`；只有兼容旧命令时才建议放进 `--filters`。",
                suggested_commands=[
                    "python3 scripts/jumpserver_api/jms_diagnose.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
                ],
            ),
        )
    method = str(args.method or filters.get("method") or "GET").strip().upper()
    params = filters.get("params") if isinstance(filters.get("params"), dict) else None
    if method == "OPTIONS":
        payload = client.options(path, params=params)
    elif method == "GET":
        payload = client.get(path, params=params)
    else:
        raise CLIError(
            "不支持的验证方法：%s" % method,
            payload=build_cli_guidance_payload(
                UNSUPPORTED_VERIFICATION_METHOD_REASON_CODE,
                user_message="`endpoint-verify` 目前只支持 `GET` 和 `OPTIONS`。",
                action_hint="请把 `--method` 改成 `GET` 或 `OPTIONS`。",
                suggested_commands=[
                    "python3 scripts/jumpserver_api/jms_diagnose.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
                ],
                method=method,
            ),
        )
    return {"method": method, "path": path, "payload": payload}


def _inspect(args: argparse.Namespace):
    filters = merge_filter_args(
        args,
        explicit_fields=(
            "days",
            "date_from",
            "date_to",
            "limit",
            "offset",
            "top",
            "search",
            "user",
            "user_id",
            "asset",
            "asset_keywords",
            "status",
            "direction",
            "keyword",
            "protocol",
        ),
        usage_examples=INSPECT_EXAMPLES,
    )
    return run_capability(args.capability, filters)


def _capabilities(_: argparse.Namespace):
    return [
        {
            "id": item.capability_id,
            "name": item.name,
            "category": item.category,
            "priority": item.priority,
            "entrypoint": item.entrypoint,
        }
        for item in CAPABILITIES
        if item.entrypoint.startswith("jms_diagnose.py")
    ]


def _add_optional_org_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--org-id")
    parser.add_argument("--org-name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 诊断、访问分析与系统巡检入口。",
        epilog=(
            "推荐路径:\n"
            "  1. 预检先用 config-status 与 ping\n"
            "  2. 组织切换优先用 select-org --org-name/--org-id\n"
            "  3. 高级补充筛选优先用重复的 --filter key=value"
        ),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_status_parser = subparsers.add_parser(
        "config-status",
        help="查看本地运行时配置状态。",
        description="检查 .env 是否完整，以及当前鉴权模式和非敏感配置。",
        formatter_class=CLIHelpFormatter,
    )
    config_status_parser.add_argument("--json", action="store_true")
    config_status_parser.set_defaults(func=_config_status)

    config_write_parser = subparsers.add_parser(
        "config-write",
        help="写入本地 .env 配置。",
        description="把准备好的运行时配置写回本地 .env；执行前必须加 --confirm。",
        formatter_class=CLIHelpFormatter,
    )
    config_write_parser.add_argument("--payload", required=True)
    config_write_parser.add_argument("--confirm", action="store_true")
    config_write_parser.set_defaults(func=_config_write)

    ping_parser = subparsers.add_parser(
        "ping",
        help="检查连通性、当前用户和组织上下文。",
        description="验证 JumpServer 可连接，并回显当前用户、当前组织和可切换组织。",
        formatter_class=CLIHelpFormatter,
    )
    ping_parser.set_defaults(func=_ping)

    select_org_parser = subparsers.add_parser(
        "select-org",
        help="预览或切换当前组织。",
        description="不带参数时查看当前组织上下文；带 `--org-id` 或 `--org-name` 时预览切换结果，追加 `--confirm` 才会写回本地配置。",
        epilog="Examples:\n  " + "\n  ".join(SELECT_ORG_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    select_org_parser.add_argument("--org-id")
    select_org_parser.add_argument("--org-name")
    select_org_parser.add_argument("--confirm", action="store_true")
    select_org_parser.set_defaults(func=_select_org)

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="把自然语言对象名解析成精确对象。",
        description="用于资产、节点、用户、组织、平台等对象的精确解析。",
        formatter_class=CLIHelpFormatter,
    )
    resolve_parser.add_argument("--resource", required=True, choices=["asset", "node", "user", "user-group", "organization", "account", "platform", "permission"])
    resolve_parser.add_argument("--id")
    resolve_parser.add_argument("--name")
    resolve_parser.add_argument("--search", help="服务端搜索关键字。")
    _add_pagination_arguments(resolve_parser)
    add_filter_arguments(resolve_parser)
    resolve_parser.set_defaults(func=_resolve)

    resolve_platform_parser = subparsers.add_parser(
        "resolve-platform",
        help="解析平台名称或分类。",
        description="把平台名、slug 或 category 解析成平台对象。",
        formatter_class=CLIHelpFormatter,
    )
    resolve_platform_parser.add_argument("--value", required=True)
    resolve_platform_parser.set_defaults(func=_resolve_platform)

    user_assets_parser = subparsers.add_parser(
        "user-assets",
        help="查询用户当前可访问资产。",
        description="读取 JumpServer effective access 接口，返回用户在指定组织下当前可访问的资产。",
        formatter_class=CLIHelpFormatter,
    )
    user_assets_parser.add_argument("--user-id")
    user_assets_parser.add_argument("--username", "--user-name", dest="username")
    _add_optional_org_arguments(user_assets_parser)
    user_assets_parser.set_defaults(func=_user_assets)

    user_nodes_parser = subparsers.add_parser(
        "user-nodes",
        help="查询用户当前可访问节点。",
        description="读取 JumpServer effective access 接口，返回用户在指定组织下当前可访问的节点。",
        formatter_class=CLIHelpFormatter,
    )
    user_nodes_parser.add_argument("--user-id")
    user_nodes_parser.add_argument("--username", "--user-name", dest="username")
    _add_optional_org_arguments(user_nodes_parser)
    user_nodes_parser.set_defaults(func=_user_nodes)

    user_asset_access_parser = subparsers.add_parser(
        "user-asset-access",
        help="查询用户在某资产下可用的账号和协议。",
        description="从用户和资产两个维度读取有效访问范围，返回账号和协议集合。",
        formatter_class=CLIHelpFormatter,
    )
    user_asset_access_parser.add_argument("--user-id")
    user_asset_access_parser.add_argument("--username", "--user-name", dest="username")
    user_asset_access_parser.add_argument("--asset-id")
    user_asset_access_parser.add_argument("--asset-name")
    _add_optional_org_arguments(user_asset_access_parser)
    user_asset_access_parser.set_defaults(func=_user_asset_access)

    asset_permission_explain_parser = subparsers.add_parser(
        "asset-permission-explain",
        help="解释某资产命中的权限规则。",
        description="从资产视角解释直接资产、标签和节点继承命中的授权规则。",
        formatter_class=CLIHelpFormatter,
    )
    asset_permission_explain_parser.add_argument("--asset-id")
    asset_permission_explain_parser.add_argument("--asset-name")
    _add_optional_org_arguments(asset_permission_explain_parser)
    asset_permission_explain_parser.set_defaults(func=_asset_permission_explain)

    recent_audit_parser = subparsers.add_parser(
        "recent-audit",
        help="快速查看最近审计。",
        description="快速读取最近登录、会话、命令或操作审计，参数语义与页面过滤保持一致；未给时间时默认最近 7 天。",
        epilog="Examples:\n  " + "\n  ".join(RECENT_AUDIT_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    recent_audit_parser.add_argument("--audit-type", required=True, choices=["operate", "login", "session", "command"])
    _add_page_query_time_arguments(recent_audit_parser)
    recent_audit_parser.add_argument("--user", help="页面精确用户过滤；用于 operate 和 session，输入用户名或显示名时会解析成页面显示值。")
    recent_audit_parser.add_argument("--username", help="登录日志页面用户名精确过滤；最终下发 `name(username)`，仅当 audit-type=login 时生效。")
    recent_audit_parser.add_argument("--ip", help="登录日志页面来源 IP 精确过滤，仅当 audit-type=login 时生效。")
    recent_audit_parser.add_argument("--type", help="登录日志页面设备类型精确过滤；仅当 audit-type=login 时生效，只支持 `W/T/U`。")
    recent_audit_parser.add_argument("--city", help="登录日志页面城市精确过滤，仅当 audit-type=login 时生效。")
    recent_audit_parser.add_argument("--mfa", help="登录日志页面 MFA 状态精确过滤；仅当 audit-type=login 时生效，只支持 `0/1/2`。")
    recent_audit_parser.add_argument("--status", help="登录日志页面状态精确过滤；仅当 audit-type=login 时生效，只支持 `0/1`。")
    recent_audit_parser.add_argument("--asset", help="页面资产精确过滤；仅当 audit-type=session 时生效，输入名称或地址时会解析成 `name(ip)`。")
    recent_audit_parser.add_argument("--asset-id", dest="asset_id", help="资产 UUID 精确过滤；仅当 audit-type=session 或 command 时生效。")
    recent_audit_parser.add_argument("--account", help="页面账号精确过滤；仅当 audit-type=session 时生效，输入名称或用户名时会解析成 `name(username)`。")
    recent_audit_parser.add_argument("--protocol", help="页面协议精确过滤；仅当 audit-type=session 时生效。")
    recent_audit_parser.add_argument("--login-from", dest="login_from", help="页面登录来源精确过滤；仅当 audit-type=session 时生效，只支持 `WT/ST/RT/DT/VT`。")
    recent_audit_parser.add_argument("--remote-addr", dest="remote_addr", help="页面远端地址精确过滤；仅当 audit-type=session 时生效。")
    recent_audit_parser.add_argument("--order", help="页面排序字段；仅当 audit-type=session 或 command 时生效。")
    recent_audit_parser.add_argument("--command-storage-id", dest="command_storage_id", help="命令记录页面指定 command storage ID，仅当 audit-type=command 时生效。")
    recent_audit_parser.add_argument(
        "--command-storage-scope",
        dest="command_storage_scope",
        choices=["all"],
        help="命令记录页面设为 `all` 时汇总全部可访问 command storage，仅当 audit-type=command 时生效。",
    )
    recent_audit_parser.add_argument("--action", help="操作日志页面动作精确过滤；仅当 audit-type=operate 时生效，支持 create/创建 等值。")
    recent_audit_parser.add_argument("--resource-type", dest="resource_type", help="操作日志页面资源类型精确过滤，仅当 audit-type=operate 时生效。")
    add_filter_arguments(recent_audit_parser)
    recent_audit_parser.set_defaults(func=_recent_audit)

    settings_category_parser = subparsers.add_parser(
        "settings-category",
        help="按分类读取系统设置。",
        description="根据 settings category 读取系统设置原始结果。",
        formatter_class=CLIHelpFormatter,
    )
    settings_category_parser.add_argument("--category", required=True)
    settings_category_parser.add_argument("--id", help="页面 settings ID。")
    add_filter_arguments(settings_category_parser)
    settings_category_parser.set_defaults(func=_settings_category)

    license_parser = subparsers.add_parser(
        "license-detail",
        help="查看许可证详情。",
        description="读取当前环境下的许可证详情。",
        formatter_class=CLIHelpFormatter,
    )
    license_parser.set_defaults(func=_license_detail)

    tickets_parser = subparsers.add_parser(
        "tickets",
        help="查看工单列表。",
        description="查询工单列表，支持页面搜索和申请人/状态/类型精确过滤。",
        formatter_class=CLIHelpFormatter,
    )
    tickets_parser.add_argument("--search", help="页面搜索框的直接搜索关键字。")
    tickets_parser.add_argument("--applicant", dest="applicant_username_name", help="页面申请人精确过滤；输入用户名或显示名时会解析成申请人显示名。")
    tickets_parser.add_argument("--state", help="页面审批状态精确过滤；只支持 `closed/pending/approved/rejected/all`。")
    tickets_parser.add_argument("--type", help="页面工单类型精确过滤；只支持 `apply_asset/login_confirm/command_confirm/login_asset_confirm`。")
    _add_pagination_arguments(tickets_parser)
    add_filter_arguments(tickets_parser)
    tickets_parser.set_defaults(func=_tickets)

    command_storages_parser = subparsers.add_parser(
        "command-storages",
        help="查看命令存储列表。",
        description="查询 command storage 列表，支持名称搜索和分页。",
        formatter_class=CLIHelpFormatter,
    )
    _add_lookup_filter_arguments(command_storages_parser)
    add_filter_arguments(command_storages_parser)
    command_storages_parser.set_defaults(func=_command_storages)

    replay_storages_parser = subparsers.add_parser(
        "replay-storages",
        help="查看录像存储列表。",
        description="查询 replay storage 列表，支持名称搜索和分页。",
        formatter_class=CLIHelpFormatter,
    )
    _add_lookup_filter_arguments(replay_storages_parser)
    add_filter_arguments(replay_storages_parser)
    replay_storages_parser.set_defaults(func=_replay_storages)

    terminals_parser = subparsers.add_parser(
        "terminals",
        help="查看终端组件列表。",
        description="查询终端组件列表，支持名称搜索和分页。",
        formatter_class=CLIHelpFormatter,
    )
    _add_lookup_filter_arguments(terminals_parser)
    add_filter_arguments(terminals_parser)
    terminals_parser.set_defaults(func=_terminals)

    reports_parser = subparsers.add_parser(
        "reports",
        help="读取系统报表与 dashboard。",
        description="读取 account / asset 等系统报表，支持时间范围和分页参数。",
        epilog="Examples:\n  " + "\n  ".join(REPORTS_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    reports_parser.add_argument(
        "--report-type",
        required=True,
        choices=[
            "account-statistic",
            "account-automation",
            "asset-statistic",
            "asset-activity",
            "users",
            "user-change-password",
            "pam-dashboard",
            "change-secret-dashboard",
        ],
    )
    _add_time_filter_arguments(reports_parser)
    _add_pagination_arguments(reports_parser)
    reports_parser.add_argument("--top", type=int, help="排行类报表返回前 N 条。")
    _add_enabled_flag_argument(
        reports_parser,
        "--daily-success-and-failure-metrics",
        dest="daily_success_and_failure_metrics",
        help_text="change-secret-dashboard 页面指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-long-time-no-login-accounts",
        dest="total_long_time_no_login_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-new-found-accounts",
        dest="total_new_found_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-groups-changed-accounts",
        dest="total_groups_changed_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-sudoers-changed-accounts",
        dest="total_sudoers_changed_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-authorized-keys-changed-accounts",
        dest="total_authorized_keys_changed_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-account-deleted-accounts",
        dest="total_account_deleted_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-password-expired-accounts",
        dest="total_password_expired_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-long-time-password-accounts",
        dest="total_long_time_password_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-weak-password-accounts",
        dest="total_weak_password_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-leaked-password-accounts",
        dest="total_leaked_password_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    _add_enabled_flag_argument(
        reports_parser,
        "--total-repeated-password-accounts",
        dest="total_repeated_password_accounts",
        help_text="pam-dashboard 指标开关。",
    )
    add_filter_arguments(reports_parser)
    reports_parser.set_defaults(func=_reports)

    account_automations_parser = subparsers.add_parser(
        "account-automations",
        help="查看账号自动化与风险概览。",
        description="查询账号自动化、风险、备份和改密等聚合结果。",
        formatter_class=CLIHelpFormatter,
    )
    _add_time_filter_arguments(account_automations_parser)
    account_automations_parser.add_argument("--search", help="搜索关键字。")
    _add_pagination_arguments(account_automations_parser)
    account_automations_parser.add_argument("--top", type=int, help="排行类场景返回前 N 条。")
    add_filter_arguments(account_automations_parser)
    account_automations_parser.set_defaults(func=_account_automations)

    endpoint_inventory_parser = subparsers.add_parser(
        "endpoint-inventory",
        help="查看端点 inventory。",
        description="输出当前环境探测到的核心端点 inventory 与缓存。",
        formatter_class=CLIHelpFormatter,
    )
    endpoint_inventory_parser.add_argument("--refresh", action="store_true")
    endpoint_inventory_parser.set_defaults(func=_endpoint_inventory)

    endpoint_verify_parser = subparsers.add_parser(
        "endpoint-verify",
        help="验证单个端点的 GET/OPTIONS 能力。",
        description="对指定 API 路径做只读验证。",
        formatter_class=CLIHelpFormatter,
    )
    endpoint_verify_parser.add_argument("--path")
    endpoint_verify_parser.add_argument("--method", choices=["GET", "OPTIONS"], default="GET")
    add_filter_arguments(endpoint_verify_parser)
    endpoint_verify_parser.set_defaults(func=_endpoint_verify)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="执行 capability 化治理与巡检。",
        description="执行治理、巡检、统计类 capability，支持时间范围和常见筛选参数。",
        epilog="Examples:\n  " + "\n  ".join(INSPECT_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    inspect_parser.add_argument("--capability", required=True)
    _add_time_filter_arguments(inspect_parser)
    inspect_parser.add_argument("--search", help="搜索关键字。")
    inspect_parser.add_argument("--user", help="用户名或显示名。")
    inspect_parser.add_argument("--user-id", dest="user_id", help="用户 UUID。")
    inspect_parser.add_argument("--asset", help="资产名称、地址或关键字。")
    inspect_parser.add_argument("--asset-keywords", dest="asset_keywords", help="敏感资产关键字。")
    inspect_parser.add_argument("--status", help="状态过滤。")
    inspect_parser.add_argument("--direction", help="方向过滤，例如 upload / download。")
    inspect_parser.add_argument("--keyword", help="关键字过滤。")
    inspect_parser.add_argument("--protocol", help="协议过滤。")
    _add_pagination_arguments(inspect_parser)
    inspect_parser.add_argument("--top", type=int, help="排行类场景返回前 N 条。")
    add_filter_arguments(inspect_parser)
    inspect_parser.set_defaults(func=_inspect)

    capabilities_parser = subparsers.add_parser(
        "capabilities",
        help="列出 inspect capability 目录。",
        description="输出所有由 jms_diagnose.py inspect 支持的 capability。",
        formatter_class=CLIHelpFormatter,
    )
    capabilities_parser.set_defaults(func=_capabilities)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_and_print(args.func, args)


if __name__ == "__main__":
    raise SystemExit(main())
