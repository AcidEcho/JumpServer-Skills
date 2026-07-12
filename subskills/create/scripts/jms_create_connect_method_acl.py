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

from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    GLOBAL_ORG_ID,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    current_runtime_values,
    has_cli_value,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    parse_strict_bool,
    parse_json_arg,
    resolve_command_org_context,
    run_and_print,
)
from jumpserver_common.jms_acl_validation import (  # noqa: E402
    USER_ATTR_BOOL_FIELDS,
    USER_ATTR_CONNECT_METHOD_M2M_FIELDS,
    USER_ATTR_TEXT_FIELDS,
    validate_selector_attrs,
)


CREATE_CONNECT_METHOD_ACL_PATH = "/api/v1/acls/connect-method-acls/"
CONNECT_METHOD_CHOICES_PATH = "/api/v1/terminal/components/connect-methods/"
CREATE_CONNECT_METHOD_ACL_FIELDS = frozenset({"connect_methods", "action", "is_active", "users", "name", "comment"})
CONNECT_METHOD_ACL_ACTIONS = frozenset({"accept", "reject"})
CREATE_CONNECT_METHOD_ACL_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_connect_method_acl.py create-connect-method-acl "
        "--org-id 00000000-0000-0000-0000-000000000000 --payload '<json>' --confirm"
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


def _merge_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_CONNECT_METHOD_ACL_EXAMPLES)


def _reject_unknown_fields(payload: dict[str, Any]) -> None:
    unknown_fields = sorted(set(payload) - CREATE_CONNECT_METHOD_ACL_FIELDS)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_connect_method_acl_payload_fields",
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(CREATE_CONNECT_METHOD_ACL_FIELDS)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_CONNECT_METHOD_ACL_FIELDS),
            ),
        )


def _build_connect_method_acl_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.action):
        payload["action"] = args.action
    if getattr(args, "connect_method", None):
        payload["connect_methods"] = [item for item in args.connect_method if has_cli_value(item)]
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_strict_bool(args.is_active, field_name="is_active")
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(payload)
    if "connect_methods" in payload:
        payload["connect_methods"] = [_text(item) for item in _as_list(payload.get("connect_methods")) if has_cli_value(item)]
    if not has_cli_value(payload.get("action")):
        payload["action"] = "reject"
    if "is_active" in payload:
        payload["is_active"] = parse_strict_bool(payload.get("is_active"), field_name="is_active")
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_CONNECT_METHOD_ACL_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_connect_method_acl_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in ("name", "action"):
        if not _text(payload.get(field)):
            missing.append(field)
    for field in ("users", "connect_methods"):
        if not payload.get(field):
            missing.append(field)
    if missing:
        raise CLIError(
            "创建连接方式过滤器参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_connect_method_acl_fields",
                user_message="创建连接方式过滤器缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入完整 JSON，或补齐 --name、--action、--connect-method 及 users。",
                suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("action")) not in CONNECT_METHOD_ACL_ACTIONS:
        raise CLIError(
            "连接方式过滤器动作不支持。",
            payload=build_cli_guidance_payload(
                "invalid_connect_method_acl_action",
                user_message="`action` 只允许 accept/reject。",
                action_hint="请改成受支持的 action 后重试。",
                suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
                action=payload.get("action"),
                allowed_actions=sorted(CONNECT_METHOD_ACL_ACTIONS),
            ),
        )
    validate_selector_attrs(
        payload.get("users"),
        attr_scope="users",
        reason_prefix="connect_method_acl",
        examples=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
        resource_label="连接方式过滤器",
        text_fields=USER_ATTR_TEXT_FIELDS,
        bool_fields=USER_ATTR_BOOL_FIELDS,
        m2m_fields=USER_ATTR_CONNECT_METHOD_M2M_FIELDS,
    )


def _raise_global_org_required(org_id: str = "", org_name: str = "") -> None:
    raise CLIError(
        "当前命令只能在全局组织创建。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建连接方式过滤器时，effective org 必须是全局组织 ID。",
            action_hint="请使用 `--org-id 00000000-0000-0000-0000-000000000000`，或确保 .env JMS_ORG_ID 为全局组织 ID。",
            org_id=org_id or None,
            org_name=org_name or None,
            required_org_id=GLOBAL_ORG_ID,
        ),
    )


def _global_org_context(source: str, *, name: str = "Global") -> dict[str, Any]:
    return {
        "effective_org": {"id": GLOBAL_ORG_ID, "name": name, "source": source},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前命令范围固定为全局组织 (%s)；不写入 .env。" % GLOBAL_ORG_ID,
    }


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id and requested_org_name:
        resolve_command_org_context(args, allow_global=True, fallback_to_selected=False)
    if requested_org_id:
        if requested_org_id != GLOBAL_ORG_ID:
            _raise_global_org_required(org_id=requested_org_id)
        return _global_org_context("command_explicit")
    if requested_org_name:
        if requested_org_name.lower() not in {"global", "全局", "全局组织"}:
            _raise_global_org_required(org_name=requested_org_name)
        return _global_org_context("command_org_name_preview", name=requested_org_name)
    org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
    if org_id != GLOBAL_ORG_ID:
        _raise_global_org_required(org_id=org_id)
    return _global_org_context("env_preview")


def _resolve_global_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        context = resolve_command_org_context(args, allow_global=True, fallback_to_selected=False)
    else:
        org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
        if org_id != GLOBAL_ORG_ID:
            _raise_global_org_required(org_id=org_id)
        context = _global_org_context("env")
    if org_id_from_context(context) != GLOBAL_ORG_ID:
        effective = context.get("effective_org") or {}
        _raise_global_org_required(org_id=_text(effective.get("id")), org_name=_text(effective.get("name")))
    return context


def _selector_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": None, "attr_count": 0}
    return {
        "type": value.get("type"),
        "attr_count": len(value.get("attrs") or []) if isinstance(value.get("attrs"), list) else 0,
    }


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "action": payload.get("action"),
        "users": _selector_summary(payload.get("users")),
        "connect_method_count": len(payload.get("connect_methods") or [])
        if isinstance(payload.get("connect_methods"), list)
        else 0,
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
    }


def _brief_connect_method_choice(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": item.get("value"),
        "label": item.get("label"),
    }


def _list_connect_method_choices(client, *, search: str) -> list[dict[str, Any]]:
    records = client.list_paginated(
        CONNECT_METHOD_CHOICES_PATH,
        params={"flat": "1", "os": "all", "search": search, "limit": 100},
    )
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _resolve_connect_method(client, method: str) -> tuple[str, dict[str, Any]]:
    wanted = _text(method)
    choices = _list_connect_method_choices(client, search=wanted)
    value_matches = [item for item in choices if _text(item.get("value")) == wanted]
    if len(value_matches) == 1:
        item = value_matches[0]
        return _text(item.get("value")), _brief_connect_method_choice(item)
    if len(value_matches) > 1:
        raise CLIError(
            "连接方式匹配到多个 value。",
            payload=build_cli_guidance_payload(
                "connect_method_acl_connect_method_ambiguous",
                user_message="连接方式 `%s` 匹配到多个 value，已阻止创建。" % wanted,
                action_hint="请从 candidate_connect_methods 中选择准确 value 后重试。",
                suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
                connect_method=wanted,
                candidate_connect_methods=[_brief_connect_method_choice(item) for item in value_matches],
            ),
        )

    label_matches = [item for item in choices if _text(item.get("label")) == wanted]
    if len(label_matches) == 1:
        item = label_matches[0]
        return _text(item.get("value")), _brief_connect_method_choice(item)
    if len(label_matches) > 1:
        raise CLIError(
            "连接方式名称匹配到多个选项。",
            payload=build_cli_guidance_payload(
                "connect_method_acl_connect_method_ambiguous",
                user_message="连接方式显示名 `%s` 匹配到多个选项，已阻止创建。" % wanted,
                action_hint="请从 candidate_connect_methods 中选择准确 value 后重试。",
                suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
                connect_method=wanted,
                candidate_connect_methods=[_brief_connect_method_choice(item) for item in label_matches],
            ),
        )

    raise CLIError(
        "连接方式不存在。",
        payload=build_cli_guidance_payload(
            "connect_method_acl_connect_method_not_found",
            user_message="未在 JumpServer 连接方式选项接口中找到 `%s`。" % wanted,
            action_hint="请调用 `/api/v1/terminal/components/connect-methods/?flat=1&os=all&search=<keyword>` 查询可用选项，并传 value 字段。",
            suggested_commands=CREATE_CONNECT_METHOD_ACL_EXAMPLES,
            connect_method=wanted,
            candidate_connect_methods=[_brief_connect_method_choice(item) for item in choices[:10]],
        ),
    )


def _resolve_connect_methods(client, payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved_values = []
    resolved_choices = []
    seen = set()
    for method in payload.get("connect_methods") or []:
        value, choice = _resolve_connect_method(client, method)
        if value in seen:
            continue
        seen.add(value)
        resolved_values.append(value)
        resolved_choices.append(choice)
    resolved_payload = dict(payload)
    resolved_payload["connect_methods"] = resolved_values
    return resolved_payload, resolved_choices


def _brief_connect_method_acl(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "action": item.get("action"),
        "is_active": item.get("is_active"),
    }


def _create_connect_method_acl(args: argparse.Namespace):
    payload = _build_connect_method_acl_payload(args)
    _validate_connect_method_acl_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_CONNECT_METHOD_ACL_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_global_org_context(args)
    client = create_client(org_id=org_id_from_context(org_context))
    payload, resolved_connect_methods = _resolve_connect_methods(client, payload)
    created = client.post(CREATE_CONNECT_METHOD_ACL_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_CONNECT_METHOD_ACL_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_connect_methods": resolved_connect_methods,
        "created_connect_method_acl": _brief_connect_method_acl(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建连接方式过滤器入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_CONNECT_METHOD_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    connect_method_acl = subparsers.add_parser(
        "create-connect-method-acl",
        help="创建连接方式过滤器。",
        description="POST /api/v1/acls/connect-method-acls/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_CONNECT_METHOD_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    connect_method_acl.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    connect_method_acl.add_argument("--name")
    connect_method_acl.add_argument("--action")
    connect_method_acl.add_argument("--connect-method", dest="connect_method", action="append", help="连接方式，可重复。")
    connect_method_acl.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    connect_method_acl.add_argument("--comment")
    connect_method_acl.add_argument("--org-id", dest="org_id", help="组织 ID；未传时只读取 .env JMS_ORG_ID。")
    connect_method_acl.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    connect_method_acl.add_argument("--confirm", action="store_true")
    add_filter_arguments(connect_method_acl)
    connect_method_acl.set_defaults(func=_create_connect_method_acl)

    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
