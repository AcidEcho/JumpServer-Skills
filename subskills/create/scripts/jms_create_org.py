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
    create_client,
    has_cli_value,
    merge_filter_args,
    run_and_print,
)


CREATE_ORGANIZATION_PATH = "/api/v1/orgs/orgs/"
CREATE_ORGANIZATION_EXAMPLES = [
    "python3 subskills/create/scripts/jms_create_org.py create-organization --name new",
    "python3 subskills/create/scripts/jms_create_org.py create-organization --name new --comment 备注 --confirm",
]


def _brief_organization(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "comment": item.get("comment"),
    }


def _build_create_organization_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=CREATE_ORGANIZATION_EXAMPLES,
    )
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    allowed_fields = {"name", "comment"}
    return {
        key: value
        for key, value in payload.items()
        if key in allowed_fields
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _validate_create_organization_payload(payload: dict[str, Any]) -> None:
    if not str(payload.get("name") or "").strip():
        raise CLIError(
            "创建组织参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_organization_fields",
                user_message="创建组织缺少必填字段：name。",
                action_hint="补齐 --name 后重试。",
                suggested_commands=CREATE_ORGANIZATION_EXAMPLES,
                missing_fields=["name"],
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "comment_sent": "comment" in payload,
    }


def _create_organization(args: argparse.Namespace):
    payload = _build_create_organization_payload(args)
    _validate_create_organization_payload(payload)

    if not args.confirm:
        return {
            "dry_run": True,
            "api_path": CREATE_ORGANIZATION_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            "next_step": (
                "python3 subskills/create/scripts/jms_create_org.py create-organization "
                "--name %s --confirm" % payload.get("name")
            ),
            "org_header": "not_sent",
        }

    client = create_client(org_id="")
    created = client.post(CREATE_ORGANIZATION_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_ORGANIZATION_PATH,
        "payload_summary": _payload_summary(payload),
        "created_organization": _brief_organization(created) if isinstance(created, dict) else created,
        "org_header": "not_sent",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建组织入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ORGANIZATION_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_org = subparsers.add_parser(
        "create-organization",
        help="创建组织。",
        description="POST /api/v1/orgs/orgs/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ORGANIZATION_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_org.add_argument("--name", required=True)
    create_org.add_argument("--comment")
    create_org.add_argument("--confirm", action="store_true")
    create_org.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(create_org)
    create_org.set_defaults(func=_create_organization)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
