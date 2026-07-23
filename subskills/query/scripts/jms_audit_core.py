from __future__ import annotations

"""Audit domain functions for JumpServer audit subskill."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import hashlib
import json
import re
from typing import Any
from jumpserver_common.jms_text_utils import (
    lower_text as _lower,
    value_from_path as _value_from_path,
)
from jumpserver_common.jms_runtime import (
    CLIError,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    ensure_selected_org_context,
    is_uuid_like,
    org_id_from_context,
    org_context_output,
    normalize_relative_time_window,
    parse_bool,
    parse_strict_bool,
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

def _simplify_display_name(value: Any) -> str:
    text = _string_value(value).strip()
    if "(" in text and text.endswith(")"):
        prefix, suffix = text.rsplit("(", 1)
        prefix = prefix.strip()
        inner = suffix[:-1].strip()
        if prefix:
            return prefix
        if inner:
            return inner
    return text

def _first_field(item: dict[str, Any], *candidates: str) -> Any:
    for path in candidates:
        value = _value_from_path(item, path)
        if not _is_empty_like(value):
            return value
    return None

def _extract_identifier(item: dict[str, Any], *candidates: str) -> str:
    value = _first_field(item, *candidates)
    return _string_value(value).strip()

def _extract_user(item: dict[str, Any]) -> str:
    return _extract_identifier(
        item,
        "user",
        "user_display",
        "user.username",
        "user.name",
        "username",
        "created_by",
    )

def _extract_user_id(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "user_id", "user.id")

def _extract_asset(item: dict[str, Any]) -> str:
    return _simplify_display_name(
        _extract_identifier(
            item,
            "asset",
            "asset_display",
            "asset.name",
            "asset.address",
            "name",
            "hostname",
            "target",
        )
    )

def _extract_asset_id(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "asset_id", "asset.id")

def _append_unique_text(target: list[str], seen: set[str], value: Any, *, simplify: bool = False) -> None:
    text = _string_value(value).strip()
    if not text:
        return
    candidates = [text]
    if simplify:
        simplified = _simplify_display_name(text)
        if simplified and simplified != text:
            candidates.append(simplified)
    for candidate in candidates:
        key = _lower(candidate)
        if not candidate or key in seen:
            continue
        seen.add(key)
        target.append(candidate)

def _asset_candidate_values(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for path in ("asset", "asset_display", "asset.name", "asset.address", "name", "hostname", "target"):
        raw = _value_from_path(item, path)
        if isinstance(raw, dict):
            for key in ("name", "address", "label", "value", "id"):
                _append_unique_text(values, seen, raw.get(key), simplify=(key != "id"))
            _append_unique_text(values, seen, raw, simplify=True)
            continue
        _append_unique_text(values, seen, raw, simplify=True)
    _append_unique_text(values, seen, _extract_asset_id(item))
    return values

def _asset_filter_evidence(item: dict[str, Any], expected: Any = None) -> dict[str, Any]:
    expected_text = str(expected or "").strip()
    candidates = _asset_candidate_values(item)
    matched_values = [value for value in candidates if expected_text and _lower(expected_text) in _lower(value)]
    return {
        "asset": _extract_asset(item) or None,
        "asset_id": _extract_asset_id(item) or None,
        "candidate_values": candidates,
        "matched_filter": expected_text or None,
        "matched_values": matched_values,
        "is_match": bool(matched_values) if expected_text else None,
    }

def _extract_account(item: dict[str, Any]) -> str:
    return _simplify_display_name(
        _extract_identifier(
            item,
            "account",
            "account_display",
            "account.username",
            "account.name",
            "username",
            "name",
        )
    )

def _extract_protocol(item: dict[str, Any]) -> str:
    return _extract_identifier(
        item,
        "protocol",
        "protocol_display",
        "connect_method",
        "terminal_type",
        "terminal_display",
        "type",
    )

def _extract_login_type(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "type", "type_display", "login_type")

def _extract_login_city(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "city", "city_display", "login_city")

def _extract_login_mfa(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "mfa", "mfa_display", "mfa_status")

def _extract_source_ip(item: dict[str, Any]) -> str:
    return _extract_identifier(
        item,
        "remote_addr",
        "remote_address",
        "src_ip",
        "source_ip",
        "ip",
        "client_ip",
    )

def _extract_login_from(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "login_from", "login_from_display", "from", "terminal_from")

def _extract_status(item: dict[str, Any]) -> str:
    return _extract_identifier(
        item,
        "status",
        "status_display",
        "result",
        "reason",
        "type",
    )

def _extract_direction(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "operate", "direction", "type", "action")

def _extract_resource_type(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "resource_type", "resource.type", "resource_type_display")

def _extract_change_by(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "change_by", "change_by_display", "operator", "operator_display")

def _extract_creator_name(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "creator__name", "creator.name", "creator", "created_by", "user.name")

def _extract_material(item: dict[str, Any]) -> str:
    return _extract_identifier(item, "material", "command", "input", "cmd")

def _extract_ticket_applicant(item: dict[str, Any]) -> str:
    return _extract_identifier(
        item,
        "applicant_username_name",
        "applicant.name",
        "applicant.username",
        "applicant",
        "applicant_display",
    )

def _extract_datetime(item: dict[str, Any]) -> datetime | None:
    value = _first_field(
        item,
        "date_from",
        "date_to",
        "timestamp_display",
        "date_start",
        "date_end",
        "date_finished",
        "date_created",
        "date_expired",
        "datetime",
        "timestamp",
    )
    return parse_datetime_value(value, naive_tz=timezone.utc)

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

def _extract_duration(item: dict[str, Any]) -> float | None:
    raw = _first_field(item, "duration", "duration_display")
    if raw not in {None, ""}:
        try:
            return float(raw)
        except (TypeError, ValueError):
            text = str(raw).strip()
            if ":" in text:
                parts = text.split(":")
                try:
                    values = [float(part) for part in parts]
                except ValueError:
                    values = []
                if len(values) == 3:
                    return values[0] * 3600 + values[1] * 60 + values[2]
                if len(values) == 2:
                    return values[0] * 60 + values[1]
    start = _extract_datetime(item)
    end = _first_field(item, "date_end", "date_finished")
    if start and end:
        end_dt = _extract_datetime({"date_end": end})
        if end_dt:
            return max((end_dt - start).total_seconds(), 0.0)
    return None

def _match_text(value: str, expected: Any) -> bool:
    expected_text = _lower(expected)
    if not expected_text:
        return True
    value_text = _lower(value)
    if expected_text in value_text:
        return True
    parsed_display = _parse_display_style_value(expected)
    if parsed_display is None:
        return False
    display_name = _lower(parsed_display.get("name"))
    display_identifier = _lower(parsed_display.get("identifier"))
    return value_text in {display_name, display_identifier} or (
        bool(display_name) and display_name in value_text
    ) or (
        bool(display_identifier) and display_identifier in value_text
    )

def _match_time(record_time: datetime | None, filters: dict[str, Any]) -> bool:
    if record_time is None:
        return True
    if filters.get("_date_from") and record_time < filters["_date_from"]:
        return False
    if filters.get("_date_to") and record_time > filters["_date_to"]:
        return False
    return True

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

def _compact_asset_summary(asset: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(asset, dict):
        return None
    return {
        "id": str(asset.get("id") or "").strip() or None,
        "name": str(asset.get("name") or "").strip() or None,
        "address": str(asset.get("address") or "").strip() or None,
    }

def _compact_account_summary(account: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(account, dict):
        return None
    return {
        "id": str(account.get("id") or "").strip() or None,
        "name": str(account.get("name") or "").strip() or None,
        "username": str(account.get("username") or "").strip() or None,
    }

def _format_user_display_value(user: dict[str, Any] | None) -> str:
    if not isinstance(user, dict):
        return ""
    name = str(user.get("name") or "").strip()
    username = str(user.get("username") or "").strip()
    if name and username and _lower(name) != _lower(username):
        return f"{name}({username})"
    return name or username

def _format_asset_display_value(asset: dict[str, Any] | None) -> str:
    if not isinstance(asset, dict):
        return ""
    name = str(asset.get("name") or "").strip()
    address = str(asset.get("address") or "").strip()
    if name and address:
        return f"{name}({address})"
    return name or address

def _format_account_display_value(account: dict[str, Any] | None) -> str:
    if not isinstance(account, dict):
        return ""
    name = str(account.get("name") or "").strip()
    username = str(account.get("username") or "").strip()
    if name and username:
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

def _parse_display_style_asset(value: Any) -> dict[str, str] | None:
    parsed = _parse_display_style_value(value)
    if parsed is None:
        return None
    return {"name": parsed["name"], "address": parsed["identifier"]}

def _parse_display_style_account(value: Any) -> dict[str, str] | None:
    parsed = _parse_display_style_value(value)
    if parsed is None:
        return None
    return {"name": parsed["name"], "username": parsed["identifier"]}

def _normalize_operate_action_filter(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    requested_action = str(payload.get("action") or "").strip()
    if not requested_action:
        return payload
    diagnostics = dict(payload.get("_filter_diagnostics") or {})
    canonical_action = OPERATE_ACTION_ALIASES.get(_lower(requested_action))
    if canonical_action is None:
        raise CLIError(
            "无法解析操作日志动作过滤条件。",
            payload=build_cli_guidance_payload(
                "invalid_operate_action",
                user_message="`operate` 审计的 `--action` 只支持页面动作枚举，请改用英文值或中文别名。",
                action_hint="例如 `--action create`、`--action 创建` 或 `--filter action=create`。",
                action=requested_action,
                allowed_actions=list(OPERATE_ACTION_CANONICAL_VALUES),
            ),
        )
    diagnostics["operate_action_normalization"] = {
        "requested_action": requested_action,
        "effective_action": canonical_action,
        "applied": canonical_action != requested_action,
    }
    payload["action"] = canonical_action
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _normalize_operate_user_filter(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = dict(filters)
    requested_user = str(payload.get("user") or "").strip()
    if not requested_user:
        return payload
    diagnostics = dict(payload.get("_filter_diagnostics") or {})
    user_diagnostics = {
        "requested_user": requested_user,
        "effective_user": requested_user,
        "applied": False,
        "strategy": None,
        "fallback_raw": False,
        "resolved_user": None,
    }
    active_discovery = discovery or create_discovery()
    parsed_display_user = _parse_display_style_user(requested_user)
    if parsed_display_user is not None:
        try:
            target = parsed_display_user.get("username") or parsed_display_user.get("name")
            resolved_user = _resolve_user(target, discovery=active_discovery)
        except CLIError as exc:
            if exc.payload.get("reason_code") == "ambiguous_user":
                raise
            user_diagnostics["strategy"] = "display_value_passthrough"
            user_diagnostics["fallback_raw"] = True
            user_diagnostics["fallback_reason"] = exc.payload.get("reason_code") or "user_not_resolved"
            diagnostics["operate_user_filter_normalization"] = user_diagnostics
            payload["_filter_diagnostics"] = diagnostics
            return payload
        effective_user = _format_user_display_value(resolved_user) or requested_user
        payload["user"] = effective_user
        user_diagnostics["effective_user"] = effective_user
        user_diagnostics["applied"] = effective_user != requested_user
        user_diagnostics["strategy"] = "display_value_resolved"
        user_diagnostics["resolved_user"] = _compact_user_summary(resolved_user)
    else:
        resolved_user = _resolve_user(requested_user, discovery=active_discovery)
        effective_user = _format_user_display_value(resolved_user) or requested_user
        payload["user"] = effective_user
        user_diagnostics["effective_user"] = effective_user
        user_diagnostics["applied"] = effective_user != requested_user
        user_diagnostics["strategy"] = "user_resolved_to_display"
        user_diagnostics["resolved_user"] = _compact_user_summary(resolved_user)
        if is_uuid_like(requested_user) and payload.get("user_id") == requested_user:
            payload.pop("user_id", None)
            user_diagnostics["dropped_promoted_user_id"] = True
    diagnostics["operate_user_filter_normalization"] = user_diagnostics
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _normalize_operate_audit_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = _normalize_operate_user_filter(filters, discovery=discovery)
    payload = _normalize_operate_action_filter(payload)
    return payload

def _normalize_filter_alias(
    filters: dict[str, Any],
    *,
    source_key: str,
    target_key: str,
    diagnostics_key: str,
) -> dict[str, Any]:
    payload = dict(filters)
    source_value = str(payload.get(source_key) or "").strip()
    if not source_value or payload.get(target_key) not in {None, ""}:
        return payload
    diagnostics = dict(payload.get("_filter_diagnostics") or {})
    payload[target_key] = source_value
    payload.pop(source_key, None)
    diagnostics[diagnostics_key] = {
        "requested_key": source_key,
        "requested_value": source_value,
        "effective_key": target_key,
        "effective_value": source_value,
        "applied": True,
    }
    payload["_filter_diagnostics"] = diagnostics
    return payload

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

def _normalize_asset_display_filter(
    filters: dict[str, Any],
    *,
    key: str,
    diagnostics_key: str,
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
        "resolved_asset": None,
    }
    active_discovery = discovery or create_discovery()
    parsed_display = _parse_display_style_asset(requested_value)
    try:
        # Keep the full `name(address)` display value so asset resolution can
        # use both parts together; using only the address can become ambiguous.
        resolved_asset = _resolve_asset(requested_value, discovery=active_discovery)
    except CLIError as exc:
        payload_detail = exc.payload if isinstance(exc.payload, dict) else {}
        if parsed_display is not None and payload_detail.get("reason_code") != "ambiguous_asset":
            field_diagnostics["strategy"] = "display_value_passthrough"
            field_diagnostics["fallback_raw"] = True
            field_diagnostics["fallback_reason"] = payload_detail.get("reason_code") or "asset_not_resolved"
            diagnostics[diagnostics_key] = field_diagnostics
            payload["_filter_diagnostics"] = diagnostics
            return payload
        raise
    effective_value = _format_asset_display_value(resolved_asset) or requested_value
    payload[key] = effective_value
    field_diagnostics["effective_value"] = effective_value
    field_diagnostics["applied"] = effective_value != requested_value
    field_diagnostics["strategy"] = "display_value_resolved" if parsed_display is not None else "asset_resolved_to_display"
    field_diagnostics["resolved_asset"] = _compact_asset_summary(resolved_asset)
    diagnostics[diagnostics_key] = field_diagnostics
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _normalize_account_display_filter(
    filters: dict[str, Any],
    *,
    key: str,
    diagnostics_key: str,
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
        "resolved_account": None,
    }
    active_discovery = discovery or create_discovery()
    parsed_display = _parse_display_style_account(requested_value)
    try:
        resolve_target = requested_value
        if parsed_display is not None:
            resolve_target = parsed_display.get("username") or parsed_display.get("name") or requested_value
        resolved_account = _resolve_account(resolve_target, discovery=active_discovery)
    except CLIError as exc:
        payload_detail = exc.payload if isinstance(exc.payload, dict) else {}
        if parsed_display is not None and payload_detail.get("reason_code") != "ambiguous_account":
            field_diagnostics["strategy"] = "display_value_passthrough"
            field_diagnostics["fallback_raw"] = True
            field_diagnostics["fallback_reason"] = payload_detail.get("reason_code") or "account_not_resolved"
            diagnostics[diagnostics_key] = field_diagnostics
            payload["_filter_diagnostics"] = diagnostics
            return payload
        raise
    effective_value = _format_account_display_value(resolved_account) or requested_value
    payload[key] = effective_value
    field_diagnostics["effective_value"] = effective_value
    field_diagnostics["applied"] = effective_value != requested_value
    field_diagnostics["strategy"] = "display_value_resolved" if parsed_display is not None else "account_resolved_to_display"
    field_diagnostics["resolved_account"] = _compact_account_summary(resolved_account)
    diagnostics[diagnostics_key] = field_diagnostics
    payload["_filter_diagnostics"] = diagnostics
    return payload

def _normalize_login_audit_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = _normalize_filter_alias(
        filters,
        source_key="source_ip",
        target_key="ip",
        diagnostics_key="login_ip_filter_normalization",
    )
    payload = _normalize_user_display_filter(
        payload,
        key="username",
        diagnostics_key="login_username_filter_normalization",
        output_mode="display",
        discovery=discovery,
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="type",
        allowed_values=LOGIN_TYPE_VALUES,
        reason_code="invalid_login_type",
        user_message="`login` 审计的 `--type` 只支持页面设备类型枚举。",
        action_hint="请改用 `W`、`T` 或 `U`。",
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="mfa",
        allowed_values=LOGIN_MFA_VALUES,
        reason_code="invalid_login_mfa",
        user_message="`login` 审计的 `--mfa` 只支持页面枚举值。",
        action_hint="请改用 `0`、`1` 或 `2`。",
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="status",
        allowed_values=LOGIN_STATUS_VALUES,
        reason_code="invalid_login_status",
        user_message="`login` 审计的 `--status` 只支持页面状态枚举。",
        action_hint="请改用 `0` 或 `1`。",
    )
    return payload

def _normalize_password_change_audit_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = _normalize_filter_alias(
        filters,
        source_key="source_ip",
        target_key="remote_addr",
        diagnostics_key="password_change_remote_addr_filter_normalization",
    )
    payload = _normalize_user_display_filter(
        payload,
        key="user",
        diagnostics_key="password_change_user_filter_normalization",
        output_mode="display",
        discovery=discovery,
    )
    payload = _normalize_user_display_filter(
        payload,
        key="change_by",
        diagnostics_key="password_change_change_by_filter_normalization",
        output_mode="display",
        discovery=discovery,
    )
    return payload

def _normalize_job_audit_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    return _normalize_user_display_filter(
        filters,
        key="creator__name",
        diagnostics_key="job_creator_filter_normalization",
        output_mode="name",
        discovery=discovery,
    )

def _normalize_terminal_session_filters(filters: dict[str, Any], *, discovery=None) -> dict[str, Any]:
    payload = _normalize_filter_alias(
        filters,
        source_key="source_ip",
        target_key="remote_addr",
        diagnostics_key="terminal_session_remote_addr_filter_normalization",
    )
    payload = _normalize_user_display_filter(
        payload,
        key="user",
        diagnostics_key="terminal_session_user_filter_normalization",
        output_mode="display",
        discovery=discovery,
    )
    payload = _normalize_account_display_filter(
        payload,
        key="account",
        diagnostics_key="terminal_session_account_filter_normalization",
        discovery=discovery,
    )
    payload = _normalize_asset_display_filter(
        payload,
        key="asset",
        diagnostics_key="terminal_session_asset_filter_normalization",
        discovery=discovery,
    )
    payload = _normalize_allowed_values_filter(
        payload,
        key="login_from",
        allowed_values=SESSION_LOGIN_FROM_VALUES,
        reason_code="invalid_terminal_session_login_from",
        user_message="`terminal-session` 的 `--login-from` 只支持页面来源类型枚举。",
        action_hint="请改用 `WT`、`ST`、`RT`、`DT` 或 `VT`。",
    )
    return payload

def _extract_filter_diagnostics(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    diagnostics = (filters or {}).get("_filter_diagnostics")
    return dict(diagnostics) if isinstance(diagnostics, dict) and diagnostics else None

def _normalize_time_filters(filters: dict[str, Any], *, default_days: int = 7) -> dict[str, Any]:
    payload = _normalize_user_filter_payload(filters)
    now = _local_now()
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    days = payload.get("days")
    date_from_dt = None
    date_to_dt = None
    date_from_dt, date_to_dt = normalize_relative_time_window(
        days=days,
        date_from=date_from,
        date_to=date_to,
        now=now,
        default_days=default_days,
    )
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

def _match_asset_filter(item: dict[str, Any], expected: Any) -> bool:
    expected_text = _lower(expected)
    if not expected_text:
        return True
    return any(expected_text in _lower(value) for value in _asset_candidate_values(item))

def _apply_common_filters(items: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    final = []
    for item in items:
        timestamp = _extract_datetime(item)
        if not _match_time(timestamp, filters):
            continue
        requested_username = str(filters.get("username") or "").strip()
        if requested_username and not _match_text(_extract_user(item), requested_username):
            continue
        requested_user_id = str(filters.get("user_id") or "").strip()
        if requested_user_id and _extract_user_id(item) != requested_user_id:
            continue
        requested_user = str(filters.get("user") or "").strip()
        if requested_user and not is_uuid_like(requested_user) and not _match_text(_extract_user(item), requested_user):
            continue
        requested_change_by = str(filters.get("change_by") or "").strip()
        if requested_change_by and not _match_text(_extract_change_by(item), requested_change_by):
            continue
        requested_creator_name = str(filters.get("creator__name") or "").strip()
        if requested_creator_name and not _match_text(_extract_creator_name(item), requested_creator_name):
            continue
        requested_applicant = str(filters.get("applicant_username_name") or "").strip()
        if requested_applicant and not _match_text(_extract_ticket_applicant(item), requested_applicant):
            continue
        requested_action = str(filters.get("action") or "").strip()
        if requested_action and not _match_text(_extract_direction(item), requested_action):
            continue
        requested_resource_type = str(filters.get("resource_type") or "").strip()
        if requested_resource_type and not _match_text(_extract_resource_type(item), requested_resource_type):
            continue
        requested_type = str(filters.get("type") or "").strip()
        if requested_type and not _match_text(_extract_login_type(item), requested_type):
            continue
        requested_city = str(filters.get("city") or "").strip()
        if requested_city and not _match_text(_extract_login_city(item), requested_city):
            continue
        requested_mfa = str(filters.get("mfa") or "").strip()
        if requested_mfa and not _match_text(_extract_login_mfa(item), requested_mfa):
            continue
        requested_state = str(filters.get("state") or "").strip()
        if requested_state and not _match_text(_extract_status(item), requested_state):
            continue
        if filters.get("asset") and not _match_asset_filter(item, filters["asset"]):
            continue
        if filters.get("account") and not _match_text(_extract_account(item), filters["account"]):
            continue
        if filters.get("protocol") and not _match_text(_extract_protocol(item), filters["protocol"]):
            continue
        if filters.get("ip") and not _match_text(_extract_source_ip(item), filters["ip"]):
            continue
        if filters.get("remote_addr") and not _match_text(_extract_source_ip(item), filters["remote_addr"]):
            continue
        if filters.get("source_ip") and not _match_text(_extract_source_ip(item), filters["source_ip"]):
            continue
        if filters.get("login_from") and not _match_text(_extract_login_from(item), filters["login_from"]):
            continue
        if filters.get("material") and not _match_text(_extract_material(item), filters["material"]):
            continue
        keyword = filters.get("keyword")
        if keyword:
            haystack = " ".join(
                [
                    _string_value(_first_field(item, "input", "output", "comment", "detail")),
                    _extract_user(item),
                    " ".join(_asset_candidate_values(item)),
                    _extract_account(item),
                    _extract_protocol(item),
                ]
            )
            if not _match_text(haystack, keyword):
                continue
        final.append(item)
    return final

def _empty_result(message: str, filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {"message": message, "total": 0, "filters": {key: value for key, value in filters.items() if not str(key).startswith("_")}},
        "records": [],
    }

def _with_org_context(result: dict[str, Any]) -> dict[str, Any]:
    context = ensure_selected_org_context()
    payload = dict(result)
    payload.update(org_context_output(context))
    return payload


def _org_id_from_filters(filters: dict[str, Any] | None) -> str:
    return str((filters or {}).get("_org_id") or "").strip() or org_id_from_context(ensure_selected_org_context())

def _fetch_list(path: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    client = create_client(org_id=_org_id_from_filters(filters))
    result = client.list_paginated(path, params=_list_request_filters(path, filters))
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []

def _drop_local_time_only_filters(payload: dict[str, Any]) -> dict[str, Any]:
    server_payload = dict(payload)
    server_payload.pop("days", None)
    return server_payload

def _account_inventory_filters(payload: dict[str, Any]) -> dict[str, Any]:
    server_payload = dict(payload)
    for key in (
        "days",
        "date_from",
        "date_to",
        "_date_from",
        "_date_to",
        "limit",
        "offset",
        "top",
        "account",
        "asset",
        "privileged",
        "is_active",
    ):
        server_payload.pop(key, None)
    return server_payload

def _default_command_storage_id(filters: dict[str, Any]) -> str:
    if filters.get("command_storage_id") not in {None, ""}:
        return str(filters["command_storage_id"])
    storages = _fetch_list(COMMAND_STORAGES_PATH, filters)
    for item in storages:
        if isinstance(item, dict) and item.get("is_default") and item.get("id"):
            return str(item["id"])
    if len(storages) == 1 and isinstance(storages[0], dict) and storages[0].get("id"):
        return str(storages[0]["id"])
    return ""

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

def _command_record_storage_id(item: dict[str, Any], *, fallback: Any = None) -> str:
    for candidate in (fallback, item.get("command_storage_id"), item.get("_command_storage_id")):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""

def _command_record_session_id(item: dict[str, Any]) -> str:
    return str(_first_field(item, "session", "session_id") or "").strip()

def _command_record_timestamp(item: dict[str, Any]) -> int:
    raw = item.get("timestamp")
    if raw not in {None, ""}:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            pass
    parsed = _extract_datetime(item)
    if parsed is not None:
        return int(parsed.timestamp())
    return 0

def _command_record_risk_level_value(item: dict[str, Any]) -> int:
    raw = _first_field(item, "risk_level.value", "risk_level")
    if isinstance(raw, dict):
        raw = raw.get("value")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0

def _command_record_stable_payload(item: dict[str, Any], *, command_storage_id: str | None = None, include_storage: bool = True) -> dict[str, Any]:
    payload = {
        "org_id": str(item.get("org_id") or "").strip(),
        "user": str(item.get("user") or "").strip(),
        "asset": str(item.get("asset") or "").strip(),
        "account": str(item.get("account") or "").strip(),
        "session": _command_record_session_id(item),
        "timestamp": _command_record_timestamp(item),
        "input": str(item.get("input") or "").strip(),
        "remote_addr": str(_first_field(item, "remote_addr", "remote_address", "src_ip", "source_ip") or "").strip(),
        "risk_level": _command_record_risk_level_value(item),
    }
    if include_storage:
        payload["command_storage_id"] = _command_record_storage_id(item, fallback=command_storage_id)
    return payload

def _command_record_sha1(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()

def _build_command_record_stable_id(item: dict[str, Any], *, command_storage_id: str | None = None) -> str:
    payload = _command_record_stable_payload(item, command_storage_id=command_storage_id, include_storage=True)
    storage_id = str(payload.get("command_storage_id") or "").strip() or "-"
    session_id = str(payload.get("session") or "").strip() or "-"
    timestamp = int(payload.get("timestamp") or 0)
    return "cmdrec:v1:%s:%s:%s:%s" % (storage_id, session_id, timestamp, _command_record_sha1(payload))

def _parse_command_record_stable_id(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 6 or parts[0] != "cmdrec" or parts[1] != "v1":
        return None
    try:
        timestamp = int(parts[4])
    except (TypeError, ValueError):
        return None
    digest = str(parts[5] or "").strip().lower()
    if len(digest) != 40 or any(ch not in "0123456789abcdef" for ch in digest):
        return None
    storage_id = str(parts[2] or "").strip()
    session_id = str(parts[3] or "").strip()
    return {
        "storage_id": None if storage_id in {"", "-"} else storage_id,
        "session_id": None if session_id in {"", "-"} else session_id,
        "timestamp": timestamp,
        "sha1": digest,
        "stable_id": text,
    }

def _normalize_command_record(item: dict[str, Any], *, command_storage_id: str | None = None) -> dict[str, Any]:
    cloned = dict(item)
    storage_id = _command_record_storage_id(cloned, fallback=command_storage_id)
    existing_source_row_id = str(cloned.get("source_row_id") or "").strip()
    current_id = str(cloned.get("id") or "").strip()
    if existing_source_row_id:
        cloned["source_row_id"] = existing_source_row_id
    elif current_id and _parse_command_record_stable_id(current_id) is None:
        cloned["source_row_id"] = current_id
    if storage_id:
        cloned["command_storage_id"] = storage_id
        cloned.setdefault("_command_storage_id", storage_id)
    cloned["id"] = _build_command_record_stable_id(cloned, command_storage_id=storage_id)
    return cloned

def _command_record_merge_identity(item: dict[str, Any]) -> str:
    payload = _command_record_stable_payload(item, include_storage=False)
    return "merge:%s" % _command_record_sha1(payload)

def _record_page_signature(records: list[dict[str, Any]]) -> str:
    try:
        raw = json.dumps(records, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = repr(records)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def _command_page_records(page: Any) -> list[dict[str, Any]]:
    if isinstance(page, dict) and isinstance(page.get("results"), list):
        return [item for item in page.get("results") or [] if isinstance(item, dict)]
    if isinstance(page, list):
        return [item for item in page if isinstance(item, dict)]
    return []

def _command_query_records(client, query_payload: dict[str, Any]) -> list[dict[str, Any]]:
    page_limit = int(query_payload.get("limit") or 100)
    offset = int(query_payload.get("offset") or 0)
    records: list[dict[str, Any]] = []
    seen_page_signatures: set[str] = set()

    while True:
        page = client.get(TERMINAL_COMMANDS_PATH, params=query_payload)
        page_records = _command_page_records(page)
        if page_records:
            page_signature = _record_page_signature(page_records)
            if page_signature in seen_page_signatures:
                break
            seen_page_signatures.add(page_signature)
        records.extend(page_records)
        if len(page_records) < page_limit:
            break
        offset += len(page_records)
        query_payload = {**query_payload, "limit": page_limit, "offset": offset}
    return records

def _fetch_command_records_for_session(session_id: str, *, page_limit: int = 200, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    session_value = str(session_id or "").strip()
    if not session_value:
        return []
    client = create_client(org_id=_org_id_from_filters(filters))
    return _command_query_records(
        client,
        {
            "session_id": session_value,
            "limit": page_limit,
            "offset": 0,
            "display": 1,
            "draw": 1,
        },
    )

def _command_record_time_windows(timestamp: int) -> list[tuple[datetime, datetime]]:
    record_time = datetime.fromtimestamp(int(timestamp or 0), tz=timezone.utc)
    narrow_start = record_time - timedelta(minutes=5)
    narrow_end = record_time + timedelta(minutes=5)
    day_start = datetime.combine(record_time.date(), time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(record_time.date(), time.max, tzinfo=timezone.utc)
    return [(narrow_start, narrow_end), (day_start, day_end)]

def _fetch_command_records_for_storage_and_window(
    command_storage_id: str,
    *,
    date_from: datetime,
    date_to: datetime,
    page_limit: int = 200,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    storage_id = str(command_storage_id or "").strip()
    if not storage_id:
        return []
    client = create_client(org_id=_org_id_from_filters(filters))
    query_payload = _command_audit_server_filters(
        {
            "command_storage_id": storage_id,
            "date_from": date_from,
            "date_to": date_to,
            "limit": page_limit,
            "offset": 0,
        }
    )
    return _command_query_records(client, query_payload)

def _legacy_fetch_command_record_by_raw_id(record_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters or {})
    target_id = str(record_id or "").strip()
    if not target_id:
        raise CLIError("Command audit record id is required.")

    storage_context = resolve_command_storage_context(payload)
    storage_ids = []
    selected_storage_id = str(storage_context.get("selected_command_storage_id") or "").strip()
    if selected_storage_id:
        storage_ids.append(selected_storage_id)
    for item in storage_context.get("available_command_storages") or []:
        candidate = str((item or {}).get("id") or "").strip()
        if candidate and candidate not in storage_ids:
            storage_ids.append(candidate)
    if not storage_ids:
        storage_ids.append("")

    client = create_client(org_id=_org_id_from_filters(filters))
    page_limit = 200
    for storage_id in storage_ids:
        query_payload = _command_audit_server_filters(
            {
                "command_storage_id": storage_id,
                "limit": page_limit,
                "offset": 0,
            }
        )
        for item in _command_query_records(client, query_payload):
            if str(item.get("id") or "").strip() != target_id:
                continue
            return _normalize_command_record(item, command_storage_id=storage_id)

    raise CLIError(
        "Command audit record not found.",
        payload={
            "record_id": target_id,
            "queried_command_storage_ids": storage_ids,
        },
    )

def _fetch_command_records_for_storage(payload: dict[str, Any], *, command_storage_id: str | None = None) -> list[dict[str, Any]]:
    server_payload = _command_audit_server_filters(_drop_local_time_only_filters(dict(payload)))
    if command_storage_id not in {None, ""}:
        server_payload["command_storage_id"] = command_storage_id
    elif server_payload.get("command_storage_id") in {None, ""}:
        server_payload.pop("command_storage_id", None)
    client = create_client(org_id=_org_id_from_filters(payload))
    records = _command_query_records(
        client,
        server_payload,
    )
    records = _apply_common_filters(records, payload)
    final: list[dict[str, Any]] = []
    for item in records:
        final.append(_normalize_command_record(item, command_storage_id=str(command_storage_id or "").strip() or None))
    return final

def _fetch_command_records(filters: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _normalize_time_filters(filters)
    if _use_all_command_storages(payload):
        storages = _fetch_list(COMMAND_STORAGES_PATH, payload)
        records = []
        seen_record_ids: set[str] = set()
        for storage in storages:
            storage_id = str((storage or {}).get("id") or "").strip()
            if not storage_id:
                continue
            for record in _fetch_command_records_for_storage(payload, command_storage_id=storage_id):
                record_identity = _command_record_merge_identity(record)
                if record_identity in seen_record_ids:
                    continue
                seen_record_ids.add(record_identity)
                records.append(record)
    else:
        effective_storage_id = str(payload.get("command_storage_id") or "").strip()
        if not effective_storage_id:
            default_storage_id = _default_command_storage_id(payload)
            if default_storage_id:
                effective_storage_id = default_storage_id
                payload["command_storage_id"] = default_storage_id
        records = _fetch_command_records_for_storage(payload, command_storage_id=effective_storage_id or None)
    if payload.get("risk_level") not in {None, ""}:
        threshold = int(payload["risk_level"])
        records = [item for item in records if int(_first_field(item, "risk_level.value", "risk_level") or 0) >= threshold]
    records.sort(key=lambda item: _extract_datetime(item) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return records

def _fetch_command_record_by_id(record_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    target_id = str(record_id or "").strip()
    if not target_id:
        raise CLIError("Command audit record id is required.")
    parsed = _parse_command_record_stable_id(target_id)
    if parsed is None:
        return _legacy_fetch_command_record_by_raw_id(target_id, filters or {})

    session_id = parsed.get("session_id")
    storage_id = str(parsed.get("storage_id") or "").strip()
    if session_id:
        for item in _fetch_command_records_for_session(session_id, filters=filters):
            record = _normalize_command_record(item, command_storage_id=storage_id or None)
            if record["id"] == target_id:
                return record

    if storage_id:
        for date_from, date_to in _command_record_time_windows(int(parsed.get("timestamp") or 0)):
            for item in _fetch_command_records_for_storage_and_window(
                storage_id,
                date_from=date_from,
                date_to=date_to,
                filters=filters,
            ):
                record = _normalize_command_record(item, command_storage_id=storage_id)
                if record["id"] == target_id:
                    return record

    raise CLIError(
        "Command audit record not found.",
        payload={
            "record_id": target_id,
            "lookup_strategy": "stable_id",
            "session_id": session_id,
            "command_storage_id": storage_id or None,
        },
    )

def _fetch_terminal_session_records(filters: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _normalize_terminal_session_filters(_normalize_time_filters(filters))
    server_payload = _drop_local_time_only_filters(dict(payload))
    resolved_asset = ((_extract_filter_diagnostics(payload) or {}).get("terminal_session_asset_filter_normalization") or {}).get("resolved_asset")
    if server_payload.get("asset_id"):
        server_payload.pop("asset", None)
    records = _fetch_list(TERMINAL_SESSIONS_PATH, server_payload)
    filtered = _apply_common_filters(records, payload)
    filter_strategy = "server"

    if payload.get("asset") and not filtered:
        fallback_payload = _drop_sampling_filters(dict(server_payload))
        fallback_payload.pop("asset", None)
        fallback_payload.pop("asset_id", None)
        records = _fetch_list(TERMINAL_SESSIONS_PATH, fallback_payload)
        filtered = _apply_common_filters(records, payload)
        filter_strategy = "local_asset_fallback"

    for item in filtered:
        if isinstance(item, dict):
            item.setdefault("_filter_strategy", filter_strategy)
            item.setdefault("_data_source", TERMINAL_SESSIONS_PATH)
    filtered.sort(key=lambda item: _extract_datetime(item) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return filtered, {"filter_strategy": filter_strategy, "resolved_asset": resolved_asset}

def _fetch_session_records(filters: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _normalize_terminal_session_filters(_normalize_time_filters(filters))
    records, _ = _fetch_terminal_session_records(payload)
    if not records:
        audit_payload = _drop_local_time_only_filters(dict(payload))
        filter_strategy = "audit_user_sessions_fallback"
        if payload.get("asset"):
            audit_payload = _drop_sampling_filters(audit_payload)
            audit_payload.pop("asset", None)
            audit_payload.pop("asset_id", None)
            filter_strategy = "audit_user_sessions_local_asset_fallback"
        records = _apply_common_filters(_fetch_list("/api/v1/audits/user-sessions/", audit_payload), payload)
        for item in records:
            if isinstance(item, dict):
                item.setdefault("_filter_strategy", filter_strategy)
                item.setdefault("_data_source", "/api/v1/audits/user-sessions/")
    if payload.get("status"):
        records = [item for item in records if _match_text(_extract_status(item), payload["status"])]
    records.sort(key=lambda item: _extract_datetime(item) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return records

def _fetch_file_transfer_records(filters: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _normalize_time_filters(filters)
    records = _apply_common_filters(_fetch_list("/api/v1/audits/ftp-logs/", payload), payload)
    direction = payload.get("direction")
    if direction:
        records = [item for item in records if _match_text(_extract_direction(item), direction)]
    records.sort(key=lambda item: _extract_datetime(item) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return records

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

def _resolve_asset(
    target: str | None = None,
    name: str | None = None,
    *,
    discovery=None,
) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    assets = active_discovery.list_assets()
    target_value = str(name or target or "").strip()
    if target and is_uuid_like(target):
        for item in assets:
            if str(item.get("id")) == target:
                return item
    parsed_display = _parse_display_style_asset(target_value)
    if parsed_display is not None:
        wanted_address = _lower(parsed_display.get("address"))
        wanted_name = _lower(parsed_display.get("name"))
        matches = [
            item
            for item in assets
            if wanted_address
            and _lower(item.get("address")) == wanted_address
            and (not wanted_name or _lower(item.get("name")) == wanted_name)
        ]
    else:
        wanted = _lower(target_value)
        matches = [item for item in assets if wanted and wanted in {_lower(item.get("name")), _lower(item.get("address"))}]
    if not matches:
        raise CLIError(
            "无法解析资产标识。",
            payload=build_cli_guidance_payload(
                "asset_not_found",
                user_message="当前组织下找不到你指定的资产，请改用更精确的资产名称、地址或资产 UUID。",
                action_hint="可以先用 `resolve --resource asset --name <资产名>` 确认唯一资产对象。",
                asset=target_value,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "资产标识匹配到多个候选对象。",
            payload=build_cli_guidance_payload(
                "ambiguous_asset",
                user_message="当前输入命中了多个资产，请改用更精确的名称、地址或直接使用资产 UUID。",
                action_hint="建议先执行 `resolve --resource asset --name <关键字>` 查看候选对象。",
                candidates=matches[:10],
            ),
        )
    return matches[0]

def _resolve_account(
    target: str | None = None,
    *,
    discovery=None,
) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    accounts = active_discovery.list_accounts()
    target_value = str(target or "").strip()
    if target_value and is_uuid_like(target_value):
        for item in accounts:
            if str(item.get("id")) == target_value:
                return item
    parsed_display = _parse_display_style_account(target_value)
    if parsed_display is not None:
        wanted_username = _lower(parsed_display.get("username"))
        wanted_name = _lower(parsed_display.get("name"))
        matches = [
            item
            for item in accounts
            if wanted_username
            and _lower(item.get("username")) == wanted_username
            and (not wanted_name or _lower(item.get("name")) == wanted_name)
        ]
    else:
        wanted = _lower(target_value)
        matches = [item for item in accounts if wanted and wanted in {_lower(item.get("username")), _lower(item.get("name"))}]
    if not matches:
        raise CLIError(
            "无法解析资产账号标识。",
            payload=build_cli_guidance_payload(
                "account_not_found",
                user_message="当前组织下找不到你指定的资产账号，请改用更精确的账号名称、用户名或账号 UUID。",
                action_hint="如果页面里看到的是 `名称(username)`，建议直接按这个格式输入。",
                account=target_value,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "资产账号标识匹配到多个候选对象。",
            payload=build_cli_guidance_payload(
                "ambiguous_account",
                user_message="当前输入命中了多个资产账号，请改用更精确的 `名称(username)` 或直接使用账号 UUID。",
                action_hint="如果已知页面显示值，建议直接输入完整的 `名称(username)`。",
                candidates=matches[:10],
            ),
        )
    return matches[0]

def command_records(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    records = _fetch_command_records(payload)
    if not records:
        return _with_command_storage_context(_empty_result("No command records matched the current filters.", payload), payload)
    risk_counter = Counter()
    user_counter = Counter()
    asset_counter = Counter()
    for item in records:
        risk_counter[str(_first_field(item, "risk_level", "risk_level_display") or "unknown")] += 1
        user_counter[_extract_user(item) or "unknown"] += 1
        asset_counter[_extract_asset(item) or "unknown"] += 1
    return _with_command_storage_context(
        {
            "summary": {
                "total": len(records),
                "risk_levels": _top(risk_counter),
                "top_users": _top(user_counter),
                "top_assets": _top(asset_counter),
            },
            "records": records,
        },
        payload,
    )

def high_risk_commands(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    payload.setdefault("risk_level", 4)
    return command_records(payload)

def session_records(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    records = _fetch_session_records(payload)
    if not records:
        return _with_org_context(_empty_result("No session records matched the current filters.", payload))
    protocol_counter = Counter()
    asset_counter = Counter()
    user_counter = Counter()
    durations = []
    for item in records:
        protocol_counter[_extract_protocol(item) or "unknown"] += 1
        asset_counter[_extract_asset(item) or "unknown"] += 1
        user_counter[_extract_user(item) or "unknown"] += 1
        duration = _extract_duration(item)
        if duration is not None:
            durations.append(duration)
    return _with_org_context(
        {
            "summary": {
                "total": len(records),
                "top_protocols": _top(protocol_counter),
                "top_assets": _top(asset_counter),
                "top_users": _top(user_counter),
                "average_duration_seconds": round(sum(durations) / len(durations), 2) if durations else None,
            },
            "records": records,
        }
    )

def file_transfer_logs(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    records = _fetch_file_transfer_records(payload)
    if not records:
        return _with_org_context(_empty_result("No file transfer records matched the current filters.", payload))
    direction_counter = Counter()
    user_counter = Counter()
    asset_counter = Counter()
    for item in records:
        direction_counter[_extract_direction(item) or "unknown"] += 1
        user_counter[_extract_user(item) or "unknown"] += 1
        asset_counter[_extract_asset(item) or "unknown"] += 1
    return _with_org_context(
        {
            "summary": {
                "total": len(records),
                "directions": _top(direction_counter),
                "top_users": _top(user_counter),
                "top_assets": _top(asset_counter),
            },
            "records": records,
        }
    )

def file_transfer_risk(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    keyword = payload.get("keyword")
    if not keyword:
        payload["keyword"] = ".sh .sql .pem .key .zip .tar .gz"
    return file_transfer_logs(payload)

def _is_failed_login(item: dict[str, Any]) -> bool:
    raw_status = _string_value(_first_field(item, "status")).strip().lower()
    if raw_status == "0":
        return True
    if raw_status == "1":
        return False
    haystack = " ".join(
        [
            _extract_status(item),
            _string_value(_first_field(item, "reason", "detail", "type")),
        ]
    ).lower()
    return any(token in haystack for token in ("fail", "failed", "auth_err", "error", "denied", "block", "失败", "错误", "拒绝", "锁定"))

def _login_records(filters: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _normalize_login_audit_filters(_normalize_time_filters(filters))
    records = _apply_common_filters(_fetch_list("/api/v1/audits/login-logs/", payload), payload)
    return records

def abnormal_logins(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    start_hour = int(payload.get("hour_start") or 0)
    end_hour = int(payload.get("hour_end") or 6)
    records = []
    for item in _login_records(payload):
        timestamp = _extract_datetime(item)
        if timestamp is None:
            continue
        hour = timestamp.astimezone(timezone.utc).hour
        if start_hour <= hour < end_hour:
            records.append(item)
    if not records:
        return _with_org_context(_empty_result("No abnormal-hour logins matched the current filters.", payload))
    ip_counter = Counter(_extract_source_ip(item) or "unknown" for item in records)
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    return _with_org_context(
        {
            "summary": {
                "total": len(records),
                "top_source_ips": _top(ip_counter),
                "top_users": _top(user_counter),
                "hour_window": {"start": start_hour, "end": end_hour},
            },
            "records": records,
        }
    )

def login_source_ip(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    records = _login_records(payload)
    if payload.get("source_ip"):
        records = [item for item in records if _match_text(_extract_source_ip(item), payload["source_ip"])]
    if not records:
        return _with_org_context(_empty_result("No login records matched the current source IP filters.", payload))
    ip_counter = Counter(_extract_source_ip(item) or "unknown" for item in records)
    success_counter = Counter()
    for item in records:
        label = "failed" if _is_failed_login(item) else "success"
        success_counter[label] += 1
    return _with_org_context(
        {
            "summary": {
                "total": len(records),
                "top_source_ips": _top(ip_counter),
                "status_distribution": _top(success_counter),
            },
            "records": records,
        }
    )

def failed_login_statistics(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters)
    records = [item for item in _login_records(payload) if _is_failed_login(item)]
    if not records:
        return _with_org_context(_empty_result("No failed logins matched the current filters.", payload))
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    ip_counter = Counter(_extract_source_ip(item) or "unknown" for item in records)
    asset_counter = Counter(_extract_asset(item) or "unknown" for item in records)
    return _with_org_context(
        {
            "summary": {
                "total": len(records),
                "top_users": _top(user_counter, limit=int(payload.get("top") or 10)),
                "top_source_ips": _top(ip_counter, limit=int(payload.get("top") or 10)),
                "top_assets": _top(asset_counter, limit=int(payload.get("top") or 10)),
            },
            "records": records,
        }
    )

def sensitive_asset_access(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    asset_keyword = payload.get("asset") or payload.get("asset_keywords")
    if not asset_keyword:
        raise CLIError("Sensitive asset access queries require asset or asset_keywords filters, e.g. {\"asset_keywords\":\"192.0.2.12\",\"date_from\":\"2026-03-01 00:00:00\",\"date_to\":\"2026-03-21 23:59:59\"}.")
    return session_records(payload)

def _drop_sampling_filters(payload: dict[str, Any]) -> dict[str, Any]:
    server_payload = dict(payload)
    server_payload.pop("limit", None)
    server_payload.pop("offset", None)
    server_payload.pop("top", None)
    return server_payload

def _normalize_match_key(value: Any) -> str:
    return _lower(_simplify_display_name(value))

def _merge_last_seen(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current

def _is_high_privilege_name(value: Any) -> bool:
    return _normalize_match_key(value) in {"root", "administrator", "dba", "sa"}

def _top_usage_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    return [{"name": item["account"], "count": item["usage_count"]} for item in rows[:limit] if item.get("account")]

def _high_privilege_account_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    final = []
    for item in rows:
        if item.get("privileged"):
            final.append({**item, "privilege_source": "privileged_field"})
            continue
        if _is_high_privilege_name(item.get("account")):
            final.append({**item, "privilege_source": "name_rule"})
    return final

def privileged_account_usage(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters, default_days=int(filters.get("days") or 30))
    rows = [item for item in _high_privilege_account_rows(_account_activity_rows(payload)) if item["usage_count"] > 0]
    if not rows:
        return _with_org_context(_empty_result("No privileged account activity matched the current filters.", payload))
    total_commands = sum(item["command_count"] for item in rows)
    total_sessions = sum(item["session_count"] for item in rows)
    return _with_org_context(
        {
            "summary": {
                "total": len(rows),
                "total_privileged_accounts_with_activity": len(rows),
                "total_commands": total_commands,
                "total_sessions": total_sessions,
                "top_accounts": _top_usage_rows(rows, limit=int(payload.get("top") or 10)),
            },
            "records": rows,
        }
    )

def _account_activity_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    rows_by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_account_asset: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in _build_account_rows(payload):
        row = {
            "id": item.get("id"),
            "account": item["name"],
            "username": item.get("username"),
            "asset": item.get("asset"),
            "privileged": item.get("privileged"),
            "is_active": item.get("is_active"),
            "template": item.get("template"),
            "source": item.get("source"),
            "source_id": item.get("source_id"),
            "command_count": 0,
            "session_count": 0,
            "usage_count": 0,
            "last_seen": None,
            "never_seen": True,
        }
        rows.append(row)
        account_keys = {_normalize_match_key(item.get("name")), _normalize_match_key(item.get("username"))}
        asset_key = _normalize_match_key(item.get("asset"))
        for account_key in [value for value in account_keys if value]:
            rows_by_account[account_key].append(row)
            if asset_key:
                rows_by_account_asset[(account_key, asset_key)].append(row)

    activity_payload = _drop_sampling_filters(payload)

    def _resolve_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
        account_key = _normalize_match_key(_extract_account(record))
        if not account_key:
            return []
        asset_key = _normalize_match_key(_extract_asset(record))
        if asset_key:
            exact_matches = rows_by_account_asset.get((account_key, asset_key), [])
            if exact_matches:
                return exact_matches
        name_matches = rows_by_account.get(account_key, [])
        if len(name_matches) == 1:
            return name_matches
        return []

    for item in _fetch_command_records(activity_payload):
        timestamp = _extract_datetime(item)
        for row in _resolve_rows(item):
            row["command_count"] += 1
            row["usage_count"] += 1
            row["last_seen"] = _merge_last_seen(row["last_seen"], timestamp)
            row["never_seen"] = False

    for item in _fetch_session_records(activity_payload):
        timestamp = _extract_datetime(item)
        for row in _resolve_rows(item):
            row["session_count"] += 1
            row["usage_count"] += 1
            row["last_seen"] = _merge_last_seen(row["last_seen"], timestamp)
            row["never_seen"] = False

    rows.sort(
        key=lambda item: (
            item["usage_count"],
            item["last_seen"] or datetime.fromtimestamp(0, tz=timezone.utc),
            item["account"],
        ),
        reverse=True,
    )
    return rows

def _build_account_rows(payload: dict[str, Any], accounts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    payload = dict(payload)
    if payload.get("privileged") not in {None, ""}:
        payload["privileged"] = parse_strict_bool(payload["privileged"], field_name="privileged")
    if payload.get("is_active") not in {None, ""}:
        payload["is_active"] = parse_strict_bool(payload["is_active"], field_name="is_active")
    accounts = list(accounts or _fetch_list("/api/v1/accounts/accounts/", _account_inventory_filters(payload)))
    rows = []
    for item in accounts:
        row = {
            "id": item.get("id"),
            "name": _extract_account(item),
            "asset": _extract_asset(item),
            "username": _string_value(_first_field(item, "username")),
            "privileged": parse_bool(item.get("privileged")),
            "is_active": item.get("is_active"),
            "template": _first_field(item, "template.name", "template", "source_id"),
            "source": _string_value(_first_field(item, "source.value", "source.label", "source")),
            "source_id": _string_value(_first_field(item, "source_id", "template.id", "source.id")),
        }
        if payload.get("account") and not _match_text(row["name"], payload["account"]):
            continue
        if payload.get("asset") and not _match_text(row["asset"], payload["asset"]):
            continue
        if payload.get("privileged") not in {None, ""} and row["privileged"] != payload["privileged"]:
            continue
        if payload.get("is_active") not in {None, ""} and bool(row["is_active"]) != payload["is_active"]:
            continue
        rows.append(row)
    return rows

def frequent_operation_users(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters, default_days=30)
    records = _fetch_command_records(payload)
    counter = Counter()
    last_seen: dict[str, datetime] = {}
    assets_by_user = defaultdict(set)
    for item in records:
        user = _extract_user(item) or "unknown"
        counter[user] += 1
        assets_by_user[user].add(_extract_asset(item) or "unknown")
        timestamp = _extract_datetime(item)
        if timestamp and (user not in last_seen or timestamp > last_seen[user]):
            last_seen[user] = timestamp
    rows = []
    for user, count in counter.most_common():
        rows.append(
            {
                "user": user,
                "command_count": count,
                "asset_count": len(assets_by_user[user]),
                "last_seen": last_seen.get(user),
            }
        )
    return _with_org_context(
        {
            "summary": {
                "total_users": len(counter),
                "total_commands": len(records),
                "ranking": rows[: int(payload.get("top") or 20)],
            },
            "records": rows,
        }
    )

def session_behavior_statistics(filters: dict[str, Any]) -> dict[str, Any]:
    return session_records(filters)

def suspicious_operation_summary(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_time_filters(filters, default_days=7)
    high_risk = high_risk_commands(payload)
    abnormal_login = abnormal_logins(payload)
    transfer_risk = file_transfer_risk(payload)
    records = [
        {
            "type": "high_risk_commands",
            "count": high_risk.get("summary", {}).get("total", len(high_risk.get("records", []))),
            "samples": high_risk.get("records", []),
        },
        {
            "type": "abnormal_hour_logins",
            "count": abnormal_login.get("summary", {}).get("total", len(abnormal_login.get("records", []))),
            "samples": abnormal_login.get("records", []),
        },
        {
            "type": "risky_file_transfers",
            "count": transfer_risk.get("summary", {}).get("total", len(transfer_risk.get("records", []))),
            "samples": transfer_risk.get("records", []),
        },
    ]
    total = sum(item["count"] for item in records)
    return _with_org_context({"summary": {"suspicious_event_count": total, "dimensions": len(records)}, "records": records})

def session_dimension_analysis(filters: dict[str, Any], dimension: str) -> dict[str, Any]:
    payload = _normalize_time_filters(filters, default_days=30)
    records = _fetch_session_records(payload)
    counter = Counter()
    duration_totals = Counter()
    for item in records:
        key = _extract_user(item) if dimension == "user" else _extract_asset(item)
        key = key or "unknown"
        counter[key] += 1
        duration = _extract_duration(item)
        if duration is not None:
            duration_totals[key] += duration
    rows = []
    for key, count in counter.most_common():
        rows.append(
            {
                dimension: key,
                "session_count": count,
                "average_duration_seconds": round(duration_totals[key] / count, 2) if count and duration_totals[key] else None,
            }
        )
    return _with_org_context(
        {
            "summary": {
                "total_groups": len(counter),
                "dimension": dimension,
                "ranking": rows[: int(payload.get("top") or 20)],
            },
            "records": rows,
        }
    )

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

HANDLERS = {
    "command_records": command_records,
    "session_records": session_records,
    "file_transfer_logs": file_transfer_logs,
    "high_risk_commands": high_risk_commands,
    "sensitive_asset_access": sensitive_asset_access,
    "abnormal_logins": abnormal_logins,
    "login_source_ip": login_source_ip,
    "failed_login_statistics": failed_login_statistics,
    "privileged_account_usage": privileged_account_usage,
    "file_transfer_risk": file_transfer_risk,
    "session_behavior_statistics": session_behavior_statistics,
    "frequent_operation_users": frequent_operation_users,
    "suspicious_operation_summary": suspicious_operation_summary,
    "user_session_analysis": lambda filters: session_dimension_analysis(filters, "user"),
    "asset_session_analysis": lambda filters: session_dimension_analysis(filters, "asset"),
}
