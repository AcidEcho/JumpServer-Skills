#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jumpserver_common.jms_runtime import (
    CLIError,
    DEFAULT_PAGE_SIZE,
    build_cli_guidance_payload,
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
    _select_connection_method,
    _select_connection_protocol,
    _validate_connection_asset_selector,
    _validate_org_override_selector,
)


DATABASE_PROTOCOLS = (
    "postgresql",
    "redis",
    "mongodb",
    "sqlserver",
    "oracle",
    "clickhouse",
)
DATABASE_PROTOCOL_ALIASES = {
    "serversql": "sqlserver",
    "server-sql": "sqlserver",
    "mssql": "sqlserver",
}
DATABASE_PROTOCOL_CHOICES = (*DATABASE_PROTOCOLS, *DATABASE_PROTOCOL_ALIASES)
DATABASE_CONNECTION_METHOD = "db_client"
CLICKHOUSE_CONNECTION_METHOD = "web_cli"
KOKO_SMART_ENDPOINT_PATH = "/api/v1/terminal/endpoints/smart/"

CONNECTION_METHOD_UNAVAILABLE_REASON_CODE = "koko_connection_method_unavailable"
CONNECTION_PROTOCOL_UNAVAILABLE_REASON_CODE = "koko_connection_protocol_unavailable"
CONNECTION_ACCOUNT_SELECTION_REASON_CODE = "koko_connection_account_selection_required"
CONNECTION_CLIENT_URL_INVALID_REASON_CODE = "koko_connection_client_url_invalid"
KOKO_SSH_ENDPOINT_INVALID_REASON_CODE = "koko_ssh_endpoint_invalid"
DATABASE_ASSET_SELECTION_REASON_CODE = "koko_database_asset_selection_required"


@dataclass(frozen=True)
class ConnectionTarget:
    client: Any
    org_context: dict[str, Any]
    asset: dict[str, Any]
    asset_detail: dict[str, Any]
    detail_path: str
    protocol: str
    account: dict[str, Any]
    account_alias: str
    connect_method: str


def normalize_database_protocol(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    return DATABASE_PROTOCOL_ALIASES.get(normalized, normalized)


def _protocol_value(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("value") or "").strip()
    return str(item or "").strip()


def _select_database_protocol(protocols: list[Any], requested: str) -> dict[str, Any]:
    normalized = normalize_database_protocol(requested)
    if normalized not in DATABASE_PROTOCOLS:
        raise CLIError(
            "Requested database protocol is not supported.",
            payload=build_cli_guidance_payload(
                CONNECTION_PROTOCOL_UNAVAILABLE_REASON_CODE,
                user_message="当前入口不支持所选数据库协议。",
                action_hint="请选择 PostgreSQL、Redis、MongoDB、SQL Server、Oracle 或 ClickHouse。",
                requested_protocol=requested,
                normalized_protocol=normalized or None,
                supported_protocols=list(DATABASE_PROTOCOLS),
                permed_protocols=protocols,
            ),
        )
    matches = [
        item
        for item in protocols
        if _protocol_value(item).casefold() == normalized
    ]
    if len(matches) != 1:
        raise CLIError(
            "Requested database protocol is not available on the selected asset.",
            payload=build_cli_guidance_payload(
                CONNECTION_PROTOCOL_UNAVAILABLE_REASON_CODE,
                user_message="当前身份对目标资产没有所选数据库协议权限。",
                action_hint="检查资产平台协议和当前用户的有效授权；不会猜测或替换资产协议。",
                requested_protocol=requested,
                normalized_protocol=normalized,
                permed_protocols=protocols,
            ),
        )
    selected = matches[0]
    if isinstance(selected, dict):
        return dict(selected)
    return {"name": _protocol_value(selected)}


def _select_database_connection_method(client: Any, protocol: str) -> str:
    payload = client.get(CONNECTION_METHODS_PATH, params={"os": "linux"})
    methods = payload.get(protocol, []) if isinstance(payload, dict) else []
    required_method = (
        CLICKHOUSE_CONNECTION_METHOD
        if protocol == "clickhouse"
        else DATABASE_CONNECTION_METHOD
    )
    method_values = [
        str(item.get("value") or "").strip()
        for item in methods
        if isinstance(item, dict)
    ]
    if method_values.count(required_method) == 1:
        return required_method
    raise CLIError(
        "No permitted database connection method is available.",
        payload=build_cli_guidance_payload(
            CONNECTION_METHOD_UNAVAILABLE_REASON_CODE,
            user_message="当前用户没有该协议允许的数据库连接方式。",
            action_hint="检查数据库协议、终端组件配置和连接方式 ACL。",
            protocol=protocol,
            requested_method=required_method,
            connect_methods=methods,
        ),
    )


def resolve_connection_target(
    args: Any,
    *,
    requested_protocol: str,
    scope_resolver: Any = None,
) -> ConnectionTarget:
    _validate_connection_asset_selector(args)
    _validate_org_override_selector(args)
    connection_scope = (scope_resolver or _resolve_connection_scope)(args)
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

    requested = str(requested_protocol or "").strip()
    if requested.casefold() == "ssh":
        selected_protocol = _select_connection_protocol(
            list(asset_detail.get("permed_protocols") or []),
            "ssh",
        )
        protocol = _protocol_value(selected_protocol)
        connect_method = _select_connection_method(client, protocol)
    else:
        category = asset_detail.get("category") or {}
        category_value = (
            str(category.get("value") or "").strip()
            if isinstance(category, dict)
            else str(category).strip()
        )
        if category_value not in {"database", ""}:
            raise CLIError(
                "Selected asset is not a database asset.",
                payload=build_cli_guidance_payload(
                    DATABASE_ASSET_SELECTION_REASON_CODE,
                    user_message="所选资产不是数据库资产。",
                    action_hint="请选择当前身份有权访问的唯一数据库资产。",
                    asset=_connection_asset_summary(asset_detail),
                ),
            )
        selected_protocol = _select_database_protocol(
            list(asset_detail.get("permed_protocols") or []),
            requested,
        )
        protocol = _protocol_value(selected_protocol)
        connect_method = _select_database_connection_method(client, protocol)

    account = _select_connection_account(
        [
            item
            for item in (asset_detail.get("permed_accounts") or [])
            if isinstance(item, dict)
        ],
        getattr(args, "account", None),
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
    return ConnectionTarget(
        client=client,
        org_context=connection_scope["org_context"],
        asset=asset,
        asset_detail=asset_detail,
        detail_path=detail_path,
        protocol=protocol,
        account=account,
        account_alias=account_alias,
        connect_method=connect_method,
    )


def resolve_koko_ssh_endpoint(client: Any, asset_id: str) -> dict[str, Any]:
    payload = client.get(
        KOKO_SMART_ENDPOINT_PATH,
        params={"asset_id": asset_id, "protocol": "ssh"},
    )
    host = str(payload.get("host") or "").strip() if isinstance(payload, dict) else ""
    raw_port = payload.get("ssh_port") if isinstance(payload, dict) else None
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise CLIError(
            "JumpServer SSH Smart Endpoint returned an invalid port.",
            payload=build_cli_guidance_payload(
                KOKO_SSH_ENDPOINT_INVALID_REASON_CODE,
                user_message="JumpServer 返回的 KoKo SSH 端口无效。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint 配置和终端组件状态。",
                asset_id=asset_id,
                endpoint_path=KOKO_SMART_ENDPOINT_PATH,
            ),
        ) from exc
    if not host or not 1 <= port <= 65535:
        raise CLIError(
            "JumpServer SSH Smart Endpoint is missing a valid host or port.",
            payload=build_cli_guidance_payload(
                KOKO_SSH_ENDPOINT_INVALID_REASON_CODE,
                user_message="JumpServer 未返回有效的 KoKo SSH 主机或端口。",
                action_hint="检查 KoKo SSH 服务、Smart Endpoint 配置和终端组件状态。",
                asset_id=asset_id,
                endpoint_path=KOKO_SMART_ENDPOINT_PATH,
            ),
        )
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "host": host,
        "port": port,
    }


def create_one_time_connection(target: ConnectionTarget) -> dict[str, Any]:
    token = target.client.post(
        CONNECTION_TOKEN_PATH,
        json_body={
            "asset": str(target.asset_detail.get("id") or target.asset.get("id") or "").strip(),
            "account": target.account_alias,
            "protocol": target.protocol,
            "connect_method": target.connect_method,
            "connect_options": {},
            "is_reusable": False,
        },
    )
    if not isinstance(token, dict) or not token.get("id"):
        raise CLIError("JumpServer connection-token API returned an unexpected payload.")
    token_id = str(token.get("id") or "").strip()
    if str(token.get("is_active", True)).strip().lower() in {
        "false",
        "0",
        "no",
        "off",
    }:
        return {"status": "pending", "token": token, "token_id": token_id}

    client_url_path = "%s%s/client-url/" % (CONNECTION_TOKEN_PATH, token_id)
    try:
        connection_data = _decode_connection_client_url(
            target.client.get(client_url_path)
        )
    except CLIError as exc:
        payload = dict(exc.payload)
        payload["reason_code"] = CONNECTION_CLIENT_URL_INVALID_REASON_CODE
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
            "Decoded JumpServer client-url payload is missing token fields.",
            payload=build_cli_guidance_payload(
                CONNECTION_CLIENT_URL_INVALID_REASON_CODE,
                user_message="JumpServer 返回的连接信息缺少令牌 ID 或一次性密码。",
                action_hint="检查 JumpServer API 版本和 connection token 状态。",
            ),
        )
    return {
        "status": "ready",
        "token": token,
        "token_id": effective_token_id,
        "password": token_value,
        "connection_data": connection_data,
        "client_url_path": client_url_path,
    }


def asset_summary(target: ConnectionTarget) -> dict[str, Any]:
    return _connection_asset_summary(target.asset_detail)


def account_summary(target: ConnectionTarget) -> dict[str, Any]:
    return _connection_account_summary(target.account)
