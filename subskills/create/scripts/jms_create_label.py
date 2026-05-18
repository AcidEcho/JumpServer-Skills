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
    add_filter_arguments,
    build_cli_guidance_payload,
    create_env_org_context,
    create_client,
    has_cli_value,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    preview_create_org_context,
    resolve_command_org_context,
    run_and_print,
)


CREATE_LABEL_PATH = "/api/v1/labels/labels/"
CREATE_LABEL_FIELDS = frozenset({"color", "name", "value", "comment"})
CREATE_LABEL_EXAMPLES = [
    "python3 subskills/create/scripts/jms_create_label.py create-label --name env --value prod",
    "python3 subskills/create/scripts/jms_create_label.py create-label --name env --value prod --confirm",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _brief_label(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
        "color": item.get("color"),
        "comment": item.get("comment"),
    }


def _env_org_context() -> dict[str, Any]:
    return create_env_org_context(
        resource_name="标签创建",
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定标签创建组织。",
        global_user_message="创建标签时，目标组织不能使用全局组织 ID。",
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="创建标签",
        global_user_message="创建标签时，目标组织不能使用全局组织 ID。",
    )


def _resolve_label_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context()


def _build_create_label_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=CREATE_LABEL_EXAMPLES,
    )
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.value):
        payload["value"] = args.value
    if has_cli_value(args.color):
        payload["color"] = args.color
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_LABEL_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_create_label_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("name", "value") if not _text(payload.get(field))]
    if missing:
        raise CLIError(
            "创建标签参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_label_fields",
                user_message="创建标签缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --name 和 --value 后重试。",
                suggested_commands=CREATE_LABEL_EXAMPLES,
                missing_fields=missing,
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "value": payload.get("value"),
        "color_sent": "color" in payload,
        "comment_sent": "comment" in payload,
    }


def _existing_labels(client, *, name: str, value: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_LABEL_PATH, params={"search": name})
    if not isinstance(records, list):
        records = []

    wanted_name = _text(name)
    wanted_value = _text(value)
    matches = []
    seen = set()
    for item in records:
        if not isinstance(item, dict):
            continue
        if _text(item.get("name")) != wanted_name or _text(item.get("value")) != wanted_value:
            continue
        signature = str(item.get("id") or item.get("pk") or "%s:%s" % (item.get("name"), item.get("value")))
        if signature in seen:
            continue
        seen.add(signature)
        matches.append(_brief_label(item))
    return matches


def _create_label(args: argparse.Namespace):
    payload = _build_create_label_payload(args)
    _validate_create_label_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_LABEL_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            "next_step": (
                "python3 subskills/create/scripts/jms_create_label.py create-label "
                "--name %s --value %s --confirm" % (payload.get("name"), payload.get("value"))
            ),
            **org_context_output(org_context),
        }

    org_context = _resolve_label_org_context(args)
    client = create_client(org_id=org_id_from_context(org_context))
    duplicates = _existing_labels(
        client,
        name=str(payload.get("name") or ""),
        value=str(payload.get("value") or ""),
    )
    if duplicates:
        raise CLIError(
            "标签已存在。",
            payload=build_cli_guidance_payload(
                "label_already_exists",
                user_message="目标组织内已存在相同 name 和 value 的标签，已阻止创建。",
                action_hint="请改用已有标签，或换一个 name/value 组合。",
                duplicate_labels=duplicates,
            ),
        )

    created = client.post(CREATE_LABEL_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_LABEL_PATH,
        "payload_summary": _payload_summary(payload),
        "created_label": _brief_label(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建标签入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LABEL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_label = subparsers.add_parser(
        "create-label",
        help="创建标签。",
        description="POST /api/v1/labels/labels/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LABEL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_label.add_argument("--name")
    create_label.add_argument("--value")
    create_label.add_argument("--color")
    create_label.add_argument("--comment")
    create_label.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    create_label.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    create_label.add_argument("--confirm", action="store_true")
    create_label.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(create_label)
    create_label.set_defaults(func=_create_label)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
