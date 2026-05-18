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
    is_uuid_like,
    list_accessible_orgs,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    persist_selected_org,
    run_and_print,
)


CREATE_USER_GROUP_PATH = "/api/v1/users/groups/"
CREATE_USER_GROUP_EXAMPLES = [
    "python3 subskills/create/scripts/jms_create_user_group.py create-user-group --name 运维组",
    "python3 subskills/create/scripts/jms_create_user_group.py create-user-group --name 运维组 --user <user-id> --user <user-id> --confirm",
]
ORG_NOT_ACCESSIBLE_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
AMBIGUOUS_ORG_SELECTOR_REASON_CODE = "ambiguous_organization_selector"


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


def _brief_user_group(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "comment": item.get("comment"),
    }


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "username": item.get("username"),
        "name": item.get("name"),
        "email": item.get("email"),
        "is_active": item.get("is_active"),
    }


def _append_values(values: list[str] | None) -> list[str]:
    return [str(item).strip() for item in values or [] if str(item or "").strip()]


def _build_create_user_group_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=CREATE_USER_GROUP_EXAMPLES,
    )
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    users = _append_values(args.user)
    if users:
        payload["users"] = [{"pk": item} for item in users]
    return {
        key: value
        for key, value in payload.items()
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _validate_create_user_group_payload(payload: dict[str, Any]) -> None:
    if not str(payload.get("name") or "").strip():
        raise CLIError(
            "创建用户组参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_user_group_fields",
                user_message="创建用户组缺少必填字段：name。",
                action_hint="补齐 --name 后重试。",
                suggested_commands=CREATE_USER_GROUP_EXAMPLES,
                missing_fields=["name"],
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "comment_sent": "comment" in payload,
        "user_count": len(payload.get("users") or []),
    }


def _existing_user_groups(client, *, name: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CORE_ENDPOINTS["groups"], params={"search": name})
    if not isinstance(records, list):
        records = []
    wanted = _lower(name)
    matches = []
    seen = set()
    for item in records:
        if not isinstance(item, dict):
            continue
        if _lower(item.get("name")) != wanted:
            continue
        signature = str(item.get("id") or item.get("pk") or item.get("name") or "")
        if signature in seen:
            continue
        seen.add(signature)
        matches.append(_brief_user_group(item))
    return matches


def _user_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    values = payload.get("users") or []
    if isinstance(values, (str, dict)):
        values = [values]
    user_ids: list[str] = []
    for item in values:
        if isinstance(item, dict):
            value = item.get("pk") or item.get("id")
        else:
            value = item
        text = str(value or "").strip()
        if text:
            user_ids.append(text)
    return user_ids


def _available_users(client) -> list[dict[str, Any]]:
    records = client.list_paginated(CORE_ENDPOINTS["users"])
    if not isinstance(records, list):
        records = []
    return [_brief_user(item) for item in records if isinstance(item, dict)]


def _ensure_user_ids_exist(client, user_ids: list[str]) -> list[dict[str, str]]:
    users_payload = []
    for user_id in user_ids:
        if not is_uuid_like(user_id):
            raise CLIError(
                "创建用户组成员必须使用用户 ID。",
                payload=build_cli_guidance_payload(
                    "create_user_group_user_id_required",
                    user_message="`--user` 只接受用户 ID：%s。" % user_id,
                    action_hint="请先执行 `python3 subskills/query/scripts/jms_query.py resolve --resource user --name <value>` 解析用户 ID，再重试。",
                    invalid_user=user_id,
                ),
            )
        records = client.list_paginated(CORE_ENDPOINTS["users"], params={"search": user_id})
        if not isinstance(records, list):
            records = []
        matches = [
            item
            for item in records
            if isinstance(item, dict) and user_id in {str(item.get("id") or "").strip(), str(item.get("pk") or "").strip()}
        ]
        if not matches:
            raise CLIError(
                "创建用户组成员用户不存在。",
                payload=build_cli_guidance_payload(
                    "create_user_group_user_not_found",
                    user_message="没有找到用户 ID：%s。" % user_id,
                    action_hint="请确认用户 ID，或先用 query 解析用户。",
                    missing_user_id=user_id,
                    available_users=_available_users(client),
                ),
            )
        users_payload.append({"pk": user_id})
    return users_payload


def _create_user_group(args: argparse.Namespace):
    payload = _build_create_user_group_payload(args)
    _validate_create_user_group_payload(payload)

    if not args.confirm:
        org_context = _preview_create_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_USER_GROUP_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            "next_step": (
                "python3 subskills/create/scripts/jms_create_user_group.py create-user-group "
                "--name %s --confirm" % payload.get("name")
            ),
            **org_context_output(org_context),
        }

    org_context = _resolve_create_org_context(args, persist_org_name=True)
    client = create_client(org_id=org_id_from_context(org_context))
    duplicates = _existing_user_groups(client, name=str(payload.get("name") or ""))
    if duplicates:
        raise CLIError(
            "用户组已存在。",
            payload=build_cli_guidance_payload(
                "user_group_already_exists",
                user_message="创建前查重发现用户组名称已存在，已阻止创建。",
                action_hint="请确认是否改用已有用户组，或换一个用户组名称。",
                duplicate_user_groups=duplicates,
            ),
        )

    user_ids = _user_ids_from_payload(payload)
    if user_ids:
        payload = dict(payload)
        payload["users"] = _ensure_user_ids_exist(client, user_ids)

    created = client.post(CREATE_USER_GROUP_PATH, json_body=payload)
    created_group = _brief_user_group(created) if isinstance(created, dict) else created
    if isinstance(created_group, dict):
        created_group["user_count"] = len(payload.get("users") or [])
    return {
        "dry_run": False,
        "api_path": CREATE_USER_GROUP_PATH,
        "payload_summary": _payload_summary(payload),
        "created_user_group": created_group,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建用户组入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_USER_GROUP_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_group = subparsers.add_parser(
        "create-user-group",
        help="创建用户组。",
        description="POST /api/v1/users/groups/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_USER_GROUP_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_group.add_argument("--name", required=True)
    create_group.add_argument("--comment")
    create_group.add_argument("--user", action="append", help="用户 ID；通过多个 --user <user-id> 添加多个用户 ID。")
    create_group.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    create_group.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 且唯一匹配时会写入 .env JMS_ORG_ID。")
    create_group.add_argument("--confirm", action="store_true")
    create_group.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(create_group)
    create_group.set_defaults(func=_create_user_group)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
