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
    create_discovery,
    current_runtime_values,
    has_cli_value,
    is_uuid_like,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    parse_bool,
    parse_json_arg,
    resolve_command_org_context,
    run_and_print,
)
from jumpserver_common.jms_acl_validation import (  # noqa: E402
    USER_ATTR_BOOL_FIELDS,
    USER_ATTR_ROLE_M2M_FIELDS,
    USER_ATTR_TEXT_FIELDS,
    validate_acl_rules,
    validate_selector_attrs,
)
from jumpserver_common.jms_types import JumpServerAPIError  # noqa: E402


CREATE_LOGIN_ACL_PATH = "/api/v1/acls/login-acls/"
CREATE_LOGIN_ACL_FIELDS = frozenset(
    {"name", "priority", "users", "rules", "action", "reviewers", "is_active", "comment"}
)
LOGIN_ACL_ACTIONS = frozenset({"review", "accept", "reject", "notice"})
CREATE_LOGIN_ACL_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_login_acl.py create-login-acl "
        "--org-id 00000000-0000-0000-0000-000000000000 --payload '<json>' --confirm"
    ),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_int(value: Any) -> Any:
    text = _text(value)
    if text.isdigit():
        return int(text)
    return value


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_identifier_list(value: Any) -> list[str]:
    identifiers = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = (
                item.get("id")
                or item.get("pk")
                or item.get("value")
                or item.get("username")
                or item.get("name")
            )
        else:
            candidate = item
        text = _text(candidate)
        if text:
            identifiers.append(text)
    return identifiers


def _normalize_reviewer_pk_list(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in _normalize_identifier_list(value):
        normalized.append({"pk": item})
    return normalized


def _merge_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=CREATE_LOGIN_ACL_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_LOGIN_ACL_EXAMPLES)


def _reject_unknown_fields(payload: dict[str, Any]) -> None:
    unknown_fields = sorted(set(payload) - CREATE_LOGIN_ACL_FIELDS)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_create_login_acl_payload_fields",
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(CREATE_LOGIN_ACL_FIELDS)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_LOGIN_ACL_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_LOGIN_ACL_FIELDS),
            ),
        )


def _build_login_acl_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.priority):
        payload["priority"] = _normalize_int(args.priority)
    if has_cli_value(args.action):
        payload["action"] = args.action
    if getattr(args, "reviewer", None):
        payload["reviewers"] = _normalize_reviewer_pk_list(args.reviewer)
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_bool(args.is_active)
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(payload)
    if not has_cli_value(payload.get("priority")):
        payload["priority"] = 50
    else:
        payload["priority"] = _normalize_int(payload.get("priority"))
    if not has_cli_value(payload.get("action")):
        payload["action"] = "reject"
    if "reviewers" in payload:
        payload["reviewers"] = _normalize_reviewer_pk_list(payload.get("reviewers"))
    if "is_active" in payload:
        payload["is_active"] = parse_bool(payload.get("is_active"))
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_LOGIN_ACL_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_login_acl_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in ("name", "action"):
        if not _text(payload.get(field)):
            missing.append(field)
    for field in ("users", "rules"):
        if not payload.get(field):
            missing.append(field)
    if _text(payload.get("action")) in {"review", "notice"} and not payload.get("reviewers"):
        missing.append("reviewers")
    if missing:
        raise CLIError(
            "创建用户登录控制参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_login_acl_fields",
                user_message="创建用户登录控制缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入完整 JSON，或补齐 --name、--action 及 users/rules。",
                suggested_commands=CREATE_LOGIN_ACL_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("action")) not in LOGIN_ACL_ACTIONS:
        raise CLIError(
            "用户登录控制动作不支持。",
            payload=build_cli_guidance_payload(
                "invalid_login_acl_action",
                user_message="`action` 只允许 review/accept/reject/notice。",
                action_hint="请改成受支持的 action 后重试。",
                suggested_commands=CREATE_LOGIN_ACL_EXAMPLES,
                action=payload.get("action"),
                allowed_actions=sorted(LOGIN_ACL_ACTIONS),
            ),
        )
    validate_acl_rules(
        payload.get("rules"),
        reason_prefix="login_acl",
        examples=CREATE_LOGIN_ACL_EXAMPLES,
        resource_label="用户登录控制",
    )
    validate_selector_attrs(
        payload.get("users"),
        attr_scope="users",
        reason_prefix="login_acl",
        examples=CREATE_LOGIN_ACL_EXAMPLES,
        resource_label="用户登录控制",
        text_fields=USER_ATTR_TEXT_FIELDS,
        bool_fields=USER_ATTR_BOOL_FIELDS,
        m2m_fields=USER_ATTR_ROLE_M2M_FIELDS,
    )


def _raise_global_org_required(org_id: str = "", org_name: str = "") -> None:
    raise CLIError(
        "当前命令只能在全局组织创建。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建用户登录控制时，effective org 必须是全局组织 ID。",
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
        "priority": payload.get("priority"),
        "action": payload.get("action"),
        "users": _selector_summary(payload.get("users")),
        "rules": _selector_summary(payload.get("rules")),
        "reviewer_count": len(payload.get("reviewers") or []) if isinstance(payload.get("reviewers"), list) else 0,
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
    }


def _brief_login_acl(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "priority": item.get("priority"),
        "action": item.get("action"),
        "is_active": item.get("is_active"),
    }


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
        "email": item.get("email"),
    }


def _item_id(item: dict[str, Any]) -> str:
    return _text(item.get("id") or item.get("pk"))


def _find_item_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    wanted = _text(item_id)
    for item in items:
        if _item_id(item) == wanted:
            return item
    return None


def _resolve_user_ids(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    users = [item for item in discovery.list_users() if isinstance(item, dict)]
    resolved_ids = []
    resolved_items = []
    seen = set()
    for value in values:
        if is_uuid_like(value):
            user = _find_item_by_id(users, value)
            if not user:
                raise CLIError(
                    "无法解析审批人用户 ID。",
                    payload=build_cli_guidance_payload(
                        "login_acl_reviewer_user_not_found",
                        user_message="全局组织下找不到审批人/通知接收人：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_LOGIN_ACL_EXAMPLES,
                        user=value,
                        candidate_users=[_brief_user(item) for item in users[:20]],
                    ),
                )
            user_id = _item_id(user)
        else:
            try:
                resolved = discovery.resolve_user_ids([value])
            except JumpServerAPIError as exc:
                raise CLIError(
                    "无法解析审批人用户标识。",
                    payload=build_cli_guidance_payload(
                        "login_acl_reviewer_user_not_found",
                        user_message="全局组织下找不到审批人/通知接收人：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_LOGIN_ACL_EXAMPLES,
                        user=value,
                        candidate_users=[_brief_user(item) for item in users[:20]],
                    ),
                ) from exc
            user_id = _text((resolved or [""])[0])
            user = _find_item_by_id(users, user_id) or {"id": user_id}
        if user_id and user_id not in seen:
            seen.add(user_id)
            resolved_ids.append(user_id)
            resolved_items.append(_brief_user(user))
    return resolved_ids, resolved_items


def _resolve_reviewer_references(payload: dict[str, Any], *, org_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}
    reviewers = resolved_payload.get("reviewers")
    if isinstance(reviewers, list) and reviewers:
        discovery = create_discovery(org_id=org_id)
        reviewer_ids, reviewer_items = _resolve_user_ids(discovery, _normalize_identifier_list(reviewers))
        resolved_payload["reviewers"] = [{"pk": user_id} for user_id in reviewer_ids]
        resolved_refs["reviewers"] = reviewer_items
    return resolved_payload, resolved_refs


def _existing_by_name(client, *, name: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_LOGIN_ACL_PATH, params={"search": name})
    if not isinstance(records, list):
        records = []
    wanted_name = _text(name)
    return [_brief_login_acl(item) for item in records if isinstance(item, dict) and _text(item.get("name")) == wanted_name]


def _create_login_acl(args: argparse.Namespace):
    payload = _build_login_acl_payload(args)
    _validate_login_acl_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_LOGIN_ACL_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_global_org_context(args)
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references = _resolve_reviewer_references(payload, org_id=org_id)
    duplicates = _existing_by_name(client, name=str(payload.get("name") or ""))
    if duplicates:
        raise CLIError(
            "用户登录控制已存在。",
            payload=build_cli_guidance_payload(
                "login_acl_already_exists",
                user_message="全局组织内已存在同名用户登录控制，已阻止创建。",
                action_hint="请改用已有用户登录控制，或换一个名称。",
                duplicate_login_acls=duplicates,
            ),
        )

    created = client.post(CREATE_LOGIN_ACL_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_LOGIN_ACL_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "created_login_acl": _brief_login_acl(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建用户登录控制入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LOGIN_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_acl = subparsers.add_parser(
        "create-login-acl",
        help="创建用户登录控制。",
        description="POST /api/v1/acls/login-acls/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LOGIN_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    login_acl.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    login_acl.add_argument("--name")
    login_acl.add_argument("--priority")
    login_acl.add_argument("--action")
    login_acl.add_argument("--reviewer", action="append", help="审批人或通知接收人用户 ID、用户名或姓名；可重复。")
    login_acl.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    login_acl.add_argument("--comment")
    login_acl.add_argument("--org-id", dest="org_id", help="组织 ID；未传时只读取 .env JMS_ORG_ID。")
    login_acl.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    login_acl.add_argument("--confirm", action="store_true")
    add_filter_arguments(login_acl)
    login_acl.set_defaults(func=_create_login_acl)

    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
