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


ADD_USER_TO_GROUP_PATH = "/api/v1/users/users-groups-relations/"
ADD_USER_TO_GROUP_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group "
        "--org-name Default --user zhangsan --user-group 运维组"
    ),
    (
        "python3 subskills/create/scripts/jms_add_user_to_group.py add-user-to-user-group "
        "--org-name Default --user zhangsan --user-group 运维组 --confirm"
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


def _first_text(*values: Any) -> str:
    for value in values:
        items = _as_text_list(value)
        if items:
            return items[0]
    return ""


def _env_org_preview_context() -> dict[str, Any]:
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式添加时未传组织将使用 .env JMS_ORG_ID。",
    }


def _raise_global_target_org_error(org_id: str) -> None:
    raise CLIError(
        "添加用户到用户组的目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="添加用户到用户组时，目标组织不能使用全局组织 ID。",
            action_hint="请改用具体目标组织 ID 或 `--org-name <target-org>`。",
            org_id=org_id,
        ),
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                "ambiguous_organization_selector",
                user_message="添加用户到用户组命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个目标组织定位参数后重试。",
                provided=["org_id", "org_name"],
            ),
        )
    if requested_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(requested_org_id)
    if requested_org_id:
        return {
            "effective_org": {"id": requested_org_id, "name": "Unknown", "source": "command_explicit_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织 ID %s；追加 --confirm 后才添加用户到用户组。" % requested_org_id,
        }
    if requested_org_name:
        return {
            "effective_org": {"id": "", "name": requested_org_name, "source": "command_org_name_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织并添加关系。" % requested_org_name,
        }
    return _env_org_preview_context()


def _ensure_target_org(context: dict[str, Any]) -> None:
    org_id = org_id_from_context(context)
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "username": item.get("username"),
        "name": item.get("name"),
        "email": item.get("email"),
        "is_active": item.get("is_active"),
    }


def _brief_group(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "comment": item.get("comment"),
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


def _fetch_candidates(client, path: str, requested: str) -> list[dict[str, Any]]:
    params = {"search": requested} if requested else None
    records = client.list_paginated(path, params=params)
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _available_users(client, requested: str) -> list[dict[str, Any]]:
    candidates = _fetch_candidates(client, CORE_ENDPOINTS["users"], requested)
    if not candidates:
        candidates = _fetch_candidates(client, CORE_ENDPOINTS["users"], "")
    return [_brief_user(item) for item in candidates[:50]]


def _available_groups(client, requested: str) -> list[dict[str, Any]]:
    candidates = _fetch_candidates(client, CORE_ENDPOINTS["groups"], requested)
    if not candidates:
        candidates = _fetch_candidates(client, CORE_ENDPOINTS["groups"], "")
    return [_brief_group(item) for item in candidates[:50]]


def _resolve_user_identifier(client, requested: str) -> str:
    candidates = _fetch_candidates(client, CORE_ENDPOINTS["users"], requested)
    matches = _exact_matches(candidates, requested, ("id", "pk", "username", "email", "name"))
    if not matches and is_uuid_like(requested):
        candidates = _fetch_candidates(client, CORE_ENDPOINTS["users"], "")
        matches = _exact_matches(candidates, requested, ("id", "pk"))
    if not matches:
        raise CLIError(
            "目标组织下用户不存在。",
            payload=build_cli_guidance_payload(
                "add_user_group_user_not_found",
                user_message="目标组织下没有找到用户：%s。" % requested,
                action_hint="请确认用户已在目标组织内，或改用目标组织下可见的 username、email、姓名或用户 ID。",
                requested_user=requested,
                available_users=_available_users(client, requested),
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "目标组织下用户匹配到多个候选。",
            payload=build_cli_guidance_payload(
                "add_user_group_user_ambiguous",
                user_message="目标组织下用户标识匹配到多个候选：%s。" % requested,
                action_hint="请改用唯一 username、email 或用户 ID。",
                requested_user=requested,
                candidate_users=[_brief_user(item) for item in matches[:20]],
            ),
        )
    user_id = _reference_id(matches[0])
    if not user_id:
        raise CLIError(
            "目标组织下用户缺少 ID。",
            payload=build_cli_guidance_payload(
                "add_user_group_user_missing_id",
                user_message="已找到用户但无法读取用户 ID：%s。" % requested,
                action_hint="请改用明确用户 ID 重试。",
                requested_user=requested,
                matched_user=_brief_user(matches[0]),
            ),
        )
    return user_id


def _resolve_group_identifier(client, requested: str) -> str:
    candidates = _fetch_candidates(client, CORE_ENDPOINTS["groups"], requested)
    matches = _exact_matches(candidates, requested, ("id", "pk", "name"))
    if not matches and is_uuid_like(requested):
        candidates = _fetch_candidates(client, CORE_ENDPOINTS["groups"], "")
        matches = _exact_matches(candidates, requested, ("id", "pk"))
    if not matches:
        raise CLIError(
            "目标组织下用户组不存在。",
            payload=build_cli_guidance_payload(
                "add_user_group_group_not_found",
                user_message="目标组织下没有找到用户组：%s。" % requested,
                action_hint="请确认用户组在目标组织内，或改用用户组 ID。",
                requested_user_group=requested,
                available_user_groups=_available_groups(client, requested),
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "目标组织下用户组匹配到多个候选。",
            payload=build_cli_guidance_payload(
                "add_user_group_group_ambiguous",
                user_message="目标组织下用户组匹配到多个候选：%s。" % requested,
                action_hint="请改用准确用户组 ID。",
                requested_user_group=requested,
                candidate_user_groups=[_brief_group(item) for item in matches[:20]],
            ),
        )
    group_id = _reference_id(matches[0])
    if not group_id:
        raise CLIError(
            "目标组织下用户组缺少 ID。",
            payload=build_cli_guidance_payload(
                "add_user_group_group_missing_id",
                user_message="已找到用户组但无法读取用户组 ID：%s。" % requested,
                action_hint="请改用明确用户组 ID 重试。",
                requested_user_group=requested,
                matched_user_group=_brief_group(matches[0]),
            ),
        )
    return group_id


def _build_relations(users: list[str], user_group: str) -> list[dict[str, str]]:
    return [{"user": user, "usergroup": user_group} for user in users]


def _build_add_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=ADD_USER_TO_GROUP_EXAMPLES,
    )
    users = _append_values(args.user)
    if users:
        payload["users"] = users
    if args.user_group:
        payload["usergroup"] = args.user_group

    payload["users"] = _as_text_list(payload.get("users") or payload.get("user"))
    payload["usergroup"] = _first_text(
        payload.get("usergroup"),
        payload.get("user_group"),
        payload.get("group"),
        payload.get("user_groups"),
    )
    return {
        key: value
        for key, value in payload.items()
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _validate_add_payload(payload: dict[str, Any]) -> None:
    missing = []
    if not payload.get("users"):
        missing.append("users")
    if not str(payload.get("usergroup") or "").strip():
        missing.append("usergroup")
    if missing:
        raise CLIError(
            "添加用户到用户组参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_add_user_group_fields",
                user_message="添加用户到用户组缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --user 和 --user-group 后重试。",
                suggested_commands=ADD_USER_TO_GROUP_EXAMPLES,
                missing_fields=missing,
            ),
        )


def _payload_summary(relations: list[dict[str, str]]) -> dict[str, Any]:
    groups = sorted({item.get("usergroup") for item in relations if item.get("usergroup")})
    return {
        "relation_count": len(relations),
        "user_count": len({item.get("user") for item in relations if item.get("user")}),
        "user_group_count": len(groups),
        "usergroup": groups[0] if len(groups) == 1 else None,
    }


def _add_user_to_group(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_add_payload(args)
    _validate_add_payload(payload)
    preview_relations = _build_relations(_as_text_list(payload.get("users")), str(payload.get("usergroup") or ""))

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": ADD_USER_TO_GROUP_PATH,
            "payload": preview_relations,
            "payload_summary": _payload_summary(preview_relations),
            "next_step": "追加 --confirm 后在目标组织解析用户、用户组并添加关系。",
            **org_context_output(org_context),
        }

    org_context = resolve_command_org_context(args, allow_global=False)
    _ensure_target_org(org_context)
    client = create_client(org_id=org_id_from_context(org_context))
    group_id = _resolve_group_identifier(client, str(payload.get("usergroup") or ""))
    user_ids: list[str] = []
    for requested_user in _as_text_list(payload.get("users")):
        user_id = _resolve_user_identifier(client, requested_user)
        if user_id not in user_ids:
            user_ids.append(user_id)
    relations = _build_relations(user_ids, group_id)
    relation_result = client.post(ADD_USER_TO_GROUP_PATH, json_body=relations)
    return {
        "dry_run": False,
        "api_path": ADD_USER_TO_GROUP_PATH,
        "payload_summary": _payload_summary(relations),
        "relation_result": relation_result,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 添加用户到用户组入口。",
        epilog="Examples:\n  " + "\n  ".join(ADD_USER_TO_GROUP_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_relation = subparsers.add_parser(
        "add-user-to-user-group",
        help="添加用户到用户组。",
        description="POST /api/v1/users/users-groups-relations/；无 --confirm 只预览，追加 --confirm 才添加。",
        epilog="Examples:\n  " + "\n  ".join(ADD_USER_TO_GROUP_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    add_relation.add_argument("--user", action="append", help="用户 UUID、username、email 或姓名；可重复。")
    add_relation.add_argument("--user-group", dest="user_group", help="用户组 ID 或精确名称。")
    add_relation.add_argument("--org-id", dest="org_id", help="目标组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    add_relation.add_argument("--org-name", dest="org_name", help="目标组织名称；只限定本次命令，不写 .env。")
    add_relation.add_argument("--confirm", action="store_true")
    add_relation.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(add_relation)
    add_relation.set_defaults(func=_add_user_to_group)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
