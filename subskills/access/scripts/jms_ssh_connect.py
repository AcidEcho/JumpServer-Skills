#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
import shlex
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_text_utils import exact_first_filter as _exact_first_filter
from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    DEFAULT_PAGE_SIZE,
    build_cli_guidance_payload,
    create_client,
    ensure_selected_org_context,
    list_accessible_orgs,
    org_id_from_context,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


CONNECTION_ASSET_SELECTION_REASON_CODE = "connection_asset_selection_required"
CONNECTION_ACCOUNT_SELECTION_REASON_CODE = "connection_account_selection_required"
CONNECTION_PROTOCOL_UNAVAILABLE_REASON_CODE = "connection_protocol_unavailable"
CONNECTION_METHOD_UNAVAILABLE_REASON_CODE = "connection_method_unavailable"
CONNECTION_CONFIRMATION_REASON_CODE = "connection_token_confirmation_required"
CONNECTION_CLIENT_URL_INVALID_REASON_CODE = "connection_client_url_invalid"
CONNECTION_TOKEN_PATH = "/api/v1/authentication/connection-token/"
CONNECTION_SELF_ASSETS_PATH = "/api/v1/perms/users/self/assets/"
CONNECTION_METHODS_PATH = "/api/v1/terminal/components/connect-methods/"


def _require_exactly_one_selector(*, values: dict[str, str | None], message: str) -> None:
    provided = [name for name, value in values.items() if str(value or "").strip()]
    if len(provided) != 1:
        raise CLIError(message, payload={"provided": provided})


def _validate_connection_asset_selector(args: argparse.Namespace) -> None:
    _require_exactly_one_selector(
        values={
            "asset_id": args.asset_id,
            "asset_name": args.asset_name,
            "asset_address": args.asset_address,
        },
        message="Provide exactly one of --asset-id, --asset-name, or --asset-address.",
    )


def _validate_org_override_selector(args: argparse.Namespace) -> None:
    provided = [
        name
        for name, value in {
            "org_id": getattr(args, "org_id", None),
            "org_name": getattr(args, "org_name", None),
        }.items()
        if str(value or "").strip()
    ]
    if len(provided) > 1:
        raise CLIError(
            "Provide at most one of --org-id or --org-name.",
            payload={"provided": provided},
        )


def _build_connection_org_context(
    selected_org: dict[str, Any],
    accessible_orgs: list[dict[str, Any]],
) -> dict[str, Any]:
    effective_org = {**selected_org, "source": "command_explicit"}
    effective_org_id = str(effective_org.get("id") or "").strip()
    switchable_orgs = [
        item
        for item in accessible_orgs
        if str(item.get("id") or "").strip()
        and str(item.get("id") or "").strip() != effective_org_id
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
        "org_context_hint": (
            "当前连接范围固定为组织 %s；本次命令仅临时按该组织执行，不会写回本地配置。"
            % org_scope
        ),
    }


def _resolve_connection_scope(args: argparse.Namespace) -> dict[str, Any]:
    org_id = str(getattr(args, "org_id", None) or "").strip()
    org_name = str(getattr(args, "org_name", None) or "").strip()
    if not org_id and not org_name:
        org_context = ensure_selected_org_context()
        effective_org_id = org_id_from_context(org_context)
        return {
            "client": create_client(org_id=effective_org_id),
            "org_context": org_context,
        }

    accessible_orgs = list_accessible_orgs()
    if org_id:
        matches = [
            item
            for item in accessible_orgs
            if str(item.get("id") or "").strip() == org_id
        ]
    else:
        matches = _exact_first_filter(
            [item for item in accessible_orgs if isinstance(item, dict)],
            org_name,
            "name",
        )
    if not matches:
        raise CLIError(
            "Organization %s is not accessible in the current environment."
            % (org_id or org_name),
            payload={
                "org_id": org_id or None,
                "org_name": org_name or None,
                "candidate_orgs": accessible_orgs,
            },
        )
    if len(matches) > 1:
        raise CLIError(
            "Multiple organizations matched the provided identifier.",
            payload={
                "org_id": org_id or None,
                "org_name": org_name or None,
                "candidate_orgs": matches[:10],
            },
        )
    org_context = _build_connection_org_context(dict(matches[0]), accessible_orgs)
    effective_org_id = str(
        (org_context.get("effective_org") or {}).get("id") or ""
    ).strip()
    return {
        "client": create_client(org_id=effective_org_id),
        "org_context": org_context,
    }


def _connection_asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": asset.get("id"),
        "name": asset.get("name"),
        "address": asset.get("address"),
        "platform": asset.get("platform"),
        "org_id": asset.get("org_id"),
        "org_name": asset.get("org_name"),
    }


def _account_has_secret(account: dict[str, Any]) -> bool:
    value = account.get("has_secret")
    return value is True or value == 1 or str(value or "").strip().lower() == "true"


def _connection_account_summary(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": account.get("id"),
        "alias": account.get("alias"),
        "name": account.get("name"),
        "username": account.get("username"),
        "has_secret": _account_has_secret(account),
        "secret_type": account.get("secret_type"),
        "actions": account.get("actions") or [],
        "date_expired": account.get("date_expired"),
    }


def _select_connection_asset(
    assets: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if args.asset_id:
        selector_name = "asset_id"
        selector_value = str(args.asset_id).strip()
        matches = [
            item
            for item in assets
            if str(item.get("id") or "").strip() == selector_value
        ]
    elif args.asset_address:
        selector_name = "asset_address"
        selector_value = str(args.asset_address).strip()
        matches = [
            item
            for item in assets
            if str(item.get("address") or "").strip() == selector_value
        ]
    else:
        selector_name = "asset_name"
        selector_value = str(args.asset_name).strip()
        wanted = selector_value.casefold()
        matches = [
            item
            for item in assets
            if str(item.get("name") or "").strip().casefold() == wanted
        ]

    if len(matches) != 1:
        raise CLIError(
            "Connection asset could not be resolved uniquely.",
            payload=build_cli_guidance_payload(
                CONNECTION_ASSET_SELECTION_REASON_CODE,
                user_message=(
                    "当前身份在生效组织内没有唯一匹配到目标资产，请补充精确资产 ID、名称或地址。"
                    if not matches
                    else "当前身份匹配到多个目标资产，请改用唯一资产 ID。"
                ),
                action_hint="先确认 effective_org，再从 candidates 中选择唯一资产后重试。",
                selector={selector_name: selector_value},
                candidates=[
                    _connection_asset_summary(item) for item in matches[:10]
                ],
                candidate_count=len(matches),
            ),
        )
    return matches[0]


def _select_connection_protocol(
    protocols: list[Any],
    requested: str,
) -> dict[str, Any]:
    wanted = str(requested or "ssh").strip().casefold()
    matches = []
    for item in protocols:
        if isinstance(item, dict):
            value = str(item.get("name") or item.get("value") or "").strip()
            protocol = dict(item)
        else:
            value = str(item or "").strip()
            protocol = {"name": value}
        if value.casefold() == wanted:
            matches.append(protocol)
    if len(matches) != 1:
        raise CLIError(
            "Requested connection protocol is not available.",
            payload=build_cli_guidance_payload(
                CONNECTION_PROTOCOL_UNAVAILABLE_REASON_CODE,
                user_message="当前身份对目标资产没有可用的 SSH 协议权限。",
                action_hint="请检查资产平台协议和当前用户的有效授权。",
                requested_protocol=requested,
                permed_protocols=protocols,
            ),
        )
    return matches[0]


def _select_connection_account(
    accounts: list[dict[str, Any]],
    requested: str | None,
) -> dict[str, Any]:
    eligible = [
        item
        for item in accounts
        if isinstance(item, dict) and _account_has_secret(item)
    ]
    requested_value = str(requested or "").strip()
    if requested_value:
        wanted = requested_value.casefold()
        matches = []
        for item in eligible:
            values = {
                str(item.get(field) or "").strip().casefold()
                for field in ("id", "alias", "name", "username")
            }
            if wanted in values:
                matches.append(item)
    else:
        matches = eligible

    if len(matches) != 1:
        raise CLIError(
            "Connection account could not be resolved uniquely.",
            payload=build_cli_guidance_payload(
                CONNECTION_ACCOUNT_SELECTION_REASON_CODE,
                user_message=(
                    "当前资产没有可直接使用的托管凭据账号。"
                    if not eligible
                    else "目标资产存在多个可用账号，请使用 `--account` 指定账号 alias、名称、用户名或 ID。"
                ),
                action_hint="从 permed_accounts 中选择一个 `has_secret=true` 的账号后重试。",
                requested_account=requested_value or None,
                permed_accounts=[
                    _connection_account_summary(item)
                    for item in accounts
                    if isinstance(item, dict)
                ],
                candidate_count=len(matches),
            ),
        )
    return matches[0]


def _select_connection_method(client: Any, protocol: str) -> str:
    payload = client.get(CONNECTION_METHODS_PATH, params={"os": "linux"})
    methods = payload.get(protocol, []) if isinstance(payload, dict) else []
    allowed = {
        str(item.get("value") or "").strip()
        for item in methods
        if isinstance(item, dict) and str(item.get("value") or "").strip()
    }
    for candidate in ("ssh_guide", "ssh_client"):
        if candidate in allowed:
            return candidate
    raise CLIError(
        "No permitted SSH connection method is available.",
        payload=build_cli_guidance_payload(
            CONNECTION_METHOD_UNAVAILABLE_REASON_CODE,
            user_message="当前用户没有可用的 SSH 向导或 SSH 客户端连接方式。",
            action_hint="请检查 KoKo SSH 服务状态、终端组件配置和连接方式 ACL。",
            protocol=protocol,
            connect_methods=methods,
        ),
    )


def _decode_connection_client_url(payload: Any) -> dict[str, Any]:
    raw_url = str(payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not raw_url.startswith("jms://"):
        raise CLIError(
            "JumpServer client-url response did not include a valid jms URL.",
            payload=build_cli_guidance_payload(
                CONNECTION_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 未返回有效的 SSH 客户端连接信息。",
                action_hint="检查连接方式、KoKo 状态和当前 JumpServer 版本兼容性。",
                payload_type=type(payload).__name__,
            ),
        )
    try:
        decoded = base64.b64decode(raw_url[6:], validate=True).decode("utf-8")
        connection_data = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CLIError(
            "Unable to decode JumpServer client-url response.",
            payload=build_cli_guidance_payload(
                CONNECTION_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的 SSH 客户端连接信息无法解码。",
                action_hint="检查 JumpServer API 版本和 client-url 返回格式。",
            ),
        ) from exc
    if not isinstance(connection_data, dict):
        raise CLIError(
            "JumpServer client-url payload must decode to an object.",
            payload=build_cli_guidance_payload(
                CONNECTION_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的 SSH 客户端连接信息结构无效。",
                action_hint="检查 JumpServer API 版本和 client-url 返回格式。",
            ),
        )
    return connection_data


def _connect_info(args: argparse.Namespace) -> dict[str, Any]:
    _validate_connection_asset_selector(args)
    _validate_org_override_selector(args)

    connection_scope = _resolve_connection_scope(args)
    client = connection_scope["client"]
    assets = client.list_paginated(
        CONNECTION_SELF_ASSETS_PATH,
        params={"limit": DEFAULT_PAGE_SIZE},
    )
    if not isinstance(assets, list):
        raise CLIError(
            "Current-user effective asset API returned an unexpected payload.",
            payload={"payload_type": type(assets).__name__},
        )
    asset = _select_connection_asset(
        [item for item in assets if isinstance(item, dict)],
        args,
    )
    asset_id = str(asset.get("id") or "").strip()
    detail_path = "%s%s/" % (CONNECTION_SELF_ASSETS_PATH, asset_id)
    asset_detail = client.get(detail_path)
    if not isinstance(asset_detail, dict):
        raise CLIError(
            "Current-user effective asset detail API returned an unexpected payload.",
            payload={"payload_type": type(asset_detail).__name__},
        )

    protocol = _select_connection_protocol(
        list(asset_detail.get("permed_protocols") or []),
        args.protocol,
    )
    protocol_name = str(
        protocol.get("name") or protocol.get("value") or args.protocol
    ).strip()
    account = _select_connection_account(
        [
            item
            for item in (asset_detail.get("permed_accounts") or [])
            if isinstance(item, dict)
        ],
        args.account,
    )
    account_alias = str(account.get("alias") or "").strip()
    if not account_alias:
        raise CLIError(
            "Selected JumpServer account does not include an alias.",
            payload=build_cli_guidance_payload(
                CONNECTION_ACCOUNT_SELECTION_REASON_CODE,
                user_message="已选账号缺少创建 connection token 所需的 alias。",
                action_hint="检查资产账号数据或选择其他托管凭据账号。",
                account=_connection_account_summary(account),
            ),
        )
    connect_method = _select_connection_method(client, protocol_name)

    if not args.confirm:
        raise CLIError(
            "Connection token creation requires explicit confirmation.",
            payload=build_cli_guidance_payload(
                CONNECTION_CONFIRMATION_REASON_CODE,
                user_message="即将为当前 API 身份创建一次性 JumpServer connection token。",
                action_hint="确认资产、账号和协议无误后，追加 `--confirm` 重试。",
                suggested_commands=[
                    "python3 subskills/access/scripts/jms_ssh_connect.py connect-info --asset-id <asset-id> --confirm",
                ],
                asset=_connection_asset_summary(asset_detail),
                account=_connection_account_summary(account),
                protocol=protocol_name,
                connect_method=connect_method,
                **org_context_output(connection_scope["org_context"]),
            ),
        )

    token = client.post(
        CONNECTION_TOKEN_PATH,
        json_body={
            "asset": asset_id,
            "account": account_alias,
            "protocol": protocol_name,
            "connect_method": connect_method,
            "connect_options": {},
            "is_reusable": False,
        },
    )
    if not isinstance(token, dict) or not token.get("id"):
        raise CLIError(
            "JumpServer connection-token API returned an unexpected payload."
        )
    token_id = str(token.get("id") or "").strip()
    if str(token.get("is_active", True)).strip().lower() in {
        "false",
        "0",
        "no",
        "off",
    }:
        return {
            "status": "pending",
            "reason_code": "connection_token_inactive",
            "user_message": "Connection token 已创建，但仍需完成审批或身份验证后才能连接。",
            "asset": _connection_asset_summary(asset_detail),
            "account": _connection_account_summary(account),
            "protocol": protocol_name,
            "connect_method": connect_method,
            "connection_token": {
                "id": token_id,
                "date_expired": token.get("date_expired"),
                "from_ticket": token.get("from_ticket"),
                "from_ticket_info": token.get("from_ticket_info") or {},
            },
            **org_context_output(connection_scope["org_context"]),
        }

    client_url_path = "%s%s/client-url/" % (CONNECTION_TOKEN_PATH, token_id)
    connection_data = _decode_connection_client_url(client.get(client_url_path))
    endpoint = connection_data.get("endpoint") or {}
    client_token = connection_data.get("token") or {}
    endpoint_host = (
        str(endpoint.get("host") or "").strip()
        if isinstance(endpoint, dict)
        else ""
    )
    endpoint_port = endpoint.get("port") if isinstance(endpoint, dict) else None
    effective_token_id = (
        str(client_token.get("id") or token_id).strip()
        if isinstance(client_token, dict)
        else token_id
    )
    token_value = (
        str(client_token.get("value") or token.get("value") or "")
        if isinstance(client_token, dict)
        else str(token.get("value") or "")
    )
    if (
        not endpoint_host
        or not str(endpoint_port or "").strip()
        or not effective_token_id
        or not token_value
    ):
        raise CLIError(
            "Decoded JumpServer client-url payload is missing SSH connection fields.",
            payload=build_cli_guidance_payload(
                CONNECTION_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的 SSH 连接信息缺少主机、端口、令牌 ID 或一次性密码。",
                action_hint="检查 JumpServer API 版本、KoKo 端点和 connection token 状态。",
            ),
        )

    ssh_username = "JMS-%s" % effective_token_id
    command_argv = ["ssh"]
    if str(endpoint_port) != "22":
        command_argv.extend(["-p", str(endpoint_port)])
    command_argv.append("%s@%s" % (ssh_username, endpoint_host))
    command = " ".join(shlex.quote(item) for item in command_argv)

    return {
        "status": "ready",
        "asset": _connection_asset_summary(asset_detail),
        "account": _connection_account_summary(account),
        "protocol": protocol_name,
        "connect_method": connect_method,
        "connection": {
            "host": endpoint_host,
            "port": endpoint_port,
            "username": ssh_username,
            "password": token_value,
            "command": command,
            "command_argv": command_argv,
            "expires_at": token.get("date_expired"),
            "expires_in_seconds": token.get("expire_time"),
        },
        "data_source": {
            "effective_asset_detail": detail_path,
            "connection_token": CONNECTION_TOKEN_PATH,
            "client_url": client_url_path,
        },
        **org_context_output(connection_scope["org_context"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 当前身份一次性 SSH 连接入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    connect_info = subparsers.add_parser(
        "connect-info",
        help="获取当前身份连接某资产所需的一次性 JumpServer SSH 信息。",
        description=(
            "为当前 API 身份创建一次性 connection token，并从 client-url 返回 "
            "SSH 主机、端口、用户名和临时密码。"
        ),
        formatter_class=CLIHelpFormatter,
    )
    connect_info.add_argument("--asset-id")
    connect_info.add_argument("--asset-name")
    connect_info.add_argument("--asset-address")
    connect_info.add_argument(
        "--account",
        help="账号 alias、名称、用户名或 ID；只有一个可用账号时可省略。",
    )
    connect_info.add_argument("--protocol", default="ssh", choices=["ssh"])
    connect_info.add_argument("--confirm", action="store_true")
    connect_info.add_argument("--org-id")
    connect_info.add_argument("--org-name")
    connect_info.set_defaults(func=_connect_info)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_ssh_connect.py",
            deprecated_commands=set(),
            usage_examples_by_command={},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(
        _run_cli,
        allowed_sensitive_result_paths={("connection", "password")},
    )


if __name__ == "__main__":
    raise SystemExit(main())
