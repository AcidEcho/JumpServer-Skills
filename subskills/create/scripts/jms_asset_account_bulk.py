#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_discovery import CORE_ENDPOINTS  # noqa: E402
from jumpserver_common.jms_text_utils import (  # noqa: E402
    lower_text as _lower,
    text as _text,
)
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    GLOBAL_ORG_ID,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    create_env_org_context,
    has_cli_value,
    is_uuid_like,
    mask_secret,
    org_context_output,
    org_id_from_context,
    preview_create_org_context,
    raise_create_global_org_error,
    resolve_command_org_context,
    run_and_print,
)


BULK_ACCOUNT_PATH = "/api/v1/accounts/accounts/bulk/"
ADD_ACCOUNT_FIELDS = frozenset(
    {
        "privileged",
        "secret_type",
        "secret_reset",
        "push_now",
        "on_invalid",
        "is_active",
        "name",
        "username",
        "assets",
        "comment",
        "secret",
        "passphrase",
    }
)
ADD_TEMPLATE_FIELDS = frozenset(
    {
        "privileged",
        "secret_type",
        "secret_reset",
        "push_now",
        "on_invalid",
        "is_active",
        "template",
        "nodes",
        "assets",
        "comment",
    }
)
SECRET_TYPES = frozenset({"ssh_key", "password", "token", "access_key", "api_key"})
ON_INVALID_VALUES = frozenset({"skip", "update", "error"})
SENSITIVE_FIELDS = frozenset({"secret", "passphrase"})
ADD_ACCOUNT_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets "
        "--name root --username root --secret-type password --secret '<secret>' --asset web-01"
    ),
    (
        "python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-to-assets "
        "--org-name Default --name root --username root --secret-type password --secret '<secret>' "
        "--asset web-01 --confirm"
    ),
]
ADD_TEMPLATE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets "
        "--secret-type password --template root-template --node /Default/Web"
    ),
    (
        "python3 subskills/create/scripts/jms_asset_account_bulk.py add-account-template-to-assets "
        "--org-name Default --secret-type password --template root-template --asset web-01 --confirm"
    ),
]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bool_arg(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _parse_payload(raw_payload: str | None, *, examples: list[str]) -> dict[str, Any]:
    if not has_cli_value(raw_payload):
        return {}
    try:
        payload = json.loads(str(raw_payload))
    except json.JSONDecodeError as exc:
        raise CLIError(
            "无法解析 --payload 参数。",
            payload=build_cli_guidance_payload(
                "invalid_json_payload",
                user_message="`--payload` 需要传入 JSON 对象字符串。",
                action_hint="请检查 JSON 引号、逗号和花括号；不要在错误回显中暴露 secret。",
                suggested_commands=examples,
                input_name="--payload",
                parser_error=exc.msg,
            ),
        ) from exc
    if not isinstance(payload, dict):
        raise CLIError(
            "--payload 必须是 JSON 对象。",
            payload=build_cli_guidance_payload(
                "invalid_json_payload",
                user_message="`--payload` 需要传入 JSON 对象，而不是数组或普通字符串。",
                action_hint="请改成 `{\"key\": \"value\"}` 这种对象形式。",
                suggested_commands=examples,
                input_name="--payload",
            ),
        )
    return payload


def _normalize_refs(value: Any) -> list[str]:
    refs = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = item.get("id") or item.get("pk") or item.get("name") or item.get("value")
        else:
            candidate = item
        text = _text(candidate)
        if text:
            refs.append(text)
    return refs


def _clean_payload(payload: dict[str, Any], allowed_fields: frozenset[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key in allowed_fields
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _reject_unknown_fields(payload: dict[str, Any], allowed_fields: frozenset[str], *, examples: list[str]) -> None:
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise CLIError(
            "bulk payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_bulk_account_payload_fields",
                user_message="bulk payload 只允许字段：%s。" % ", ".join(sorted(allowed_fields)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=examples,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(allowed_fields),
            ),
        )


def _apply_common_args(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    for attr in ("secret_type", "on_invalid", "name", "username", "secret", "passphrase", "comment"):
        if hasattr(args, attr) and has_cli_value(getattr(args, attr)):
            payload[attr] = getattr(args, attr)
    for attr in ("privileged", "secret_reset", "push_now", "is_active"):
        if hasattr(args, attr) and getattr(args, attr) is not None:
            payload[attr] = _bool_arg(getattr(args, attr))
    return payload


def _build_add_account_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _parse_payload(args.payload, examples=ADD_ACCOUNT_EXAMPLES)
    payload = _apply_common_args(payload, args)
    if getattr(args, "asset", None):
        payload["assets"] = _normalize_refs(args.asset)
    _reject_unknown_fields(payload, ADD_ACCOUNT_FIELDS, examples=ADD_ACCOUNT_EXAMPLES)
    if "assets" in payload:
        payload["assets"] = _normalize_refs(payload.get("assets"))
    return _clean_payload(payload, ADD_ACCOUNT_FIELDS)


def _build_add_template_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _parse_payload(args.payload, examples=ADD_TEMPLATE_EXAMPLES)
    payload = _apply_common_args(payload, args)
    if getattr(args, "asset", None):
        payload["assets"] = _normalize_refs(args.asset)
    if getattr(args, "node", None):
        payload["nodes"] = _normalize_refs(args.node)
    if getattr(args, "template", None):
        payload["template"] = _normalize_refs(args.template)
    _reject_unknown_fields(payload, ADD_TEMPLATE_FIELDS, examples=ADD_TEMPLATE_EXAMPLES)
    for field in ("assets", "nodes", "template"):
        if field in payload:
            payload[field] = _normalize_refs(payload.get(field))
    return _clean_payload(payload, ADD_TEMPLATE_FIELDS)


def _validate_common_payload(payload: dict[str, Any], *, examples: list[str]) -> None:
    secret_type = _text(payload.get("secret_type"))
    if secret_type and secret_type not in SECRET_TYPES:
        raise CLIError(
            "不支持的 secret_type。",
            payload=build_cli_guidance_payload(
                "invalid_bulk_account_secret_type",
                user_message="secret_type 只允许：%s。" % ", ".join(sorted(SECRET_TYPES)),
                action_hint="改成支持的 secret_type 后重试。",
                suggested_commands=examples,
                secret_type=secret_type,
            ),
        )
    on_invalid = _text(payload.get("on_invalid"))
    if on_invalid and on_invalid not in ON_INVALID_VALUES:
        raise CLIError(
            "不支持的 on_invalid。",
            payload=build_cli_guidance_payload(
                "invalid_bulk_account_on_invalid",
                user_message="on_invalid 只允许：skip, update, error。",
                action_hint="改成支持的 on_invalid 后重试。",
                suggested_commands=examples,
                on_invalid=on_invalid,
            ),
        )
    invalid_bool_fields = [
        field
        for field in ("privileged", "secret_reset", "push_now", "is_active")
        if field in payload and not isinstance(payload.get(field), bool)
    ]
    if invalid_bool_fields:
        raise CLIError(
            "bulk payload 布尔字段不合法。",
            payload=build_cli_guidance_payload(
                "invalid_bulk_account_boolean_field",
                user_message="布尔字段必须是 true/false：%s。" % ", ".join(invalid_bool_fields),
                action_hint="请把这些字段改成 JSON boolean，或使用对应 CLI 开关。",
                suggested_commands=examples,
                invalid_fields=invalid_bool_fields,
            ),
        )


def _validate_add_account_payload(payload: dict[str, Any]) -> None:
    _validate_common_payload(payload, examples=ADD_ACCOUNT_EXAMPLES)
    missing = [field for field in ("name", "username", "secret_type") if not _text(payload.get(field))]
    if not payload.get("assets"):
        missing.append("assets")
    if not has_cli_value(payload.get("secret")):
        missing.append("secret")
    if missing:
        raise CLIError(
            "批量添加账号参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_bulk_account_fields",
                user_message="批量添加账号缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐账号字段和至少 1 个 --asset 后重试。",
                suggested_commands=ADD_ACCOUNT_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if "passphrase" in payload and _text(payload.get("secret_type")) != "ssh_key":
        raise CLIError(
            "passphrase 只适用于 ssh_key。",
            payload=build_cli_guidance_payload(
                "invalid_bulk_account_passphrase",
                user_message="只有 `secret_type=ssh_key` 时才允许填写 `passphrase`。",
                action_hint="请移除 passphrase，或把 secret_type 改为 ssh_key。",
                suggested_commands=ADD_ACCOUNT_EXAMPLES,
                invalid_fields=["passphrase"],
            ),
        )


def _validate_add_template_payload(payload: dict[str, Any]) -> None:
    _validate_common_payload(payload, examples=ADD_TEMPLATE_EXAMPLES)
    missing = []
    if not _text(payload.get("secret_type")):
        missing.append("secret_type")
    if not payload.get("template"):
        missing.append("template")
    if not payload.get("assets") and not payload.get("nodes"):
        missing.append("assets_or_nodes")
    if missing:
        raise CLIError(
            "批量添加账号模板参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_bulk_account_template_fields",
                user_message="批量添加账号模板缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --template，并至少传 1 个 --asset 或 --node。",
                suggested_commands=ADD_TEMPLATE_EXAMPLES,
                missing_fields=missing,
            ),
        )


_GLOBAL_USER_MESSAGE = "批量添加资产账号时，目标组织不能使用全局组织 ID。"


def _raise_global_target_org_error(org_id: str) -> None:
    raise_create_global_org_error(
        org_id,
        resource_name="批量添加资产账号",
        user_message=_GLOBAL_USER_MESSAGE,
    )


def _env_org_context() -> dict[str, Any]:
    return create_env_org_context(
        resource_name="批量添加资产账号",
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定批量添加目标组织。",
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="批量添加资产账号",
        confirm_action="批量添加",
        no_org_hint="dry-run 仅预览 payload；正式批量添加时未传组织将使用 .env JMS_ORG_ID。",
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _resolve_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context()


def _field_value(item: dict[str, Any], field: str) -> Any:
    current: Any = item
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _brief_resource(resource: str, item: dict[str, Any]) -> dict[str, Any]:
    if resource == "asset":
        platform = item.get("platform")
        return {
            "id": item.get("id") or item.get("pk"),
            "name": item.get("name"),
            "address": item.get("address"),
            "platform": platform.get("name") if isinstance(platform, dict) else platform,
            "nodes_display": item.get("nodes_display"),
        }
    if resource == "node":
        return {
            "id": item.get("id") or item.get("pk"),
            "name": item.get("name") or item.get("value"),
            "full_value": item.get("full_value"),
            "org_name": item.get("org_name"),
        }
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
    }


def _matches_ref(items: list[dict[str, Any]], ref: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = _lower(ref)
    if not wanted:
        return []
    if is_uuid_like(wanted):
        return [item for item in items if _lower(_field_value(item, "id") or item.get("pk")) == wanted]

    exact = []
    partial = []
    for item in items:
        values = [_lower(_field_value(item, field)) for field in fields]
        if wanted in values:
            exact.append(item)
        elif any(wanted in value for value in values if value):
            partial.append(item)
    return exact or partial


def _resolve_refs(
    refs: list[str],
    *,
    items: list[dict[str, Any]],
    resource: str,
    fields: tuple[str, ...],
) -> tuple[list[str], list[dict[str, Any]]]:
    resolved_ids = []
    resolved_items = []
    for ref in refs:
        matches = _matches_ref(items, ref, fields)
        if not matches:
            raise CLIError(
                "无法解析对象引用。",
                payload=build_cli_guidance_payload(
                    "bulk_account_reference_not_found",
                    user_message="找不到 %s：%s。" % (resource, ref),
                    action_hint="请先用 query resolve/object-list 确认对象 ID 或名称后重试。",
                    resource=resource,
                    reference=ref,
                    available_candidates=[_brief_resource(resource, item) for item in items[:20]],
                ),
            )
        if len(matches) > 1:
            raise CLIError(
                "对象引用命中多个候选。",
                payload=build_cli_guidance_payload(
                    "bulk_account_reference_ambiguous",
                    user_message="%s 引用不唯一：%s。" % (resource, ref),
                    action_hint="请改用唯一 ID 后重试。",
                    resource=resource,
                    reference=ref,
                    candidates=[_brief_resource(resource, item) for item in matches[:20]],
                ),
            )
        item = matches[0]
        item_id = _text(item.get("id") or item.get("pk"))
        if item_id not in resolved_ids:
            resolved_ids.append(item_id)
            resolved_items.append(_brief_resource(resource, item))
    return resolved_ids, resolved_items


def _resolve_payload_references(payload: dict[str, Any], *, org_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}

    if "assets" in resolved_payload:
        asset_ids, assets = _resolve_refs(
            _normalize_refs(resolved_payload.get("assets")),
            items=[item for item in discovery.list_assets() if isinstance(item, dict)],
            resource="asset",
            fields=("id", "pk", "name", "address"),
        )
        resolved_payload["assets"] = asset_ids
        resolved_refs["assets"] = assets
    if "nodes" in resolved_payload:
        node_ids, nodes = _resolve_refs(
            _normalize_refs(resolved_payload.get("nodes")),
            items=[item for item in discovery.list_nodes() if isinstance(item, dict)],
            resource="node",
            fields=("id", "pk", "name", "value", "full_value"),
        )
        resolved_payload["nodes"] = node_ids
        resolved_refs["nodes"] = nodes
    if "template" in resolved_payload:
        templates_raw = discovery.client.list_paginated(CORE_ENDPOINTS["account_templates"])
        templates = [item for item in templates_raw if isinstance(item, dict)] if isinstance(templates_raw, list) else []
        template_ids, template_items = _resolve_refs(
            _normalize_refs(resolved_payload.get("template")),
            items=templates,
            resource="account_template",
            fields=("id", "pk", "name"),
        )
        resolved_payload["template"] = template_ids
        resolved_refs["template"] = template_items
    return resolved_payload, resolved_refs


def _mask_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        masked = {}
        for key, value in payload.items():
            if str(key) in SENSITIVE_FIELDS:
                masked[key] = mask_secret(value)
            else:
                masked[key] = _mask_payload(value)
        return masked
    if isinstance(payload, list):
        return [_mask_payload(item) for item in payload]
    return payload


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "username": payload.get("username"),
        "secret_type": payload.get("secret_type"),
        "on_invalid": payload.get("on_invalid"),
        "asset_count": len(payload.get("assets") or []) if isinstance(payload.get("assets"), list) else 0,
        "node_count": len(payload.get("nodes") or []) if isinstance(payload.get("nodes"), list) else 0,
        "template_count": len(payload.get("template") or []) if isinstance(payload.get("template"), list) else 0,
        "secret_sent": "secret" in payload,
        "passphrase_sent": "passphrase" in payload,
        "comment_sent": "comment" in payload,
    }


def _dry_run_result(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    org_context = _preview_org_context(args)
    return {
        "dry_run": True,
        "api_path": BULK_ACCOUNT_PATH,
        "payload": _mask_payload(payload),
        "payload_summary": _payload_summary(payload),
        **org_context_output(org_context),
    }


def _post_bulk_result(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    org_context = _resolve_org_context(args)
    target_org_id = org_id_from_context(org_context)
    if target_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(target_org_id)
    client = create_client(org_id=target_org_id)
    resolved_payload, resolved_refs = _resolve_payload_references(payload, org_id=target_org_id)
    bulk_result = client.post(BULK_ACCOUNT_PATH, json_body=resolved_payload)
    return {
        "dry_run": False,
        "api_path": BULK_ACCOUNT_PATH,
        "payload": _mask_payload(resolved_payload),
        "payload_summary": _payload_summary(resolved_payload),
        "resolved_references": resolved_refs,
        "bulk_result": _mask_payload(bulk_result),
        **org_context_output(org_context),
    }


def _add_account_to_assets(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_add_account_payload(args)
    _validate_add_account_payload(payload)
    if not args.confirm:
        return _dry_run_result(args, payload)
    return _post_bulk_result(args, payload)


def _add_account_template_to_assets(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_add_template_payload(args)
    _validate_add_template_payload(payload)
    if not args.confirm:
        return _dry_run_result(args, payload)
    return _post_bulk_result(args, payload)


def _add_bool_pair(parser: argparse.ArgumentParser, name: str, dest: str, help_text: str) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--%s" % name, dest=dest, action="store_true", default=None, help=help_text)
    group.add_argument("--no-%s" % name, dest=dest, action="store_false", default=None, help="禁用：%s" % help_text)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--payload", help="JSON 对象 payload；复杂结构优先放这里，显式参数会覆盖同名字段。")
    parser.add_argument("--secret-type", dest="secret_type", choices=sorted(SECRET_TYPES))
    parser.add_argument("--on-invalid", dest="on_invalid", choices=sorted(ON_INVALID_VALUES))
    parser.add_argument("--comment")
    _add_bool_pair(parser, "privileged", "privileged", "是否为特权账号。")
    _add_bool_pair(parser, "secret-reset", "secret_reset", "是否重置密文。")
    _add_bool_pair(parser, "push-now", "push_now", "是否立即推送。")
    _add_bool_pair(parser, "is-active", "is_active", "是否启用。")
    parser.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    parser.add_argument("--org-name", dest="org_name", help="组织名称；只限定本次命令，不写 .env。")
    parser.add_argument("--confirm", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 批量给资产添加账号或账号模板入口。",
        epilog="Examples:\n  " + "\n  ".join(ADD_ACCOUNT_EXAMPLES + ADD_TEMPLATE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_account = subparsers.add_parser(
        "add-account-to-assets",
        help="给一个或多个资产批量添加账号。",
        description="POST /api/v1/accounts/accounts/bulk/；无 --confirm 只预览，追加 --confirm 才解析资产并 POST。",
        epilog="Examples:\n  " + "\n  ".join(ADD_ACCOUNT_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    _add_common_arguments(add_account)
    add_account.add_argument("--name", help="账号名称。")
    add_account.add_argument("--username", help="账号用户名。")
    add_account.add_argument("--secret", help="账号密文；输出中会脱敏。")
    add_account.add_argument("--passphrase", help="ssh_key 密钥密码；输出中会脱敏。")
    add_account.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    add_account.set_defaults(func=_add_account_to_assets)

    add_template = subparsers.add_parser(
        "add-account-template-to-assets",
        help="给资产或节点批量添加账号模板。",
        description="POST /api/v1/accounts/accounts/bulk/；无 --confirm 只预览，追加 --confirm 才解析模板、节点、资产并 POST。",
        epilog="Examples:\n  " + "\n  ".join(ADD_TEMPLATE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    _add_common_arguments(add_template)
    add_template.add_argument("--template", "--template-id", dest="template", action="append", help="账号模板 ID 或名称；可重复。")
    add_template.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    add_template.add_argument("--node", "--node-id", dest="node", action="append", help="节点 ID、名称或 full_value；可重复。")
    add_template.set_defaults(func=_add_account_template_to_assets)
    return parser


def main() -> int:
    def _run_cli():
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
