#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
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
    DEFAULT_PAGE_SIZE,
    build_cli_guidance_payload,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)
from jms_ssh_connect import (
    CONNECTION_METHODS_PATH,
    CONNECTION_SELF_ASSETS_PATH,
    CONNECTION_TOKEN_PATH,
    _connection_account_summary,
    _connection_asset_summary,
    _decode_connection_client_url,
    _resolve_connection_scope,
    _select_connection_account,
    _select_connection_asset,
    _select_connection_protocol,
    _validate_connection_asset_selector,
    _validate_org_override_selector,
)


DATABASE_CONNECTION_METHOD = "db_client"
DATABASE_PROTOCOLS = ("mysql", "mariadb")
DATABASE_ASSET_SELECTION_REASON_CODE = "database_connection_asset_selection_required"
DATABASE_ACCOUNT_SELECTION_REASON_CODE = "database_connection_account_selection_required"
DATABASE_PROTOCOL_UNAVAILABLE_REASON_CODE = "database_connection_protocol_unavailable"
DATABASE_PROTOCOL_SELECTION_REQUIRED_REASON_CODE = "database_connection_protocol_selection_required"
DATABASE_METHOD_UNAVAILABLE_REASON_CODE = "database_connection_method_unavailable"
DATABASE_CONFIRMATION_REASON_CODE = "database_connection_token_confirmation_required"
DATABASE_CLIENT_URL_INVALID_REASON_CODE = "database_connection_client_url_invalid"
DATABASE_SSH_ENDPOINT_INVALID_REASON_CODE = "database_connection_ssh_endpoint_invalid"
DATABASE_CONNECTION_FAILED_REASON_CODE = "database_connection_failed"
DATABASE_SMART_ENDPOINT_PATH = "/api/v1/terminal/endpoints/smart/"


def _select_database_protocol(
    protocols: list[Any],
    requested: str | None,
    platform: Any = None,
) -> dict[str, Any]:
    requested_value = str(requested or "").strip()
    if requested_value and requested_value.casefold() not in DATABASE_PROTOCOLS:
        raise CLIError(
            "Requested database protocol is not supported.",
            payload=build_cli_guidance_payload(
                DATABASE_PROTOCOL_UNAVAILABLE_REASON_CODE,
                user_message="当前入口只支持 MySQL 或 MariaDB 数据库协议。",
                action_hint="请使用 `--protocol mysql` 或 `--protocol mariadb`。",
                requested_protocol=requested_value,
                supported_protocols=list(DATABASE_PROTOCOLS),
                permed_protocols=protocols,
            ),
        )

    available_names = []
    for item in protocols:
        if isinstance(item, dict):
            value = str(item.get("name") or item.get("value") or "").strip()
        else:
            value = str(item or "").strip()
        normalized = value.casefold()
        if normalized in DATABASE_PROTOCOLS and normalized not in available_names:
            available_names.append(normalized)

    if not requested_value:
        if not available_names:
            raise CLIError(
                "No supported database protocol is available.",
                payload=build_cli_guidance_payload(
                    DATABASE_PROTOCOL_UNAVAILABLE_REASON_CODE,
                    user_message="当前身份对目标资产没有可用的 MySQL 或 MariaDB 协议权限。",
                    action_hint="请检查资产平台协议和当前用户的有效授权。",
                    supported_protocols=list(DATABASE_PROTOCOLS),
                    permed_protocols=protocols,
                ),
            )
        if len(available_names) == 1:
            requested_value = available_names[0]
        else:
            platform_values = []
            if isinstance(platform, dict):
                for key in ("name", "slug", "value"):
                    value = platform.get(key)
                    if isinstance(value, dict):
                        value = value.get("name") or value.get("slug") or value.get("value")
                    if value:
                        platform_values.append(str(value))
            elif platform:
                platform_values.append(str(platform))
            platform_text = " ".join(platform_values).casefold()
            preferred_protocol = next(
                (
                    candidate
                    for candidate in ("mariadb", "mysql")
                    if candidate in available_names and candidate in platform_text
                ),
                None,
            )
            if preferred_protocol:
                requested_value = preferred_protocol
            else:
                raise CLIError(
                    "Multiple supported database protocols are available.",
                    payload=build_cli_guidance_payload(
                        DATABASE_PROTOCOL_SELECTION_REQUIRED_REASON_CODE,
                        user_message="目标资产存在多个可用数据库协议，且平台信息无法唯一判断。",
                        action_hint="追加 `--protocol mysql` 或 `--protocol mariadb` 后重试。",
                        supported_protocols=list(DATABASE_PROTOCOLS),
                        available_protocols=available_names,
                        platform=platform,
                        permed_protocols=protocols,
                    ),
                )

    try:
        return _select_connection_protocol(protocols, requested_value)
    except CLIError as exc:
        payload = dict(exc.payload)
        payload["reason_code"] = DATABASE_PROTOCOL_UNAVAILABLE_REASON_CODE
        payload["supported_protocols"] = list(DATABASE_PROTOCOLS)
        raise CLIError(str(exc), payload=payload) from exc


def _select_database_connection_method(client: Any, protocol: str) -> str:
    payload = client.get(CONNECTION_METHODS_PATH, params={"os": "linux"})
    methods = payload.get(protocol, []) if isinstance(payload, dict) else []
    matches = [
        item
        for item in methods
        if isinstance(item, dict) and str(item.get("value") or "").strip() == DATABASE_CONNECTION_METHOD
    ]
    if len(matches) != 1:
        raise CLIError(
            "No permitted database-client connection method is available.",
            payload=build_cli_guidance_payload(
                DATABASE_METHOD_UNAVAILABLE_REASON_CODE,
                user_message="当前用户没有可用的 MySQL/MariaDB 数据库客户端连接方式。",
                action_hint="请检查所选数据库协议、终端组件配置和连接方式 ACL。",
                protocol=protocol,
                requested_method=DATABASE_CONNECTION_METHOD,
                connect_methods=methods,
            ),
        )
    return DATABASE_CONNECTION_METHOD


def _resolve_database_ssh_endpoint(client: Any, asset_id: str) -> dict[str, Any]:
    payload = client.get(
        DATABASE_SMART_ENDPOINT_PATH,
        params={"asset_id": asset_id, "protocol": "ssh"},
    )
    host = str(payload.get("host") or "").strip() if isinstance(payload, dict) else ""
    raw_port = payload.get("ssh_port") if isinstance(payload, dict) else None
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise CLIError(
            "JumpServer SSH Smart Endpoint returned an invalid SSH service port.",
            payload=build_cli_guidance_payload(
                DATABASE_SSH_ENDPOINT_INVALID_REASON_CODE,
                user_message="JumpServer 返回的 SSH 服务端口无效。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint 配置和终端组件状态。",
                asset_id=asset_id,
                endpoint_path=DATABASE_SMART_ENDPOINT_PATH,
            ),
        ) from exc
    if not host or not 1 <= port <= 65535:
        raise CLIError(
            "JumpServer SSH Smart Endpoint is missing a valid host or SSH service port.",
            payload=build_cli_guidance_payload(
                DATABASE_SSH_ENDPOINT_INVALID_REASON_CODE,
                user_message="JumpServer 未返回有效的 KoKo SSH 服务主机或端口。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint 配置和终端组件状态。",
                asset_id=asset_id,
                endpoint_path=DATABASE_SMART_ENDPOINT_PATH,
            ),
        )
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "host": host,
        "port": port,
    }


def _read_channel(channel: Any, *, timeout: float, idle_timeout: float) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + timeout
    last_data = time.monotonic()
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
        if time.monotonic() - last_data >= idle_timeout:
            break
        time.sleep(0.05)
    return bytes(output)


def _clean_terminal_output(output: bytes, *, sql: str | None = None) -> str:
    text = re.sub(
        rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x08|\r|\x1b\[K|\x1b\[J|\x1b\[\?[0-9]*[hl]",
        b"",
        output,
    )
    text = re.sub(rb"\n\s*\n+", b"\n", text)
    value = text.decode(errors="replace")
    if sql:
        echo_index = value.rfind(sql)
        if echo_index >= 0:
            value = value[echo_index + len(sql):]
    lines = value.splitlines()
    terminal_prompt = re.compile(r"\s*(?:[A-Za-z0-9_.-]+(?:=>|>)\s*)+")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and (not lines[-1].strip() or terminal_prompt.fullmatch(lines[-1])):
        lines.pop()
    return "\n".join(lines).strip()


def _execute_database_query(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    sql: str,
    read_timeout: float,
    idle_timeout: float,
) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=20,
            allow_agent=False,
            look_for_keys=False,
            auth_timeout=20,
            banner_timeout=20,
        )
        channel = ssh.invoke_shell()
        channel.settimeout(4)
        _read_channel(channel, timeout=2.0, idle_timeout=0.5)
        channel.send(sql + "\r\n")
        output = _read_channel(
            channel,
            timeout=read_timeout,
            idle_timeout=idle_timeout,
        )
        try:
            channel.send("\\q\r\n")
        except Exception:
            pass
        return _clean_terminal_output(output, sql=sql)
    except Exception as exc:
        raise CLIError(
            "Unable to connect to the JumpServer database terminal.",
            payload=build_cli_guidance_payload(
                DATABASE_CONNECTION_FAILED_REASON_CODE,
                user_message="无法连接 JumpServer MySQL/MariaDB 数据库终端。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint 和网络可达性。",
                endpoint={"host": host, "port": port},
                error_type=type(exc).__name__,
            ),
        ) from exc
    finally:
        ssh.close()


def _database_query(args: argparse.Namespace) -> dict[str, Any]:
    _validate_connection_asset_selector(args)
    _validate_org_override_selector(args)
    sql = str(getattr(args, "sql", "") or "")
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
            "Current-user effective database asset detail API returned an unexpected payload.",
            payload={"payload_type": type(asset_detail).__name__},
        )
    category = asset_detail.get("category") or {}
    category_value = (
        str(category.get("value") or "").strip()
        if isinstance(category, dict)
        else str(category).strip()
    )
    if category_value not in {"database", ""}:
        raise CLIError(
            "Selected asset is not a database asset.",
            payload={"reason_code": DATABASE_ASSET_SELECTION_REASON_CODE, "asset": _connection_asset_summary(asset_detail)},
        )
    protocol = _select_database_protocol(
        list(asset_detail.get("permed_protocols") or []),
        args.protocol,
        asset_detail.get("platform"),
    )
    protocol_name = str(
        protocol.get("name") or protocol.get("value") or args.protocol
    ).strip()
    account = _select_connection_account(
        [item for item in (asset_detail.get("permed_accounts") or []) if isinstance(item, dict)],
        args.account,
    )
    account_alias = str(account.get("alias") or "").strip()
    if not account_alias:
        raise CLIError(
            "Selected database account does not include an alias.",
            payload={
                "reason_code": DATABASE_ACCOUNT_SELECTION_REASON_CODE,
                "account": _connection_account_summary(account),
            },
        )
    connect_method = _select_database_connection_method(client, protocol_name)
    if not args.confirm:
        raise CLIError(
            "Database connection token creation requires explicit confirmation.",
            payload=build_cli_guidance_payload(
                DATABASE_CONFIRMATION_REASON_CODE,
                user_message="即将为当前 API 身份创建一次性 MySQL/MariaDB 数据库连接 token 并执行 SQL。",
                action_hint="确认资产、账号、协议和 SQL 无误后，追加 `--confirm` 重试；SQL 权限和阻断由 JumpServer 负责。",
                suggested_commands=[
                    "python3 subskills/access/scripts/jms_db_connect.py db-query --asset-id <asset-id> --sql 'SHOW DATABASES;' --confirm",
                ],
                sql=sql,
                asset=_connection_asset_summary(asset_detail),
                account=_connection_account_summary(account),
                protocol=protocol_name,
                connect_method=connect_method,
                **org_context_output(connection_scope["org_context"]),
            ),
        )
    ssh_endpoint = _resolve_database_ssh_endpoint(client, asset_id)
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
        raise CLIError("JumpServer database connection-token API returned an unexpected payload.")
    token_id = str(token.get("id") or "").strip()
    if str(token.get("is_active", True)).strip().lower() in {"false", "0", "no", "off"}:
        return {
            "status": "pending",
            "reason_code": "database_connection_token_inactive",
            "user_message": "数据库 connection token 已创建，但仍需完成审批或身份验证后才能连接。",
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
    try:
        connection_data = _decode_connection_client_url(client.get(client_url_path))
    except CLIError as exc:
        payload = dict(exc.payload)
        payload.update(
            build_cli_guidance_payload(
                DATABASE_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的数据库 token 连接信息无效。",
                action_hint="检查 JumpServer API 版本和数据库 connection token 状态。",
            )
        )
        raise CLIError(str(exc), payload=payload) from exc
    client_token = connection_data.get("token") or {}
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
    if not effective_token_id or not token_value:
        raise CLIError(
            "Decoded JumpServer client-url payload is missing database token fields.",
            payload=build_cli_guidance_payload(
                DATABASE_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的数据库连接信息缺少令牌 ID 或一次性密码。",
                action_hint="检查 JumpServer API 版本和数据库 connection token 状态。",
            ),
        )
    connection_username = "JMS-%s" % effective_token_id
    output = _execute_database_query(
        host=ssh_endpoint["host"],
        port=ssh_endpoint["port"],
        username=connection_username,
        password=token_value,
        sql=sql,
        read_timeout=float(args.read_timeout),
        idle_timeout=float(args.idle_timeout),
    )
    return {
        "status": "completed",
        "sql": sql,
        "output": output,
        "asset": _connection_asset_summary(asset_detail),
        "account": _connection_account_summary(account),
        "protocol": protocol_name,
        "connect_method": connect_method,
        "connection": {
            "host": ssh_endpoint["host"],
            "port": ssh_endpoint["port"],
            "username": connection_username,
            "expires_at": token.get("date_expired"),
            "expires_in_seconds": token.get("expire_time"),
        },
        "data_source": {
            "effective_asset_detail": detail_path,
            "ssh_endpoint": DATABASE_SMART_ENDPOINT_PATH,
            "connection_token": CONNECTION_TOKEN_PATH,
            "client_url": client_url_path,
        },
        **org_context_output(connection_scope["org_context"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 当前身份一次性 MySQL/MariaDB SQL 执行入口。",
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    query = subparsers.add_parser(
        "db-query",
        help="通过一次性 MySQL/MariaDB db_client token 执行 SQL；SQL 权限由 JumpServer 控制。",
        formatter_class=CLIHelpFormatter,
    )
    query.add_argument("--asset-id")
    query.add_argument("--asset-name")
    query.add_argument("--asset-address")
    query.add_argument(
        "--account",
        help="账号 alias、名称、用户名或 ID；只有一个可用账号时可省略。",
    )
    query.add_argument(
        "--protocol",
        choices=DATABASE_PROTOCOLS,
        help="数据库协议；省略时从资产授权的 MySQL/MariaDB 协议中唯一选择。",
    )
    query.add_argument("--confirm", action="store_true")
    query.add_argument("--org-id")
    query.add_argument("--org-name")
    query.add_argument("--sql", required=True, help="要执行的 SQL；本地不限制语句类型、语句数量或 SQL 关键字。")
    query.add_argument("--read-timeout", type=float, default=15.0)
    query.add_argument("--idle-timeout", type=float, default=2.0)
    query.set_defaults(func=_database_query)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_db_connect.py",
            deprecated_commands=set(),
            usage_examples_by_command={},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
