#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    GLOBAL_ORG_ID,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    create_env_org_context,
    has_cli_value,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    preview_create_org_context,
    raise_create_global_org_error,
    resolve_command_org_context,
    run_and_print,
)


CREATE_ZONE_PATH = "/api/v1/assets/zones/"
CREATE_GATEWAY_PATH = "/api/v1/assets/gateways/"
CREATE_LABEL_PATH = "/api/v1/labels/labels/"
CREATE_ZONE_FIELDS = frozenset({"name", "assets", "comment"})
CREATE_GATEWAY_FIELDS = frozenset(
    {
        "platform",
        "nodes",
        "protocols",
        "zone",
        "labels",
        "is_active",
        "name",
        "address",
        "accounts",
        "comment",
    }
)
GATEWAY_ACCOUNT_SECRET_TYPES = frozenset({"password", "ssh_key"})
GATEWAY_ACCOUNT_ON_INVALID = frozenset({"skip", "update", "error"})
CREATE_ZONE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone "
        "--name 网域名称 --asset <asset-id>"
    ),
    (
        "python3 subskills/create/scripts/jms_create_zone_gateway.py create-zone "
        "--org-name Default --name 网域名称 --asset <asset-id> --confirm"
    ),
]
CREATE_GATEWAY_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_zone_gateway.py create-gateway "
        "--org-name Default --payload '<json>' --confirm"
    ),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_assets(value: Any) -> list[str]:
    return [_text(item) for item in _as_list(value) if _text(item)]


def _normalize_pk_list(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            pk = item.get("pk")
        else:
            pk = item
        if has_cli_value(pk):
            normalized.append({"pk": pk})
    return normalized


def _normalize_platform_pk(value: Any) -> Any:
    text = _text(value)
    if text.isdigit():
        return int(text)
    return value


def _parse_protocol(value: str) -> dict[str, Any]:
    text = _text(value)
    if ":" not in text:
        raise CLIError(
            "无法解析协议参数。",
            payload=build_cli_guidance_payload(
                "invalid_gateway_protocol",
                user_message="`--protocol` 需要使用 `name:port` 形式，例如 `ssh:22`。",
                action_hint="请改成 `--protocol ssh:22` 后重试。",
                suggested_commands=CREATE_GATEWAY_EXAMPLES,
                protocol=value,
            ),
        )
    name, port = text.split(":", 1)
    name = _text(name)
    port = _text(port)
    if not name or not port.isdigit():
        raise CLIError(
            "无法解析协议参数。",
            payload=build_cli_guidance_payload(
                "invalid_gateway_protocol",
                user_message="`--protocol` 的名称不能为空，端口必须是数字。",
                action_hint="请改成 `--protocol ssh:22` 后重试。",
                suggested_commands=CREATE_GATEWAY_EXAMPLES,
                protocol=value,
            ),
        )
    return {"name": name, "port": int(port)}


def _mask_secret_value(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return "%s***%s" % (text[:2], text[-2:])


def _mask_gateway_payload(payload: dict[str, Any]) -> dict[str, Any]:
    masked = copy.deepcopy(payload)
    accounts = masked.get("accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if isinstance(account, dict) and "secret" in account:
                account["secret"] = _mask_secret_value(account.get("secret"))
            if isinstance(account, dict) and "passphrase" in account:
                account["passphrase"] = _mask_secret_value(account.get("passphrase"))
    return masked


def _brief_zone(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "asset_count": len(item.get("assets") or []) if isinstance(item.get("assets"), list) else None,
        "comment": item.get("comment"),
    }


def _brief_gateway(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "address": item.get("address"),
        "zone": item.get("zone"),
        "is_active": item.get("is_active"),
    }


def _brief_platform(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "slug": item.get("slug") or item.get("type"),
        "category": item.get("category"),
    }


def _brief_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
        "full_value": item.get("full_value"),
    }


def _brief_label(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
    }


def _item_id(item: dict[str, Any]) -> Any:
    return item.get("id") or item.get("pk")


def _platform_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        payload = item.to_dict()
        raw = payload.get("raw")
        if isinstance(raw, dict) and raw.get("id") is not None:
            payload["id"] = raw.get("id")
        return payload
    if isinstance(item, dict):
        return item
    return {}


def _field_value(item: dict[str, Any], field: str) -> Any:
    value: Any = item
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _value_matches(candidate: Any, requested: str) -> bool:
    return _text(candidate).lower() == _text(requested).lower()


def _find_unique_reference(
    items: list[dict[str, Any]],
    requested: Any,
    *,
    fields: tuple[str, ...],
    reason_code: str,
    not_found_message: str,
    ambiguous_message: str,
    candidate_key: str,
    brief_func,
) -> tuple[dict[str, Any], dict[str, Any]]:
    wanted = _text(requested)
    matches = []
    for item in items:
        if any(_value_matches(_field_value(item, field), wanted) for field in fields):
            matches.append(item)
    if len(matches) == 1:
        item = matches[0]
        return item, brief_func(item)
    if len(matches) > 1:
        raise CLIError(
            "对象匹配到多个结果。",
            payload=build_cli_guidance_payload(
                reason_code,
                user_message=ambiguous_message % wanted,
                action_hint="请从候选对象中选择准确 ID 后重试。",
                suggested_commands=CREATE_GATEWAY_EXAMPLES,
                requested=wanted,
                **{candidate_key: [brief_func(item) for item in matches[:20]]},
            ),
        )
    raise CLIError(
        "对象不存在。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=not_found_message % wanted,
            action_hint="请从候选对象中选择准确 ID、名称或值后重试。",
            suggested_commands=CREATE_GATEWAY_EXAMPLES,
            requested=wanted,
            **{candidate_key: [brief_func(item) for item in items[:20]]},
        ),
    )


_GLOBAL_USER_MESSAGE = "创建网域或网关机器时，目标组织不能使用全局组织 ID。"


def _raise_global_target_org_error(org_id: str) -> None:
    raise_create_global_org_error(
        org_id,
        resource_name="网域/网关机器创建",
        user_message=_GLOBAL_USER_MESSAGE,
    )


def _env_org_context(resource_name: str) -> dict[str, Any]:
    return create_env_org_context(
        resource_name=resource_name,
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定%s创建组织。" % resource_name,
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="创建网域/网关机器",
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _resolve_org_context(args: argparse.Namespace, resource_name: str) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context(resource_name)


def _reject_unknown_fields(payload: dict[str, Any], allowed_fields: frozenset[str], *, reason_code: str, examples: list[str]) -> None:
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                reason_code,
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(allowed_fields)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=examples,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(allowed_fields),
            ),
        )


def _build_zone_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(args, default={}, explicit_fields=(), usage_examples=CREATE_ZONE_EXAMPLES)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if getattr(args, "asset", None):
        payload["assets"] = args.asset
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(
        payload,
        CREATE_ZONE_FIELDS,
        reason_code="invalid_create_zone_payload_fields",
        examples=CREATE_ZONE_EXAMPLES,
    )
    if "assets" in payload:
        payload["assets"] = _normalize_assets(payload.get("assets"))
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_ZONE_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _build_gateway_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(args, default={}, explicit_fields=(), usage_examples=CREATE_GATEWAY_EXAMPLES)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.address):
        payload["address"] = args.address
    if has_cli_value(args.zone):
        payload["zone"] = args.zone
    if has_cli_value(getattr(args, "platform", None)):
        payload["platform"] = {"pk": _normalize_platform_pk(args.platform)}
    if has_cli_value(args.platform_pk):
        payload["platform"] = {"pk": _normalize_platform_pk(args.platform_pk)}
    if getattr(args, "node", None):
        payload["nodes"] = _normalize_pk_list(args.node)
    if getattr(args, "label", None):
        payload["labels"] = _normalize_pk_list(args.label)
    if getattr(args, "protocol", None):
        payload["protocols"] = [_parse_protocol(item) for item in args.protocol]
    _reject_unknown_fields(
        payload,
        CREATE_GATEWAY_FIELDS,
        reason_code="invalid_create_gateway_payload_fields",
        examples=CREATE_GATEWAY_EXAMPLES,
    )
    if "nodes" in payload:
        payload["nodes"] = _normalize_pk_list(payload.get("nodes"))
    if "labels" in payload:
        payload["labels"] = _normalize_pk_list(payload.get("labels"))
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_GATEWAY_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_zone_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("name",) if not _text(payload.get(field))]
    if missing:
        raise CLIError(
            "创建网域参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_zone_fields",
                user_message="创建网域缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --name 后重试。",
                suggested_commands=CREATE_ZONE_EXAMPLES,
                missing_fields=missing,
            ),
        )


def _validate_gateway_payload(payload: dict[str, Any]) -> None:
    missing = []
    if not _text(payload.get("name")):
        missing.append("name")
    if not _text(payload.get("address")):
        missing.append("address")
    if not _text(payload.get("zone")):
        missing.append("zone")
    if not isinstance(payload.get("platform"), dict) or not has_cli_value(payload["platform"].get("pk")):
        missing.append("platform.pk")
    for field in ("nodes", "protocols", "accounts"):
        if not isinstance(payload.get(field), list) or not payload.get(field):
            missing.append(field)
    if missing:
        raise CLIError(
            "创建网关机器参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_gateway_fields",
                user_message="创建网关机器缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入 API.md 第 14 项完整 JSON。",
                suggested_commands=CREATE_GATEWAY_EXAMPLES,
                missing_fields=missing,
            ),
        )
    _validate_gateway_accounts(payload)


def _raise_invalid_gateway_accounts(message: str, *, accounts: Any, invalid_fields: list[str] | None = None) -> None:
    raise CLIError(
        "网关机器账号参数不合法。",
        payload=build_cli_guidance_payload(
            "invalid_gateway_accounts",
            user_message=message,
            action_hint="请按 API.md 第 14 项修正 accounts 后重试。",
            suggested_commands=CREATE_GATEWAY_EXAMPLES,
            accounts=accounts,
            invalid_fields=invalid_fields,
            allowed_secret_types=sorted(GATEWAY_ACCOUNT_SECRET_TYPES),
            allowed_on_invalid=sorted(GATEWAY_ACCOUNT_ON_INVALID),
        ),
    )


def _validate_gateway_accounts(payload: dict[str, Any]) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return
    invalid_fields = []
    for index, account in enumerate(accounts):
        field_prefix = "accounts[%s]" % index
        if not isinstance(account, dict):
            _raise_invalid_gateway_accounts(
                "`accounts` 中每一项都必须是对象。",
                accounts=accounts,
                invalid_fields=[field_prefix],
            )
        for field in ("name", "username", "secret_type", "secret"):
            if not has_cli_value(account.get(field)):
                invalid_fields.append("%s.%s" % (field_prefix, field))
        secret_type = _text(account.get("secret_type"))
        if secret_type and secret_type not in GATEWAY_ACCOUNT_SECRET_TYPES:
            invalid_fields.append("%s.secret_type" % field_prefix)
        on_invalid = _text(account.get("on_invalid"))
        if on_invalid and on_invalid not in GATEWAY_ACCOUNT_ON_INVALID:
            invalid_fields.append("%s.on_invalid" % field_prefix)
        for field in ("privileged", "secret_reset", "push_now", "is_active"):
            if field in account and not isinstance(account.get(field), bool):
                invalid_fields.append("%s.%s" % (field_prefix, field))
    if invalid_fields:
        _raise_invalid_gateway_accounts(
            "`accounts` 缺少必填字段，或字段类型/取值不合法。",
            accounts=accounts,
            invalid_fields=invalid_fields,
        )


def _zone_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "asset_count": len(payload.get("assets") or []) if isinstance(payload.get("assets"), list) else 0,
        "comment_sent": "comment" in payload,
    }


def _gateway_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "address": payload.get("address"),
        "zone": payload.get("zone"),
        "platform_pk": (payload.get("platform") or {}).get("pk") if isinstance(payload.get("platform"), dict) else None,
        "node_count": len(payload.get("nodes") or []) if isinstance(payload.get("nodes"), list) else 0,
        "protocol_count": len(payload.get("protocols") or []) if isinstance(payload.get("protocols"), list) else 0,
        "label_count": len(payload.get("labels") or []) if isinstance(payload.get("labels"), list) else 0,
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "comment_sent": "comment" in payload,
    }


def _resolve_gateway_pk_list(
    values: list[dict[str, Any]],
    *,
    items: list[dict[str, Any]],
    fields: tuple[str, ...],
    reason_code: str,
    not_found_message: str,
    ambiguous_message: str,
    candidate_key: str,
    brief_func,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved = []
    refs = []
    seen = set()
    for raw in values:
        requested = raw.get("pk") if isinstance(raw, dict) else raw
        item, brief = _find_unique_reference(
            items,
            requested,
            fields=fields,
            reason_code=reason_code,
            not_found_message=not_found_message,
            ambiguous_message=ambiguous_message,
            candidate_key=candidate_key,
            brief_func=brief_func,
        )
        item_id = _item_id(item)
        if _text(item_id) in seen:
            continue
        seen.add(_text(item_id))
        resolved.append({"pk": item_id})
        refs.append(brief)
    return resolved, refs


def _resolve_gateway_references(payload: dict[str, Any], *, client, org_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}

    platform_ref = resolved_payload.get("platform")
    if isinstance(platform_ref, dict) and has_cli_value(platform_ref.get("pk")):
        platform_items = [_platform_to_dict(item) for item in discovery.list_platforms()]
        platform_items = [item for item in platform_items if item]
        platform, brief = _find_unique_reference(
            platform_items,
            platform_ref.get("pk"),
            fields=("id", "pk", "name", "slug", "type.value"),
            reason_code="gateway_platform_not_found",
            not_found_message="找不到平台：%s。",
            ambiguous_message="平台 `%s` 匹配到多个结果。",
            candidate_key="candidate_platforms",
            brief_func=_brief_platform,
        )
        resolved_payload["platform"] = {"pk": _item_id(platform)}
        resolved_refs["platform"] = brief

    if has_cli_value(resolved_payload.get("zone")):
        zones = client.list_paginated(CREATE_ZONE_PATH)
        zones = [item for item in zones if isinstance(item, dict)] if isinstance(zones, list) else []
        zone, brief = _find_unique_reference(
            zones,
            resolved_payload.get("zone"),
            fields=("id", "pk", "name"),
            reason_code="gateway_zone_not_found",
            not_found_message="找不到网域：%s。",
            ambiguous_message="网域 `%s` 匹配到多个结果。",
            candidate_key="candidate_zones",
            brief_func=_brief_zone,
        )
        resolved_payload["zone"] = _item_id(zone)
        resolved_refs["zone"] = brief

    if isinstance(resolved_payload.get("nodes"), list) and resolved_payload.get("nodes"):
        nodes = [item for item in discovery.list_nodes() if isinstance(item, dict)]
        node_refs, node_items = _resolve_gateway_pk_list(
            resolved_payload["nodes"],
            items=nodes,
            fields=("id", "pk", "name", "value", "full_value"),
            reason_code="gateway_node_not_found",
            not_found_message="找不到节点：%s。",
            ambiguous_message="节点 `%s` 匹配到多个结果。",
            candidate_key="candidate_nodes",
            brief_func=_brief_node,
        )
        resolved_payload["nodes"] = node_refs
        resolved_refs["nodes"] = node_items

    if isinstance(resolved_payload.get("labels"), list) and resolved_payload.get("labels"):
        labels = client.list_paginated(CREATE_LABEL_PATH)
        labels = [item for item in labels if isinstance(item, dict)] if isinstance(labels, list) else []
        label_refs, label_items = _resolve_gateway_pk_list(
            resolved_payload["labels"],
            items=labels,
            fields=("id", "pk", "name", "value"),
            reason_code="gateway_label_not_found",
            not_found_message="找不到标签：%s。",
            ambiguous_message="标签 `%s` 匹配到多个结果。",
            candidate_key="candidate_labels",
            brief_func=_brief_label,
        )
        resolved_payload["labels"] = label_refs
        resolved_refs["labels"] = label_items

    return resolved_payload, resolved_refs


def _create_zone(args: argparse.Namespace):
    payload = _build_zone_payload(args)
    _validate_zone_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_ZONE_PATH,
            "payload": payload,
            "payload_summary": _zone_payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args, "网域")
    client = create_client(org_id=org_id_from_context(org_context))
    created = client.post(CREATE_ZONE_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_ZONE_PATH,
        "payload_summary": _zone_payload_summary(payload),
        "created_zone": _brief_zone(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def _create_gateway(args: argparse.Namespace):
    payload = _build_gateway_payload(args)
    _validate_gateway_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_GATEWAY_PATH,
            "payload": _mask_gateway_payload(payload),
            "payload_summary": _gateway_payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args, "网关机器")
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references = _resolve_gateway_references(payload, client=client, org_id=org_id)
    created = client.post(CREATE_GATEWAY_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_GATEWAY_PATH,
        "payload_summary": _gateway_payload_summary(payload),
        "resolved_references": resolved_references,
        "created_gateway": _brief_gateway(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建网域与网关机器入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ZONE_EXAMPLES + CREATE_GATEWAY_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    zone = subparsers.add_parser(
        "create-zone",
        help="创建网域。",
        description="POST /api/v1/assets/zones/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ZONE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    zone.add_argument("--name")
    zone.add_argument("--asset", action="append", help="资产 ID，可重复。")
    zone.add_argument("--comment")
    zone.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    zone.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    zone.add_argument("--confirm", action="store_true")
    zone.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(zone)
    zone.set_defaults(func=_create_zone)

    gateway = subparsers.add_parser(
        "create-gateway",
        help="创建网关机器。",
        description="POST /api/v1/assets/gateways/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_GATEWAY_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    gateway.add_argument("--name")
    gateway.add_argument("--address")
    gateway.add_argument("--zone", help="网域 ID 或名称。")
    gateway.add_argument("--platform", help="平台 ID、名称或 slug；--confirm 时解析。")
    gateway.add_argument("--platform-pk", dest="platform_pk", help="平台 pk。")
    gateway.add_argument("--node", action="append", help="节点 ID、名称或 full_value；可重复。")
    gateway.add_argument("--label", action="append", help="标签 ID、名称或 value；可重复。")
    gateway.add_argument("--protocol", action="append", help="协议，格式 name:port，例如 ssh:22，可重复。")
    gateway.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    gateway.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    gateway.add_argument("--confirm", action="store_true")
    gateway.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(gateway)
    gateway.set_defaults(func=_create_gateway)

    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
