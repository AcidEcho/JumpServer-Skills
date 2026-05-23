from __future__ import annotations

from typing import Any

from jumpserver_common.jms_runtime import create_discovery


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


def asset_node_paths(asset: dict[str, Any], *, node_lookup) -> list[dict[str, Any]]:
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


def permission_node_paths(permission: dict[str, Any], *, node_lookup) -> list[dict[str, Any]]:
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

    asset_paths = asset_node_paths(asset, node_lookup=node_lookup)
    permission_paths = permission_node_paths(permission, node_lookup=node_lookup)
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
