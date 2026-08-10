#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

import paramiko

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
    CONNECTION_TOKEN_PATH,
    account_summary,
    asset_summary,
    create_one_time_connection,
    resolve_connection_target,
)
from jms_ssh_connect import _resolve_connection_scope


SSH_EXEC_CONFIRMATION_REASON_CODE = "ssh_exec_confirmation_required"
SSH_EXEC_CONNECTION_FAILED_REASON_CODE = "ssh_exec_connection_failed"
SSH_EXEC_ENDPOINT_INVALID_REASON_CODE = "ssh_exec_endpoint_invalid"


def _execute_ssh_commands(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    commands: list[str],
    connect_timeout: float,
    command_timeout: float,
) -> list[dict[str, Any]]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=connect_timeout,
            allow_agent=False,
            look_for_keys=False,
            auth_timeout=connect_timeout,
            banner_timeout=connect_timeout,
        )
        results = []
        for command in commands:
            _, stdout, stderr = ssh.exec_command(command, timeout=command_timeout)
            stdout_value = stdout.read().decode("utf-8", errors="replace")
            stderr_value = stderr.read().decode("utf-8", errors="replace")
            results.append(
                {
                    "command": command,
                    "stdout": stdout_value,
                    "stderr": stderr_value,
                    "exit_status": stdout.channel.recv_exit_status(),
                }
            )
        return results
    except Exception as exc:
        raise CLIError(
            "Unable to execute commands through the JumpServer SSH terminal.",
            payload=build_cli_guidance_payload(
                SSH_EXEC_CONNECTION_FAILED_REASON_CODE,
                user_message="无法通过 JumpServer SSH 终端执行命令。",
                action_hint="检查 KoKo SSH 服务、网络可达性和目标账号权限。",
                endpoint={"host": host, "port": port},
                error_type=type(exc).__name__,
            ),
        ) from exc
    finally:
        ssh.close()


def _ssh_exec(args: argparse.Namespace) -> dict[str, Any]:
    commands = [str(item) for item in (args.command_values or [])]
    target = resolve_connection_target(
        args,
        requested_protocol="ssh",
        scope_resolver=_resolve_connection_scope,
    )
    if not args.confirm:
        raise CLIError(
            "SSH command execution requires explicit confirmation.",
            payload=build_cli_guidance_payload(
                SSH_EXEC_CONFIRMATION_REASON_CODE,
                user_message="即将为当前 API 身份创建一次性 SSH token 并执行远程命令。",
                action_hint="确认资产、账号和命令无误后，追加 `--confirm` 重试。",
                commands=commands,
                asset=asset_summary(target),
                account=account_summary(target),
                protocol=target.protocol,
                connect_method=target.connect_method,
                **org_context_output(target.org_context),
            ),
        )
    one_time = create_one_time_connection(target)
    if one_time["status"] == "pending":
        token = one_time["token"]
        return {
            "status": "pending",
            "reason_code": "ssh_connection_token_inactive",
            "user_message": "SSH connection token 已创建，但仍需完成审批或身份验证。",
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
    endpoint = one_time["connection_data"].get("endpoint") or {}
    host = str(endpoint.get("host") or "").strip() if isinstance(endpoint, dict) else ""
    raw_port = endpoint.get("port") if isinstance(endpoint, dict) else None
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise CLIError(
            "JumpServer client-url returned an invalid SSH endpoint.",
            payload={"reason_code": SSH_EXEC_ENDPOINT_INVALID_REASON_CODE},
        ) from exc
    if not host or not 1 <= port <= 65535:
        raise CLIError(
            "JumpServer client-url returned an invalid SSH endpoint.",
            payload={"reason_code": SSH_EXEC_ENDPOINT_INVALID_REASON_CODE},
        )
    username = "JMS-%s" % one_time["token_id"]
    results = _execute_ssh_commands(
        host=host,
        port=port,
        username=username,
        password=one_time["password"],
        commands=commands,
        connect_timeout=float(args.connect_timeout),
        command_timeout=float(args.command_timeout),
    )
    return {
        "status": "completed",
        "results": results,
        "asset": asset_summary(target),
        "account": account_summary(target),
        "protocol": target.protocol,
        "connect_method": target.connect_method,
        "connection": {
            "host": host,
            "port": port,
            "username": username,
            "expires_at": one_time["token"].get("date_expired"),
            "expires_in_seconds": one_time["token"].get("expire_time"),
        },
        "data_source": {
            "effective_asset_detail": target.detail_path,
            "connection_token": CONNECTION_TOKEN_PATH,
            "client_url": one_time["client_url_path"],
        },
        **org_context_output(target.org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 当前身份一次性 SSH 命令执行入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser(
        "ssh-exec",
        help="在单个一次性 SSH 连接中按顺序执行命令。",
        formatter_class=CLIHelpFormatter,
    )
    execute.add_argument("--asset-id")
    execute.add_argument("--asset-name")
    execute.add_argument("--asset-address")
    execute.add_argument("--account")
    execute.add_argument(
        "--command",
        dest="command_values",
        action="append",
        required=True,
        help="远程命令；可重复传入并在同一个 SSH 连接中按顺序执行。",
    )
    execute.add_argument("--confirm", action="store_true")
    execute.add_argument("--org-id")
    execute.add_argument("--org-name")
    execute.add_argument("--connect-timeout", type=float, default=20.0)
    execute.add_argument("--command-timeout", type=float, default=30.0)
    execute.set_defaults(func=_ssh_exec)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_ssh_exec.py",
            deprecated_commands=set(),
            usage_examples_by_command={},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
