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

from jumpserver_common.jms_create_org_context import (  # noqa: E402
    preview_create_org_context,
    resolve_create_org_context,
)
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


def _resolve_create_org_context(args: argparse.Namespace, *, persist_org_name: bool = False) -> dict[str, Any]:
    return resolve_create_org_context(
        args,
        persist_org_name=persist_org_name,
        ensure_selected_org_context=ensure_selected_org_context,
        list_accessible_orgs=list_accessible_orgs,
        persist_selected_org=persist_selected_org,
    )


def _preview_create_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(args, current_runtime_values=current_runtime_values)


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
