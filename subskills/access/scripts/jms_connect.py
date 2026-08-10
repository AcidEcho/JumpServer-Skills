#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))
ACCESS_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(ACCESS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ACCESS_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    build_cli_guidance_payload,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)
from jms_koko_connection import (
    CONNECTION_METHODS_PATH,
    CONNECTION_METHOD_UNAVAILABLE_REASON_CODE,
    CONNECTION_TOKEN_PATH,
    DATABASE_PROTOCOL_CHOICES,
    KOKO_SMART_ENDPOINT_PATH,
    account_summary,
    asset_summary,
    create_one_time_connection,
    normalize_database_protocol,
    resolve_connection_target,
    resolve_koko_ssh_endpoint,
)
from jms_ssh_connect import _resolve_connection_scope


CONNECTION_CONFIRMATION_REASON_CODE = "multi_protocol_connection_confirmation_required"
CONNECTION_ENDPOINT_INVALID_REASON_CODE = "multi_protocol_connection_endpoint_invalid"


def _connect_info(args: argparse.Namespace) -> dict[str, Any]:
    requested_protocol = str(args.protocol or "").strip()
    protocol = (
        "ssh"
        if requested_protocol.casefold() == "ssh"
        else normalize_database_protocol(requested_protocol)
    )
    target = resolve_connection_target(
        args,
        requested_protocol=protocol,
        scope_resolver=_resolve_connection_scope,
    )
    if not args.confirm:
        raise CLIError(
            "Connection token creation requires explicit confirmation.",
            payload=build_cli_guidance_payload(
                CONNECTION_CONFIRMATION_REASON_CODE,
                user_message="即将为当前 API 身份创建不可复用的一次性连接 token。",
                action_hint="确认资产、账号和协议无误后，追加 `--confirm` 重试。",
                asset=asset_summary(target),
                account=account_summary(target),
                protocol=target.protocol,
                connect_method=target.connect_method,
                **org_context_output(target.org_context),
            ),
        )

    asset_id = str(target.asset_detail.get("id") or target.asset.get("id") or "").strip()
    koko_endpoint = None
    if target.protocol != "ssh":
        koko_endpoint = resolve_koko_ssh_endpoint(target.client, asset_id)
    one_time = create_one_time_connection(target)
    if one_time["status"] == "pending":
        token = one_time["token"]
        return {
            "status": "pending",
            "reason_code": "connection_token_inactive",
            "user_message": "Connection token 已创建，但仍需完成审批或身份验证后才能连接。",
            "asset": asset_summary(target),
            "account": account_summary(target),
            "protocol": target.protocol,
            "connect_method": target.connect_method,
            "connection_token": {
                "id": one_time["token_id"],
                "date_expired": token.get("date_expired"),
                "from_ticket": token.get("from_ticket"),
                "from_ticket_info": token.get("from_ticket_info") or {},
            },
            **org_context_output(target.org_context),
        }

    if target.protocol == "ssh":
        endpoint = one_time["connection_data"].get("endpoint") or {}
        host = str(endpoint.get("host") or "").strip() if isinstance(endpoint, dict) else ""
        raw_port = endpoint.get("port") if isinstance(endpoint, dict) else None
        try:
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise CLIError(
                "JumpServer client-url returned an invalid SSH endpoint.",
                payload={"reason_code": CONNECTION_ENDPOINT_INVALID_REASON_CODE},
            ) from exc
        if not host or not 1 <= port <= 65535:
            raise CLIError(
                "JumpServer client-url returned an invalid SSH endpoint.",
                payload={"reason_code": CONNECTION_ENDPOINT_INVALID_REASON_CODE},
            )
        endpoint_source = one_time["client_url_path"]
    else:
        host = koko_endpoint["host"]
        port = koko_endpoint["port"]
        endpoint_source = KOKO_SMART_ENDPOINT_PATH

    username = "JMS-%s" % one_time["token_id"]
    command_argv = ["ssh"]
    if port != 22:
        command_argv.extend(["-p", str(port)])
    command_argv.append("%s@%s" % (username, host))
    return {
        "status": "ready",
        "asset": asset_summary(target),
        "account": account_summary(target),
        "protocol": target.protocol,
        "connect_method": target.connect_method,
        "connection": {
            "host": host,
            "port": port,
            "username": username,
            "password": one_time["password"],
            "command": " ".join(shlex.quote(item) for item in command_argv),
            "command_argv": command_argv,
            "expires_at": one_time["token"].get("date_expired"),
            "expires_in_seconds": one_time["token"].get("expire_time"),
        },
        "data_source": {
            "effective_asset_detail": target.detail_path,
            "endpoint": endpoint_source,
            "connection_token": CONNECTION_TOKEN_PATH,
            "client_url": one_time["client_url_path"],
        },
        **org_context_output(target.org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 当前身份多协议一次性连接入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    connect_info = subparsers.add_parser(
        "connect-info",
        help="获取 SSH 或 KoKo 数据库终端的一次性连接信息。",
        formatter_class=CLIHelpFormatter,
    )
    connect_info.add_argument("--asset-id")
    connect_info.add_argument("--asset-name")
    connect_info.add_argument("--asset-address")
    connect_info.add_argument("--account")
    connect_info.add_argument(
        "--protocol",
        required=True,
        choices=("ssh", *DATABASE_PROTOCOL_CHOICES),
    )
    connect_info.add_argument("--confirm", action="store_true")
    connect_info.add_argument("--org-id")
    connect_info.add_argument("--org-name")
    connect_info.set_defaults(func=_connect_info)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_connect.py",
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
