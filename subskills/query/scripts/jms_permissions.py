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

from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    ensure_selected_org_context,
    is_uuid_like,
    list_accessible_orgs,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    parse_bool,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


PERMISSION_PATH = "/api/v1/perms/asset-permissions/"
PERMISSION_RESOURCE_PATHS = {
    "asset-permission": PERMISSION_PATH,
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

PERMISSION_LIST_EXAMPLES = [
    "python3 subskills/query/scripts/jms_permissions.py permission-list --resource asset-permission --name 生产环境授权",
    "python3 subskills/query/scripts/jms_permissions.py permission-list --resource asset-permission --filter users=example.user",
]
ASSET_PERM_USERS_EXAMPLES = [
    "python3 subskills/query/scripts/jms_permissions.py asset-perm-users --asset-id <asset-id>",
]


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


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


def _value_from_path(item: dict[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _exact_first_filter(items: list[dict[str, Any]], expected: Any, *paths: str) -> list[dict[str, Any]]:
    wanted = _lower(expected)
    if not wanted:
        return items
    exact_matches = []
    partial_matches = []
    for item in items:
        values = [_value_from_path(item, path) for path in paths]
        text_values = [_lower(value) for value in values if value not in {None, ""}]
        if wanted in text_values:
            exact_matches.append(item)
        elif any(wanted in value for value in text_values):
            partial_matches.append(item)
    return exact_matches or partial_matches


def _merge_match_strategy(current: str, addition: str) -> str:
    parts = [item for item in str(current or "").split("+") if item]
    if addition not in parts:
        parts.append(addition)
    return "+".join(parts) if parts else addition


def _without_pagination(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    payload.pop("limit", None)
    payload.pop("offset", None)
    return payload


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


def node_full_value(node_lookup, node_id: str, *, fallback_name: str | None = None) -> str:
    node = node_lookup.get(node_id) or {}
    full_value = str(node.get("full_value") or "").strip()
    if full_value:
        return full_value
    fallback = str(fallback_name or "").strip()
    if fallback.startswith("/"):
        return fallback
    name = str(node.get("value") or node.get("name") or fallback).strip()
    return "/%s" % name if name else ""


def build_node_lookup(*, discovery=None) -> dict[str, dict[str, Any]]:
    active_discovery = discovery or create_discovery()
    return {
        str(item.get("id") or "").strip(): item
        for item in active_discovery.list_nodes()
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _asset_node_paths(asset: dict[str, Any], *, node_lookup) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for node in asset.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        resolved_path = node_full_value(
            node_lookup,
            node_id,
            fallback_name=str(node.get("full_value") or node.get("name") or node.get("value") or ""),
        )
        if not resolved_path or resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        paths.append(
            {
                "path": resolved_path,
                "node_id": node_id or None,
                "node_name": str(node.get("name") or node.get("value") or "").strip() or None,
                "source": "asset.nodes",
            }
        )
    for display in asset.get("nodes_display", []) or []:
        display_text = str(display or "").strip()
        if not display_text or display_text in seen_paths:
            continue
        seen_paths.add(display_text)
        paths.append({"path": display_text, "node_id": None, "node_name": None, "source": "asset.nodes_display"})
    return paths


def _permission_node_paths(permission: dict[str, Any], *, node_lookup) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for node in permission.get("nodes", []) or []:
        if isinstance(node, dict):
            node_id = str(node.get("id") or "").strip()
            fallback_name = str(node.get("full_value") or node.get("name") or node.get("value") or "")
            resolved_path = node_full_value(node_lookup, node_id, fallback_name=fallback_name)
            node_name = str(node.get("name") or node.get("value") or "").strip() or None
        else:
            node_id = str(node or "").strip()
            resolved_path = node_full_value(node_lookup, node_id, fallback_name=node_id)
            node_name = None
        if not resolved_path or resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        paths.append(
            {
                "path": resolved_path,
                "node_id": node_id or None,
                "node_name": node_name,
                "source": "permission.nodes",
            }
        )
    return paths


def match_permission_to_asset(permission: dict[str, Any], asset: dict[str, Any], *, node_lookup) -> dict[str, Any] | None:
    asset_id = str(asset.get("id") or "").strip()
    permission_asset_ids = {
        str(obj.get("id", obj)).strip()
        for obj in permission.get("assets", []) or []
        if str(obj.get("id", obj) if isinstance(obj, dict) else obj).strip()
    }
    if asset_id and asset_id in permission_asset_ids:
        return {
            "match_source": "direct_asset",
            "match_evidence": {
                "matched_asset_id": asset_id,
                "permission_asset_ids": sorted(permission_asset_ids),
            },
        }

    asset_label_ids = {
        str(obj.get("id", obj)).strip()
        for obj in asset.get("labels", []) or []
        if str(obj.get("id", obj) if isinstance(obj, dict) else obj).strip()
    }
    permission_label_ids = {
        str(obj.get("id", obj)).strip()
        for obj in permission.get("labels", []) or []
        if str(obj.get("id", obj) if isinstance(obj, dict) else obj).strip()
    }
    matched_label_ids = sorted(asset_label_ids & permission_label_ids)
    if matched_label_ids:
        return {
            "match_source": "shared_label",
            "match_evidence": {
                "matched_label_ids": matched_label_ids,
                "asset_label_ids": sorted(asset_label_ids),
                "permission_label_ids": sorted(permission_label_ids),
            },
        }

    asset_paths = _asset_node_paths(asset, node_lookup=node_lookup)
    permission_paths = _permission_node_paths(permission, node_lookup=node_lookup)
    path_matches: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        asset_value = str(asset_path.get("path") or "").strip()
        if not asset_value:
            continue
        for permission_path in permission_paths:
            permission_value = str(permission_path.get("path") or "").strip()
            if not permission_value:
                continue
            prefix = permission_value.rstrip("/") + "/"
            if asset_value == permission_value or asset_value.startswith(prefix):
                depth = len([part for part in permission_value.split("/") if part])
                path_matches.append(
                    {
                        "depth": depth,
                        "asset_path": asset_path,
                        "permission_path": permission_path,
                        "relationship": "exact" if asset_value == permission_value else "ancestor_prefix",
                    }
                )
    if path_matches:
        best_match = sorted(
            path_matches,
            key=lambda item: (
                int(item.get("depth") or 0),
                len(str((item.get("permission_path") or {}).get("path") or "")),
            ),
            reverse=True,
        )[0]
        return {
            "match_source": "node_ancestor",
            "match_evidence": {
                "relationship": best_match["relationship"],
                "matched_asset_path": best_match["asset_path"],
                "matched_permission_path": best_match["permission_path"],
                "asset_node_paths": asset_paths,
                "permission_node_paths": permission_paths,
            },
        }
    return None


def _list_permissions(*, client=None) -> list[dict[str, Any]]:
    active_client = client or create_client()
    try:
        payload = active_client.list_paginated(PERMISSION_PATH)
    except Exception as exc:  # noqa: BLE001
        raise CLIError(
            "Asset permission API is unavailable or not yet confirmed in the current environment.",
            payload={"path": PERMISSION_PATH, "reason": str(exc)},
        ) from exc
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def explain_asset_permissions(asset: dict[str, Any], *, client=None, discovery=None) -> dict[str, Any]:
    active_client = client or create_client()
    active_discovery = discovery or create_discovery()
    node_lookup = build_node_lookup(discovery=active_discovery)
    matched_permissions = []
    for item in _list_permissions(client=active_client):
        permission_id = str(item.get("id") or "").strip()
        if not permission_id:
            continue
        detail = active_client.get("%s%s/" % (PERMISSION_PATH, permission_id))
        if not isinstance(detail, dict):
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
    return {
        "asset": asset,
        "matched_permission_count": len(matched_permissions),
        "matched_permissions": matched_permissions,
    }


def _permission_resource_path(resource: str) -> str:
    return PERMISSION_RESOURCE_PATHS[resource]


def _permission_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "is_expired": item.get("is_expired"),
        "from_ticket": item.get("from_ticket"),
        "date_start": item.get("date_start"),
        "date_expired": item.get("date_expired"),
    }


def _permission_detail_matches_user(detail: dict[str, Any], *, resolved_user: dict[str, Any]) -> bool:
    user_id = str(resolved_user.get("id") or "").strip()
    user_name = _lower(resolved_user.get("name"))
    user_username = _lower(resolved_user.get("username"))
    user_group_ids = {
        str(item.get("id", item)).strip()
        for item in (resolved_user.get("groups") or [])
        if str(item.get("id", item) if isinstance(item, dict) else item).strip()
    }
    expected_values = {value for value in {user_id, user_name, user_username} if value}

    for item in detail.get("users", []) or []:
        if isinstance(item, dict):
            item_id = str(item.get("id") or "").strip()
            item_name = _lower(item.get("name"))
            item_username = _lower(item.get("username"))
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


def _permission_list(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search", "user", "user_id", "users", "is_expired"),
        forbidden_fields=("limit", "offset"),
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
            discovery = create_discovery(org_id=org_id)
            broader_filters = _without_pagination({key: value for key, value in filters.items() if key not in {"user", "users"}})
            broader_records = client.list_paginated(path, params=broader_filters)
            broader_records = [item for item in broader_records if isinstance(item, dict)] if isinstance(broader_records, list) else []
            locally_filtered_records, resolved_user = _filter_asset_permission_records_by_user(
                client,
                broader_records,
                field_value,
                discovery=discovery,
            )
            filtered_records = locally_filtered_records
            match_strategy = _merge_match_strategy(match_strategy, "local_detail_user_filter")
            summary["requested_user_filter"] = {"field": field_name, "value": field_value}
            summary["matched_user"] = {
                "id": resolved_user.get("id"),
                "name": resolved_user.get("name"),
                "username": resolved_user.get("username"),
                "email": resolved_user.get("email"),
            }
            summary["local_detail_user_filter_candidate_count"] = len(broader_records)
            summary["local_detail_user_filter_total"] = len(locally_filtered_records)
            summary["local_detail_user_filter_total_before_pagination"] = len(locally_filtered_records)
            if not filtered_records and not summary.get("empty_reason_hint"):
                summary["empty_reason_hint"] = "当前组织下实时可见的 asset-permission 中未发现匹配该用户或其用户组的规则。"

    if isinstance(filtered_records, list) and args.resource == "asset-permission":
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


def _permission_get(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    client = create_client(org_id=org_id_from_context(context))
    record_id = str(args.id or args.permission_id or "").strip()
    if not record_id:
        raise CLIError("Provide --id. --permission-id is kept only for backward compatibility.")
    record = client.get("%s%s/" % (_permission_resource_path(args.resource), record_id))
    return {
        "resource": args.resource,
        "record": record,
        **org_context_output(context),
    }


def _asset_perm_users(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    discovery = create_discovery(org_id=org_id)
    filters = merge_filter_args(
        args,
        explicit_fields=("search",),
        forbidden_fields=("limit", "offset"),
        usage_examples=ASSET_PERM_USERS_EXAMPLES,
    )
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


def _asset_permission_explain(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.asset_id) == bool(args.asset_name):
        raise CLIError("Provide exactly one of --asset-id or --asset-name.")
    query_scope = _resolve_command_query_scope(args)
    asset = _resolve_asset(args.asset_id, args.asset_name, discovery=query_scope["discovery"])
    explanation = explain_asset_permissions(
        asset,
        client=query_scope["client"],
        discovery=query_scope["discovery"],
    )
    return {**explanation, **org_context_output(query_scope["org_context"])}


def _add_optional_org_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--org-id")
    parser.add_argument("--org-name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 权限、ACL、RBAC 与授权解释入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    permission_resources = sorted(PERMISSION_RESOURCE_PATHS)

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
    add_filter_arguments(asset_perm_users)
    asset_perm_users.set_defaults(func=_asset_perm_users)

    asset_permission_explain = subparsers.add_parser(
        "asset-permission-explain",
        help="解释某资产命中的权限规则。",
        description="从资产视角解释直接资产、标签和节点继承命中的授权规则。",
        formatter_class=CLIHelpFormatter,
    )
    asset_permission_explain.add_argument("--asset-id")
    asset_permission_explain.add_argument("--asset-name")
    _add_optional_org_arguments(asset_permission_explain)
    asset_permission_explain.set_defaults(func=_asset_permission_explain)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_permissions.py",
            deprecated_commands={"permission-list", "asset-perm-users"},
            usage_examples_by_command={
                "permission-list": PERMISSION_LIST_EXAMPLES,
                "asset-perm-users": ASSET_PERM_USERS_EXAMPLES,
            },
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
