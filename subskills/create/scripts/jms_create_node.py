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
    resolve_command_org_context,
    run_and_print,
)


CREATE_NODE_PATH = "/api/v1/assets/nodes/"
CREATE_NODE_FIELDS = frozenset({"org_id", "full_value", "value"})
CREATE_NODE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_node.py create-node "
        "--full-value /Default/Web --value Web"
    ),
    (
        "python3 subskills/create/scripts/jms_create_node.py create-node "
        "--full-value /Default/Web --value Web --confirm"
    ),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _brief_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "org_id": item.get("org_id"),
        "full_value": item.get("full_value"),
        "value": item.get("value"),
        "name": item.get("name"),
    }


def _raise_global_target_org_error(org_id: str) -> None:
    raise CLIError(
        "创建节点的目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建节点时，目标组织不能使用全局组织 ID。",
            action_hint="请改用具体目标组织 ID 或 `--org-name <target-org>`。",
            org_id=org_id,
        ),
    )


def _env_org_context() -> dict[str, Any]:
    org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
    if not org_id:
        raise CLIError(
            "未选择目标组织。",
            payload=build_cli_guidance_payload(
                "organization_selection_required",
                user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定节点创建组织。",
                action_hint="请传入 `--org-id <org-id>` 或 `--org-name <name>`，或先用 common 子 skill 选择当前组织。",
            ),
        )
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)
    return {
        "effective_org": {"id": org_id, "name": "Unknown", "source": "env"},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前命令范围使用 .env JMS_ORG_ID=%s；不写入 .env。" % org_id,
    }


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id and requested_org_name:
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                "ambiguous_organization_selector",
                user_message="命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
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
            "org_context_hint": "dry-run 仅预览组织 ID %s；追加 --confirm 后才解析组织并创建。" % requested_org_id,
        }
    if requested_org_name:
        return {
            "effective_org": {"id": "", "name": requested_org_name, "source": "command_org_name_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织并创建。" % requested_org_name,
        }

    org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式创建时未传组织将使用 .env JMS_ORG_ID。",
    }


def _resolve_node_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context()


def _build_create_node_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload", None) and not getattr(args, "filters", None):
        args.filters = args.payload
    raw_payload = merge_filter_args(
        args,
        default={},
        explicit_fields=(),
        usage_examples=CREATE_NODE_EXAMPLES,
    )
    if has_cli_value(args.full_value):
        raw_payload["full_value"] = args.full_value
    if has_cli_value(args.value):
        raw_payload["value"] = args.value

    unknown_fields = sorted(set(raw_payload) - CREATE_NODE_FIELDS)
    if unknown_fields:
        raise CLIError(
            "创建节点 payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_create_node_payload_fields",
                user_message="创建节点 payload 只允许字段：org_id, full_value, value。",
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_NODE_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_NODE_FIELDS),
            ),
        )

    return {
        key: value
        for key, value in raw_payload.items()
        if key in CREATE_NODE_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_create_node_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("full_value", "value") if not _text(payload.get(field))]
    if missing:
        raise CLIError(
            "创建节点参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_node_fields",
                user_message="创建节点缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --full-value 和 --value 后重试。",
                suggested_commands=CREATE_NODE_EXAMPLES,
                missing_fields=missing,
            ),
        )


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "org_id": payload.get("org_id"),
        "full_value": payload.get("full_value"),
        "value": payload.get("value"),
    }


def _ensure_payload_org_matches_target(payload: dict[str, Any], target_org_id: str) -> dict[str, Any]:
    target_org_id = _text(target_org_id)
    if not target_org_id or target_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(target_org_id)

    payload_org_id = _text(payload.get("org_id"))
    if payload_org_id and payload_org_id != target_org_id:
        raise CLIError(
            "payload.org_id 与目标组织不一致。",
            payload=build_cli_guidance_payload(
                "organization_not_accessible",
                user_message="payload.org_id 必须等于解析出的目标组织 ID。",
                action_hint="请移除 payload.org_id，或改成目标组织 ID 后重试。",
                payload_org_id=payload_org_id,
                target_org_id=target_org_id,
            ),
        )

    final_payload = dict(payload)
    final_payload["org_id"] = target_org_id
    return final_payload


def _preview_payload_for_org(payload: dict[str, Any], org_context: dict[str, Any]) -> dict[str, Any]:
    target_org_id = org_id_from_context(org_context)
    if target_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(target_org_id)
    payload_org_id = _text(payload.get("org_id"))
    if payload_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(payload_org_id)
    if payload_org_id and target_org_id and payload_org_id != target_org_id:
        raise CLIError(
            "payload.org_id 与目标组织不一致。",
            payload=build_cli_guidance_payload(
                "organization_not_accessible",
                user_message="payload.org_id 必须等于目标组织 ID。",
                action_hint="请移除 payload.org_id，或改成目标组织 ID 后重试。",
                payload_org_id=payload_org_id,
                target_org_id=target_org_id,
            ),
        )
    preview_payload = dict(payload)
    if target_org_id and not payload_org_id:
        preview_payload["org_id"] = target_org_id
    return preview_payload


def _existing_nodes(client, *, full_value: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_NODE_PATH, params={"search": full_value})
    if not isinstance(records, list):
        records = []

    wanted_full_value = _text(full_value)
    matches = []
    seen = set()
    for item in records:
        if not isinstance(item, dict) or _text(item.get("full_value")) != wanted_full_value:
            continue
        signature = str(item.get("id") or item.get("pk") or item.get("full_value") or "")
        if signature in seen:
            continue
        seen.add(signature)
        matches.append(_brief_node(item))
    return matches


def _create_node(args: argparse.Namespace):
    payload = _build_create_node_payload(args)
    _validate_create_node_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        payload = _preview_payload_for_org(payload, org_context)
        return {
            "dry_run": True,
            "api_path": CREATE_NODE_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_node_org_context(args)
    target_org_id = org_id_from_context(org_context)
    payload = _ensure_payload_org_matches_target(payload, target_org_id)
    client = create_client(org_id=target_org_id)
    duplicates = _existing_nodes(client, full_value=str(payload.get("full_value") or ""))
    if duplicates:
        raise CLIError(
            "节点已存在。",
            payload=build_cli_guidance_payload(
                "node_already_exists",
                user_message="目标组织内已存在相同 full_value 的节点，已阻止创建。",
                action_hint="请改用已有节点，或换一个 full_value。",
                duplicate_nodes=duplicates,
            ),
        )

    created = client.post(CREATE_NODE_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_NODE_PATH,
        "payload_summary": _payload_summary(payload),
        "created_node": _brief_node(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建节点入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_NODE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_node = subparsers.add_parser(
        "create-node",
        help="创建资产节点。",
        description="POST /api/v1/assets/nodes/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_NODE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_node.add_argument("--full-value", dest="full_value")
    create_node.add_argument("--value")
    create_node.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    create_node.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    create_node.add_argument("--confirm", action="store_true")
    create_node.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(create_node)
    create_node.set_defaults(func=_create_node)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
