#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_text_utils import (
    exact_first_filter as _exact_first_filter,
    lower_text as _lower,
    value_from_path as _value_from_path,
)
from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    ORG_SELECTION_NEXT_STEP,
    add_filter_arguments,
    build_cli_guidance_payload,
    build_org_selection_required_payload,
    create_client,
    create_discovery,
    get_config_status,
    ensure_selected_org_context,
    list_accessible_orgs,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    parse_json_arg,
    persist_selected_org,
    reject_deprecated_pagination_cli_args,
    resolve_effective_org_context,
    run_and_print,
    user_profile,
    write_local_env_config,
)


SELECT_ORG_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
MISSING_ENDPOINT_PATH_REASON_CODE = "missing_endpoint_path"
UNSUPPORTED_VERIFICATION_METHOD_REASON_CODE = "unsupported_verification_method"

SELECT_ORG_EXAMPLES = [
    "python3 subskills/common/scripts/jms_common.py select-org",
    "python3 subskills/common/scripts/jms_common.py select-org --org-name Default",
]


def _config_status(_: argparse.Namespace) -> dict[str, Any]:
    return get_config_status()


def _config_write(args: argparse.Namespace) -> dict[str, Any]:
    if not getattr(args, "confirm", False):
        raise CLIError(
            "当前操作需要显式确认。",
            payload=build_cli_guidance_payload(
                "confirmation_required",
                user_message="这个命令会改写本地运行时配置，继续前必须追加 `--confirm`。",
                action_hint="先查看当前返回的预览结果，确认无误后再重跑一次并加上 `--confirm`。",
            ),
        )
    payload = parse_json_arg(
        args.payload,
        source="--payload",
        usage_examples=[
            "python3 subskills/common/scripts/jms_common.py config-write --payload '{\"JMS_API_URL\": \"https://jump.example.com\"}' --confirm",
        ],
        include_raw_value=False,
    )
    return write_local_env_config(
        payload,
        recover_invalid=bool(getattr(args, "recover_invalid_env", False)),
    )


def _ping(_: argparse.Namespace) -> dict[str, Any]:
    client = create_client()
    health = client.health_check()
    profile = user_profile(client)
    org_context = resolve_effective_org_context()
    current = client.get("/api/v1/orgs/orgs/current/")
    config_status = get_config_status()
    return {
        "health": health,
        "profile": profile,
        "candidate_orgs": org_context.get("candidate_orgs"),
        "current_org": current,
        "auth_mode": config_status.get("auth_mode"),
        "config_status": config_status,
        **org_context_output(org_context),
    }


def _select_org(args: argparse.Namespace) -> dict[str, Any]:
    candidates = list_accessible_orgs()
    current_context = resolve_effective_org_context(auto_select=False)
    provided_selectors = [
        name
        for name, value in {"org_id": getattr(args, "org_id", None), "org_name": getattr(args, "org_name", None)}.items()
        if str(value or "").strip()
    ]
    if len(provided_selectors) > 1:
        raise CLIError(
            "组织选择参数冲突。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="`select-org` 只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                provided=provided_selectors,
            ),
        )
    if not args.org_id and not getattr(args, "org_name", None):
        if current_context.get("selection_required"):
            return build_org_selection_required_payload(current_context)
        return {
            "selection_required": False,
            "candidate_orgs": candidates,
            "next_step": ORG_SELECTION_NEXT_STEP,
            **org_context_output(current_context),
        }

    target_org_id = str(getattr(args, "org_id", None) or "").strip()
    target_org_name = str(getattr(args, "org_name", None) or "").strip()
    if target_org_id:
        matches = [item for item in candidates if str(item.get("id") or "").strip() == target_org_id]
    else:
        matches = _exact_first_filter([item for item in candidates if isinstance(item, dict)], target_org_name, "name")
    if not matches:
        raise CLIError(
            "指定的组织当前不可访问。",
            payload=build_cli_guidance_payload(
                SELECT_ORG_REASON_CODE,
                user_message="当前账号下找不到你指定的组织，请先从 `candidate_orgs` 里确认可访问组织。",
                action_hint="可以先执行不带参数的 `select-org` 查看候选组织，再改用 `--org-id` 或精确的 `--org-name`。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                org_id=target_org_id or None,
                org_name=target_org_name or None,
                candidate_orgs=candidates,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "给定的组织名称匹配到多个候选组织。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称或直接使用 `--org-id`。",
                action_hint="优先从返回的 `candidate_orgs` 中复制准确的 org_id 再执行。",
                suggested_commands=SELECT_ORG_EXAMPLES,
                org_name=target_org_name or None,
                candidate_orgs=matches[:10],
            ),
        )

    selected = matches[0]
    selected_org_id = str(selected.get("id") or "").strip()
    preview_scope = "%s (%s)" % (
        str(selected.get("name") or "").strip() or "Unknown",
        selected_org_id or "<unknown-org-id>",
    )
    preview_context = {
        **current_context,
        "effective_org": {**selected, "source": "user_selected"},
        "switchable_orgs": [item for item in candidates if str(item.get("id") or "") != selected_org_id],
        "switchable_org_count": len([item for item in candidates if str(item.get("id") or "") != selected_org_id]),
        "org_context_hint": "当前预览的查询范围将切换为组织 %s；确认写入后才能按该组织继续查询。" % preview_scope,
    }
    if not args.confirm:
        return {
            "selection_required": False,
            "next_step": "python3 subskills/common/scripts/jms_common.py select-org --org-id %s --confirm" % selected_org_id,
            **org_context_output(preview_context),
        }

    persisted = persist_selected_org(selected_org_id)
    confirmed_context = {
        **preview_context,
        "org_context_hint": (
            "当前查询范围固定为组织 %s；如需切换查询范围，请先切换组织。" % preview_scope
            if preview_context["switchable_org_count"]
            else None
        ),
    }
    return {
        "selection_required": False,
        "current_nonsecret": persisted["current_nonsecret"],
        "env_file_path": persisted["env_file_path"],
        **org_context_output(confirmed_context),
    }


def _endpoint_inventory(args: argparse.Namespace) -> dict[str, Any]:
    org_context = ensure_selected_org_context()
    org_id = org_id_from_context(org_context)
    create_client(org_id=org_id)
    discovery = create_discovery(org_id=org_id)
    return discovery.core_inventory_payload(refresh=args.refresh)


def _endpoint_verify(args: argparse.Namespace) -> dict[str, Any]:
    org_context = ensure_selected_org_context()
    client = create_client(org_id=org_id_from_context(org_context))
    filters = merge_filter_args(
        args,
        usage_examples=[
            "python3 subskills/common/scripts/jms_common.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
        ],
    )
    path = str(args.path or filters.get("path") or "").strip()
    if not path:
        raise CLIError(
            "缺少待验证的端点路径。",
            payload=build_cli_guidance_payload(
                MISSING_ENDPOINT_PATH_REASON_CODE,
                user_message="请通过 `--path` 指定要验证的 API 路径。",
                action_hint="例如 `--path /api/v1/settings/setting/`；只有兼容旧命令时才建议放进 `--filters`。",
                suggested_commands=[
                    "python3 subskills/common/scripts/jms_common.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
                ],
            ),
        )
    method = str(args.method or filters.get("method") or "GET").strip().upper()
    params = filters.get("params") if isinstance(filters.get("params"), dict) else None
    if method == "OPTIONS":
        payload = client.options(path, params=params)
    elif method == "GET":
        payload = client.get(path, params=params)
    else:
        raise CLIError(
            "不支持的验证方法：%s" % method,
            payload=build_cli_guidance_payload(
                UNSUPPORTED_VERIFICATION_METHOD_REASON_CODE,
                user_message="`endpoint-verify` 目前只支持 `GET` 和 `OPTIONS`。",
                action_hint="请把 `--method` 改成 `GET` 或 `OPTIONS`。",
                suggested_commands=[
                    "python3 subskills/common/scripts/jms_common.py endpoint-verify --path /api/v1/settings/setting/ --method GET",
                ],
                method=method,
            ),
        )
    return {"method": method, "path": path, "payload": payload}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 公共配置、预检、组织选择与连通性入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_status = subparsers.add_parser("config-status", help="查看本地运行时配置状态。", formatter_class=CLIHelpFormatter)
    config_status.add_argument("--json", action="store_true")
    config_status.set_defaults(func=_config_status)

    config_write = subparsers.add_parser("config-write", help="写入本地 .env 配置。", formatter_class=CLIHelpFormatter)
    config_write.add_argument("--payload", required=True)
    config_write.add_argument(
        "--recover-invalid-env",
        action="store_true",
        help="仅恢复现存且无法解析的 .env；要求完整 payload，并先生成 0600 原始字节备份。",
    )
    config_write.add_argument("--confirm", action="store_true")
    config_write.set_defaults(func=_config_write)

    ping = subparsers.add_parser("ping", help="检查连通性、当前用户和组织上下文。", formatter_class=CLIHelpFormatter)
    ping.set_defaults(func=_ping)

    select_org = subparsers.add_parser(
        "select-org",
        help="查看、解析或预览组织。",
        epilog="Examples:\n  " + "\n  ".join(SELECT_ORG_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    select_org.add_argument("--org-id")
    select_org.add_argument("--org-name")
    select_org.add_argument("--confirm", action="store_true")
    select_org.set_defaults(func=_select_org)

    endpoint_inventory = subparsers.add_parser("endpoint-inventory", help="查看端点 inventory。", formatter_class=CLIHelpFormatter)
    endpoint_inventory.add_argument("--refresh", action="store_true")
    endpoint_inventory.set_defaults(func=_endpoint_inventory)

    endpoint_verify = subparsers.add_parser("endpoint-verify", help="验证单个端点的 GET/OPTIONS 能力。", formatter_class=CLIHelpFormatter)
    endpoint_verify.add_argument("--path")
    endpoint_verify.add_argument("--method", choices=["GET", "OPTIONS"], default="GET")
    add_filter_arguments(endpoint_verify)
    endpoint_verify.set_defaults(func=_endpoint_verify)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_common.py",
            deprecated_commands=set(),
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
