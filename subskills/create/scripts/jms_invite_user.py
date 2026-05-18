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
    GLOBAL_ORG_ID,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    current_runtime_values,
    is_uuid_like,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    resolve_command_org_context,
    run_and_print,
)


INVITE_USER_PATH = "/api/v1/users/users/invite/"
INVITE_USER_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org "
        "--org-name Default --user zhangsan --org-role 组织用户"
    ),
    (
        "python3 subskills/create/scripts/jms_invite_user.py invite-user-to-org "
        "--org-name Default --user zhangsan --org-role 组织用户 --confirm"
    ),
]


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _append_values(values: list[str] | None) -> list[str]:
    return [str(item).strip() for item in values or [] if str(item or "").strip()]


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _env_org_preview_context() -> dict[str, Any]:
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式邀请时未传组织将使用 .env JMS_ORG_ID。",
    }


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                "ambiguous_organization_selector",
                user_message="邀请命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个目标组织定位参数后重试。",
                provided=["org_id", "org_name"],
            ),
        )
    if requested_org_id == GLOBAL_ORG_ID:
        raise CLIError(
            "邀请目标组织不能是全局组织。",
            payload=build_cli_guidance_payload(
                "organization_not_accessible",
                user_message="邀请用户加入组织时，目标组织不能使用全局组织 ID。",
                action_hint="请改用具体目标组织 ID 或 `--org-name <target-org>`。",
                org_id=requested_org_id,
            ),
        )
    if requested_org_id:
        return {
            "effective_org": {"id": requested_org_id, "name": "Unknown", "source": "command_explicit_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织 ID %s；追加 --confirm 后才发送邀请。" % requested_org_id,
        }
    if requested_org_name:
        return {
            "effective_org": {"id": "", "name": requested_org_name, "source": "command_org_name_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织并发送邀请。" % requested_org_name,
        }
    return _env_org_preview_context()


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "username": item.get("username"),
        "name": item.get("name"),
        "email": item.get("email"),
        "is_active": item.get("is_active"),
    }


def _brief_role(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
    }


def _reference_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("pk") or "").strip()


def _exact_matches(records: list[dict[str, Any]], requested: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = _lower(requested)
    for field in fields:
        matches = [item for item in records if _lower(item.get(field)) == wanted]
        if matches:
            return matches
    return []


def _fetch_user_candidates(client, requested: str) -> list[dict[str, Any]]:
    params = {"search": requested} if requested else None
    records = client.list_paginated(CORE_ENDPOINTS["users"], params=params)
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _available_users(client, requested: str) -> list[dict[str, Any]]:
    candidates = _fetch_user_candidates(client, requested)
    if not candidates:
        candidates = _fetch_user_candidates(client, "")
    return [_brief_user(item) for item in candidates[:50]]


def _resolve_user_identifier(client, requested: str) -> str:
    candidates = _fetch_user_candidates(client, requested)
    matches = _exact_matches(candidates, requested, ("id", "pk", "username", "email", "name"))
    if not matches and is_uuid_like(requested):
        candidates = _fetch_user_candidates(client, "")
        matches = _exact_matches(candidates, requested, ("id", "pk"))
    if not matches:
        raise CLIError(
            "邀请用户不存在。",
            payload=build_cli_guidance_payload(
                "invite_user_not_found",
                user_message="全局组织下没有找到用户：%s。" % requested,
                action_hint="请确认用户名、邮箱、姓名或用户 ID；也可先用 query 的全局组织解析确认。",
                requested_user=requested,
                lookup_org_id=GLOBAL_ORG_ID,
                available_users=_available_users(client, requested),
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "邀请用户匹配到多个候选。",
            payload=build_cli_guidance_payload(
                "invite_user_ambiguous",
                user_message="全局组织下用户标识匹配到多个候选：%s。" % requested,
                action_hint="请改用唯一 username、email 或用户 ID。",
                requested_user=requested,
                lookup_org_id=GLOBAL_ORG_ID,
                candidate_users=[_brief_user(item) for item in matches[:20]],
            ),
        )
    user_id = _reference_id(matches[0])
    if not user_id:
        raise CLIError(
            "邀请用户缺少 ID。",
            payload=build_cli_guidance_payload(
                "invite_user_missing_id",
                user_message="已找到用户但无法读取用户 ID：%s。" % requested,
                action_hint="请改用明确用户 ID 重试。",
                requested_user=requested,
                matched_user=_brief_user(matches[0]),
            ),
        )
    return user_id


def _resolve_user_identifiers(values: list[str]) -> list[str]:
    client = create_client(org_id=GLOBAL_ORG_ID)
    resolved: list[str] = []
    for requested in values:
        user_id = _resolve_user_identifier(client, requested)
        if user_id not in resolved:
            resolved.append(user_id)
    return resolved


def _resolve_org_role_values(client, requested_values: list[str]) -> list[str]:
    records = client.list_paginated(CORE_ENDPOINTS["org_roles"])
    if not isinstance(records, list):
        records = []
    role_records = [item for item in records if isinstance(item, dict)]
    available_roles = [_brief_role(item) for item in role_records]
    resolved: list[str] = []
    for requested in requested_values:
        matches = _exact_matches(role_records, requested, ("id", "pk", "name"))
        if not matches:
            raise CLIError(
                "邀请组织角色不存在。",
                payload=build_cli_guidance_payload(
                    "invite_org_role_reference_not_found",
                    user_message="目标组织下没有找到组织角色：%s。" % requested,
                    action_hint="请从 available_org_roles 中确认正确角色 ID 或名称后重试。",
                    requested_reference=requested,
                    available_org_roles=available_roles,
                ),
            )
        if len(matches) > 1:
            raise CLIError(
                "邀请组织角色匹配到多个候选。",
                payload=build_cli_guidance_payload(
                    "invite_org_role_reference_ambiguous",
                    user_message="目标组织下组织角色匹配到多个候选：%s。" % requested,
                    action_hint="请改用准确角色 ID。",
                    requested_reference=requested,
                    available_org_roles=[_brief_role(item) for item in matches[:20]],
                ),
            )
        role_id = _reference_id(matches[0])
        if role_id not in resolved:
            resolved.append(role_id)
    return resolved


def _build_invite_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=INVITE_USER_EXAMPLES,
    )
    users = _append_values(args.user)
    org_roles = _append_values(args.org_role)
    if users:
        payload["users"] = users
    if org_roles:
        payload["org_roles"] = org_roles
    if "users" in payload:
        payload["users"] = _as_text_list(payload.get("users"))
    if "org_roles" in payload:
        payload["org_roles"] = _as_text_list(payload.get("org_roles"))
    return {
        key: value
        for key, value in payload.items()
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _validate_invite_payload(payload: dict[str, Any]) -> None:
    missing = []
    if not payload.get("users"):
        missing.append("users")
    if not payload.get("org_roles"):
        missing.append("org_roles")
    if missing:
        raise CLIError(
            "邀请用户参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_invite_user_fields",
                user_message="邀请用户缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --user 和 --org-role 后重试。",
                suggested_commands=INVITE_USER_EXAMPLES,
                missing_fields=missing,
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_count": len(_as_text_list(payload.get("users"))),
        "org_role_count": len(_as_text_list(payload.get("org_roles"))),
    }


def _invite_user_to_org(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_invite_payload(args)
    _validate_invite_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": INVITE_USER_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            "user_lookup_org_id": GLOBAL_ORG_ID,
            "next_step": "追加 --confirm 后执行全局用户解析、目标组织角色解析和邀请。",
            **org_context_output(org_context),
        }

    org_context = resolve_command_org_context(args, allow_global=False)
    client = create_client(org_id=org_id_from_context(org_context))
    resolved_payload = {
        "users": _resolve_user_identifiers(_as_text_list(payload.get("users"))),
        "org_roles": _resolve_org_role_values(client, _as_text_list(payload.get("org_roles"))),
    }
    invite_result = client.post(INVITE_USER_PATH, json_body=resolved_payload)
    return {
        "dry_run": False,
        "api_path": INVITE_USER_PATH,
        "payload_summary": _payload_summary(resolved_payload),
        "user_lookup_org_id": GLOBAL_ORG_ID,
        "invite_result": invite_result,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 邀请用户加入组织入口。",
        epilog="Examples:\n  " + "\n  ".join(INVITE_USER_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    invite = subparsers.add_parser(
        "invite-user-to-org",
        help="邀请用户加入某个组织。",
        description="POST /api/v1/users/users/invite/；无 --confirm 只预览，追加 --confirm 才邀请。",
        epilog="Examples:\n  " + "\n  ".join(INVITE_USER_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    invite.add_argument("--user", action="append", help="用户 UUID、username、email 或姓名；可重复。")
    invite.add_argument("--org-role", dest="org_role", action="append", help="组织角色 ID 或精确名称；可重复。")
    invite.add_argument("--org-id", dest="org_id", help="目标组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    invite.add_argument("--org-name", dest="org_name", help="目标组织名称；只限定本次命令，不写 .env。")
    invite.add_argument("--confirm", action="store_true")
    invite.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(invite)
    invite.set_defaults(func=_invite_user_to_org)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
