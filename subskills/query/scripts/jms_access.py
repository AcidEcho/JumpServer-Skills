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

from jumpserver_common.jms_text_utils import (
    exact_first_filter as _exact_first_filter,
    lower_text as _lower,
    value_from_path as _value_from_path,
)
from jumpserver_common.jms_permission_match import (
    asset_node_paths as _asset_node_paths,
    build_node_lookup,
    match_permission_to_asset,
    node_full_value,
    permission_node_paths as _permission_node_paths,
)
from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    DEFAULT_PAGE_SIZE,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    ensure_selected_org_context,
    is_uuid_like,
    list_accessible_orgs,
    org_id_from_context,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


PERMISSION_PATH = "/api/v1/perms/asset-permissions/"


def _parse_display_style_value(value: Any) -> dict[str, str] | None:
    text = str(value or "").strip()
    if not text.endswith(")") or "(" not in text:
        return None
    name, rest = text.rsplit("(", 1)
    inner = rest[:-1].strip()
    if not inner:
        return None
    return {"name": name.strip(), "inner": inner}


def _parse_display_style_user(value: Any) -> dict[str, str] | None:
    parsed = _parse_display_style_value(value)
    if parsed is None:
        return None
    return {"name": parsed["name"], "username": parsed["inner"]}


def _parse_display_style_asset(value: Any) -> dict[str, str] | None:
    parsed = _parse_display_style_value(value)
    if parsed is None:
        return None
    return {"name": parsed["name"], "address": parsed["inner"]}


def _resolve_user(target: str | None = None, username: str | None = None, *, discovery=None) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    users = active_discovery.list_users()
    target_value = str(username or target or "").strip()
    if target and is_uuid_like(target):
        for item in users:
            if str(item.get("id")) == target:
                return item
    parsed_display = _parse_display_style_user(target_value)
    if parsed_display is not None:
        wanted_username = _lower(parsed_display.get("username"))
        wanted_name = _lower(parsed_display.get("name"))
        matches = [
            item
            for item in users
            if wanted_username
            and _lower(item.get("username")) == wanted_username
            and (not wanted_name or _lower(item.get("name")) == wanted_name)
        ]
    else:
        wanted = _lower(target_value)
        matches = [
            item
            for item in users
            if wanted and wanted in {_lower(item.get("username")), _lower(item.get("name"))}
        ]
    if not matches:
        raise CLIError(
            "无法解析用户标识。",
            payload=build_cli_guidance_payload(
                "user_not_found",
                user_message="当前组织下找不到你指定的用户，请改用更精确的用户名、显示名或用户 UUID。",
                action_hint="可以先用 `resolve --resource user --name <用户名>` 确认唯一用户对象。",
                user=target_value,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "用户标识匹配到多个候选对象。",
            payload=build_cli_guidance_payload(
                "ambiguous_user",
                user_message="当前输入命中了多个用户，请改用更精确的用户名或直接使用用户 UUID。",
                action_hint="建议先执行 `resolve --resource user --name <关键字>` 查看候选对象。",
                candidates=matches[:10],
            ),
        )
    return matches[0]


def _resolve_asset(target: str | None = None, name: str | None = None, *, discovery=None) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    assets = active_discovery.list_assets()
    target_value = str(name or target or "").strip()
    if target and is_uuid_like(target):
        for item in assets:
            if str(item.get("id")) == target:
                return item
    parsed_display = _parse_display_style_asset(target_value)
    if parsed_display is not None:
        wanted_address = _lower(parsed_display.get("address"))
        wanted_name = _lower(parsed_display.get("name"))
        matches = [
            item
            for item in assets
            if wanted_address
            and _lower(item.get("address")) == wanted_address
            and (not wanted_name or _lower(item.get("name")) == wanted_name)
        ]
    else:
        wanted = _lower(target_value)
        matches = [
            item
            for item in assets
            if wanted and wanted in {_lower(item.get("name")), _lower(item.get("address"))}
        ]
    if not matches:
        raise CLIError(
            "无法解析资产标识。",
            payload=build_cli_guidance_payload(
                "asset_not_found",
                user_message="当前组织下找不到你指定的资产，请改用更精确的资产名称、地址或资产 UUID。",
                action_hint="可以先用 `resolve --resource asset --name <资产名>` 确认唯一资产对象。",
                asset=target_value,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "资产标识匹配到多个候选对象。",
            payload=build_cli_guidance_payload(
                "ambiguous_asset",
                user_message="当前输入命中了多个资产，请改用更精确的名称、地址或直接使用资产 UUID。",
                action_hint="建议先执行 `resolve --resource asset --name <关键字>` 查看候选对象。",
                candidates=matches[:10],
            ),
        )
    return matches[0]


def _list_permissions(*, client=None) -> list[dict[str, Any]]:
    active_client = client or create_client()
    payload = active_client.list_paginated(PERMISSION_PATH)
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


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


def _build_command_org_context(selected_org: dict[str, Any], accessible_orgs: list[dict[str, Any]]) -> dict[str, Any]:
    effective_org = {**selected_org, "source": "command_explicit"}
    effective_org_id = str(effective_org.get("id") or "").strip()
    switchable_orgs = [
        item
        for item in accessible_orgs
        if str(item.get("id") or "").strip() and str(item.get("id") or "").strip() != effective_org_id
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


def _resolve_command_query_scope(args: argparse.Namespace) -> dict[str, Any]:
    org_id = str(getattr(args, "org_id", None) or "").strip()
    org_name = str(getattr(args, "org_name", None) or "").strip()
    if not org_id and not org_name:
        org_context = ensure_selected_org_context()
        effective_org_id = org_id_from_context(org_context)
        return {
            "client": create_client(org_id=effective_org_id),
            "discovery": create_discovery(org_id=effective_org_id),
            "org_context": org_context,
        }

    accessible_orgs = list_accessible_orgs()
    if org_id:
        matches = [item for item in accessible_orgs if str(item.get("id") or "").strip() == org_id]
    else:
        matches = _exact_first_filter([item for item in accessible_orgs if isinstance(item, dict)], org_name, "name")
    if not matches:
        raise CLIError(
            "Organization %s is not accessible in the current environment." % (org_id or org_name),
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


def _normalize_effective_access_payload(payload, *, resource: str) -> tuple[list[dict[str, Any]], int]:
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


def _append_unique_effective_records(target, new_records, *, seen_ids) -> None:
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


def _effective_user_access(user: dict[str, Any], *, client=None, org_context=None) -> dict[str, Any]:
    active_client = client or create_client()
    user_id = str(user.get("id") or "")
    assets_path = "/api/v1/perms/users/%s/assets/" % user_id
    nodes_path = "/api/v1/perms/users/%s/nodes/" % user_id
    asset_params = {"all": 1, "asset": "", "node": "", "offset": 0, "limit": DEFAULT_PAGE_SIZE, "display": 1, "draw": 1}
    node_params = {"all": 1, "offset": 0, "limit": DEFAULT_PAGE_SIZE}
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
    result = {
        "asset_count": asset_count,
        "node_count": node_count,
        "assets": assets,
        "nodes": nodes,
        "matched_permissions": [],
        "data_source": {
            "assets_endpoint": assets_path,
            "assets_params": asset_params,
            "assets_reported_total": reported_asset_count,
            "nodes_endpoint": nodes_path,
            "nodes_params": node_params,
            "nodes_reported_total": reported_node_count,
        },
        "warnings": [*asset_warnings, *node_warnings],
    }
    if org_context is not None:
        result.update(org_context_output(org_context))
    return result


def _user_assets(args: argparse.Namespace) -> dict[str, Any]:
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


def _user_nodes(args: argparse.Namespace) -> dict[str, Any]:
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


def _user_asset_access(args: argparse.Namespace) -> dict[str, Any]:
    _validate_user_selector(args)
    _validate_asset_selector(args)
    _validate_org_override_selector(args)
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


def _add_optional_org_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--org-id")
    parser.add_argument("--org-name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 用户有效访问范围查询入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    user_assets = subparsers.add_parser(
        "user-assets",
        help="查询用户当前可访问资产。",
        description="读取 JumpServer effective access 接口，返回用户在指定组织下当前可访问的资产。",
        formatter_class=CLIHelpFormatter,
    )
    user_assets.add_argument("--user-id")
    user_assets.add_argument("--username", "--user-name", dest="username")
    _add_optional_org_arguments(user_assets)
    user_assets.set_defaults(func=_user_assets)

    user_nodes = subparsers.add_parser(
        "user-nodes",
        help="查询用户当前可访问节点。",
        description="读取 JumpServer effective access 接口，返回用户在指定组织下当前可访问的节点。",
        formatter_class=CLIHelpFormatter,
    )
    user_nodes.add_argument("--user-id")
    user_nodes.add_argument("--username", "--user-name", dest="username")
    _add_optional_org_arguments(user_nodes)
    user_nodes.set_defaults(func=_user_nodes)

    user_asset_access = subparsers.add_parser(
        "user-asset-access",
        help="查询用户在某资产下可用的账号和协议。",
        description="从用户和资产两个维度读取有效访问范围，返回账号和协议集合。",
        formatter_class=CLIHelpFormatter,
    )
    user_asset_access.add_argument("--user-id")
    user_asset_access.add_argument("--username", "--user-name", dest="username")
    user_asset_access.add_argument("--asset-id")
    user_asset_access.add_argument("--asset-name")
    _add_optional_org_arguments(user_asset_access)
    user_asset_access.set_defaults(func=_user_asset_access)

    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_access.py",
            deprecated_commands=set(),
            usage_examples_by_command={},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())

