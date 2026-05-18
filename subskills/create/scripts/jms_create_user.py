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

from jumpserver_common.jms_discovery import CORE_ENDPOINTS  # noqa: E402
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    current_runtime_values,
    ensure_selected_org_context,
    has_cli_value,
    list_accessible_orgs,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    parse_bool,
    persist_selected_org,
    run_and_print,
)


CREATE_USER_PATH = "/api/v1/users/users/"
DEFAULT_SYSTEM_ROLE = "00000000-0000-0000-0000-000000000003"
DEFAULT_ORG_ROLE = "00000000-0000-0000-0000-000000000007"
CREATE_USER_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_user.py create-user "
        "--username zhangsan --name 张三 --email zhangsan@example.com "
        "--password '<password>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_user.py create-user "
        "--username zhangsan --name 张三 --email zhangsan@example.com "
        "--password '<password>' --confirm"
    ),
]
ORG_NOT_ACCESSIBLE_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
AMBIGUOUS_ORG_SELECTOR_REASON_CODE = "ambiguous_organization_selector"


def _append_values(values: list[str] | None) -> list[str]:
    return [str(item).strip() for item in values or [] if str(item or "").strip()]


def _group_payload(values: list[str] | None) -> list[dict[str, str]]:
    return [{"pk": item} for item in _append_values(values)]


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _org_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip()


def _explicit_org_context(org_id: str) -> dict[str, Any]:
    effective_org = {"id": org_id, "name": "Unknown", "source": "command_explicit"}
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前创建范围固定为组织 ID %s；本次命令直接使用该组织请求头。" % org_id,
    }


def _org_name_preview_context(org_name: str) -> dict[str, Any]:
    return {
        "effective_org": {"id": "", "name": org_name, "source": "command_org_name_preview"},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织、写入 .env 并创建。" % org_name,
    }


def _env_org_preview_context() -> dict[str, Any]:
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式创建时未传组织将使用 .env JMS_ORG_ID。",
    }


def _build_org_context(selected_org: dict[str, Any], accessible_orgs: list[dict[str, Any]]) -> dict[str, Any]:
    effective_org = {**selected_org, "source": "command_explicit"}
    effective_org_id = _org_id(effective_org)
    switchable_orgs = [
        item
        for item in accessible_orgs
        if _org_id(item) and _org_id(item) != effective_org_id
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
        "org_context_hint": "当前创建范围固定为组织 %s；本次命令按该组织执行。" % org_scope,
    }


def _raise_org_selector_conflict() -> None:
    raise CLIError(
        "组织参数冲突。",
        payload=build_cli_guidance_payload(
            AMBIGUOUS_ORG_SELECTOR_REASON_CODE,
            user_message="创建命令只能传 `--org-id` 或 `--org-name` 其中一个。",
            action_hint="请保留一个组织定位参数后重试。",
            provided=["org_id", "org_name"],
        ),
    )


def _resolve_org_name_context(org_name: str, *, persist: bool) -> dict[str, Any]:
    accessible_orgs = list_accessible_orgs()
    wanted = _lower(org_name)
    matches = [
        item
        for item in accessible_orgs
        if isinstance(item, dict) and _lower(item.get("name")) == wanted
    ]
    if not matches:
        raise CLIError(
            "指定的组织当前不可访问。",
            payload=build_cli_guidance_payload(
                ORG_NOT_ACCESSIBLE_REASON_CODE,
                user_message="当前账号下找不到你指定的组织，请先从 `candidate_orgs` 里确认可访问组织。",
                action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试；匹配成功后会写入 `.env` 并创建。",
                org_name=org_name,
                candidate_orgs=accessible_orgs,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "给定的组织名称匹配到多个候选组织。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称。",
                action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试；匹配成功后会写入 `.env` 并创建。",
                org_name=org_name,
                candidate_orgs=matches[:10],
            ),
        )
    selected = dict(matches[0])
    selected_org_id = _org_id(selected)
    if persist:
        persist_selected_org(selected_org_id)
    return _build_org_context(selected, accessible_orgs)


def _resolve_create_org_context(args: argparse.Namespace, *, persist_org_name: bool = False) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        _raise_org_selector_conflict()
    if requested_org_id:
        return _explicit_org_context(requested_org_id)
    if requested_org_name:
        return _resolve_org_name_context(requested_org_name, persist=persist_org_name)
    return ensure_selected_org_context()


def _preview_create_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        _raise_org_selector_conflict()
    if requested_org_id:
        return _explicit_org_context(requested_org_id)
    if requested_org_name:
        return _org_name_preview_context(requested_org_name)
    return _env_org_preview_context()


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    if redacted.get("password"):
        redacted["password"] = "***"
    return redacted


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "username": item.get("username"),
        "name": item.get("name"),
        "email": item.get("email"),
        "is_active": item.get("is_active"),
    }


def _brief_reference(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
    }


def _reference_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("pk") or "").strip()


def _reference_requested_values(values: Any, *, groups: bool = False) -> list[str]:
    raw_values = values or []
    if isinstance(raw_values, (str, dict)):
        raw_values = [raw_values]
    requested: list[str] = []
    for item in raw_values:
        if groups and isinstance(item, dict):
            value = item.get("pk") or item.get("id") or item.get("name")
        else:
            value = item.get("id") or item.get("name") if isinstance(item, dict) else item
        text = str(value or "").strip()
        if text:
            requested.append(text)
    return requested


def _raise_reference_error(
    *,
    reason_code: str,
    failed_reference_type: str,
    requested: str,
    available_key: str,
    available_items: list[dict[str, Any]],
) -> None:
    labels = {
        "system_roles": "系统角色",
        "org_roles": "组织角色",
        "groups": "用户组",
    }
    label = labels.get(failed_reference_type, failed_reference_type)
    message = "创建用户时无法唯一确认%s。" % label
    if reason_code == "create_user_reference_not_found":
        user_message = "未找到匹配的%s：%s。请先从返回列表中确认正确 ID 或名称。" % (label, requested)
    else:
        user_message = "%s 匹配到多个候选：%s。请改用准确 ID。" % (label, requested)
    payload = build_cli_guidance_payload(
        reason_code,
        user_message=user_message,
        action_hint="请确认当前%s后重试；系统按 system_roles -> org_roles -> groups 顺序逐项确认。" % label,
        failed_reference_type=failed_reference_type,
        requested_reference=requested,
        **{available_key: available_items},
    )
    raise CLIError(message, payload=payload)


def _resolve_reference_values(
    client,
    *,
    path: str,
    requested_values: list[str],
    failed_reference_type: str,
    available_key: str,
) -> list[str]:
    if not requested_values:
        return []
    records = client.list_paginated(path)
    if not isinstance(records, list):
        records = []
    available_items = [_brief_reference(item) for item in records if isinstance(item, dict)]
    resolved: list[str] = []
    for requested in requested_values:
        wanted = _lower(requested)
        matches = [
            item
            for item in records
            if isinstance(item, dict)
            and wanted
            and wanted in {_lower(item.get("id") or item.get("pk")), _lower(item.get("name"))}
        ]
        if not matches:
            _raise_reference_error(
                reason_code="create_user_reference_not_found",
                failed_reference_type=failed_reference_type,
                requested=requested,
                available_key=available_key,
                available_items=available_items,
            )
        if len(matches) > 1:
            _raise_reference_error(
                reason_code="create_user_reference_ambiguous",
                failed_reference_type=failed_reference_type,
                requested=requested,
                available_key=available_key,
                available_items=available_items,
            )
        resolved_id = _reference_id(matches[0])
        if not resolved_id:
            _raise_reference_error(
                reason_code="create_user_reference_not_found",
                failed_reference_type=failed_reference_type,
                requested=requested,
                available_key=available_key,
                available_items=available_items,
            )
        resolved.append(resolved_id)
    return resolved


def _resolve_create_user_references(client, payload: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(payload)
    system_roles = _resolve_reference_values(
        client,
        path=CORE_ENDPOINTS["system_roles"],
        requested_values=_reference_requested_values(payload.get("system_roles")),
        failed_reference_type="system_roles",
        available_key="available_system_roles",
    )
    if system_roles:
        resolved["system_roles"] = system_roles

    org_roles = _resolve_reference_values(
        client,
        path=CORE_ENDPOINTS["org_roles"],
        requested_values=_reference_requested_values(payload.get("org_roles")),
        failed_reference_type="org_roles",
        available_key="available_org_roles",
    )
    if org_roles:
        resolved["org_roles"] = org_roles

    groups = _resolve_reference_values(
        client,
        path=CORE_ENDPOINTS["groups"],
        requested_values=_reference_requested_values(payload.get("groups"), groups=True),
        failed_reference_type="groups",
        available_key="available_groups",
    )
    if groups:
        resolved["groups"] = [{"pk": item} for item in groups]
    return resolved


def _existing_users(client, *, username: str, email: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CORE_ENDPOINTS["users"], params={"search": username})
    if not isinstance(records, list):
        records = []
    email_records = client.list_paginated(CORE_ENDPOINTS["users"], params={"search": email})
    if isinstance(email_records, list):
        records.extend(email_records)

    matches_by_signature: dict[str, dict[str, Any]] = {}
    matched_fields_by_signature: dict[str, set[str]] = {}
    wanted_username = str(username or "").strip().lower()
    wanted_email = str(email or "").strip().lower()
    for item in records:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("pk") or "")
        signature = item_id or "%s:%s" % (item.get("username"), item.get("email"))
        matched_fields = matched_fields_by_signature.setdefault(signature, set())
        if str(item.get("username") or "").strip().lower() == wanted_username:
            matched_fields.add("username")
        if wanted_email and str(item.get("email") or "").strip().lower() == wanted_email:
            matched_fields.add("email")
        if matched_fields:
            matches_by_signature.setdefault(signature, item)
    matches = []
    for signature, item in matches_by_signature.items():
        summary = _brief_user(item)
        summary["matched_fields"] = sorted(matched_fields_by_signature.get(signature) or [])
        matches.append(summary)
    return matches


def _build_create_user_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={
            "password_strategy": "custom",
            "need_update_password": True,
            "mfa_level": 0,
            "source": "local",
            "is_active": True,
            "system_roles": [DEFAULT_SYSTEM_ROLE],
            "org_roles": [DEFAULT_ORG_ROLE],
        },
        explicit_fields=(),
        usage_examples=CREATE_USER_EXAMPLES,
    )
    explicit = {
        "username": args.username,
        "name": args.name,
        "email": args.email,
        "phone": args.phone,
        "password": args.password,
        "password_strategy": args.password_strategy,
        "need_update_password": args.need_update_password,
        "mfa_level": args.mfa_level,
        "is_active": args.is_active,
        "date_expired": args.date_expired,
        "comment": args.comment,
    }
    for key, value in explicit.items():
        if not has_cli_value(value):
            continue
        if key in {"need_update_password", "is_active"}:
            payload[key] = parse_bool(value)
        elif key == "mfa_level":
            payload[key] = int(value)
        else:
            payload[key] = value

    system_roles = _append_values(args.system_role)
    org_roles = _append_values(args.org_role)
    groups = _group_payload(args.group)
    if system_roles:
        payload["system_roles"] = system_roles
    if org_roles:
        payload["org_roles"] = org_roles
    if groups:
        payload["groups"] = groups

    return {
        key: value
        for key, value in payload.items()
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _validate_create_user_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("username", "name", "email") if not str(payload.get(field) or "").strip()]
    strategy = str(payload.get("password_strategy") or "custom")
    if strategy == "custom" and not str(payload.get("password") or "").strip():
        missing.append("password")
    if missing:
        raise CLIError(
            "创建用户参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_user_fields",
                user_message="创建用户缺少必填字段：%s。" % ", ".join(sorted(set(missing))),
                action_hint="补齐字段后重试；默认 password_strategy=custom 时必须传 --password。",
                suggested_commands=CREATE_USER_EXAMPLES,
                missing_fields=sorted(set(missing)),
            ),
        )
    if strategy == "email" and str(payload.get("password") or "").strip():
        raise CLIError(
            "password_strategy=email 时不能传 password。",
            payload=build_cli_guidance_payload(
                "password_not_allowed_for_email_strategy",
                user_message="邮件链接策略由 JumpServer 发送重置链接，不应同时传入明文密码。",
                action_hint="移除 --password，或改用 --password-strategy custom。",
                suggested_commands=CREATE_USER_EXAMPLES,
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": payload.get("username"),
        "name": payload.get("name"),
        "email": payload.get("email"),
        "password_strategy": payload.get("password_strategy"),
        "need_update_password": payload.get("need_update_password"),
        "mfa_level": payload.get("mfa_level"),
        "source": payload.get("source"),
        "is_active": payload.get("is_active"),
        "system_role_count": len(payload.get("system_roles") or []),
        "org_role_count": len(payload.get("org_roles") or []),
        "group_count": len(payload.get("groups") or []),
        "date_expired_sent": "date_expired" in payload,
    }


def _create_user(args: argparse.Namespace):
    payload = _build_create_user_payload(args)
    _validate_create_user_payload(payload)

    if not args.confirm:
        org_context = _preview_create_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_USER_PATH,
            "payload": _redact_payload(payload),
            "payload_summary": _payload_summary(payload),
            "next_step": (
                "python3 subskills/create/scripts/jms_create_user.py create-user "
                "--username %s --name %s --email %s --confirm"
                % (payload.get("username"), payload.get("name"), payload.get("email"))
            ),
            **org_context_output(org_context),
        }

    org_context = _resolve_create_org_context(args, persist_org_name=True)
    client = create_client(org_id=org_id_from_context(org_context))
    duplicates = _existing_users(
        client,
        username=str(payload.get("username") or ""),
        email=str(payload.get("email") or ""),
    )
    if duplicates:
        raise CLIError(
            "用户已存在。",
            payload=build_cli_guidance_payload(
                "user_already_exists",
                user_message="创建前查重发现 username 或 email 已存在，已阻止创建。",
                action_hint="请确认是否改用已有用户，或换一个 username/email。",
                duplicate_users=duplicates,
            ),
        )
    payload = _resolve_create_user_references(client, payload)
    created = client.post(CREATE_USER_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_USER_PATH,
        "payload_summary": _payload_summary(payload),
        "created_user": _brief_user(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建用户入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_USER_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_user = subparsers.add_parser(
        "create-user",
        help="创建本地用户。",
        description="POST /api/v1/users/users/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_USER_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_user.add_argument("--username", required=True)
    create_user.add_argument("--name", required=True)
    create_user.add_argument("--email", required=True)
    create_user.add_argument("--password")
    create_user.add_argument("--password-strategy", choices=["custom", "email"], default="custom")
    create_user.add_argument("--need-update-password", dest="need_update_password")
    create_user.add_argument("--mfa-level", dest="mfa_level", type=int, choices=[0, 1, 3])
    create_user.add_argument("--phone")
    create_user.add_argument("--comment")
    create_user.add_argument("--date-expired", dest="date_expired")
    create_user.add_argument("--is-active", dest="is_active")
    create_user.add_argument("--system-role", dest="system_role", action="append")
    create_user.add_argument("--org-role", dest="org_role", action="append")
    create_user.add_argument("--group", action="append", help="用户组 ID 或精确名称；通过多个 --group 添加多个用户组。")
    create_user.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    create_user.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 且唯一匹配时会写入 .env JMS_ORG_ID。")
    create_user.add_argument("--confirm", action="store_true")
    create_user.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(create_user)
    create_user.set_defaults(func=_create_user)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
