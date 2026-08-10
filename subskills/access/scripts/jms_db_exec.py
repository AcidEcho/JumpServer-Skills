#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
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
from jms_db_connect import _clean_terminal_output
from jms_koko_connection import (
    CONNECTION_METHODS_PATH,
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


DATABASE_EXEC_CONFIRMATION_REASON_CODE = "database_exec_confirmation_required"
DATABASE_EXEC_CONNECTION_FAILED_REASON_CODE = "database_exec_connection_failed"
DATABASE_TERMINAL_REPORTED_ERROR_REASON_CODE = "database_terminal_reported_error"
DATABASE_TERMINAL_EMPTY_OUTPUT_REASON_CODE = "database_terminal_empty_output"


def _normalize_newlines(value: str) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _frame_command(protocol: str, command: str) -> str:
    normalized_protocol = normalize_database_protocol(protocol)
    value = _normalize_newlines(command)
    if normalized_protocol == "sqlserver":
        lines = value.splitlines()
        if not lines or lines[-1].strip().casefold() != "go":
            lines.append("GO")
        value = "\n".join(lines)
    elif normalized_protocol == "oracle":
        if value and not value.rstrip().endswith((";", "/")):
            value += ";"
    return value.replace("\n", "\r\n") + "\r\n"


def _exit_command(protocol: str) -> str:
    commands = {
        "postgresql": "\\q",
        "redis": "quit",
        "mongodb": "quit()",
        "sqlserver": "EXIT",
        "oracle": "exit",
        "clickhouse": "exit",
    }
    return commands[normalize_database_protocol(protocol)] + "\r\n"


def _read_channel(channel: Any, *, timeout: float, idle_timeout: float) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + timeout
    last_data = None
    while time.monotonic() < deadline:
        try:
            if channel.recv_ready():
                chunk = channel.recv(65536)
                if not chunk:
                    break
                output.extend(chunk)
                last_data = time.monotonic()
                continue
        except Exception:
            pass
        if last_data is not None and time.monotonic() - last_data >= idle_timeout:
            break
        time.sleep(0.05)
    return bytes(output)


def _clean_database_output(output: bytes, *, command: str, protocol: str) -> str:
    value = _clean_terminal_output(output, sql=command)
    lines = value.splitlines()
    normalized_protocol = normalize_database_protocol(protocol)

    def is_prompt(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) > 512:
            return False
        folded = stripped.casefold()
        if normalized_protocol == "redis":
            return "redis" in folded and folded.endswith(">")
        if normalized_protocol == "mongodb":
            return folded == "mongosh" or folded.endswith(">")
        if normalized_protocol == "sqlserver":
            return folded.endswith(">") and folded[:-1].strip().isdigit()
        if normalized_protocol == "oracle":
            return folded == "sql>"
        if normalized_protocol == "clickhouse":
            return folded.endswith(":)")
        return False

    while lines and (
        not lines[-1].strip()
        or is_prompt(lines[-1])
    ):
        lines.pop()
    def is_redraw_ticker(text: str) -> bool:
        return (
            len(text) > 32
            and text.count(".") >= 10
            and all(character.isdigit() or character == "." for character in text)
        )

    while lines and is_redraw_ticker(lines[0].strip()):
        lines.pop(0)
    cleaned = "\n".join(lines).strip()
    if is_redraw_ticker(cleaned):
        return ""
    return cleaned


def _terminal_reported_error(value: str) -> bool:
    folded = value.casefold()
    markers = (
        "connection refused",
        "failed to connect",
        "unable to connect",
        "连接拒绝",
        "网络不通",
    )
    return ("开始连接数据库" in value and "error:" in folded) or any(
        marker in folded for marker in markers
    )


def _execute_database_commands(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    protocol: str,
    commands: list[str],
    connect_timeout: float,
    read_timeout: float,
    idle_timeout: float,
    require_output: bool = False,
) -> list[dict[str, str]]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connection_stage = "authenticate"
    terminal_banner = ""
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
        connection_stage = "open_terminal"
        channel = ssh.invoke_shell()
        channel.settimeout(4)
        connection_stage = "read_banner"
        terminal_banner = _clean_terminal_output(
            _read_channel(
                channel,
                timeout=min(connect_timeout, 2.0),
                idle_timeout=max(1.0, idle_timeout),
            ),
            sql="",
        )
        if _terminal_reported_error(terminal_banner):
            raise CLIError(
                "JumpServer database terminal reported a connection error.",
                payload=build_cli_guidance_payload(
                    DATABASE_TERMINAL_REPORTED_ERROR_REASON_CODE,
                    user_message="KoKo 已认证，但数据库终端报告目标数据库连接失败。",
                    action_hint="检查数据库服务监听、网络可达性、资产地址和托管账号。",
                    protocol=protocol,
                    terminal_output=terminal_banner,
                ),
            )
        results = []
        for command in commands:
            connection_stage = "execute_command"
            channel.send(_frame_command(protocol, command))
            output = _read_channel(
                channel,
                timeout=read_timeout,
                idle_timeout=idle_timeout,
            )
            cleaned_output = _clean_database_output(
                output,
                command=command,
                protocol=protocol,
            )
            if require_output and not cleaned_output:
                raise CLIError(
                    "JumpServer database terminal returned no command output.",
                    payload=build_cli_guidance_payload(
                        DATABASE_TERMINAL_EMPTY_OUTPUT_REASON_CODE,
                        user_message="数据库终端未返回可验证的探针结果。",
                        action_hint="检查数据库服务、网络可达性和终端启动状态后重试。",
                        protocol=protocol,
                    ),
                )
            if _terminal_reported_error(cleaned_output):
                raise CLIError(
                    "JumpServer database terminal reported a connection error.",
                    payload=build_cli_guidance_payload(
                        DATABASE_TERMINAL_REPORTED_ERROR_REASON_CODE,
                        user_message="KoKo 已认证，但数据库终端报告目标数据库连接失败。",
                        action_hint="检查数据库服务监听、网络可达性、资产地址和托管账号。",
                        protocol=protocol,
                        terminal_output=cleaned_output,
                    ),
                )
            results.append({"command": command, "output": cleaned_output})
        try:
            channel.send(_exit_command(protocol))
        except Exception:
            pass
        return results
    except CLIError:
        raise
    except Exception as exc:
        raise CLIError(
            "Unable to execute commands through the JumpServer database terminal.",
            payload=build_cli_guidance_payload(
                DATABASE_EXEC_CONNECTION_FAILED_REASON_CODE,
                user_message="无法通过 JumpServer 数据库终端执行命令。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint、网络可达性和数据库权限。",
                protocol=protocol,
                endpoint={"host": host, "port": port},
                error_type=type(exc).__name__,
                error_message=str(exc),
                connection_stage=connection_stage,
                terminal_banner=terminal_banner[-2000:] or None,
            ),
        ) from exc
    finally:
        ssh.close()


def _database_exec(args: argparse.Namespace) -> dict[str, Any]:
    protocol = normalize_database_protocol(args.protocol)
    commands = [str(item) for item in (args.command_values or [])]
    target = resolve_connection_target(
        args,
        requested_protocol=protocol,
        scope_resolver=_resolve_connection_scope,
    )
    if not args.confirm:
        raise CLIError(
            "Database command execution requires explicit confirmation.",
            payload=build_cli_guidance_payload(
                DATABASE_EXEC_CONFIRMATION_REASON_CODE,
                user_message="即将创建不可复用的一次性数据库 token，并通过 KoKo SSH 终端执行命令。",
                action_hint="确认资产、账号、协议和命令无误后，追加 `--confirm` 重试。",
                commands=commands,
                asset=asset_summary(target),
                account=account_summary(target),
                protocol=target.protocol,
                connect_method=target.connect_method,
                **org_context_output(target.org_context),
            ),
        )
    asset_id = str(target.asset_detail.get("id") or target.asset.get("id") or "").strip()
    endpoint = resolve_koko_ssh_endpoint(target.client, asset_id)
    one_time = create_one_time_connection(target)
    if one_time["status"] == "pending":
        token = one_time["token"]
        return {
            "status": "pending",
            "reason_code": "database_connection_token_inactive",
            "user_message": "数据库 connection token 已创建，但仍需完成审批或身份验证。",
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
    username = "JMS-%s" % one_time["token_id"]
    results = _execute_database_commands(
        host=endpoint["host"],
        port=endpoint["port"],
        username=username,
        password=one_time["password"],
        protocol=target.protocol,
        commands=commands,
        connect_timeout=float(args.connect_timeout),
        read_timeout=float(args.read_timeout),
        idle_timeout=float(args.idle_timeout),
        require_output=bool(args.require_output),
    )
    return {
        "status": "completed",
        "results": results,
        "asset": asset_summary(target),
        "account": account_summary(target),
        "protocol": target.protocol,
        "connect_method": target.connect_method,
        "connection": {
            "host": endpoint["host"],
            "port": endpoint["port"],
            "username": username,
            "expires_at": one_time["token"].get("date_expired"),
            "expires_in_seconds": one_time["token"].get("expire_time"),
        },
        "data_source": {
            "effective_asset_detail": target.detail_path,
            "ssh_endpoint": KOKO_SMART_ENDPOINT_PATH,
            "connection_token": CONNECTION_TOKEN_PATH,
            "client_url": one_time["client_url_path"],
        },
        **org_context_output(target.org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 当前身份 KoKo 数据库命令执行入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser(
        "db-exec",
        help="通过 KoKo SSH 数据库终端执行命令。",
        formatter_class=CLIHelpFormatter,
    )
    execute.add_argument("--asset-id")
    execute.add_argument("--asset-name")
    execute.add_argument("--asset-address")
    execute.add_argument("--account")
    execute.add_argument(
        "--protocol",
        required=True,
        choices=DATABASE_PROTOCOL_CHOICES,
    )
    execute.add_argument(
        "--command",
        dest="command_values",
        action="append",
        required=True,
        help="数据库命令或 SQL；可重复传入并在同一个 KoKo SSH 会话中顺序执行。",
    )
    execute.add_argument("--confirm", action="store_true")
    execute.add_argument("--org-id")
    execute.add_argument("--org-name")
    execute.add_argument("--connect-timeout", type=float, default=20.0)
    execute.add_argument("--read-timeout", type=float, default=15.0)
    execute.add_argument("--idle-timeout", type=float, default=2.0)
    execute.add_argument(
        "--require-output",
        action="store_true",
        help="若命令没有可验证输出则失败；适合连接探针，不适合无结果集写入语句。",
    )
    execute.set_defaults(func=_database_exec)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_db_exec.py",
            deprecated_commands=set(),
            usage_examples_by_command={},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
