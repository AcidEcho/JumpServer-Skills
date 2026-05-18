#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jms_audit_core import (  # noqa: E402
    _apply_common_filters,
    _asset_filter_evidence,
    _extract_account,
    _extract_asset,
    _extract_datetime,
    _extract_duration,
    _extract_filter_diagnostics,
    _extract_protocol,
    _extract_source_ip,
    _extract_status,
    _extract_user,
    _fetch_command_record_by_id,
    _fetch_command_records,
    _fetch_session_records,
    _fetch_terminal_session_records,
    _list_request_filters,
    _login_records,
    _normalize_job_audit_filters,
    _normalize_login_audit_filters,
    _normalize_operate_audit_filters,
    _normalize_password_change_audit_filters,
    _normalize_terminal_session_filters,
    _normalize_time_filters,
    _normalize_user_filter_payload,
    _operate_audit_server_filters,
    resolve_command_storage_context,
    run_capability,
)
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIHelpFormatter,
    add_filter_arguments,
    create_client,
    ensure_selected_org_context,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


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
COMMAND_AUDIT_CAPABILITIES = {"command-record-query", "high-risk-command-audit"}
COMMON_QUERY_FIELDS = ("date_from", "date_to", "days", "search")
AUDIT_ALLOWED_FIELDS = {
    "operate": COMMON_QUERY_FIELDS + ("user", "action", "resource_type"),
    "login": COMMON_QUERY_FIELDS + ("username", "ip", "type", "city", "mfa", "status"),
    "session": COMMON_QUERY_FIELDS + ("user", "asset", "asset_id", "account", "protocol", "login_from", "remote_addr", "order"),
    "terminal-session": COMMON_QUERY_FIELDS + ("user", "asset", "asset_id", "account", "protocol", "login_from", "remote_addr", "order"),
    "password_change": COMMON_QUERY_FIELDS + ("user", "change_by", "remote_addr"),
    "jobs": COMMON_QUERY_FIELDS + ("creator__name", "material"),
    "command": COMMON_QUERY_FIELDS + ("asset_id", "command_storage_id", "command_storage_scope", "order"),
    "ftp": COMMON_QUERY_FIELDS + ("user", "asset", "direction"),
}
AUDIT_STRATEGY_FIELDS = {
    "operate": (("user", "server_user_exact"), ("action", "server_action_exact"), ("resource_type", "server_resource_type_exact")),
    "login": (("username", "server_username_exact"), ("ip", "server_ip_exact"), ("type", "server_type_exact"), ("city", "server_city_exact"), ("mfa", "server_mfa_exact"), ("status", "server_status_exact")),
    "password_change": (("user", "server_user_exact"), ("change_by", "server_change_by_exact"), ("remote_addr", "server_remote_addr_exact")),
    "jobs": (("creator__name", "server_creator_name_exact"), ("material", "server_material_exact")),
    "session": (("user", "server_user_exact"), ("account", "server_account_exact"), ("asset", "server_asset_exact"), ("asset_id", "server_asset_id_exact"), ("protocol", "server_protocol_exact"), ("login_from", "server_login_from_exact"), ("remote_addr", "server_remote_addr_exact")),
    "terminal-session": (("user", "server_user_exact"), ("account", "server_account_exact"), ("asset", "server_asset_exact"), ("asset_id", "server_asset_id_exact"), ("protocol", "server_protocol_exact"), ("login_from", "server_login_from_exact"), ("remote_addr", "server_remote_addr_exact")),
    "command": (("asset_id", "server_asset_id_exact"),),
}
AUDIT_LIST_EXAMPLES = [
    "python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login --days 30 --username 示例用户(example.user)",
    "python3 subskills/query/scripts/jms_audit.py audit-list --audit-type operate --days 30 --user example.user --action 创建 --resource-type 'User session'",
]
TERMINAL_SESSION_EXAMPLES = [
    "python3 subskills/query/scripts/jms_audit.py terminal-sessions --view history --days 7 --user example.user",
]
JOB_LIST_EXAMPLES = ["python3 subskills/query/scripts/jms_audit.py job-list --name 删除Windows用户"]
COMMAND_STORAGE_HINT_EXAMPLES = ["python3 subskills/query/scripts/jms_audit.py command-storage-hint"]
AUDIT_ANALYZE_EXAMPLES = [
    "python3 subskills/query/scripts/jms_audit.py audit-analyze --capability session-record-query --days 7 --user example.user",
]
RECENT_AUDIT_EXAMPLES = [
    "python3 subskills/query/scripts/jms_audit.py recent-audit --audit-type login --days 30 --username 示例用户(example.user)",
]
AUDIT_GET_EXAMPLES = [
    "python3 subskills/query/scripts/jms_audit.py audit-get --audit-type command --id <stable-command-id>",
    "audit-type=command 使用稳定 ID。",
]


def _merge_match_strategy(current: str, addition: str) -> str:
    parts = [item for item in str(current or "").split("+") if item]
    if addition not in parts:
        parts.append(addition)
    return "+".join(parts) if parts else addition


def _requested_server_filter_strategy(audit_type: str, filters: dict[str, Any], *, base: str = "server") -> str:
    strategy = str(base or "server")
    if filters.get("search") not in {None, ""}:
        strategy = "server_search" if strategy == "server" else _merge_match_strategy(strategy, "server_search")
    for key, strategy_name in AUDIT_STRATEGY_FIELDS.get(audit_type, ()):
        if filters.get(key) not in {None, ""}:
            strategy = strategy_name if strategy == "server" else _merge_match_strategy(strategy, strategy_name)
    return strategy


def _trim_audit_filters(audit_type: str, filters: dict[str, Any]) -> dict[str, Any]:
    allowed = set(AUDIT_ALLOWED_FIELDS.get(audit_type, COMMON_QUERY_FIELDS))
    return {key: value for key, value in filters.items() if key in allowed or str(key).startswith("_")}


def _normalize_audit_filters(audit_type: str, filters: dict[str, Any]) -> dict[str, Any]:
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


def _add_time_filter_arguments(parser: argparse.ArgumentParser, *, include_days: bool = True) -> None:
    parser.add_argument("--date-from", dest="date_from")
    parser.add_argument("--date-to", dest="date_to")
    if include_days:
        parser.add_argument("--days", type=int)


def _add_page_query_time_arguments(parser: argparse.ArgumentParser) -> None:
    _add_time_filter_arguments(parser)
    parser.add_argument("--search")


def _add_common_audit_filter_arguments(parser: argparse.ArgumentParser) -> None:
    _add_time_filter_arguments(parser)
    parser.add_argument("--user")
    parser.add_argument("--user-id", dest="user_id")
    parser.add_argument("--asset")
    parser.add_argument("--asset-keywords", dest="asset_keywords")
    parser.add_argument("--search")
    parser.add_argument("--status")
    parser.add_argument("--protocol")
    parser.add_argument("--account")
    parser.add_argument("--source-ip", dest="source_ip")
    parser.add_argument("--keyword")
    parser.add_argument("--direction")
    parser.add_argument("--command-storage-id", dest="command_storage_id")
    parser.add_argument("--command-storage-scope", dest="command_storage_scope", choices=["all"])
    parser.add_argument("--top", type=int)


def _attach_filter_diagnostics(result: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    diagnostics = _extract_filter_diagnostics(filters)
    if not diagnostics:
        return result
    payload = dict(result)
    payload.setdefault("filter_diagnostics", diagnostics)
    return payload


def _command_storage_hint_payload(filters: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or ensure_selected_org_context()
    storage_context = resolve_command_storage_context({**filters, "_org_id": org_id_from_context(context)})
    return {
        "storage_count": storage_context["available_command_storage_count"],
        "default_storage_count": storage_context["default_storage_count"],
        "storages": storage_context["available_command_storages"],
        "warning": storage_context["command_storage_hint"],
        **storage_context,
        **org_context_output(context),
    }


def _audit_list(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    filters = _trim_audit_filters(
        args.audit_type,
        merge_filter_args(
            args,
            explicit_fields=(
                "date_from", "date_to", "days", "search", "user", "username", "ip", "type", "city", "mfa", "status",
                "change_by", "remote_addr", "creator__name", "material", "asset", "asset_id", "account", "protocol",
                "login_from", "order", "action", "resource_type", "command_storage_id", "command_storage_scope",
            ),
            forbidden_fields=("limit", "offset"),
            usage_examples=AUDIT_LIST_EXAMPLES,
        ),
    )
    filters = _normalize_audit_filters(args.audit_type, _normalize_time_filters(filters, default_days=7))
    filters["_org_id"] = org_id
    filter_strategy = _requested_server_filter_strategy(args.audit_type, filters)
    if args.audit_type == "terminal-session":
        result, meta = _fetch_terminal_session_records(filters)
        filter_strategy = _requested_server_filter_strategy(args.audit_type, filters, base=meta.get("filter_strategy") or filter_strategy)
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
    total = len(result) if isinstance(result, list) else None
    return _attach_filter_diagnostics(
        {
            "audit_type": args.audit_type,
            "summary": {
                "total": total,
                "returned": total,
                "filters": {key: value for key, value in filters.items() if not str(key).startswith("_")},
                "filter_strategy": filter_strategy,
            },
            "filter_strategy": filter_strategy,
            "records": result,
            **org_context_output(context),
        },
        filters,
    )


def _audit_get(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    if args.audit_type == "command":
        result = _fetch_command_record_by_id(args.id, filters={"_org_id": org_id})
    else:
        result = client.get("%s%s/" % (AUDIT_PATHS[args.audit_type], args.id))
    return {"audit_type": args.audit_type, "record": result, **org_context_output(context)}


def _terminal_sessions(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    filters = _normalize_terminal_session_filters(
        _normalize_time_filters(
            merge_filter_args(
                args,
                explicit_fields=("date_from", "date_to", "days", "search", "user", "asset", "asset_id", "account", "protocol", "login_from", "remote_addr", "order"),
                forbidden_fields=("limit", "offset"),
                usage_examples=TERMINAL_SESSION_EXAMPLES,
            ),
            default_days=7,
        )
    )
    filters["_org_id"] = org_id
    preset = TERMINAL_SESSION_PRESETS.get(args.view or "")
    if preset:
        for key, value in preset.items():
            filters.setdefault(key, value)
    filtered, meta = _fetch_terminal_session_records(filters)
    filter_strategy = _requested_server_filter_strategy("terminal-session", filters, base=meta.get("filter_strategy") or "server")
    return _attach_filter_diagnostics(
        {
            "audit_type": "terminal-session",
            "view": args.view or "all",
            "summary": {
                "total": len(filtered),
                "filters": {key: value for key, value in filters.items() if not str(key).startswith("_")},
                "filter_strategy": filter_strategy,
                "resolved_asset": meta.get("resolved_asset"),
            },
            "records": [{**item, "asset_evidence": _asset_filter_evidence(item, expected=filters.get("asset"))} for item in filtered],
            **org_context_output(context),
        },
        filters,
    )


def _job_list(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    filters = merge_filter_args(args, explicit_fields=("name", "search"), forbidden_fields=("limit", "offset"), usage_examples=JOB_LIST_EXAMPLES)
    path = "/api/v1/audits/jobs/"
    records = client.list_paginated(path, params=_list_request_filters(path, filters))
    filter_strategy = "server"
    if filters.get("search") not in {None, ""}:
        filter_strategy = "server_search"
    if filters.get("name") not in {None, ""}:
        filter_strategy = "server_name_exact" if filter_strategy == "server" else _merge_match_strategy(filter_strategy, "server_name_exact")
    return {"resource": "job-list", "summary": {"total": len(records) if isinstance(records, list) else 0, "filters": filters, "filter_strategy": filter_strategy}, "records": records, **org_context_output(context)}


def _command_storage_hint(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, explicit_fields=("command_storage_id", "command_storage_scope"), usage_examples=COMMAND_STORAGE_HINT_EXAMPLES)
    return _command_storage_hint_payload(filters, context=context)


def _audit_analyze(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    filters = _normalize_user_filter_payload(
        merge_filter_args(
            args,
            explicit_fields=("date_from", "date_to", "days", "user", "user_id", "asset", "asset_keywords", "search", "keyword", "direction", "status", "protocol", "account", "source_ip", "command_storage_id", "command_storage_scope", "top"),
            forbidden_fields=("limit", "offset"),
            usage_examples=AUDIT_ANALYZE_EXAMPLES,
        )
    )
    filters["_org_id"] = org_id
    effective_filters = dict(filters)
    storage_context = None
    if args.capability in COMMAND_AUDIT_CAPABILITIES:
        storage_context = resolve_command_storage_context(effective_filters)
        if not effective_filters.get("command_storage_id"):
            if storage_context.get("selection_required"):
                return _attach_filter_diagnostics(
                    {"blocked": True, "block_reason": "Multiple command storages detected and no default storage is available. Select one command_storage_id before querying command audit capabilities.", "capability": args.capability, **_command_storage_hint_payload(effective_filters, context=context)},
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


def _format_recent_audit_record(audit_type: str, item: dict[str, Any], *, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    active_filters = dict(filters or {})
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
        "asset_evidence": _asset_filter_evidence(item, expected=active_filters.get("asset")),
        "raw": item,
    }
    if audit_type == "command":
        record["command"] = str(item.get("input") or item.get("command") or "").strip() or None
    elif audit_type == "login":
        record["reason"] = str(item.get("reason") or item.get("detail") or "").strip() or None
    elif audit_type == "operate":
        record["action"] = str(item.get("operate") or item.get("action") or item.get("type") or "").strip() or None
    return record


def _recent_audit(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    filters = _normalize_time_filters(
        merge_filter_args(
            args,
            explicit_fields=("date_from", "date_to", "days", "search", "user", "username", "ip", "type", "city", "mfa", "status", "asset", "asset_id", "protocol", "account", "login_from", "remote_addr", "order", "action", "resource_type", "command_storage_id", "command_storage_scope"),
            forbidden_fields=("limit", "offset"),
            usage_examples=RECENT_AUDIT_EXAMPLES,
        ),
        default_days=7,
    )
    filters["_org_id"] = org_id
    if args.audit_type == "operate":
        filters = _normalize_operate_audit_filters(filters)
    elif args.audit_type == "login":
        filters = _normalize_login_audit_filters(filters)
    elif args.audit_type == "session":
        filters = _normalize_terminal_session_filters(filters)
    filter_strategy = _requested_server_filter_strategy(args.audit_type, filters)
    if args.audit_type == "operate":
        client = create_client(org_id=org_id)
        result = client.list_paginated("/api/v1/audits/operate-logs/", params=_operate_audit_server_filters(filters))
        records = _apply_common_filters([item for item in result if isinstance(item, dict)], filters)
        if len(records) != len(result):
            filter_strategy = _merge_match_strategy(filter_strategy, "local_common_filters")
    elif args.audit_type == "login":
        records = _login_records(filters)
    elif args.audit_type == "session":
        records = _fetch_session_records(filters)
        filter_strategy = _requested_server_filter_strategy(args.audit_type, filters, base=next((str(item.get("_filter_strategy") or "").strip() for item in records if isinstance(item, dict) and str(item.get("_filter_strategy") or "").strip()), "server"))
    else:
        records = _fetch_command_records(filters)
        filter_strategy = _requested_server_filter_strategy(args.audit_type, filters, base="server+command_storage_context")
    formatted = [_format_recent_audit_record(args.audit_type, item, filters=filters) for item in records]
    payload = {
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
        payload.update(resolve_command_storage_context(filters))
    return payload


def _audit_capabilities(_: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {"id": item.capability_id, "name": item.name, "category": item.category, "priority": item.priority, "entrypoint": item.entrypoint}
        for item in sorted(run_capability.__globals__["CAPABILITY_BY_ID"].values(), key=lambda item: item.capability_id)
        if item.entrypoint.startswith("jms_audit.py audit-analyze")
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JumpServer 审计查询入口，属于 query 子 skill。", formatter_class=CLIHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_list = subparsers.add_parser("audit-list", help="读取登录、会话、命令等审计明细。", epilog="Examples:\n  " + "\n  ".join(AUDIT_LIST_EXAMPLES), formatter_class=CLIHelpFormatter)
    audit_list.add_argument("--audit-type", required=True, choices=sorted(AUDIT_PATHS))
    _add_page_query_time_arguments(audit_list)
    for name in ("user", "username", "ip", "type", "city", "mfa", "status", "material", "asset", "account", "protocol", "order", "action"):
        audit_list.add_argument("--" + name.replace("_", "-"), dest=name)
    audit_list.add_argument("--change-by", dest="change_by")
    audit_list.add_argument("--remote-addr", dest="remote_addr")
    audit_list.add_argument("--creator-name", dest="creator__name")
    audit_list.add_argument("--asset-id", dest="asset_id")
    audit_list.add_argument("--login-from", dest="login_from")
    audit_list.add_argument("--resource-type", dest="resource_type")
    audit_list.add_argument("--command-storage-id", dest="command_storage_id")
    audit_list.add_argument("--command-storage-scope", dest="command_storage_scope", choices=["all"])
    add_filter_arguments(audit_list)
    audit_list.set_defaults(func=_audit_list)

    audit_get = subparsers.add_parser("audit-get", help="按 ID 读取单条审计详情。", epilog="Examples:\n  " + "\n  ".join(AUDIT_GET_EXAMPLES), formatter_class=CLIHelpFormatter)
    audit_get.add_argument("--audit-type", required=True, choices=sorted(AUDIT_PATHS))
    audit_get.add_argument("--id", required=True)
    audit_get.set_defaults(func=_audit_get)

    terminal_sessions = subparsers.add_parser("terminal-sessions", help="读取 terminal 在线或历史会话。", epilog="Examples:\n  " + "\n  ".join(TERMINAL_SESSION_EXAMPLES), formatter_class=CLIHelpFormatter)
    terminal_sessions.add_argument("--view", choices=["online", "history"])
    _add_page_query_time_arguments(terminal_sessions)
    for name in ("user", "account", "asset", "protocol", "order"):
        terminal_sessions.add_argument("--" + name, dest=name)
    terminal_sessions.add_argument("--login-from", dest="login_from")
    terminal_sessions.add_argument("--remote-addr", dest="remote_addr")
    terminal_sessions.add_argument("--asset-id", dest="asset_id")
    add_filter_arguments(terminal_sessions)
    terminal_sessions.set_defaults(func=_terminal_sessions)

    job_list = subparsers.add_parser("job-list", help="读取作业列表。", epilog="Examples:\n  " + "\n  ".join(JOB_LIST_EXAMPLES), formatter_class=CLIHelpFormatter)
    job_list.add_argument("--name")
    job_list.add_argument("--search")
    add_filter_arguments(job_list)
    job_list.set_defaults(func=_job_list)

    command_storage_hint = subparsers.add_parser("command-storage-hint", help="查看 command storage 选择上下文。", formatter_class=CLIHelpFormatter)
    command_storage_hint.add_argument("--command-storage-id", dest="command_storage_id")
    command_storage_hint.add_argument("--command-storage-scope", dest="command_storage_scope", choices=["all"])
    add_filter_arguments(command_storage_hint)
    command_storage_hint.set_defaults(func=_command_storage_hint)

    audit_analyze = subparsers.add_parser("audit-analyze", help="执行审计分析 capability。", epilog="Examples:\n  " + "\n  ".join(AUDIT_ANALYZE_EXAMPLES), formatter_class=CLIHelpFormatter)
    audit_analyze.add_argument("--capability", required=True)
    _add_common_audit_filter_arguments(audit_analyze)
    add_filter_arguments(audit_analyze)
    audit_analyze.set_defaults(func=_audit_analyze)

    recent_audit = subparsers.add_parser("recent-audit", help="快速查看最近审计。", epilog="Examples:\n  " + "\n  ".join(RECENT_AUDIT_EXAMPLES), formatter_class=CLIHelpFormatter)
    recent_audit.add_argument("--audit-type", required=True, choices=["operate", "login", "session", "command"])
    _add_page_query_time_arguments(recent_audit)
    for name in ("user", "username", "ip", "type", "city", "mfa", "status", "asset", "account", "protocol", "order", "action"):
        recent_audit.add_argument("--" + name.replace("_", "-"), dest=name)
    recent_audit.add_argument("--asset-id", dest="asset_id")
    recent_audit.add_argument("--login-from", dest="login_from")
    recent_audit.add_argument("--remote-addr", dest="remote_addr")
    recent_audit.add_argument("--resource-type", dest="resource_type")
    recent_audit.add_argument("--command-storage-id", dest="command_storage_id")
    recent_audit.add_argument("--command-storage-scope", dest="command_storage_scope", choices=["all"])
    add_filter_arguments(recent_audit)
    recent_audit.set_defaults(func=_recent_audit)

    capabilities = subparsers.add_parser("capabilities", help="列出 audit-analyze capability。", formatter_class=CLIHelpFormatter)
    capabilities.set_defaults(func=_audit_capabilities)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_audit.py",
            deprecated_commands={"audit-list", "terminal-sessions", "job-list", "audit-analyze", "recent-audit"},
            usage_examples_by_command={"audit-list": AUDIT_LIST_EXAMPLES, "terminal-sessions": TERMINAL_SESSION_EXAMPLES, "job-list": JOB_LIST_EXAMPLES, "audit-analyze": AUDIT_ANALYZE_EXAMPLES, "recent-audit": RECENT_AUDIT_EXAMPLES},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
