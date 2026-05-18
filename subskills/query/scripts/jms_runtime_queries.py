from __future__ import annotations

"""Runtime query functions for JumpServer runtime subskill."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import hashlib
import json
import re
from typing import Any
from jumpserver_common.jms_runtime import (
    CLIError,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    ensure_selected_org_context,
    is_uuid_like,
    org_id_from_context,
    org_context_output,
    parse_bool,
)

PERMISSION_PATH = "/api/v1/perms/asset-permissions/"
ACCOUNT_TEMPLATE_PATH = "/api/v1/accounts/account-templates/"
TERMINAL_COMMANDS_PATH = "/api/v1/terminal/commands/"
TERMINAL_SESSIONS_PATH = "/api/v1/terminal/sessions/"
TERMINAL_STATUS_PATH = "/api/v1/terminal/status/"
TERMINALS_PATH = "/api/v1/terminal/terminals/"
REPLAY_STORAGES_PATH = "/api/v1/terminal/replay-storages/"
COMMAND_STORAGES_PATH = "/api/v1/terminal/command-storages/"
ENDPOINT_RULES_PATH = "/api/v1/terminal/endpoint-rules/"
ROLE_BINDINGS_PATH = "/api/v1/rbac/role-bindings/"
ORG_ROLE_BINDINGS_PATH = "/api/v1/rbac/org-role-bindings/"
SYSTEM_ROLE_BINDINGS_PATH = "/api/v1/rbac/system-role-bindings/"
ROLES_PATH = "/api/v1/rbac/roles/"
LOGIN_LOGS_PATH = "/api/v1/audits/login-logs/"
OPERATE_LOGS_PATH = "/api/v1/audits/operate-logs/"
FTP_LOGS_PATH = "/api/v1/audits/ftp-logs/"
JOB_LOGS_PATH = "/api/v1/audits/job-logs/"
PASSWORD_CHANGE_LOGS_PATH = "/api/v1/audits/password-change-logs/"
USER_SESSIONS_PATH = "/api/v1/audits/user-sessions/"
REPORT_PATHS = {
    "account-statistic": "/api/v1/reports/reports/account-statistic/",
    "account-automation": "/api/v1/reports/reports/account-automation/",
    "asset-statistic": "/api/v1/reports/reports/asset-statistic/",
    "asset-activity": "/api/v1/reports/reports/asset-activity/",
    "users": "/api/v1/reports/reports/users/",
    "user-change-password": "/api/v1/reports/reports/user-change-password/",
    "pam-dashboard": "/api/v1/accounts/pam-dashboard/",
    "change-secret-dashboard": "/api/v1/accounts/change-secret-dashboard/",
}
REPORT_TYPES_WITH_NATIVE_DAYS = {
    "account-statistic",
    "account-automation",
    "asset-statistic",
    "asset-activity",
    "users",
    "user-change-password",
    "change-secret-dashboard",
}
PAM_DASHBOARD_FLAG_FIELDS = (
    "total_long_time_no_login_accounts",
    "total_new_found_accounts",
    "total_groups_changed_accounts",
    "total_sudoers_changed_accounts",
    "total_authorized_keys_changed_accounts",
    "total_account_deleted_accounts",
    "total_password_expired_accounts",
    "total_long_time_password_accounts",
    "total_weak_password_accounts",
    "total_leaked_password_accounts",
    "total_repeated_password_accounts",
)
CHANGE_SECRET_DASHBOARD_FLAG_FIELDS = ("daily_success_and_failure_metrics",)
QUERY_TIME_WINDOW_PATHS = {
    LOGIN_LOGS_PATH,
    OPERATE_LOGS_PATH,
    FTP_LOGS_PATH,
    JOB_LOGS_PATH,
    PASSWORD_CHANGE_LOGS_PATH,
    USER_SESSIONS_PATH,
    TERMINAL_SESSIONS_PATH,
    TERMINAL_COMMANDS_PATH,
}
CANONICAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_INPUT_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
)
DATETIME_INPUT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y/%m/%d %H:%M:%S %z",
)
BASIC_NAIVE_DATETIME_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}$")
DISPLAY_STYLE_USER_RE = re.compile(r"^(?P<name>.*)\((?P<username>[^()]+)\)$")
OPERATE_ACTION_ALIASES = {
    "create": "create",
    "创建": "create",
    "view": "view",
    "查看": "view",
    "update": "update",
    "更新": "update",
    "delete": "delete",
    "删除": "delete",
    "export": "export",
    "导出": "export",
    "download": "download",
    "下载": "download",
    "connect": "connect",
    "连接": "connect",
    "login": "login",
    "登录": "login",
    "change_password": "change_password",
    "改密": "change_password",
    "accept": "accept",
    "接受": "accept",
    "review": "review",
    "审批": "review",
    "notice": "notice",
    "通知": "notice",
    "reject": "reject",
    "拒绝": "reject",
    "approve": "approve",
    "同意": "approve",
    "close": "close",
    "关闭": "close",
    "finished": "finished",
    "完成": "finished",
}
OPERATE_ACTION_CANONICAL_VALUES = (
    "create",
    "view",
    "update",
    "delete",
    "export",
    "download",
    "connect",
    "login",
    "change_password",
    "accept",
    "review",
    "notice",
    "reject",
    "approve",
    "close",
    "finished",
)
LOGIN_TYPE_VALUES = ("W", "T", "U")
LOGIN_MFA_VALUES = ("0", "1", "2")
LOGIN_STATUS_VALUES = ("0", "1")
SESSION_LOGIN_FROM_VALUES = ("WT", "ST", "RT", "DT", "VT")
TICKET_STATE_VALUES = ("closed", "pending", "approved", "rejected", "all")
TICKET_TYPE_VALUES = ("apply_asset", "login_confirm", "command_confirm", "login_asset_confirm")


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    name: str
    category: str
    priority: str
    entrypoint: str
    handler: str


def _metadata_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "metadata" / "capabilities.json"


@lru_cache(maxsize=None)
def _capability_by_id() -> dict[str, CapabilitySpec]:
    payload = json.loads(_metadata_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise CLIError("Capability metadata must be a JSON array.")
    records: dict[str, CapabilitySpec] = {}
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        capability_id = str(raw.get("capability_id") or "").strip()
        if not capability_id:
            continue
        records[capability_id] = CapabilitySpec(
            capability_id=capability_id,
            name=str(raw.get("name") or capability_id),
            category=str(raw.get("category") or ""),
            priority=str(raw.get("priority") or ""),
            entrypoint=str(raw.get("entrypoint") or ""),
            handler=str(raw.get("handler") or ""),
        )
    return records


CAPABILITY_BY_ID = _capability_by_id()

def _runtime_local_timezone() -> tzinfo:
    return datetime.now().astimezone().tzinfo or timezone.utc

def _local_now() -> datetime:
    return datetime.now(_runtime_local_timezone())

def _lower(value: Any) -> str:
    return str(value or "").strip().lower()

def parse_date_value(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None

def parse_datetime_value(value: Any, *, naive_tz: tzinfo | None = timezone.utc) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None and naive_tz is not None:
            return value.replace(tzinfo=naive_tz)
        return value
    if isinstance(value, date):
        parsed = datetime.combine(value, time())
        if naive_tz is not None:
            parsed = parsed.replace(tzinfo=naive_tz)
        return parsed
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        try:
            return datetime.fromisoformat(text[:-1] + "+00:00")
        except ValueError:
            pass

    for fmt in DATETIME_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None and naive_tz is not None:
            parsed = parsed.replace(tzinfo=naive_tz)
        return parsed
    return None

def normalize_basic_datetime_text(value: Any, *, naive_tz: tzinfo | None = timezone.utc) -> str | None:
    text = str(value or "").strip()
    if not BASIC_NAIVE_DATETIME_RE.fullmatch(text):
        return None
    parsed = parse_datetime_value(text, naive_tz=naive_tz)
    if parsed is None:
        return None
    return parsed.strftime(CANONICAL_DATETIME_FORMAT)

def _is_empty_like(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}

def _coalesce(*values: Any) -> Any:
    for value in values:
        if _is_empty_like(value):
            continue
        return value
    return None

def _value_from_path(item: dict[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current

def _string_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            _coalesce(
                value.get("label"),
                value.get("value"),
                value.get("name"),
                value.get("username"),
                value.get("id"),
            )
            or ""
        )
    return str(value or "")

def _first_field(item: dict[str, Any], *candidates: str) -> Any:
    for path in candidates:
        value = _value_from_path(item, path)
        if not _is_empty_like(value):
            return value
    return None

def _parse_filter_datetime_value(
    value: Any,
    *,
    end_of_day: bool = False,
    naive_tz: tzinfo | None = None,
) -> datetime | None:
    active_tz = naive_tz or _runtime_local_timezone()
    parsed = parse_datetime_value(value, naive_tz=active_tz)
    if parsed is not None:
        return parsed
    parsed_date = parse_date_value(value)
    if parsed_date is None:
        return None
    hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, second, tzinfo=active_tz)

def _format_local_filter_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(_runtime_local_timezone()).strftime(CANONICAL_DATETIME_FORMAT)

def _normalize_user_filter_payload(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    diagnostics = dict(payload.get("_filter_diagnostics") or {})
    if isinstance(diagnostics.get("user_filter_normalization"), dict):
        return payload

    requested_user = str(payload.get("user") or "").strip()
    requested_user_id = str(payload.get("user_id") or "").strip()
    if not requested_user and not requested_user_id:
        return payload

    normalization = {
        "applied": False,
        "strategy": None,
        "requested_user": requested_user or None,
        "requested_user_id": requested_user_id or None,
        "effective_user_id": requested_user_id or None,
    }
    if requested_user and is_uuid_like(requested_user) and not requested_user_id:
        payload["user_id"] = requested_user
        normalization["applied"] = True
        normalization["strategy"] = "user_uuid_promoted_to_user_id"
        normalization["effective_user_id"] = requested_user

    diagnostics["user_filter_normalization"] = normalization
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _compact_user_summary(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return None
    return {
        "id": str(user.get("id") or "").strip() or None,
        "name": str(user.get("name") or "").strip() or None,
        "username": str(user.get("username") or "").strip() or None,
    }

def _format_user_display_value(user: dict[str, Any] | None) -> str:
    if not isinstance(user, dict):
        return ""
    name = str(user.get("name") or "").strip()
    username = str(user.get("username") or "").strip()
    if name and username and _lower(name) != _lower(username):
        return f"{name}({username})"
    return name or username

def _parse_display_style_value(value: Any) -> dict[str, str] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = DISPLAY_STYLE_USER_RE.fullmatch(text)
    if not match:
        return None
    name = match.group("name").strip()
    identifier = match.group("username").strip()
    if not identifier:
        return None
    return {"name": name, "identifier": identifier}

def _parse_display_style_user(value: Any) -> dict[str, str] | None:
    parsed = _parse_display_style_value(value)
    if parsed is None:
        return None
    return {"name": parsed["name"], "username": parsed["identifier"]}

def _normalize_allowed_values_filter(
    filters: dict[str, Any],
    *,
    key: str,
    allowed_values: tuple[str, ...],
    reason_code: str,
    user_message: str,
    action_hint: str,
) -> dict[str, Any]:
    payload = dict(filters)
    requested_value = str(payload.get(key) or "").strip()
    if not requested_value:
        return payload
    if requested_value in allowed_values:
        return payload
    raise CLIError(
        "无法解析页面枚举过滤条件。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=user_message,
            action_hint=action_hint,
            field=key,
            value=requested_value,
            allowed_values=list(allowed_values),
        ),
    )

def _normalize_user_display_filter(
    filters: dict[str, Any],
    *,
    key: str,
    diagnostics_key: str,
    output_mode: str,
    discovery=None,
) -> dict[str, Any]:
    payload = dict(filters)
    requested_value = str(payload.get(key) or "").strip()
    if not requested_value:
        return payload
    diagnostics = dict(payload.get("_filter_diagnostics") or {})
    field_diagnostics = {
        "requested_value": requested_value,
        "effective_value": requested_value,
        "applied": False,
        "strategy": None,
        "fallback_raw": False,
        "resolved_user": None,
    }
    active_discovery = discovery or create_discovery()
    parsed_display = _parse_display_style_user(requested_value)
    try:
        resolve_target = requested_value
        if parsed_display is not None:
            resolve_target = parsed_display.get("username") or parsed_display.get("name") or requested_value
        resolved_user = _resolve_user(resolve_target, discovery=active_discovery)
    except CLIError as exc:
        payload_detail = exc.payload if isinstance(exc.payload, dict) else {}
        if parsed_display is not None and payload_detail.get("reason_code") != "ambiguous_user":
            field_diagnostics["strategy"] = "display_value_passthrough"
            field_diagnostics["fallback_raw"] = True
            field_diagnostics["fallback_reason"] = payload_detail.get("reason_code") or "user_not_resolved"
            diagnostics[diagnostics_key] = field_diagnostics
            payload["_filter_diagnostics"] = diagnostics
            return payload
        raise
    if output_mode == "name":
        effective_value = str(resolved_user.get("name") or resolved_user.get("username") or "").strip() or requested_value
        field_diagnostics["strategy"] = "user_resolved_to_name"
    else:
        effective_value = _format_user_display_value(resolved_user) or requested_value
        field_diagnostics["strategy"] = "display_value_resolved" if parsed_display is not None else "user_resolved_to_display"
    payload[key] = effective_value
    field_diagnostics["effective_value"] = effective_value
    field_diagnostics["applied"] = effective_value != requested_value
    field_diagnostics["resolved_user"] = _compact_user_summary(resolved_user)
    diagnostics[diagnostics_key] = field_diagnostics
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _normalize_ticket_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = _normalize_user_display_filter(
        filters,
        key="applicant_username_name",
        diagnostics_key="ticket_applicant_filter_normalization",
        output_mode="name",
        discovery=discovery,
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="state",
        allowed_values=TICKET_STATE_VALUES,
        reason_code="invalid_ticket_state",
        user_message="`tickets` 的 `--state` 只支持页面审批状态枚举。",
        action_hint="请改用 `closed`、`pending`、`approved`、`rejected` 或 `all`。",
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="type",
        allowed_values=TICKET_TYPE_VALUES,
        reason_code="invalid_ticket_type",
        user_message="`tickets` 的 `--type` 只支持页面工单类型枚举。",
        action_hint="请改用 `apply_asset`、`login_confirm`、`command_confirm` 或 `login_asset_confirm`。",
    )
    return payload

def _normalize_time_filters(filters: dict[str, Any], *, default_days: int = 7) -> dict[str, Any]:
    payload = _normalize_user_filter_payload(filters)
    now = _local_now()
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    days = payload.get("days")
    date_from_dt = None
    date_to_dt = None
    if days not in {None, ""} and not date_from and not date_to:
        date_from_dt = now - timedelta(days=int(days))
        date_to_dt = now
    if not date_from and not date_to:
        date_from_dt = now - timedelta(days=default_days)
        date_to_dt = now
    if date_from_dt is None and date_from not in {None, ""}:
        date_from_dt = _parse_filter_datetime_value(date_from, end_of_day=False)
    if date_to_dt is None and date_to not in {None, ""}:
        date_to_dt = _parse_filter_datetime_value(date_to, end_of_day=True)
    if date_from_dt is not None:
        payload["date_from"] = _format_local_filter_datetime(date_from_dt) or payload.get("date_from")
    elif date_from not in {None, ""}:
        payload["date_from"] = normalize_basic_datetime_text(date_from, naive_tz=_runtime_local_timezone()) or date_from
    if date_to_dt is not None:
        payload["date_to"] = _format_local_filter_datetime(date_to_dt) or payload.get("date_to")
    elif date_to not in {None, ""}:
        payload["date_to"] = normalize_basic_datetime_text(date_to, naive_tz=_runtime_local_timezone()) or date_to
    payload["_date_from"] = date_from_dt
    payload["_date_to"] = date_to_dt or now
    return payload

def _server_filters(filters: dict[str, Any]) -> dict[str, Any]:
    payload = {}
    for key in (
        "date_from",
        "date_to",
        "limit",
        "offset",
        "name",
        "search",
        "user",
        "username",
        "change_by",
        "creator__name",
        "applicant_username_name",
        "keyword",
        "material",
        "status",
        "state",
        "type",
        "ip",
        "city",
        "mfa",
        "user_id",
        "asset_id",
        "account",
        "protocol",
        "remote_addr",
        "source_ip",
        "login_from",
        "command_storage_id",
        "order",
        "is_finished",
        "users",
        "action",
        "resource_type",
        "category",
        "days",
        "id",
        "node",
        "node_id",
        "asset",
        "display",
        "draw",
        "all",
    ):
        if filters.get(key) not in {None, ""}:
            payload[key] = filters[key]
    return payload

def _format_jumpserver_api_datetime(value: Any) -> str | None:
    parsed = parse_datetime_value(value, naive_tz=_runtime_local_timezone())
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def _query_time_window_server_filters(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _server_filters(filters)
    payload.pop("days", None)
    date_from = filters.get("_date_from") or _parse_filter_datetime_value(payload.get("date_from"), end_of_day=False)
    date_to = filters.get("_date_to") or _parse_filter_datetime_value(payload.get("date_to"), end_of_day=True)
    if date_from is not None:
        payload["date_from"] = _format_jumpserver_api_datetime(date_from) or payload.get("date_from")
    elif payload.get("date_from") in {None, ""}:
        payload.pop("date_from", None)
    if date_to is not None:
        payload["date_to"] = _format_jumpserver_api_datetime(date_to) or payload.get("date_to")
    elif payload.get("date_to") in {None, ""}:
        payload.pop("date_to", None)
    return payload

def _operate_audit_server_filters(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _query_time_window_server_filters(filters)
    for key in ("user", "action"):
        if filters.get(key) not in {None, ""}:
            payload[key] = filters[key]
    return payload

def _command_audit_server_filters(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _query_time_window_server_filters(filters)
    payload.setdefault("order", "-timestamp")
    payload.setdefault("display", 1)
    payload.setdefault("draw", 1)
    return payload

def _list_request_filters(path: str, filters: dict[str, Any]) -> dict[str, Any]:
    if path == TERMINAL_COMMANDS_PATH:
        return _command_audit_server_filters(filters)
    if path == OPERATE_LOGS_PATH:
        return _operate_audit_server_filters(filters)
    if path in QUERY_TIME_WINDOW_PATHS:
        return _query_time_window_server_filters(filters)
    return _server_filters(filters)

def _top(counter: Counter, *, limit: int = 10) -> list[dict[str, Any]]:
    items = []
    for key, count in counter.most_common(limit):
        items.append({"name": key, "count": count})
    return items

def _percentage(items: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
    final = []
    for item in items:
        payload = dict(item)
        payload["ratio"] = round((float(item["count"]) / total) * 100, 2) if total else 0.0
        final.append(payload)
    return final

def _with_org_context(result: dict[str, Any]) -> dict[str, Any]:
    context = ensure_selected_org_context()
    payload = dict(result)
    payload.update(org_context_output(context))
    return payload


def _org_id_from_filters(filters: dict[str, Any]) -> str:
    return str((filters or {}).get("_org_id") or "").strip() or org_id_from_context(ensure_selected_org_context())

def _fetch_list(path: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    client = create_client(org_id=_org_id_from_filters(filters))
    result = client.list_paginated(path, params=_list_request_filters(path, filters))
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []

def _command_storage_scope(filters: dict[str, Any]) -> str:
    return _lower(filters.get("command_storage_scope"))

def _use_all_command_storages(filters: dict[str, Any]) -> bool:
    return filters.get("command_storage_id") in {None, ""} and _command_storage_scope(filters) == "all"

def resolve_command_storage_context(filters: dict[str, Any]) -> dict[str, Any]:
    rows = _fetch_list(COMMAND_STORAGES_PATH, filters)
    storages = [item for item in rows if isinstance(item, dict)]
    explicit_storage_id = str(filters.get("command_storage_id") or "").strip()
    use_all_storages = _use_all_command_storages(filters)
    selected_storage = None
    selection_mode = "unresolved"
    if explicit_storage_id:
        selected_storage = next((item for item in storages if str(item.get("id") or "") == explicit_storage_id), None)
        if selected_storage is None and explicit_storage_id:
            selected_storage = {"id": explicit_storage_id}
        selection_mode = "explicit"
    elif use_all_storages:
        selection_mode = "all"
    else:
        for item in storages:
            if item.get("is_default") and item.get("id"):
                selected_storage = item
                selection_mode = "default"
                break
        if selected_storage is None and len(storages) == 1 and storages[0].get("id"):
            selected_storage = storages[0]
            selection_mode = "single_auto"
    selected_storage_id = str((selected_storage or {}).get("id") or "").strip() or None
    storage_ids = [str(item.get("id") or "").strip() for item in storages if str(item.get("id") or "").strip()]
    if selection_mode == "all":
        switchable_storages = list(storages)
    else:
        switchable_storages = [
            item for item in storages if str(item.get("id") or "").strip() and str(item.get("id") or "").strip() != str(selected_storage_id or "")
        ]
    hint = None
    if selection_mode == "all":
        if storages:
            hint = "当前已汇总全部 command storage 查询结果；如需限定范围，可在 filters.command_storage_id 中指定单个 storage。"
        else:
            hint = "当前请求要求汇总全部 command storage，但当前环境未返回可用 storage 列表。"
    elif selection_mode == "default" and switchable_storages:
        hint = "当前已按默认 command storage 查询；如需切换，可在 filters.command_storage_id 中指定其他 storage。"
    elif selection_mode == "single_auto":
        hint = "当前环境仅发现一个 command storage，已自动使用该 storage 查询。"
    elif selection_mode == "explicit" and switchable_storages:
        hint = "当前已按指定 command storage 查询；如需切换，可改用其他 storage 的 command_storage_id。"
    elif selection_mode == "unresolved" and len(storages) > 1:
        hint = "当前存在多个 command storage，且没有默认 storage；请显式指定 command_storage_id。"
    queried_storage_ids = storage_ids if selection_mode == "all" else ([selected_storage_id] if selected_storage_id else [])
    return {
        "selected_command_storage": selected_storage,
        "selected_command_storage_id": selected_storage_id,
        "selection_mode": selection_mode,
        "command_storage_scope": "all" if selection_mode == "all" else None,
        "queried_command_storage_ids": queried_storage_ids,
        "queried_command_storage_count": len(queried_storage_ids),
        "available_command_storages": storages,
        "available_command_storage_count": len(storages),
        "switchable_command_storages": switchable_storages,
        "selection_required": selection_mode == "unresolved" and len(storages) > 1,
        "command_storage_hint": hint,
        "default_storage_count": sum(1 for item in storages if parse_bool(item.get("is_default"))),
    }

def _with_command_storage_context(result: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    payload = _with_org_context(result)
    payload.update(resolve_command_storage_context(filters))
    return payload

def _resolve_user(
    target: str | None = None,
    username: str | None = None,
    *,
    discovery=None,
) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    users = active_discovery.list_users()
    target_value = str(username or target or "").strip()
    if target and is_uuid_like(target):
        for item in users:
            if str(item.get("id")) == target:
                return item
    parsed_display = _parse_display_style_user(target_value)
    if parsed_display is not None:
        wanted_username = _lower(parsed_display.get("username"))
        wanted_name = _lower(parsed_display.get("name"))
        matches = [
            item
            for item in users
            if wanted_username
            and _lower(item.get("username")) == wanted_username
            and (not wanted_name or _lower(item.get("name")) == wanted_name)
        ]
    else:
        wanted = _lower(target_value)
        matches = [item for item in users if wanted and wanted in {_lower(item.get("username")), _lower(item.get("name"))}]
    if not matches:
        raise CLIError(
            "无法解析用户标识。",
            payload=build_cli_guidance_payload(
                "user_not_found",
                user_message="当前组织下找不到你指定的用户，请改用更精确的用户名、显示名或用户 UUID。",
                action_hint="可以先用 `resolve --resource user --name <用户名>` 确认唯一用户对象。",
                user=target_value,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "用户标识匹配到多个候选对象。",
            payload=build_cli_guidance_payload(
                "ambiguous_user",
                user_message="当前输入命中了多个用户，请改用更精确的用户名或直接使用用户 UUID。",
                action_hint="建议先执行 `resolve --resource user --name <关键字>` 查看候选对象。",
                candidates=matches[:10],
            ),
        )
    return matches[0]

def _settings_payload(category: str | None = None, *, setting_id: str | None = None, org_id: str | None = None) -> Any:
    client = create_client(org_id=org_id)
    params = {}
    if category:
        params["category"] = category
    if str(setting_id or "").strip():
        params["id"] = str(setting_id).strip()
    return client.get("/api/v1/settings/setting/", params=params)

def _settings_slice(keywords: tuple[str, ...], *, category: str | None = None, org_id: str | None = None) -> list[dict[str, Any]]:
    settings = _settings_payload(category=category, org_id=org_id)
    rows = []
    if isinstance(settings, dict):
        iterable = settings.items()
    elif isinstance(settings, list):
        iterable = []
        for item in settings:
            if isinstance(item, dict):
                key = _coalesce(item.get("key"), item.get("name"), item.get("id"))
                iterable.append((str(key or ""), item))
    else:
        iterable = []
    for key, value in iterable:
        key_text = str(key or "")
        haystack = "%s %s" % (key_text, _string_value(value))
        if any(keyword in haystack.lower() for keyword in keywords):
            rows.append({"key": key_text, "value": value})
    return rows

def setting_category_query(filters: dict[str, Any]) -> dict[str, Any]:
    category = str(filters.get("category") or "").strip()
    setting_id = str(filters.get("id") or "").strip()
    if not category:
        raise CLIError(
            "缺少设置分类参数。",
            payload=build_cli_guidance_payload(
                "missing_setting_category",
                user_message="请通过 `--category` 指定要查询的设置分类，例如 `security_auth`。",
                action_hint="推荐使用 `python3 subskills/query/scripts/jms_runtime_query.py settings-category --category security_auth`。",
            ),
        )
    payload = _settings_payload(category=category, setting_id=setting_id or None, org_id=_org_id_from_filters(filters))
    records = payload if isinstance(payload, list) else [payload]
    records = [item for item in records if item not in (None, "")]
    return _with_org_context(
        {
            "summary": {"category": category, "id": setting_id or None, "total": len(records)},
            "records": records,
        }
    )

def license_detail_query(filters: dict[str, Any]) -> dict[str, Any]:
    client = create_client(org_id=_org_id_from_filters(filters))
    payload = client.get("/api/v1/xpack/license/detail")
    return _with_org_context(
        {
            "summary": {"resource": "license_detail", "available": bool(payload)},
            "records": [payload] if payload is not None else [],
        }
    )

def ticket_list_query(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_ticket_filters(dict(filters))
    rows = _fetch_list("/api/v1/tickets/tickets/", payload)
    match_strategy = "server"
    if payload.get("search") not in {None, ""}:
        match_strategy = "server_search"
    for key, strategy_name in (
        ("applicant_username_name", "server_applicant_exact"),
        ("state", "server_state_exact"),
        ("type", "server_type_exact"),
    ):
        if payload.get(key) not in {None, ""}:
            match_strategy = strategy_name if match_strategy == "server" else "%s+%s" % (match_strategy, strategy_name)
    return _with_org_context(
        {
            "summary": {
                "ticket_count": len(rows),
                "filter_strategy": match_strategy,
                "match_strategy": match_strategy,
                "filters": {key: value for key, value in payload.items() if not str(key).startswith("_")},
            },
            "records": rows,
        }
    )

def command_storage_query(filters: dict[str, Any]) -> dict[str, Any]:
    rows = _fetch_list(COMMAND_STORAGES_PATH, filters)
    defaults = [item for item in rows if parse_bool(item.get("is_default"))]
    return _with_command_storage_context(
        {
            "summary": {"storage_count": len(rows), "default_count": len(defaults)},
            "records": rows,
        },
        filters,
    )

def replay_storage_query(filters: dict[str, Any]) -> dict[str, Any]:
    rows = _fetch_list(REPLAY_STORAGES_PATH, filters)
    defaults = [item for item in rows if parse_bool(item.get("is_default"))]
    return _with_org_context(
        {
            "summary": {"storage_count": len(rows), "default_count": len(defaults)},
            "records": rows,
        }
    )

def terminal_component_query(filters: dict[str, Any]) -> dict[str, Any]:
    rows = _fetch_list(TERMINALS_PATH, filters)
    return _with_org_context({"summary": {"terminal_count": len(rows)}, "records": rows})

def _report_server_filters(report_type: str, filters: dict[str, Any]) -> dict[str, Any]:
    payload = _server_filters(filters)
    if report_type in REPORT_TYPES_WITH_NATIVE_DAYS:
        payload.pop("date_from", None)
        payload.pop("date_to", None)
    if report_type == "pam-dashboard":
        payload.pop("days", None)
        payload.pop("date_from", None)
        payload.pop("date_to", None)
        for field in PAM_DASHBOARD_FLAG_FIELDS:
            if filters.get(field) not in {None, "", False}:
                payload[field] = int(filters.get(field))
    if report_type == "change-secret-dashboard":
        for field in CHANGE_SECRET_DASHBOARD_FLAG_FIELDS:
            if filters.get(field) not in {None, "", False}:
                payload[field] = int(filters.get(field))
    return payload

def report_query(filters: dict[str, Any]) -> dict[str, Any]:
    report_type = str(filters.get("report_type") or "").strip()
    if not report_type:
        raise CLIError(
            "缺少报表类型参数。",
            payload=build_cli_guidance_payload(
                "missing_report_type",
                user_message="请通过 `--report-type` 指定要读取的报表类型。",
                action_hint="推荐使用 `python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30`。",
            ),
        )
    path = REPORT_PATHS.get(report_type)
    if path is None:
        raise CLIError(
            "不支持的报表类型：%s" % report_type,
            payload=build_cli_guidance_payload(
                "unsupported_report_type",
                user_message="当前 `--report-type` 不在支持列表中，请改用帮助页里列出的类型。",
                action_hint="可先执行 `python3 subskills/query/scripts/jms_runtime_query.py reports --help` 查看支持值。",
                report_type=report_type,
            ),
        )
    client = create_client(org_id=_org_id_from_filters(filters))
    params = _report_server_filters(report_type, filters)
    payload = client.get(path, params=params)
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        payload = client.list_paginated(path, params=params)
    records = payload if isinstance(payload, list) else [payload]
    records = [item for item in records if item not in (None, "")]
    return _with_org_context(
        {
            "summary": {"report_type": report_type, "total": len(records), "request_params": params},
            "records": records,
        }
    )

def account_automation_overview(filters: dict[str, Any]) -> dict[str, Any]:
    specs = {
        "account_risks": {"path": "/api/v1/accounts/account-risks/", "mode": "list"},
        "backup_plans": {"path": "/api/v1/accounts/account-backup-plans/", "mode": "list"},
        "backup_executions": {"path": "/api/v1/accounts/account-backup-plan-executions/", "mode": "list"},
        "change_secret_automations": {"path": "/api/v1/accounts/change-secret-automations/", "mode": "list"},
        "change_secret_executions": {"path": "/api/v1/accounts/change-secret-executions/", "mode": "list"},
        "change_secret_records": {"path": "/api/v1/accounts/change-secret-records/", "mode": "list"},
        "change_secret_dashboard": {"path": "/api/v1/accounts/change-secret-records/dashboard/", "mode": "get"},
        "check_account_automations": {"path": "/api/v1/accounts/check-account-automations/", "mode": "list"},
        "check_account_executions": {"path": "/api/v1/accounts/check-account-executions/", "mode": "list"},
        "account_check_engines": {"path": "/api/v1/accounts/account-check-engines/", "mode": "list"},
    }
    client = create_client(org_id=_org_id_from_filters(filters))
    records = []
    partial_failures = []
    params = _server_filters(filters)
    for name, spec in specs.items():
        try:
            path = str(spec["path"])
            mode = str(spec.get("mode") or "get")
            payload = client.list_paginated(path, params=params) if mode == "list" else client.get(path, params=params)
            records.append({"module": name, "payload": payload})
        except Exception as exc:  # noqa: BLE001
            partial_failures.append({"module": name, "error": str(exc)})
    return _with_org_context(
        {
            "summary": {
                "module_count": len(records),
                "partial_failure_count": len(partial_failures),
            },
            "records": records,
            "partial_failures": partial_failures,
        }
    )

HANDLERS = {
    "setting_category_query": setting_category_query,
    "license_detail_query": license_detail_query,
    "ticket_list_query": ticket_list_query,
    "command_storage_query": command_storage_query,
    "replay_storage_query": replay_storage_query,
    "terminal_component_query": terminal_component_query,
    "report_query": report_query,
    "account_automation_overview": account_automation_overview,
}


def run_capability(capability_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    spec = CAPABILITY_BY_ID.get(capability_id)
    if spec is None:
        raise CLIError("Unknown capability: %s" % capability_id)
    handler = HANDLERS.get(spec.handler)
    if handler is None:
        raise CLIError("Capability handler is not implemented: %s" % spec.handler)
    result = handler(filters)
    payload = dict(result)
    payload["capability"] = {
        "id": spec.capability_id,
        "name": spec.name,
        "category": spec.category,
        "priority": spec.priority,
    }
    return payload
