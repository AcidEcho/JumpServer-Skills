from __future__ import annotations

from collections import Counter
from contextlib import suppress
from datetime import date, datetime, timedelta
from html import escape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import time
import tempfile
from typing import Any
import uuid

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    try:
        from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover
        ZoneInfo = None  # type: ignore[assignment]
        ZoneInfoNotFoundError = None  # type: ignore[assignment]

from jms_audit_core import (
    LOGIN_LOGS_PATH,
    OPERATE_LOGS_PATH,
    _apply_common_filters,
    _extract_account,
    _extract_asset,
    _extract_datetime,
    _extract_direction,
    _extract_duration,
    _extract_protocol,
    _extract_resource_type,
    _extract_source_ip,
    _extract_status,
    _extract_user,
    _fetch_command_records,
    _fetch_file_transfer_records,
    _fetch_list,
    _fetch_session_records,
    _first_field,
    _is_failed_login,
    _list_request_filters,
    _login_records,
    _normalize_login_audit_filters,
    _normalize_operate_audit_filters,
    _normalize_time_filters,
    _org_id_from_filters,
    _string_value,
    parse_date_value,
    parse_datetime_value,
    resolve_command_storage_context,
    suspicious_operation_summary,
)
from jms_runtime_queries import license_detail_query
from jumpserver_common.jms_runtime import (
    CLIError,
    GLOBAL_ORG_ID,
    build_cli_guidance_payload,
    create_client,
    list_accessible_orgs,
    parse_bool,
    persist_selected_org,
)


SKILL_DIR = Path(__file__).resolve().parents[3]
REPORT_TEMPLATE_PATH = SKILL_DIR / "template" / "bastion-daily-usage-template.html"
REPORT_METADATA_PATH = SKILL_DIR / "subskills" / "query" / "references" / "metadata" / "daily_usage_report_template_fields.json"
REPORT_PREPARED_DIR = SKILL_DIR / "reports" / "prepared"
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
DATE_COMPACT_RE = re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})$")
DATE_CN_RE = re.compile(r"^(?:(?P<year>\d{4})\s*年)?\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*[日号]$")
EMPTY_TEXT = "暂无数据"
if ZoneInfo is None:
    SHANGHAI_TZ = None
else:
    try:
        SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:  # pragma: no cover
        SHANGHAI_TZ = None
TEXT_CONTRACT = "text"
TBODY_ROWS_CONTRACT = "tbody_rows"
REQUIRED_KEY_FIELDS = ("login_total", "login_failed", "session_total", "risk_event_total")
SKILL_SUMMARY_FIELDS = (
    "risk_login_analysis",
    "risk_command_analysis",
    "risk_transfer_analysis",
    "high_risk_operation_analysis",
    "risk_action",
    "command_summary",
    "command_compliance_analysis",
    "file_transfer_summary",
)
REPORT_RUNTIME_REQUIRED_FIELDS = (
    "output_path",
    "output_exists",
    "output_size_bytes",
    "output_size_human",
    "template_path",
    "metadata_path",
    "effective_org",
    "switchable_orgs",
    "queried_command_storage_ids",
    "queried_command_storage_count",
    "report_date",
    "date_from",
    "date_to",
    "validation_summary",
)
SESSION_ERROR_REASON_LABEL_MAP = {
    "Connect failed": "连接失败",
    "connect_failed": "连接失败",
    "Replay unsupported": "不支持回放",
    "replay_unsupported": "不支持回放",
}
CHINESE_TEXT_RE = re.compile(r"[\u4e00-\u9fff]")
COMPONENT_PREFIX_RE = re.compile(r"^\[([^\[\]]+)\]")
LOGIN_REMAINING_TRIES_RE = re.compile(r"try\s+(\d+)\s+times?", re.IGNORECASE)
LOGIN_LOCKED_REASON_TEXT = "账号已锁定，请联系管理员解锁或 5 分钟后重试"
LOGIN_INVALID_CREDENTIALS_TEXT = "用户名或密码错误"
REPORT_ORG_SELECTION_REASON_CODE = "report_organization_not_accessible"
REPORT_DATE_ARGUMENT_REASON_CODE = "invalid_report_date_arguments"
REPORT_LOGIN_SLICE_FETCH_REASON_CODE = "login_time_slice_fetch_failed"
LOGIN_DIRECT_WINDOW_DAYS = 31
LOGIN_TIME_SLICE_DAYS = 7
LOGIN_THROTTLE_RETRY_DELAYS = (2.0, 4.0, 8.0, 16.0, 30.0)
LOGIN_RETRY_MAX_ATTEMPTS = 8
LOGIN_RETRY_MAX_ELAPSED_SECONDS = 90.0
REPORT_MAX_WINDOW_DAYS = 366
REPORT_FETCH_RECORD_LIMIT = 50000
REPORT_STORED_RECORD_LIMIT = 200
REPORT_MAX_LOGIN_PAGES = 250
REPORT_PREPARED_MAX_BYTES = 32 * 1024 * 1024
REPORT_SUMMARY_MAX_BYTES = 1024 * 1024
REPORT_SCHEMA_VERSION = 2
REPORT_ARTIFACT_TOKEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-f0-9]{16}-[A-Za-z0-9_-]{4,64}$")
LEGACY_PREPARED_NAME_RE = re.compile(r"^JumpServer-\d{4}-\d{2}-\d{2}\.prepared\.json$")
SENSITIVE_FILE_SUFFIXES = (".sh", ".sql", ".pem", ".key", ".zip", ".tar", ".gz", ".tar.gz")
STORED_RECORD_KEYS = {"records", "failed_records", "risky_records"}


def _local_now() -> datetime:
    if SHANGHAI_TZ is not None:
        return datetime.now(SHANGHAI_TZ)
    return datetime.now().astimezone()


def load_report_metadata() -> dict[str, Any]:
    payload = json.loads(REPORT_METADATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CLIError("Report metadata must be a JSON object.")
    return payload


def load_report_template() -> str:
    return REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _default_report_output_path(report_date: str, artifact_token: str | None = None) -> Path:
    date_token = str(report_date or "").strip() or _local_now().date().isoformat()
    name_token = str(artifact_token or "").strip() or date_token
    return SKILL_DIR / "reports" / ("JumpServer-%s.html" % name_token)


def _default_prepared_output_path(report_date: str, artifact_token: str | None = None) -> Path:
    date_token = str(report_date or "").strip() or _local_now().date().isoformat()
    name_token = str(artifact_token or "").strip() or date_token
    return REPORT_PREPARED_DIR / ("JumpServer-%s.prepared.json" % name_token)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _context_identity(context: dict[str, Any]) -> dict[str, Any]:
    runtime_context = context.get("runtime_context") if isinstance(context.get("runtime_context"), dict) else {}
    org_context = context.get("org_context") if isinstance(context.get("org_context"), dict) else {}
    effective_org = org_context.get("effective_org") if isinstance(org_context.get("effective_org"), dict) else {}
    return {
        "org_id": str(org_context.get("target_org_id") or effective_org.get("id") or "").strip(),
        "date_from": str(runtime_context.get("date_from") or "").strip(),
        "date_to": str(runtime_context.get("date_to") or "").strip(),
        "command_storage_id": str(context.get("command_storage_id") or "").strip() or None,
    }


def _bind_report_state(state: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
    payload = dict(state)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    identity = _context_identity(context)
    context_id = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:16]
    run_token = str(run_id or uuid.uuid4().hex[:12]).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", run_token):
        raise CLIError("Invalid report run id.", payload={"reason_code": "invalid_report_run_id"})
    runtime_context = context.get("runtime_context") if isinstance(context.get("runtime_context"), dict) else {}
    report_date = str(runtime_context.get("report_date") or "").strip()
    summary_input = dict(payload.get("summary_input") or {})
    summary_report = dict(summary_input.get("report") or {})
    summary_report["context_id"] = context_id
    summary_report["run_id"] = run_token
    summary_input["report"] = summary_report
    payload["summary_input"] = summary_input
    payload["schema_version"] = REPORT_SCHEMA_VERSION
    binding = {
        "context_id": context_id,
        "run_id": run_token,
        "artifact_token": "%s-%s-%s" % (report_date, context_id, run_token),
        "context": identity,
        "summary_input_sha256": hashlib.sha256(_canonical_json(summary_input).encode("utf-8")).hexdigest(),
    }
    payload["artifact_binding"] = binding
    digest_payload = dict(payload)
    digest_payload.pop("artifact_binding", None)
    binding["prepared_sha256"] = hashlib.sha256(_canonical_json(digest_payload).encode("utf-8")).hexdigest()
    return payload


def _format_output_size_human(size_bytes: int) -> str:
    size = float(max(int(size_bytes or 0), 0))
    if size < 1024:
        return "%d B" % int(size)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        size /= 1024.0
        if size < 1024.0 or unit == "PB":
            return "%.1f %s" % (size, unit)
    return "%.1f PB" % size


def _collect_report_artifact_metadata(output_path: Path) -> dict[str, Any]:
    try:
        output_exists = output_path.exists() and output_path.is_file()
    except OSError:
        output_exists = False
    output_size_bytes = 0
    if output_exists:
        try:
            output_size_bytes = int(output_path.stat().st_size or 0)
        except OSError:
            output_exists = False
            output_size_bytes = 0
    return {
        "output_exists": output_exists,
        "output_size_bytes": output_size_bytes,
        "output_size_human": _format_output_size_human(output_size_bytes),
    }


def extract_template_fields(template_html: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(template_html)))


def _normalize_report_org_context(org_id: str | None, org_name: str | None = None) -> dict[str, Any]:
    requested_org_id = str(org_id or "").strip()
    requested_org_name = str(org_name or "").strip()
    if requested_org_id and requested_org_name:
        raise CLIError(
            "报告组织参数冲突。",
            payload=build_cli_guidance_payload(
                REPORT_DATE_ARGUMENT_REASON_CODE,
                user_message="报告生成只能使用 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                org_id=requested_org_id,
                org_name=requested_org_name,
            ),
        )
    accessible_orgs = list_accessible_orgs()
    if requested_org_id:
        matches = [item for item in accessible_orgs if str(item.get("id") or "").strip() == requested_org_id]
    elif requested_org_name:
        wanted = requested_org_name.lower()
        matches = [item for item in accessible_orgs if str(item.get("name") or "").strip().lower() == wanted]
    else:
        matches = [item for item in accessible_orgs if str(item.get("id") or "").strip() == GLOBAL_ORG_ID]

    if not matches:
        raise CLIError(
            "当前环境下无法访问目标报告组织。",
            payload=build_cli_guidance_payload(
                REPORT_ORG_SELECTION_REASON_CODE,
                user_message="当前账号下找不到你指定的报告组织，请先确认可访问组织范围。",
                action_hint="可以先执行 `python3 subskills/common/scripts/jms_common.py ping` 查看 `candidate_orgs`，再改用精确的 `--org-id` 或 `--org-name`。",
                org_id=requested_org_id or None,
                org_name=requested_org_name or None,
                candidate_orgs=accessible_orgs,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "给定的报告组织名称匹配到多个候选组织。",
            payload=build_cli_guidance_payload(
                REPORT_ORG_SELECTION_REASON_CODE,
                user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称或直接使用 `--org-id`。",
                action_hint="建议先从 `candidate_orgs` 中复制准确的 org_id。",
                org_name=requested_org_name or None,
                candidate_orgs=matches[:10],
            ),
        )
    selected = matches[0]
    target_org_id = str(selected.get("id") or "").strip() or GLOBAL_ORG_ID
    effective_org = dict(selected)
    explicit_org = bool(requested_org_id or requested_org_name)
    effective_org["source"] = "explicit" if explicit_org else "report_default_global"
    switchable_orgs = [
        item
        for item in accessible_orgs
        if str(item.get("id") or "").strip() and str(item.get("id") or "").strip() != target_org_id
    ]
    return {
        "effective_org": effective_org,
        "switchable_orgs": switchable_orgs,
        "switchable_org_count": len(switchable_orgs),
        "candidate_orgs": accessible_orgs,
        "target_org_id": target_org_id,
        "env_update": None,
    }


def _parse_date_expr(value: str, *, reference_date: date) -> date:
    text = str(value or "").strip()
    compact = text.replace(" ", "")
    if not compact:
        raise CLIError("Date expression is required.")
    if compact == "昨天":
        return reference_date - timedelta(days=1)
    parsed_date = parse_date_value(compact)
    if parsed_date is not None:
        return parsed_date
    match = DATE_COMPACT_RE.fullmatch(compact)
    if match:
        return date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
    match = DATE_CN_RE.fullmatch(compact)
    if match:
        year = int(match.group("year") or reference_date.year)
        return date(year, int(match.group("month")), int(match.group("day")))
    raise CLIError("Unsupported date expression: %s" % value)


def _parse_datetime_expr(value: str, *, end_of_day: bool = False) -> datetime:
    text = str(value or "").strip()
    parsed = parse_datetime_value(text, naive_tz=SHANGHAI_TZ)
    if parsed is not None:
        if SHANGHAI_TZ is not None:
            return parsed.astimezone(SHANGHAI_TZ)
        return parsed.astimezone() if parsed.tzinfo is None else parsed.astimezone()
    parsed_date = _parse_date_expr(text, reference_date=_local_now().date())
    hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
    parsed = datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, second)
    return parsed.replace(tzinfo=SHANGHAI_TZ) if SHANGHAI_TZ else parsed.astimezone()


def _normalize_time_window(
    *,
    date_expr: str | None,
    period_expr: str | None,
    date_from_expr: str | None,
    date_to_expr: str | None,
) -> dict[str, str]:
    now = _local_now()
    modes = sum(
        [
            bool(str(date_expr or "").strip()),
            bool(str(period_expr or "").strip()),
            bool(str(date_from_expr or "").strip() or str(date_to_expr or "").strip()),
        ]
    )
    if modes != 1:
        raise CLIError(
            "报告时间参数不完整或互相冲突。",
            payload=build_cli_guidance_payload(
                REPORT_DATE_ARGUMENT_REASON_CODE,
                user_message="`daily-usage-prepare` 只能三选一：`--date`、`--period`、或 `--date-from + --date-to`。",
                action_hint="请只保留一种时间写法后重试。",
                suggested_commands=[
                    "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --date 20260310",
                    "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --period 上周",
                    "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --date-from '2026-03-10 00:00:00' --date-to '2026-03-24 23:59:59'",
                ],
            ),
        )

    if str(date_from_expr or "").strip() or str(date_to_expr or "").strip():
        if not str(date_from_expr or "").strip() or not str(date_to_expr or "").strip():
            raise CLIError(
                "显式时间范围参数不完整。",
                payload=build_cli_guidance_payload(
                    REPORT_DATE_ARGUMENT_REASON_CODE,
                    user_message="显式时间范围必须同时提供 `--date-from` 和 `--date-to`。",
                    action_hint="请把开始时间和结束时间成对传入。",
                    suggested_commands=[
                        "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --date-from '2026-03-10 00:00:00' --date-to '2026-03-24 23:59:59'",
                    ],
                ),
            )
        date_from = _parse_datetime_expr(str(date_from_expr), end_of_day=False)
        date_to = _parse_datetime_expr(str(date_to_expr), end_of_day=True)
    elif str(date_expr or "").strip():
        parsed_date = _parse_date_expr(str(date_expr), reference_date=now.date())
        date_from = datetime(parsed_date.year, parsed_date.month, parsed_date.day, 0, 0, 0, tzinfo=now.tzinfo)
        date_to = datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, tzinfo=now.tzinfo)
    else:
        period = str(period_expr or "").strip()
        if period == "上周":
            this_week_start = now.date() - timedelta(days=now.date().weekday())
            period_start = this_week_start - timedelta(days=7)
            period_end = period_start + timedelta(days=6)
        elif period == "本月":
            period_start = now.date().replace(day=1)
            period_end = now.date()
        else:
            raise CLIError(
                "暂不支持的周期表达：%s" % period,
                payload=build_cli_guidance_payload(
                    REPORT_DATE_ARGUMENT_REASON_CODE,
                    user_message="当前 `--period` 只支持 `上周` 和 `本月`。",
                    action_hint="请改用支持的周期表达，或改用 `--date` / `--date-from` + `--date-to`。",
                ),
            )
        date_from = datetime(period_start.year, period_start.month, period_start.day, 0, 0, 0, tzinfo=now.tzinfo)
        date_to = datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=now.tzinfo)

    if date_to < date_from:
        raise CLIError(
            "报告时间范围非法。",
            payload=build_cli_guidance_payload(
                REPORT_DATE_ARGUMENT_REASON_CODE,
                user_message="`date_to` 必须大于或等于 `date_from`。",
                action_hint="请检查开始时间和结束时间是否写反。",
            ),
        )

    if date_to - date_from > timedelta(days=REPORT_MAX_WINDOW_DAYS):
        raise CLIError(
            "报告时间范围过大。",
            payload=build_cli_guidance_payload(
                REPORT_DATE_ARGUMENT_REASON_CODE,
                user_message="单次报告时间范围不能超过 %s 天。" % REPORT_MAX_WINDOW_DAYS,
                action_hint="请缩小时间范围并分批生成报告。",
                max_window_days=REPORT_MAX_WINDOW_DAYS,
            ),
        )

    report_date = date_to.date().isoformat()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "report_date": report_date,
        "date_from": date_from.strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": date_to.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_at": generated_at,
        "current_date": generated_at,
    }


def _unwrap_single_result_layers(payload: Any) -> Any:
    current = payload
    while isinstance(current, dict) and "result" in current:
        other_keys = [key for key in current if key not in {"ok", "result"}]
        if other_keys:
            break
        current = current.get("result")
    return current


def _extract_city(item: dict[str, Any]) -> str:
    return _string_value(
        _first_field(
            item,
            "city",
            "city_display",
            "location",
            "location_display",
            "geoip.city",
            "addr_city",
            "detail.city",
        )
    ).strip()


def _extract_reason(item: dict[str, Any]) -> str:
    return _string_value(
        _first_field(
            item,
            "error_reason.label",
            "error_reason.value",
            "error_reason",
            "reason",
            "detail",
            "message",
            "error",
            "type",
        )
    ).strip()


def _extract_session_error_reason(item: dict[str, Any]) -> str:
    return _string_value(_first_field(item, "error_reason.label", "error_reason.value")).strip()


def _display_session_error_reason(item: dict[str, Any]) -> str:
    label = _string_value(_first_field(item, "error_reason.label")).strip()
    value = _string_value(_first_field(item, "error_reason.value")).strip()
    if label:
        if CHINESE_TEXT_RE.search(label):
            return label
        return SESSION_ERROR_REASON_LABEL_MAP.get(label, label)
    if value:
        return SESSION_ERROR_REASON_LABEL_MAP.get(value, value)
    return ""


def _extract_bracket_component(value: Any) -> str:
    text = _string_value(value).strip()
    if not text:
        return ""
    match = COMPONENT_PREFIX_RE.match(text)
    if match:
        component = str(match.group(1) or "").strip()
        if component:
            return component
    return text


def _extract_component(item: dict[str, Any]) -> str:
    for candidate in (
        "terminal_display",
        "terminal.name",
        "terminal",
        "component",
        "component_display",
        "terminal_name",
        "terminal.type",
        "terminal_type",
    ):
        value = _first_field(item, candidate)
        if value in {None, ""}:
            continue
        component = _extract_bracket_component(value)
        if component:
            return component
    return ""


def _extract_login_failure_reason(item: dict[str, Any]) -> str:
    return _string_value(
        _first_field(
            item,
            "reason",
            "detail",
            "message",
            "error",
            "type.label",
            "type.value",
            "type",
        )
    ).strip()


def _display_login_failure_reason(item: dict[str, Any]) -> str:
    raw_reason = _extract_login_failure_reason(item)
    if not raw_reason:
        return ""
    if CHINESE_TEXT_RE.search(raw_reason):
        return raw_reason
    lowered = raw_reason.lower()
    if "account has been locked" in lowered:
        return LOGIN_LOCKED_REASON_TEXT
    if "username or password" in lowered and ("incorrect" in lowered or "wrong" in lowered):
        match = LOGIN_REMAINING_TRIES_RE.search(raw_reason)
        if match:
            return "%s，还可再尝试 %s 次" % (LOGIN_INVALID_CREDENTIALS_TEXT, match.group(1))
        return LOGIN_INVALID_CREDENTIALS_TEXT
    return raw_reason


def _display_login_failure_status(_: dict[str, Any]) -> str:
    return "失败"


def _extract_command_text(item: dict[str, Any]) -> str:
    return _string_value(
        _first_field(
            item,
            "input",
            "command",
            "command_text",
            "cmd",
            "content",
            "output",
        )
    ).strip()


def _looks_failed_session(item: dict[str, Any]) -> bool:
    if _extract_session_error_reason(item):
        return True
    return not parse_bool(item.get("is_success"), default=True)


def _session_failure_status(item: dict[str, Any]) -> str:
    if _looks_failed_session(item):
        return "失败"
    status = _extract_status(item)
    return status or EMPTY_TEXT


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value.astimezone(SHANGHAI_TZ) if SHANGHAI_TZ and value.tzinfo else value
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    if value in {None, ""}:
        return EMPTY_TEXT
    text = str(value).strip()
    try:
        parsed = _extract_datetime({"date_from": text})
    except Exception:  # noqa: BLE001
        parsed = None
    if parsed is not None:
        return _format_datetime(parsed)
    return text


def _format_duration(value: Any) -> str:
    if value in {None, ""}:
        return EMPTY_TEXT
    try:
        total_seconds = max(int(float(value)), 0)
    except (TypeError, ValueError):
        return str(value)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append("%s小时" % hours)
    if minutes:
        parts.append("%s分" % minutes)
    if seconds or not parts:
        parts.append("%s秒" % seconds)
    return "".join(parts)


def _percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return "%.2f%%" % ((float(value) / float(total)) * 100.0)


def _top_summary(counter: Counter[str], *, limit: int = 3) -> str:
    rows = []
    for key, count in counter.most_common(limit):
        label = str(key or "").strip() or "unknown"
        rows.append("%s(%s)" % (label, count))
    return " / ".join(rows) if rows else EMPTY_TEXT


def _risk_top_summary(counter: Counter[str], *, limit: int = 3) -> str:
    rows = []
    for key, count in counter.most_common(limit):
        label = str(key or "").strip() or "unknown"
        rows.append("%s(%s次)" % (label, count))
    return "、".join(rows) if rows else EMPTY_TEXT


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _risk_level_label(
    risk_event_total: int,
    login_failed: int,
    high_risk_command_total: int,
    file_transfer_total: int,
    high_risk_operation_total: int = 0,
) -> str:
    if risk_event_total >= 10 or high_risk_command_total >= 5 or login_failed >= 10 or high_risk_operation_total >= 5:
        return "高风险"
    if risk_event_total >= 3 or high_risk_command_total > 0 or high_risk_operation_total > 0 or login_failed >= 3 or file_transfer_total >= 20:
        return "中风险"
    return "低风险"


def _empty_row(colspan: int, text: str = EMPTY_TEXT) -> str:
    return '<tr class="table-empty-row"><td colspan="%s">%s</td></tr>' % (colspan, escape(text))


def _row(cells: list[Any]) -> str:
    return "<tr>%s</tr>" % "".join("<td>%s</td>" % escape(str(cell or EMPTY_TEXT)) for cell in cells)


def _render_login_rows(records: list[dict[str, Any]]) -> str:
    if not records:
        return _empty_row(4)
    user_stats: dict[str, dict[str, int]] = {}
    for item in records:
        user = _extract_user(item) or "unknown"
        stats = user_stats.setdefault(user, {"total": 0, "success": 0, "failed": 0})
        stats["total"] += 1
        if _is_failed_login(item):
            stats["failed"] += 1
        else:
            stats["success"] += 1
    sorted_rows = sorted(user_stats.items(), key=lambda item: (-item[1]["total"], item[0]))
    return "".join(
        _row(
            [
                user,
                str(stats["total"]),
                str(stats["success"]),
                str(stats["failed"]),
            ]
        )
        for user, stats in sorted_rows[:10]
    )


def _render_login_failed_rows(records: list[dict[str, Any]], *, common_ips: set[str]) -> str:
    if not records:
        return _empty_row(6)
    return "".join(
        _row(
            [
                _extract_user(item),
                _extract_city(item),
                _extract_source_ip(item),
                "是" if _extract_source_ip(item) in common_ips else "否",
                _display_login_failure_reason(item),
                _display_login_failure_status(item),
            ]
        )
        for item in records[:10]
    )


def _render_distribution_rows(counter: Counter[str], *, total: int, first_label: str, colspan: int = 3) -> str:
    if not counter:
        return _empty_row(colspan)
    rows = []
    for key, count in counter.most_common(10):
        rows.append(_row([key or first_label, count, _percent(count, total)]))
    return "".join(rows)


def _render_asset_rows(counter: Counter[str]) -> str:
    if not counter:
        return _empty_row(2)
    return "".join(_row([asset or "unknown", count]) for asset, count in counter.most_common(10))


def _render_duration_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return _empty_row(3)
    return "".join(_row([item.get("user"), item.get("asset"), _format_duration(item.get("duration_seconds"))]) for item in rows[:10])


def _render_session_failed_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return _empty_row(5)
    return "".join(
        _row(
            [
                _extract_user(item),
                _extract_asset(item),
                _extract_protocol(item),
                _display_session_error_reason(item),
                _session_failure_status(item),
            ]
        )
        for item in rows[:10]
    )


def _render_command_risk_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return _empty_row(7)
    return "".join(
        _row(
            [
                _extract_user(item),
                _extract_asset(item),
                _extract_account(item),
                _extract_command_text(item),
                _format_datetime(_extract_datetime(item)),
                _format_datetime(_first_field(item, "date_end", "date_finished", "date_to")),
                _string_value(_first_field(item, "risk_level_display", "risk_level.value", "risk_level")),
            ]
        )
        for item in rows[:10]
    )


def _normalize_direction(value: str) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("upload", "up", "上传")):
        return "upload"
    if any(token in text for token in ("download", "down", "下载")):
        return "download"
    return text or "unknown"


def _is_delete_operation(item: dict[str, Any]) -> bool:
    text = str(_extract_direction(item) or "").strip().lower()
    return text in {"delete", "删除"}


def _get_path_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _evaluate_output_expression(payload: dict[str, Any], expression: str) -> Any:
    match = re.fullmatch(r"\s*([a-zA-Z0-9_.]+)\s*-\s*([a-zA-Z0-9_.]+)\s*", expression)
    if not match:
        return _get_path_value(payload, expression)
    left = _get_path_value(payload, match.group(1))
    right = _get_path_value(payload, match.group(2))
    try:
        return int(left or 0) - int(right or 0)
    except (TypeError, ValueError):
        return None


def _normalize_license_source() -> dict[str, Any]:
    payload = _unwrap_single_result_layers(license_detail_query({}))
    records = payload.get("records") if isinstance(payload, dict) else None
    record = records[0] if isinstance(records, list) and records else {}
    return dict(record or {})


def _login_fetch_window(filters: dict[str, Any]) -> tuple[datetime, datetime] | None:
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from in {None, ""} or date_to in {None, ""}:
        return None
    start = _parse_datetime_expr(str(date_from), end_of_day=False)
    end = _parse_datetime_expr(str(date_to), end_of_day=True)
    return start, end


def _format_login_slice_datetime(value: datetime) -> str:
    dt = value.astimezone(SHANGHAI_TZ) if SHANGHAI_TZ and value.tzinfo else value
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _login_time_slices(date_from: datetime, date_to: datetime, *, days: int = LOGIN_TIME_SLICE_DAYS) -> list[dict[str, Any]]:
    slices = []
    cursor = date_from
    while cursor <= date_to:
        next_start = cursor + timedelta(days=days)
        if next_start <= date_to:
            slices.append(
                {
                    "date_from": cursor,
                    "date_to": next_start,
                    "exclusive_to": next_start,
                }
            )
            cursor = next_start
        else:
            slices.append(
                {
                    "date_from": cursor,
                    "date_to": date_to,
                    "exclusive_to": None,
                }
            )
            break
    return slices


def _login_time_slices_exclusive(date_from: datetime, exclusive_to: datetime, *, days: int) -> list[dict[str, Any]]:
    slices = []
    cursor = date_from
    while cursor < exclusive_to:
        next_start = min(cursor + timedelta(days=days), exclusive_to)
        slices.append(
            {
                "date_from": cursor,
                "date_to": next_start,
                "exclusive_to": next_start,
            }
        )
        cursor = next_start
    return slices


def _login_record_key(item: dict[str, Any]) -> tuple[Any, ...] | None:
    record_id = _string_value(_first_field(item, "id", "pk", "uuid"))
    if record_id:
        return ("id", record_id)
    return None


def _dedupe_login_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[Any, ...]] = set()
    deduped = []
    duplicate_count = 0
    for item in records:
        key = _login_record_key(item)
        if key is None:
            deduped.append(item)
            continue
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, duplicate_count


def _should_retry_login_slice_daily(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "throttled" in text or "限速" in text


class _LoginRetryBudget:
    def __init__(
        self,
        *,
        max_retries: int = LOGIN_RETRY_MAX_ATTEMPTS,
        max_elapsed_seconds: float = LOGIN_RETRY_MAX_ELAPSED_SECONDS,
    ) -> None:
        self.max_retries = max(int(max_retries), 0)
        self.max_elapsed_seconds = max(float(max_elapsed_seconds), 0.0)
        self.retry_count = 0
        self.started_at = time.monotonic()

    def consume(self, delay: float) -> None:
        elapsed = time.monotonic() - self.started_at
        if self.retry_count >= self.max_retries or elapsed + delay > self.max_elapsed_seconds:
            raise CLIError(
                "登录日志重试预算已耗尽。",
                payload=build_cli_guidance_payload(
                    REPORT_LOGIN_SLICE_FETCH_REASON_CODE,
                    user_message="登录日志服务持续限速，已停止重试。",
                    action_hint="请稍后重试或缩小时间窗。",
                    retry_count=self.retry_count,
                    max_retries=self.max_retries,
                    max_elapsed_seconds=self.max_elapsed_seconds,
                ),
            )
        self.retry_count += 1


def _retry_delay(retry_count: int) -> float:
    return LOGIN_THROTTLE_RETRY_DELAYS[min(retry_count, len(LOGIN_THROTTLE_RETRY_DELAYS) - 1)]


def _login_page_with_backoff(
    client: Any,
    params: dict[str, Any],
    *,
    retry_budget: _LoginRetryBudget | None = None,
) -> Any:
    budget = retry_budget or _LoginRetryBudget()
    while True:
        try:
            return client.get(LOGIN_LOGS_PATH, params=params)
        except Exception as exc:  # noqa: BLE001
            if not _should_retry_login_slice_daily(exc):
                raise
            delay = _retry_delay(budget.retry_count)
            budget.consume(delay)
            time.sleep(delay)


def _login_records_paginated_with_backoff(
    filters: dict[str, Any],
    *,
    retry_budget: _LoginRetryBudget | None = None,
) -> list[dict[str, Any]]:
    payload = _normalize_login_audit_filters(_normalize_time_filters(filters))
    request_params = _list_request_filters(LOGIN_LOGS_PATH, payload)
    page_limit = min(max(int(request_params.get("limit") or 200), 1), 1000)
    offset = int(request_params.get("offset") or 0)
    request_params["limit"] = page_limit
    client = create_client(org_id=_org_id_from_filters(filters))
    records: list[dict[str, Any]] = []
    seen_offsets: set[int] = set()
    seen_pages: set[str] = set()
    page_count = 0
    finished = False

    while offset not in seen_offsets and page_count < REPORT_MAX_LOGIN_PAGES:
        if len(records) >= REPORT_FETCH_RECORD_LIMIT:
            raise CLIError(
                "登录日志记录数超过单次报告上限。",
                payload={"reason_code": "report_record_limit_exceeded", "record_limit": REPORT_FETCH_RECORD_LIMIT},
            )
        seen_offsets.add(offset)
        page_count += 1
        page_params = dict(request_params)
        page_params["offset"] = offset
        page = _login_page_with_backoff(client, page_params, retry_budget=retry_budget)
        total_count = None
        if isinstance(page, dict) and isinstance(page.get("results"), list):
            page_records = [item for item in page.get("results") or [] if isinstance(item, dict)]
            try:
                total_count = int(page.get("count"))
            except (TypeError, ValueError):
                total_count = None
        elif isinstance(page, list):
            page_records = [item for item in page if isinstance(item, dict)]
        else:
            finished = True
            break
        page_signature = hashlib.sha256(_canonical_json(page_records).encode("utf-8")).hexdigest()
        if page_signature in seen_pages:
            raise CLIError(
                "登录日志分页未向前推进。",
                payload={"reason_code": "report_repeated_page", "offset": offset, "page_count": page_count},
            )
        seen_pages.add(page_signature)
        records.extend(page_records)
        if len(records) > REPORT_FETCH_RECORD_LIMIT:
            raise CLIError(
                "登录日志记录数超过单次报告上限。",
                payload={"reason_code": "report_record_limit_exceeded", "record_limit": REPORT_FETCH_RECORD_LIMIT},
            )
        if not page_records:
            finished = True
            break
        if total_count is not None and offset + len(page_records) >= total_count:
            finished = True
            break
        if len(page_records) < page_limit:
            finished = True
            break
        offset += page_limit
    if not finished and page_count >= REPORT_MAX_LOGIN_PAGES:
        raise CLIError(
            "登录日志分页超过单次报告上限。",
            payload={"reason_code": "report_page_limit_exceeded", "page_limit": REPORT_MAX_LOGIN_PAGES},
        )
    return _apply_common_filters(records, payload)


def _fetch_login_slice_records(
    filters: dict[str, Any],
    item: dict[str, Any],
    *,
    retry_on_throttle: bool = False,
    retry_budget: _LoginRetryBudget | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    slice_filters = dict(filters)
    slice_filters.pop("_date_from", None)
    slice_filters.pop("_date_to", None)
    slice_filters["date_from"] = _format_login_slice_datetime(item["date_from"])
    slice_filters["date_to"] = _format_login_slice_datetime(item["date_to"])
    budget = retry_budget or _LoginRetryBudget()
    retries_before = budget.retry_count
    while True:
        try:
            if retry_on_throttle:
                slice_records = _login_records_paginated_with_backoff(slice_filters, retry_budget=budget)
            else:
                slice_records = list(_login_records(slice_filters))
            break
        except Exception as exc:  # noqa: BLE001
            if not retry_on_throttle or not _should_retry_login_slice_daily(exc):
                raise
            delay = _retry_delay(budget.retry_count)
            budget.consume(delay)
            time.sleep(delay)
    exclusive_to = item.get("exclusive_to")
    if exclusive_to is not None:
        slice_records = [
            record
            for record in slice_records
            if _extract_datetime(record) is None or _extract_datetime(record) < exclusive_to
        ]
    return slice_records, {
        "date_from": slice_filters["date_from"],
        "date_to": slice_filters["date_to"],
        "record_count": len(slice_records),
        "retry_count": budget.retry_count - retries_before,
    }


def _raise_login_slice_error(exc: Exception, diagnostics: dict[str, Any]) -> None:
    raise CLIError(
        "登录日志分片拉取失败。",
        payload=build_cli_guidance_payload(
            REPORT_LOGIN_SLICE_FETCH_REASON_CODE,
            user_message="登录日志分片拉取失败，未生成 prepared 工件。",
            action_hint="请检查 JumpServer API 连通性或缩小时间窗后重试。",
            slice_date_from=diagnostics["date_from"],
            slice_date_to=diagnostics["date_to"],
            original_error=str(exc),
            original_payload=getattr(exc, "payload", None),
        ),
    ) from exc


def _fetch_login_records_time_sliced(filters: dict[str, Any], date_from: datetime, date_to: datetime) -> dict[str, Any]:
    raw_records: list[dict[str, Any]] = []
    slice_diagnostics = []
    daily_fallback_count = 0
    retry_budget = _LoginRetryBudget()
    for item in _login_time_slices(date_from, date_to):
        try:
            slice_records, diagnostics = _fetch_login_slice_records(filters, item, retry_budget=retry_budget)
        except Exception as exc:  # noqa: BLE001
            diagnostics = {
                "date_from": _format_login_slice_datetime(item["date_from"]),
                "date_to": _format_login_slice_datetime(item["date_to"]),
            }
            if not _should_retry_login_slice_daily(exc):
                _raise_login_slice_error(exc, diagnostics)
            if item.get("exclusive_to") is not None:
                daily_items = _login_time_slices_exclusive(item["date_from"], item["exclusive_to"], days=1)
            else:
                daily_items = _login_time_slices(item["date_from"], item["date_to"], days=1)
            for daily_item in daily_items:
                try:
                    daily_records, daily_diagnostics = _fetch_login_slice_records(
                        filters,
                        daily_item,
                        retry_on_throttle=True,
                        retry_budget=retry_budget,
                    )
                except Exception as daily_exc:  # noqa: BLE001
                    daily_error_diagnostics = {
                        "date_from": _format_login_slice_datetime(daily_item["date_from"]),
                        "date_to": _format_login_slice_datetime(daily_item["date_to"]),
                    }
                    _raise_login_slice_error(daily_exc, daily_error_diagnostics)
                daily_diagnostics["granularity"] = "day"
                daily_diagnostics["fallback_from"] = diagnostics
                raw_records.extend(daily_records)
                if len(raw_records) > REPORT_FETCH_RECORD_LIMIT:
                    raise CLIError(
                        "登录日志记录数超过单次报告上限。",
                        payload={"reason_code": "report_record_limit_exceeded", "record_limit": REPORT_FETCH_RECORD_LIMIT},
                    )
                slice_diagnostics.append(daily_diagnostics)
                daily_fallback_count += 1
            continue
        diagnostics["granularity"] = "week"
        raw_records.extend(slice_records)
        if len(raw_records) > REPORT_FETCH_RECORD_LIMIT:
            raise CLIError(
                "登录日志记录数超过单次报告上限。",
                payload={"reason_code": "report_record_limit_exceeded", "record_limit": REPORT_FETCH_RECORD_LIMIT},
            )
        slice_diagnostics.append(diagnostics)
    records, duplicate_count = _dedupe_login_records(raw_records)
    return {
        "records": records,
        "fetch_diagnostics": {
            "fetch_strategy": "time_sliced",
            "slice_count": len(slice_diagnostics),
            "slice_granularity": "week/day" if daily_fallback_count else "week",
            "daily_fallback_count": daily_fallback_count,
            "raw_record_count": len(raw_records),
            "deduplicated_count": duplicate_count,
            "retry_count": retry_budget.retry_count,
            "slices": slice_diagnostics,
        },
    }


def _fetch_login_records_for_report(filters: dict[str, Any]) -> dict[str, Any]:
    window = _login_fetch_window(filters)
    if window is None:
        records = list(_login_records(filters))
        return {
            "records": records,
            "fetch_diagnostics": {
                "fetch_strategy": "direct",
                "slice_count": 1,
                "slice_granularity": None,
                "raw_record_count": len(records),
                "deduplicated_count": 0,
                "slices": [],
            },
        }
    date_from, date_to = window
    if date_to - date_from <= timedelta(days=LOGIN_DIRECT_WINDOW_DAYS):
        records = list(_login_records(filters))
        return {
            "records": records,
            "fetch_diagnostics": {
                "fetch_strategy": "direct",
                "slice_count": 1,
                "slice_granularity": None,
                "raw_record_count": len(records),
                "deduplicated_count": 0,
                "slices": [],
            },
        }
    return _fetch_login_records_time_sliced(filters, date_from, date_to)


def _ensure_report_record_limit(records: list[dict[str, Any]], source: str) -> None:
    if len(records) <= REPORT_FETCH_RECORD_LIMIT:
        return
    raise CLIError(
        "报告数据量超过单次处理上限。",
        payload=build_cli_guidance_payload(
            "report_record_limit_exceeded",
            user_message="%s 记录数超过 %s 条，未生成 prepared 工件。" % (source, REPORT_FETCH_RECORD_LIMIT),
            action_hint="请缩小报告时间窗并分批生成。",
            source=source,
            record_count=len(records),
            record_limit=REPORT_FETCH_RECORD_LIMIT,
        ),
    )


def _normalize_login_source(filters: dict[str, Any]) -> dict[str, Any]:
    fetch_payload = _fetch_login_records_for_report(filters)
    records = list(fetch_payload.get("records") or [])
    _ensure_report_record_limit(records, "login")
    fetch_diagnostics = dict(fetch_payload.get("fetch_diagnostics") or {})
    records.sort(key=lambda item: _extract_datetime(item) or datetime.min.replace(tzinfo=_local_now().tzinfo), reverse=True)
    failed_records = [item for item in records if _is_failed_login(item)]
    success_records = [item for item in records if not _is_failed_login(item)]
    city_counter = Counter(city for city in (_extract_city(item) for item in records) if city)
    ip_counter = Counter(ip for ip in (_extract_source_ip(item) for item in records) if ip)
    common_ips = {ip for ip, count in ip_counter.items() if count > 1}
    if not common_ips and ip_counter:
        common_ips = {ip for ip, _ in ip_counter.most_common(3)}
    return {
        "login_total": len(records),
        "login_success": len(success_records),
        "login_failed": len(failed_records),
        "unique_login_city_count": len(city_counter),
        "top_login_ip_summary": _top_summary(ip_counter),
        "risk_top_login_ip_summary": _risk_top_summary(ip_counter),
        "rows_html": _render_login_rows(records),
        "login_failed_rows": _render_login_failed_rows(failed_records, common_ips=common_ips),
        "records": records,
        "failed_records": failed_records,
        "fetch_diagnostics": fetch_diagnostics,
        "fetch_strategy": fetch_diagnostics.get("fetch_strategy"),
        "slice_count": fetch_diagnostics.get("slice_count"),
        "slice_granularity": fetch_diagnostics.get("slice_granularity"),
        "deduplicated_count": fetch_diagnostics.get("deduplicated_count"),
    }


def _normalize_session_source(filters: dict[str, Any]) -> dict[str, Any]:
    records = list(_fetch_session_records(filters))
    _ensure_report_record_limit(records, "session")
    records.sort(key=lambda item: _extract_datetime(item) or datetime.min.replace(tzinfo=_local_now().tzinfo), reverse=True)
    durations = [value for value in (_extract_duration(item) for item in records) if value is not None]
    total_duration = sum(durations) if durations else 0.0
    protocol_counter = Counter(_extract_protocol(item) or "unknown" for item in records)
    component_counter = Counter(_extract_component(item) or "unknown" for item in records)
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    asset_counter = Counter(_extract_asset(item) or "unknown" for item in records)
    duration_rows = []
    for item in records:
        duration = _extract_duration(item)
        if duration is None:
            continue
        duration_rows.append(
            {
                "user": _extract_user(item),
                "asset": _extract_asset(item),
                "duration_seconds": duration,
                "timestamp": _extract_datetime(item),
            }
        )
    duration_rows.sort(key=lambda item: item.get("duration_seconds") or 0, reverse=True)
    failed_records = [item for item in records if _looks_failed_session(item)]
    return {
        "session_total": len(records),
        "session_total_duration": _format_duration(total_duration),
        "avg_session_duration": _format_duration((total_duration / len(durations)) if durations else None),
        "longest_session": (
            "%s / %s / %s"
            % (
                duration_rows[0].get("user") or "unknown",
                duration_rows[0].get("asset") or "unknown",
                _format_duration(duration_rows[0].get("duration_seconds")),
            )
            if duration_rows
            else EMPTY_TEXT
        ),
        "protocol_distribution_rows": _render_distribution_rows(protocol_counter, total=len(records), first_label="协议"),
        "component_distribution_rows": _render_distribution_rows(component_counter, total=len(records), first_label="组件"),
        "session_user_top10_rows": _render_distribution_rows(user_counter, total=len(records), first_label="用户"),
        "session_asset_top10_rows": _render_asset_rows(asset_counter),
        "session_duration_top10_rows": _render_duration_rows(duration_rows),
        "session_failed_rows": _render_session_failed_rows(failed_records),
        "records": records,
        "failed_records": failed_records,
    }


def _build_command_filters(filters: dict[str, Any], command_storage_id: str | None) -> dict[str, Any]:
    payload = {
        "date_from": filters["date_from"],
        "date_to": filters["date_to"],
        "limit": 50,
    }
    if command_storage_id:
        payload["command_storage_id"] = str(command_storage_id)
    else:
        payload["command_storage_scope"] = "all"
    return payload


def _normalize_command_source(filters: dict[str, Any], command_storage_id: str | None) -> dict[str, Any]:
    command_filters = _build_command_filters(filters, command_storage_id)
    records = list(_fetch_command_records(command_filters))
    _ensure_report_record_limit(records, "command")
    risk_counter = Counter(str(_string_value(_first_field(item, "risk_level_display", "risk_level.value", "risk_level")) or "unknown") for item in records)
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    asset_counter = Counter(_extract_asset(item) or "unknown" for item in records)
    storage_context = resolve_command_storage_context(command_filters)
    return {
        "command_total": len(records),
        "top_command_users": _top_summary(user_counter),
        "top_command_assets": _top_summary(asset_counter),
        "risk_levels": [{"name": key, "count": value} for key, value in risk_counter.most_common(10)],
        "records": records,
        **storage_context,
    }


def _normalize_high_risk_command_source(command_source: dict[str, Any]) -> dict[str, Any]:
    records = [
        item
        for item in command_source.get("records", [])
        if int(_first_field(item, "risk_level.value", "risk_level") or 0) >= 4
    ]
    return {
        "high_risk_command_total": len(records),
        "rows_html": _render_command_risk_rows(records),
        "records": records,
    }


def _normalize_file_transfer_source(filters: dict[str, Any]) -> dict[str, Any]:
    records = list(_fetch_file_transfer_records(filters))
    _ensure_report_record_limit(records, "file_transfer")
    risky_records = [item for item in records if _is_risky_file_transfer(item)]
    direction_counter = Counter(_normalize_direction(_extract_direction(item)) for item in records)
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    asset_counter = Counter(_extract_asset(item) or "unknown" for item in records)
    return {
        "file_transfer_total": len(records),
        "file_upload_total": int(direction_counter.get("upload") or 0),
        "file_download_total": int(direction_counter.get("download") or 0),
        "file_transfer_users": _top_summary(user_counter),
        "file_transfer_assets": _top_summary(asset_counter),
        "risky_file_transfer_total": len(risky_records),
        "risky_records": risky_records,
        "records": records,
    }


def _file_transfer_name(item: dict[str, Any]) -> str:
    return _string_value(_first_field(item, "filename", "file_name", "name", "path", "filepath", "file")).strip()


def _is_risky_file_transfer(item: dict[str, Any]) -> bool:
    name = re.split(r"[?#]", _file_transfer_name(item).lower(), maxsplit=1)[0]
    return bool(name) and any(name.endswith(suffix) for suffix in SENSITIVE_FILE_SUFFIXES)


def _is_abnormal_hour_login(item: dict[str, Any], *, start_hour: int = 0, end_hour: int = 6) -> bool:
    timestamp = _extract_datetime(item)
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=SHANGHAI_TZ) if SHANGHAI_TZ else timestamp.astimezone()
    local_timestamp = timestamp.astimezone(SHANGHAI_TZ) if SHANGHAI_TZ else timestamp.astimezone()
    return start_hour <= local_timestamp.hour < end_hour


def _normalize_high_risk_operation_source(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_operate_audit_filters({**filters, "action": "delete"})
    common_filters = {key: value for key, value in payload.items() if key != "action"}
    records = [item for item in _apply_common_filters(list(_fetch_list(OPERATE_LOGS_PATH, payload)), common_filters) if _is_delete_operation(item)]
    _ensure_report_record_limit(records, "high_risk_operation")
    records.sort(key=lambda item: _extract_datetime(item) or datetime.min.replace(tzinfo=_local_now().tzinfo), reverse=True)
    user_counter = Counter(_extract_user(item) or "unknown" for item in records)
    resource_counter = Counter(_extract_resource_type(item) or "unknown" for item in records)
    return {
        "high_risk_operation_total": len(records),
        "high_risk_operation_users": _risk_top_summary(user_counter),
        "high_risk_operation_resource_types": _risk_top_summary(resource_counter),
        "records": records,
    }


def _normalize_suspicious_source(filters: dict[str, Any]) -> dict[str, Any]:
    payload = _unwrap_single_result_layers(suspicious_operation_summary(filters))
    source_records = payload.get("records") if isinstance(payload, dict) else []
    normalized_records = []
    total = 0
    for item in source_records or []:
        if not isinstance(item, dict):
            continue
        event_type = str(item.get("type") or "").strip()
        raw_samples = [sample for sample in item.get("samples") or [] if isinstance(sample, dict)]
        samples = list(raw_samples)
        if event_type == "risky_file_transfers":
            samples = [sample for sample in samples if _is_risky_file_transfer(sample)]
        elif event_type == "abnormal_hour_logins":
            samples = [sample for sample in samples if _is_abnormal_hour_login(sample)]
        if event_type in {"risky_file_transfers", "abnormal_hour_logins"} or raw_samples:
            count = len(samples)
        else:
            count = max(_int_value(item.get("count")), 0)
        normalized_records.append({**item, "count": count, "samples": samples})
        total += count
    return {
        "risk_event_total": total,
        "records": normalized_records,
    }


def _source_key(source: dict[str, Any]) -> str:
    capability_id = str(source.get("capability_id") or "").strip()
    if capability_id:
        return "capability:%s" % capability_id
    entrypoint = str(source.get("entrypoint") or "").strip()
    if entrypoint == "report runtime context":
        return "runtime"
    return "entrypoint:%s" % entrypoint


def _collect_source_payloads(
    metadata: dict[str, Any],
    *,
    runtime_context: dict[str, Any],
    filters: dict[str, Any],
    command_storage_id: str | None,
    org_id: str,
) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    source_filters = {**filters, "_org_id": org_id}

    def fetch(source_key: str) -> dict[str, Any]:
        if source_key in cache:
            return cache[source_key]
        if source_key == "runtime":
            payload = dict(runtime_context)
        elif source_key == "entrypoint:python3 subskills/query/scripts/jms_runtime_query.py license-detail":
            payload = _normalize_license_source()
        elif source_key == "entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login":
            payload = _normalize_login_source(source_filters)
        elif source_key == "capability:session-record-query":
            payload = _normalize_session_source(source_filters)
        elif source_key == "capability:session-duration-ranking":
            session_payload = fetch("capability:session-record-query")
            payload = {
                "longest_session": session_payload.get("longest_session"),
                "rows_html": session_payload.get("session_duration_top10_rows"),
            }
        elif source_key == "capability:protocol-usage-distribution":
            session_payload = fetch("capability:session-record-query")
            payload = {"rows_html": session_payload.get("protocol_distribution_rows")}
        elif source_key == "capability:recent-active-users-ranking":
            session_payload = fetch("capability:session-record-query")
            payload = {"rows_html": session_payload.get("session_user_top10_rows")}
        elif source_key == "capability:recent-active-assets-ranking":
            session_payload = fetch("capability:session-record-query")
            payload = {"rows_html": session_payload.get("session_asset_top10_rows")}
        elif source_key == "capability:command-record-query":
            payload = _normalize_command_source(source_filters, command_storage_id)
        elif source_key == "capability:high-risk-command-audit":
            payload = _normalize_high_risk_command_source(fetch("capability:command-record-query"))
        elif source_key == "capability:file-transfer-log-query":
            payload = _normalize_file_transfer_source(source_filters)
        elif source_key == "entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type operate --action delete":
            payload = _normalize_high_risk_operation_source(source_filters)
        elif source_key == "capability:file-transfer-heavy-ranking":
            file_payload = fetch("capability:file-transfer-log-query")
            payload = {
                "top_users_summary": file_payload.get("file_transfer_users"),
                "top_assets_summary": file_payload.get("file_transfer_assets"),
            }
        elif source_key == "capability:suspicious-operation-summary":
            payload = _normalize_suspicious_source(source_filters)
        elif source_key == "capability:failed-login-statistics":
            login_payload = fetch("entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login")
            payload = {
                "login_failed": login_payload.get("login_failed"),
                "rows_html": login_payload.get("login_failed_rows"),
                "top_source_ips_summary": login_payload.get("top_login_ip_summary"),
            }
        else:
            raise CLIError("Unsupported report source: %s" % source_key)
        cache[source_key] = _unwrap_single_result_layers(payload) or {}
        return cache[source_key]

    for field_spec in metadata.get("fields") or []:
        if not isinstance(field_spec, dict):
            continue
        for source in field_spec.get("sources") or []:
            if isinstance(source, dict):
                fetch(_source_key(source))
    return cache


def _resolve_simple_field(field_spec: dict[str, Any], source_payloads: dict[str, dict[str, Any]]) -> Any:
    field_name = str(field_spec.get("field") or "")
    for source in field_spec.get("sources") or []:
        if not isinstance(source, dict):
            continue
        payload = source_payloads.get(_source_key(source), {})
        output_field = source.get("output_field")
        if output_field:
            value = _evaluate_output_expression(payload, str(output_field))
            if value not in {None, ""}:
                return value
        elif field_name and field_name in payload and payload.get(field_name) not in {None, ""}:
                return payload.get(field_name)
    return None


def _derive_fields(
    resolved: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    resolved = dict(resolved)
    file_payload = source_payloads.get("capability:file-transfer-log-query", {})
    if "risky_file_transfer_total" in resolved:
        risky_file_transfer_total = int(resolved.get("risky_file_transfer_total") or 0)
    elif "risky_file_transfer_total" in file_payload:
        risky_file_transfer_total = int(file_payload.get("risky_file_transfer_total") or 0)
    else:
        # Prepared schema v1 did not separate transfer activity from transfer risk.
        risky_file_transfer_total = int(resolved.get("file_transfer_total") or 0)
    risk_event_total = (
        int(resolved.get("login_failed") or 0)
        + int(resolved.get("high_risk_command_total") or 0)
        + risky_file_transfer_total
        + int(resolved.get("high_risk_operation_total") or 0)
    )
    resolved["risk_event_total"] = risk_event_total
    risk_level = _risk_level_label(
        risk_event_total,
        int(resolved.get("login_failed") or 0),
        int(resolved.get("high_risk_command_total") or 0),
        int(resolved.get("file_transfer_total") or 0),
        int(resolved.get("high_risk_operation_total") or 0),
    )
    derived = {
        "risk_event_total": risk_event_total,
        "risky_file_transfer_total": risky_file_transfer_total,
        "daily_summary": (
            "统计时段内共发生 %s 次登录，失败 %s 次；产生 %s 个会话、%s 条命令记录、%s 次文件传输，识别到 %s 项风险/异常事件。"
            % (
                resolved.get("login_total") or 0,
                resolved.get("login_failed") or 0,
                resolved.get("session_total") or 0,
                resolved.get("command_total") or 0,
                resolved.get("file_transfer_total") or 0,
                resolved.get("risk_event_total") or 0,
            )
        ),
        "risk_level": risk_level,
        "risk_summary": (
            "综合登录失败、高危命令、风险文件传输和高危操作情况，本时段风险等级判定为%s；风险/异常事件总数为 %s。"
            % (risk_level, resolved.get("risk_event_total") or 0)
        ),
    }
    return derived


def _resolve_field_value(
    field_spec: dict[str, Any],
    *,
    resolved_values: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
    derived_values: dict[str, Any],
) -> Any:
    field_name = str(field_spec.get("field") or "").strip()
    raw_value = resolved_values.get(field_name)
    if raw_value not in {None, ""}:
        return raw_value
    raw_value = _resolve_simple_field(field_spec, source_payloads)
    if raw_value not in {None, ""}:
        return raw_value
    return derived_values.get(field_name)


def _render_field_value(field_spec: dict[str, Any], value: Any) -> str:
    contract = str(field_spec.get("render_contract") or TEXT_CONTRACT)
    if contract == TBODY_ROWS_CONTRACT:
        if value not in {None, ""}:
            return _validate_tbody_html(value)
        columns = field_spec.get("table_columns")
        colspan = len(columns) if isinstance(columns, list) and columns else 1
        return _empty_row(colspan)
    if value in {None, ""}:
        return EMPTY_TEXT
    if isinstance(value, (int, float)):
        return str(value)
    return escape(str(value))


def render_report_html(template_html: str, field_values: dict[str, str]) -> str:
    rendered = template_html
    for key, value in field_values.items():
        rendered = re.sub(r"\{\{\s*%s\s*\}\}" % re.escape(key), lambda _: value, rendered)
    return rendered


def _build_minimal_context(
    *,
    date_expr: str | None,
    period_expr: str | None,
    date_from_expr: str | None,
    date_to_expr: str | None,
    org_id: str | None,
    org_name: str | None,
    command_storage_id: str | None,
) -> dict[str, Any]:
    runtime_context = _normalize_time_window(
        date_expr=date_expr,
        period_expr=period_expr,
        date_from_expr=date_from_expr,
        date_to_expr=date_to_expr,
    )
    org_context = _normalize_report_org_context(org_id, org_name)
    filters = {
        "date_from": runtime_context["date_from"],
        "date_to": runtime_context["date_to"],
    }
    if command_storage_id:
        filters["command_storage_id"] = str(command_storage_id)
    return {
        "runtime_context": runtime_context,
        "org_context": org_context,
        "filters": filters,
        "command_storage_id": str(command_storage_id or "").strip() or None,
    }


def validate_report_contract(
    *,
    metadata: dict[str, Any] | None = None,
    template_html: str | None = None,
    sample_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    metadata_payload = metadata or load_report_metadata()
    template_payload = template_html or load_report_template()
    template_fields = extract_template_fields(template_payload)
    metadata_fields = [
        item.get("field")
        for item in metadata_payload.get("fields", [])
        if isinstance(item, dict) and item.get("field")
    ]
    required_fields = [
        item.get("field")
        for item in metadata_payload.get("fields", [])
        if isinstance(item, dict) and item.get("required") and item.get("field")
    ]
    dummy_values = dict(sample_values or {})
    for item in metadata_payload.get("fields", []):
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field") or "").strip()
        if not field_name or field_name in dummy_values:
            continue
        if item.get("render_contract") == TBODY_ROWS_CONTRACT:
            dummy_values[field_name] = "<tr><td>contract-ok</td></tr>"
        elif item.get("value_type") == "number_string":
            dummy_values[field_name] = "1"
        elif item.get("value_type") == "datetime_string":
            dummy_values[field_name] = "2026-03-10 12:00:00"
        else:
            dummy_values[field_name] = "sample_%s" % field_name
    rendered = render_report_html(template_payload, dummy_values)
    placeholder_residue = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    required_unbound = sorted([field for field in required_fields if field not in dummy_values or dummy_values[field] in {"", None}])
    return {
        "template_field_count": len(template_fields),
        "metadata_field_count": len(metadata_fields),
        "missing_in_metadata": sorted(set(template_fields) - set(metadata_fields)),
        "missing_in_template": sorted(set(metadata_fields) - set(template_fields)),
        "required_unbound_fields": required_unbound,
        "placeholder_residue": placeholder_residue,
        "contract_passed": not (
            set(template_fields) - set(metadata_fields)
            or set(metadata_fields) - set(template_fields)
            or required_unbound
            or placeholder_residue
        ),
    }


def validate_report_runtime_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    failures: list[str] = []
    missing_fields = [field for field in REPORT_RUNTIME_REQUIRED_FIELDS if field not in result]
    if missing_fields:
        failures.append("Runtime report payload is missing fields: %s" % ", ".join(sorted(missing_fields)))

    for key in ("template_path", "metadata_path", "report_date", "date_from", "date_to"):
        if key in result and not str(result.get(key) or "").strip():
            failures.append("Runtime report field %s is empty." % key)

    effective_org = result.get("effective_org")
    if not isinstance(effective_org, dict) or not str(effective_org.get("id") or "").strip():
        failures.append("effective_org must contain a non-empty id.")

    switchable_orgs = result.get("switchable_orgs")
    if not isinstance(switchable_orgs, list):
        failures.append("switchable_orgs must be a list.")

    queried_command_storage_ids = result.get("queried_command_storage_ids")
    if not isinstance(queried_command_storage_ids, list):
        failures.append("queried_command_storage_ids must be a list.")

    queried_command_storage_count = result.get("queried_command_storage_count")
    try:
        queried_command_storage_count_value = int(queried_command_storage_count)
    except (TypeError, ValueError):
        failures.append("queried_command_storage_count must be an integer.")
    else:
        if queried_command_storage_count_value < 0:
            failures.append("queried_command_storage_count must not be negative.")

    validation_summary = result.get("validation_summary")
    if not isinstance(validation_summary, dict):
        failures.append("validation_summary must be a dict.")
    elif not validation_summary.get("passed"):
        failures.append("validation_summary.passed must be true for successful report generation.")

    output_path_text = str(result.get("output_path") or "").strip()
    if not output_path_text:
        failures.append("output_path is empty.")
        return {
            "contract_passed": not failures,
            "failure_count": len(failures),
            "contract_failures": failures,
        }

    output_path = Path(output_path_text)
    actual_exists = False
    actual_size_bytes = 0
    try:
        actual_exists = output_path.exists() and output_path.is_file()
    except OSError:
        actual_exists = False
    if not actual_exists:
        failures.append("Report output artifact does not exist: %s" % output_path_text)
    else:
        try:
            actual_size_bytes = int(output_path.stat().st_size or 0)
        except OSError as exc:
            failures.append("Report output artifact could not be stat'ed: %s" % exc)
        else:
            if actual_size_bytes <= 0:
                failures.append("Report output artifact is empty: %s" % output_path_text)

    if bool(result.get("output_exists")) != actual_exists:
        failures.append("output_exists does not match filesystem state.")

    try:
        output_size_bytes = int(result.get("output_size_bytes"))
    except (TypeError, ValueError):
        failures.append("output_size_bytes must be an integer.")
        output_size_bytes = None
    if output_size_bytes is not None and output_size_bytes < 0:
        failures.append("output_size_bytes must not be negative.")
    if actual_exists and output_size_bytes is not None and output_size_bytes != actual_size_bytes:
        failures.append("output_size_bytes does not match filesystem state.")

    output_size_human = str(result.get("output_size_human") or "").strip()
    if not output_size_human:
        failures.append("output_size_human is empty.")
    elif actual_exists and output_size_human != _format_output_size_human(actual_size_bytes):
        failures.append("output_size_human does not match filesystem state.")

    return {
        "contract_passed": not failures,
        "failure_count": len(failures),
        "contract_failures": failures,
    }


def _validate_report_output(
    *,
    rendered_html: str,
    field_values: dict[str, str],
    metadata: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    placeholder_residue = sorted(set(PLACEHOLDER_RE.findall(rendered_html)))
    if placeholder_residue:
        failures.append("Rendered HTML still contains placeholders: %s" % ", ".join(placeholder_residue))

    required_fields = [
        item.get("field")
        for item in metadata.get("fields", [])
        if isinstance(item, dict) and item.get("required") and item.get("field")
    ]
    missing_required = [field for field in required_fields if field_values.get(str(field), "") in {"", None}]
    if missing_required:
        failures.append("Required fields are empty: %s" % ", ".join(sorted(missing_required)))

    for key in REQUIRED_KEY_FIELDS:
        value = str(field_values.get(key) or "").strip()
        if not value:
            failures.append("Key field %s is empty." % key)

    login_payload = source_payloads.get("entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login", {})
    session_payload = source_payloads.get("capability:session-record-query", {})
    risk_payload = source_payloads.get("capability:suspicious-operation-summary", {})
    for field_name, source_total in (
        ("login_total", int(login_payload.get("login_total") or 0)),
        ("session_total", int(session_payload.get("session_total") or 0)),
        ("risk_event_total", int(risk_payload.get("risk_event_total") or 0)),
    ):
        rendered_value = str(field_values.get(field_name) or "").strip()
        if source_total > 0 and rendered_value in {"0", EMPTY_TEXT, ""}:
            failures.append("Field %s lost non-empty source data during rendering." % field_name)

    if rendered_html.count(EMPTY_TEXT) > 12:
        warnings.append("Rendered report still contains many '%s' markers." % EMPTY_TEXT)

    return {
        "passed": not failures,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "validation_failures": failures,
        "validation_warnings": warnings,
    }


def _counter_items(counter: Counter[str], *, limit: int = 3) -> list[dict[str, Any]]:
    return [
        {"name": str(key or "").strip() or "unknown", "count": int(count or 0)}
        for key, count in counter.most_common(limit)
    ]


def _top_items_from_records(records: list[dict[str, Any]], extractor, *, limit: int = 3) -> list[dict[str, Any]]:
    counter = Counter()
    for item in records:
        value = str(extractor(item) or "").strip()
        if value:
            counter[value] += 1
    return _counter_items(counter, limit=limit)


def _sample_login_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _format_datetime(_extract_datetime(item)),
        "user": _extract_user(item),
        "source_ip": _extract_source_ip(item),
        "city": _extract_city(item),
        "status": _extract_status(item) or ("失败" if _is_failed_login(item) else "成功"),
        "failure_reason": _display_login_failure_reason(item),
    }


def _sample_command_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _format_datetime(_extract_datetime(item)),
        "user": _extract_user(item),
        "asset": _extract_asset(item),
        "account": _extract_account(item),
        "command": _extract_command_text(item),
        "risk_level": _string_value(_first_field(item, "risk_level_display", "risk_level.value", "risk_level")),
    }


def _sample_file_transfer_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _format_datetime(_extract_datetime(item)),
        "user": _extract_user(item),
        "asset": _extract_asset(item),
        "account": _extract_account(item),
        "direction": _normalize_direction(_extract_direction(item)),
        "file": _string_value(_first_field(item, "filename", "file_name", "name", "path", "filepath", "file")),
    }


def _sample_operation_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _format_datetime(_extract_datetime(item)),
        "user": _extract_user(item),
        "action": _extract_direction(item),
        "resource_type": _extract_resource_type(item),
        "resource": _string_value(_first_field(item, "resource", "resource_name", "object", "object_name", "instance")),
    }


def _build_summary_input(
    *,
    context: dict[str, Any],
    resolved_values: dict[str, Any],
    derived_values: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    login_payload = source_payloads.get("entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login", {})
    command_payload = source_payloads.get("capability:command-record-query", {})
    high_risk_payload = source_payloads.get("capability:high-risk-command-audit", {})
    file_payload = source_payloads.get("capability:file-transfer-log-query", {})
    operation_payload = source_payloads.get("entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type operate --action delete", {})

    login_records = list(login_payload.get("records") or [])
    failed_login_records = list(login_payload.get("failed_records") or [])
    command_records = list(command_payload.get("records") or [])
    high_risk_command_records = list(high_risk_payload.get("records") or [])
    file_transfer_records = list(file_payload.get("records") or [])
    risky_file_transfer_records = list(file_payload.get("risky_records") or [])
    operation_records = list(operation_payload.get("records") or [])

    upload_total = _int_value(resolved_values.get("file_upload_total"))
    download_total = _int_value(resolved_values.get("file_download_total"))
    file_direction = "mixed"
    if upload_total > 0 and download_total <= 0:
        file_direction = "upload_only"
    elif download_total > 0 and upload_total <= 0:
        file_direction = "download_only"
    elif upload_total == download_total and upload_total > 0:
        file_direction = "balanced"
    elif upload_total > download_total:
        file_direction = "upload_heavy"
    elif download_total > upload_total:
        file_direction = "download_heavy"

    return {
        "report": {
            "report_date": context["runtime_context"]["report_date"],
            "date_from": context["runtime_context"]["date_from"],
            "date_to": context["runtime_context"]["date_to"],
            "effective_org": context["org_context"]["effective_org"],
            "risk_level": derived_values.get("risk_level"),
            "risk_event_total": _int_value(derived_values.get("risk_event_total")),
        },
        "risk": {
            "risk_level": derived_values.get("risk_level"),
            "risk_event_total": _int_value(derived_values.get("risk_event_total")),
            "login_failed": _int_value(resolved_values.get("login_failed")),
            "high_risk_command_total": _int_value(resolved_values.get("high_risk_command_total")),
            "file_transfer_total": _int_value(resolved_values.get("file_transfer_total")),
            "risky_file_transfer_total": _int_value(derived_values.get("risky_file_transfer_total")),
            "high_risk_operation_total": _int_value(resolved_values.get("high_risk_operation_total")),
        },
        "login": {
            "total": _int_value(resolved_values.get("login_total")),
            "success": _int_value(resolved_values.get("login_success")),
            "failed": _int_value(resolved_values.get("login_failed")),
            "unique_city_count": _int_value(resolved_values.get("unique_login_city_count")),
            "fetch_strategy": login_payload.get("fetch_strategy"),
            "slice_count": _int_value(login_payload.get("slice_count")),
            "slice_granularity": login_payload.get("slice_granularity"),
            "raw_record_count": _int_value((login_payload.get("fetch_diagnostics") or {}).get("raw_record_count")),
            "deduplicated_count": _int_value(login_payload.get("deduplicated_count")),
            "fetch_diagnostics": login_payload.get("fetch_diagnostics") or {},
            "top_source_ips_summary": login_payload.get("top_login_ip_summary"),
            "failed_top_source_ips": _top_items_from_records(failed_login_records, _extract_source_ip),
            "failed_top_users": _top_items_from_records(failed_login_records, _extract_user),
            "failed_top_cities": _top_items_from_records(failed_login_records, _extract_city),
            "failed_samples": [_sample_login_record(item) for item in failed_login_records[:10]],
        },
        "command": {
            "total": _int_value(resolved_values.get("command_total")),
            "high_risk_total": _int_value(resolved_values.get("high_risk_command_total")),
            "high_risk_ratio": _percent(
                _int_value(resolved_values.get("high_risk_command_total")),
                _int_value(resolved_values.get("command_total")),
            ),
            "queried_command_storage_ids": command_payload.get("queried_command_storage_ids") or [],
            "queried_command_storage_count": _int_value(command_payload.get("queried_command_storage_count")),
            "top_users_all_commands": _top_items_from_records(command_records, _extract_user),
            "top_assets_all_commands": _top_items_from_records(command_records, _extract_asset),
            "top_users_high_risk": _top_items_from_records(high_risk_command_records, _extract_user),
            "top_assets_high_risk": _top_items_from_records(high_risk_command_records, _extract_asset),
            "high_risk_samples": [_sample_command_record(item) for item in high_risk_command_records[:10]],
        },
        "file_transfer": {
            "total": _int_value(resolved_values.get("file_transfer_total")),
            "upload_total": upload_total,
            "download_total": download_total,
            "direction_profile": file_direction,
            "risky_total": _int_value(derived_values.get("risky_file_transfer_total")),
            "top_users": _top_items_from_records(file_transfer_records, _extract_user),
            "top_assets": _top_items_from_records(file_transfer_records, _extract_asset),
            "samples": [_sample_file_transfer_record(item) for item in file_transfer_records[:10]],
            "risky_samples": [_sample_file_transfer_record(item) for item in risky_file_transfer_records[:10]],
        },
        "high_risk_operation": {
            "total": _int_value(resolved_values.get("high_risk_operation_total")),
            "action": "delete",
            "top_users_summary": operation_payload.get("high_risk_operation_users"),
            "top_resource_types_summary": operation_payload.get("high_risk_operation_resource_types"),
            "top_users": _top_items_from_records(operation_records, _extract_user),
            "top_resource_types": _top_items_from_records(operation_records, _extract_resource_type),
            "samples": [_sample_operation_record(item) for item in operation_records[:10]],
        },
    }


def _build_daily_usage_state(
    *,
    date_expr: str | None = None,
    period_expr: str | None = None,
    date_from_expr: str | None = None,
    date_to_expr: str | None = None,
    org_id: str | None = None,
    org_name: str | None = None,
    command_storage_id: str | None = None,
) -> dict[str, Any]:
    context = _build_minimal_context(
        date_expr=date_expr,
        period_expr=period_expr,
        date_from_expr=date_from_expr,
        date_to_expr=date_to_expr,
        org_id=org_id,
        org_name=org_name,
        command_storage_id=command_storage_id,
    )
    metadata = load_report_metadata()
    template_html = load_report_template()
    contract = validate_report_contract(metadata=metadata, template_html=template_html)
    if not contract.get("contract_passed"):
        raise CLIError(
            "Report contract validation failed before generation.",
            payload=contract,
        )

    source_payloads = _collect_source_payloads(
        metadata,
        runtime_context=context["runtime_context"],
        filters=context["filters"],
        command_storage_id=context["command_storage_id"],
        org_id=context["org_context"]["target_org_id"],
    )

    resolved_values: dict[str, Any] = {}
    for item in metadata.get("fields", []):
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field") or "").strip()
        if not field_name or item.get("source_kind") in {"derived", "skill_summary"}:
            continue
        resolved_values[field_name] = _resolve_simple_field(item, source_payloads)

    derived_values = _derive_fields(resolved_values, source_payloads)
    summary_input = _build_summary_input(
        context=context,
        resolved_values=resolved_values,
        derived_values=derived_values,
        source_payloads=source_payloads,
    )
    return _bind_report_state({
        "schema_version": REPORT_SCHEMA_VERSION,
        "context": context,
        "resolved_values": resolved_values,
        "derived_values": derived_values,
        "source_payloads": _bound_source_payloads(source_payloads),
        "summary_input": summary_input,
    })


def _normalize_skill_summary_fields(summary_payload: dict[str, Any]) -> dict[str, str]:
    payload = summary_payload.get("summary_fields") if isinstance(summary_payload.get("summary_fields"), dict) else summary_payload
    missing = []
    invalid = []
    normalized: dict[str, str] = {}
    for field in SKILL_SUMMARY_FIELDS:
        if field not in payload:
            missing.append(field)
            continue
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            invalid.append(field)
            continue
        normalized[field] = value.strip()
    if missing or invalid:
        raise CLIError(
            "Skill summary fields are required before rendering report.",
            payload=build_cli_guidance_payload(
                "missing_skill_summary_fields",
                user_message="报告分析字段必须由 Skill 根据 summary_input 总结后提供。",
                action_hint="请先运行 daily-usage-prepare，基于 summary_input 写摘要 JSON，再运行 daily-usage-render。",
                missing_fields=missing,
                invalid_fields=invalid,
                required_fields=list(SKILL_SUMMARY_FIELDS),
            ),
        )
    return normalized


def _load_json_object(path: str | Path, *, max_bytes: int | None = None) -> dict[str, Any]:
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file():
            raise CLIError("JSON input must be a regular file: %s" % target, payload={"path": str(target)})
        if max_bytes is not None and target.stat().st_size > max_bytes:
            raise CLIError(
                "JSON input exceeds the size limit: %s" % target,
                payload={"path": str(target), "max_bytes": max_bytes},
            )
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CLIError("Unable to read JSON file: %s" % target, payload={"error": str(exc), "path": str(target)})
    except json.JSONDecodeError as exc:
        raise CLIError("Invalid JSON file: %s" % target, payload={"error": str(exc), "path": str(target)})
    if not isinstance(payload, dict):
        raise CLIError("JSON file must contain an object: %s" % target, payload={"path": str(target)})
    return payload


class _PreparedHTMLValidator(HTMLParser):
    ALLOWED_TAGS = {"tr", "td"}
    ALLOWED_ATTRIBUTES = {"tr": {"class"}, "td": {"colspan"}}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.invalid_reason = ""
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.ALLOWED_TAGS:
            self.invalid_reason = "tag %s is not allowed" % tag
            return
        allowed = self.ALLOWED_ATTRIBUTES[tag]
        for name, value in attrs:
            if name not in allowed:
                self.invalid_reason = "attribute %s is not allowed" % name
                return
            if name == "class" and value != "table-empty-row":
                self.invalid_reason = "class value is not allowed"
                return
            if name == "colspan" and not re.fullmatch(r"\d{1,2}", str(value or "")):
                self.invalid_reason = "colspan value is invalid"
                return
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            self.invalid_reason = "unbalanced HTML"
            return
        self.stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.invalid_reason = "self-closing tags are not allowed"

    def handle_comment(self, data: str) -> None:
        self.invalid_reason = "comments are not allowed"

    def handle_entityref(self, name: str) -> None:
        if name not in {"amp", "lt", "gt", "quot", "apos"}:
            self.invalid_reason = "entity is not allowed"


def _validate_tbody_html(value: Any) -> str:
    text = str(value or "")
    validator = _PreparedHTMLValidator()
    try:
        validator.feed(text)
        validator.close()
    except Exception as exc:  # noqa: BLE001
        raise CLIError("Invalid prepared table HTML.", payload={"error": str(exc)}) from exc
    if validator.invalid_reason or validator.stack or "<tr" not in text.lower():
        raise CLIError(
            "Invalid prepared table HTML.",
            payload={"reason_code": "invalid_prepared_table_html", "detail": validator.invalid_reason or "missing table row"},
        )
    return text


def _validate_prepared_state(state: dict[str, Any], *, prepared_path: str | Path | None = None) -> dict[str, Any]:
    required_dicts = ("context", "resolved_values", "derived_values", "source_payloads")
    failures = ["%s must be an object" % key for key in required_dicts if not isinstance(state.get(key), dict)]
    schema_version = _int_value(state.get("schema_version") if "schema_version" in state else 1)
    if schema_version not in {1, REPORT_SCHEMA_VERSION}:
        failures.append("unsupported schema_version")
    context = state.get("context") if isinstance(state.get("context"), dict) else {}
    runtime_context = context.get("runtime_context") if isinstance(context.get("runtime_context"), dict) else {}
    org_context = context.get("org_context") if isinstance(context.get("org_context"), dict) else {}
    effective_org = org_context.get("effective_org") if isinstance(org_context.get("effective_org"), dict) else {}
    report_date = str(runtime_context.get("report_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        failures.append("report_date must use YYYY-MM-DD")
    try:
        date_from = _parse_datetime_expr(str(runtime_context.get("date_from") or ""))
        date_to = _parse_datetime_expr(str(runtime_context.get("date_to") or ""), end_of_day=True)
        if date_to < date_from or date_to - date_from > timedelta(days=REPORT_MAX_WINDOW_DAYS):
            failures.append("report time window is invalid")
        if report_date and date_to.date().isoformat() != report_date:
            failures.append("report_date must match the end of the report window")
    except Exception:  # noqa: BLE001
        failures.append("date_from/date_to are invalid")
    if not str(effective_org.get("id") or org_context.get("target_org_id") or "").strip():
        failures.append("effective organization id is missing")

    binding = state.get("artifact_binding") if isinstance(state.get("artifact_binding"), dict) else {}
    if schema_version == REPORT_SCHEMA_VERSION:
        if not isinstance(state.get("summary_input"), dict):
            failures.append("summary_input must be an object")
        if not REPORT_ARTIFACT_TOKEN_RE.fullmatch(str(binding.get("artifact_token") or "")):
            failures.append("prepared artifact token is invalid")
        current_identity = _context_identity(context)
        expected_context_id = hashlib.sha256(_canonical_json(current_identity).encode("utf-8")).hexdigest()[:16]
        run_id = str(binding.get("run_id") or "").strip()
        expected_artifact_token = "%s-%s-%s" % (report_date, expected_context_id, run_id)
        summary_input = state.get("summary_input") if isinstance(state.get("summary_input"), dict) else {}
        summary_report = summary_input.get("report") if isinstance(summary_input.get("report"), dict) else {}
        current_summary_digest = hashlib.sha256(_canonical_json(summary_input).encode("utf-8")).hexdigest()
        digest_payload = dict(state)
        digest_payload.pop("artifact_binding", None)
        current_prepared_digest = hashlib.sha256(_canonical_json(digest_payload).encode("utf-8")).hexdigest()
        if binding.get("context_id") != expected_context_id:
            failures.append("prepared context binding does not match report context")
        if binding.get("artifact_token") != expected_artifact_token:
            failures.append("prepared artifact token does not match report context")
        if summary_report.get("context_id") != binding.get("context_id") or summary_report.get("run_id") != run_id:
            failures.append("summary input report binding does not match prepared context")
        if binding.get("summary_input_sha256") != current_summary_digest:
            failures.append("prepared summary input digest does not match")
        if binding.get("prepared_sha256") != current_prepared_digest:
            failures.append("prepared state digest does not match")

    if prepared_path is not None:
        target = Path(prepared_path)
        if target.is_symlink() or not _path_is_within(target, REPORT_PREPARED_DIR):
            failures.append("prepared path is outside the managed directory")
        elif schema_version == REPORT_SCHEMA_VERSION:
            expected_name = "JumpServer-%s.prepared.json" % binding.get("artifact_token")
            if target.name != expected_name:
                failures.append("prepared filename does not match artifact binding")
        elif not LEGACY_PREPARED_NAME_RE.fullmatch(target.name):
            failures.append("legacy prepared filename is invalid")

    metadata = load_report_metadata()
    tbody_fields = {
        str(item.get("field"))
        for item in metadata.get("fields") or []
        if isinstance(item, dict) and item.get("render_contract") == TBODY_ROWS_CONTRACT
    }
    for field in tbody_fields:
        for container in (state.get("resolved_values") or {}, state.get("derived_values") or {}):
            value = container.get(field) if isinstance(container, dict) else None
            if value not in {None, ""}:
                try:
                    _validate_tbody_html(value)
                except CLIError:
                    failures.append("prepared field %s contains unsafe table HTML" % field)

    def validate_html_values(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                validate_html_values(child_value, str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                validate_html_values(child_value, key)
        elif isinstance(value, str) and (key == "rows_html" or key.endswith("_rows")) and value:
            try:
                _validate_tbody_html(value)
            except CLIError:
                failures.append("prepared source field %s contains unsafe table HTML" % key)

    validate_html_values(state.get("source_payloads") or {})

    if failures:
        raise CLIError(
            "Prepared report state validation failed.",
            payload={"reason_code": "invalid_prepared_report", "validation_failures": failures},
        )
    return state


def _validate_summary_binding(state: dict[str, Any], summary_payload: dict[str, Any]) -> None:
    binding = state.get("artifact_binding") if isinstance(state.get("artifact_binding"), dict) else {}
    if _int_value(state.get("schema_version")) < REPORT_SCHEMA_VERSION:
        return
    supplied_binding = summary_payload.get("report_binding") if isinstance(summary_payload.get("report_binding"), dict) else summary_payload
    supplied_context_id = str(supplied_binding.get("context_id") or "").strip()
    supplied_prepared_digest = str(supplied_binding.get("prepared_sha256") or "").strip()
    if supplied_context_id != binding.get("context_id") or supplied_prepared_digest != binding.get("prepared_sha256"):
        raise CLIError(
            "Skill summary does not match the prepared report context.",
            payload={
                "reason_code": "report_summary_context_mismatch",
                "required_report_binding": {
                    "context_id": binding.get("context_id"),
                    "prepared_sha256": binding.get("prepared_sha256"),
                },
            },
        )


def _bound_source_payloads(source_payloads: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def bound_mapping(value: dict[str, Any]) -> dict[str, Any]:
        payload = dict(value)
        for key, item in list(payload.items()):
            if isinstance(item, dict):
                payload[key] = bound_mapping(item)
                continue
            if isinstance(item, list) and key in STORED_RECORD_KEYS | {"samples"}:
                payload["%s_total" % key] = len(item)
                payload["%s_truncated" % key] = len(item) > REPORT_STORED_RECORD_LIMIT
                payload[key] = [bound_mapping(row) if isinstance(row, dict) else row for row in item[:REPORT_STORED_RECORD_LIMIT]]
        return payload

    bounded: dict[str, dict[str, Any]] = {}
    for source_key, source_payload in source_payloads.items():
        bounded[source_key] = bound_mapping(dict(source_payload or {}))
    return bounded


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _managed_summary_roots() -> list[Path]:
    roots = [Path(tempfile.gettempdir())]
    conventional_tmp = Path("/tmp")
    if conventional_tmp not in roots:
        roots.append(conventional_tmp)
    return roots


def _cleanup_report_intermediate_files(
    prepared_path: str | Path,
    summary_file: str | Path,
    *,
    cleanup_summary: bool = False,
) -> dict[str, Any]:
    deleted_paths = []
    failed_paths = []
    skipped_paths = []
    blocked_paths = []
    prepared_target = Path(prepared_path)
    summary_target = Path(summary_file)
    prepared_allowed = (
        not REPORT_PREPARED_DIR.is_symlink()
        and not prepared_target.is_symlink()
        and (
            LEGACY_PREPARED_NAME_RE.fullmatch(prepared_target.name) is not None
            or re.fullmatch(
                r"JumpServer-\d{4}-\d{2}-\d{2}-[a-f0-9]{16}-[A-Za-z0-9_-]{4,64}\.prepared\.json",
                prepared_target.name,
            )
            is not None
        )
        and _path_is_within(prepared_target, REPORT_PREPARED_DIR)
    )
    summary_allowed = (
        cleanup_summary
        and not summary_target.is_symlink()
        and summary_target.name.startswith("jms-summary")
        and summary_target.suffix == ".json"
        and any(_path_is_within(summary_target, root) for root in _managed_summary_roots())
    )
    path_specs = [
        (prepared_target, prepared_allowed, True),
        (summary_target, summary_allowed, cleanup_summary),
    ]

    seen: set[str] = set()
    for target, allowed, requested in path_specs:
        path_text = str(target)
        identity = str(target.resolve(strict=False))
        if identity in seen:
            continue
        seen.add(identity)
        if not requested:
            skipped_paths.append(path_text)
            continue
        if not allowed:
            blocked_paths.append(path_text)
            continue
        if not target.exists():
            skipped_paths.append(path_text)
            continue
        try:
            target.unlink()
        except OSError as exc:
            failed_paths.append({"path": path_text, "error": str(exc)})
        else:
            deleted_paths.append(path_text)
    return {
        "enabled": True,
        "summary_cleanup_enabled": cleanup_summary,
        "deleted_paths": deleted_paths,
        "failed_paths": failed_paths,
        "skipped_paths": skipped_paths,
        "blocked_paths": blocked_paths,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".json") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
            temp_name = handle.name
        os.chmod(temp_name, 0o600)
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise CLIError(
                "Report artifact already exists; refusing to overwrite it.",
                payload={"reason_code": "report_artifact_exists", "path": str(path)},
            ) from exc
    finally:
        if temp_name:
            with suppress(OSError):
                Path(temp_name).unlink()


def _write_text_atomic(path: Path, content: str, *, suffix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=suffix) as handle:
            handle.write(content)
            temp_name = handle.name
        os.chmod(temp_name, 0o600)
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise CLIError(
                "Report artifact already exists; refusing to overwrite it.",
                payload={"reason_code": "report_artifact_exists", "path": str(path)},
            ) from exc
    finally:
        if temp_name:
            with suppress(OSError):
                Path(temp_name).unlink()


def _render_daily_usage_report_from_state(
    state: dict[str, Any],
    skill_summaries: dict[str, str],
) -> dict[str, Any]:
    _validate_prepared_state(state)
    metadata = load_report_metadata()
    template_html = load_report_template()
    contract = validate_report_contract(metadata=metadata, template_html=template_html)
    if not contract.get("contract_passed"):
        raise CLIError(
            "Report contract validation failed before generation.",
            payload=contract,
        )

    context = dict(state.get("context") or {})
    runtime_context = context.get("runtime_context") or {}
    org_context = context.get("org_context") or {}
    source_payloads = dict(state.get("source_payloads") or {})
    resolved_values = dict(state.get("resolved_values") or {})
    derived_values = dict(state.get("derived_values") or {})
    derived_values.update(_normalize_skill_summary_fields(skill_summaries))

    rendered_fields: dict[str, str] = {}
    for item in metadata.get("fields", []):
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field") or "").strip()
        if not field_name:
            continue
        raw_value = _resolve_field_value(
            item,
            resolved_values=resolved_values,
            source_payloads=source_payloads,
            derived_values=derived_values,
        )
        rendered_fields[field_name] = _render_field_value(item, raw_value)

    rendered_html = render_report_html(template_html, rendered_fields)
    validation = _validate_report_output(
        rendered_html=rendered_html,
        field_values=rendered_fields,
        metadata=metadata,
        source_payloads=source_payloads,
    )
    if not validation.get("passed"):
        raise CLIError(
            "Report generation failed validation. 生成失败，需要修复模板填充逻辑。",
            payload=validation,
        )

    artifact_binding = state.get("artifact_binding") if isinstance(state.get("artifact_binding"), dict) else {}
    artifact_token = str(artifact_binding.get("artifact_token") or "").strip() or None
    output = _default_report_output_path(runtime_context.get("report_date"), artifact_token)
    _write_text_atomic(output, rendered_html, suffix=".html")

    command_source = source_payloads.get("capability:command-record-query", {})
    result = {
        "output_path": str(output),
        "template_path": str(REPORT_TEMPLATE_PATH.relative_to(SKILL_DIR)),
        "metadata_path": str(REPORT_METADATA_PATH.relative_to(SKILL_DIR)),
        "effective_org": org_context.get("effective_org") or {},
        "switchable_orgs": org_context.get("switchable_orgs") or [],
        "queried_command_storage_ids": command_source.get("queried_command_storage_ids") or [],
        "queried_command_storage_count": int(command_source.get("queried_command_storage_count") or 0),
        "report_date": runtime_context.get("report_date"),
        "date_from": runtime_context.get("date_from"),
        "date_to": runtime_context.get("date_to"),
        "validation_summary": validation,
        "skill_summary_fields": list(SKILL_SUMMARY_FIELDS),
        "report_binding": artifact_binding,
    }
    result.update(_collect_report_artifact_metadata(output))
    runtime_contract = validate_report_runtime_result(result)
    if not runtime_contract.get("contract_passed"):
        with suppress(OSError):
            output.unlink()
        raise CLIError(
            "Report generation finished but runtime artifact validation failed.",
            payload=runtime_contract,
        )
    return result


def build_daily_usage_prepare(
    *,
    date_expr: str | None = None,
    period_expr: str | None = None,
    date_from_expr: str | None = None,
    date_to_expr: str | None = None,
    org_id: str | None = None,
    org_name: str | None = None,
    command_storage_id: str | None = None,
) -> dict[str, Any]:
    state = _build_daily_usage_state(
        date_expr=date_expr,
        period_expr=period_expr,
        date_from_expr=date_from_expr,
        date_to_expr=date_to_expr,
        org_id=org_id,
        org_name=org_name,
        command_storage_id=command_storage_id,
    )
    context = state["context"]
    runtime_context = context["runtime_context"]
    command_source = state["source_payloads"].get("capability:command-record-query", {})
    login_source = state["source_payloads"].get("entrypoint:python3 subskills/query/scripts/jms_audit.py audit-list --audit-type login", {})
    artifact_binding = state.get("artifact_binding") if isinstance(state.get("artifact_binding"), dict) else {}
    artifact_token = str(artifact_binding.get("artifact_token") or "").strip() or None
    prepared_path = _default_prepared_output_path(runtime_context["report_date"], artifact_token)
    _write_json_atomic(prepared_path, state)
    return {
        "prepared_path": str(prepared_path),
        "template_path": str(REPORT_TEMPLATE_PATH.relative_to(SKILL_DIR)),
        "metadata_path": str(REPORT_METADATA_PATH.relative_to(SKILL_DIR)),
        "effective_org": context["org_context"]["effective_org"],
        "switchable_orgs": context["org_context"]["switchable_orgs"],
        "queried_command_storage_ids": command_source.get("queried_command_storage_ids") or [],
        "queried_command_storage_count": int(command_source.get("queried_command_storage_count") or 0),
        "report_date": runtime_context["report_date"],
        "date_from": runtime_context["date_from"],
        "date_to": runtime_context["date_to"],
        "summary_input": state["summary_input"],
        "login_fetch_diagnostics": login_source.get("fetch_diagnostics") or {},
        "required_summary_fields": list(SKILL_SUMMARY_FIELDS),
        "report_binding": {
            "context_id": artifact_binding.get("context_id"),
            "prepared_sha256": artifact_binding.get("prepared_sha256"),
        },
        "output_generated": False,
    }


def render_prepared_daily_usage_report(
    *,
    prepared_path: str,
    summary_file: str,
    cleanup_intermediates: bool = False,
) -> dict[str, Any]:
    summary_payload = _load_json_object(summary_file, max_bytes=REPORT_SUMMARY_MAX_BYTES)
    skill_summaries = _normalize_skill_summary_fields(summary_payload)
    prepared_target = Path(prepared_path)
    if (
        REPORT_PREPARED_DIR.is_symlink()
        or prepared_target.is_symlink()
        or not _path_is_within(prepared_target, REPORT_PREPARED_DIR)
        or not prepared_target.name.startswith("JumpServer-")
        or not prepared_target.name.endswith(".prepared.json")
    ):
        raise CLIError(
            "Prepared report path is outside the managed directory.",
            payload={"reason_code": "invalid_prepared_path", "path": str(prepared_target)},
        )
    state = _load_json_object(prepared_target, max_bytes=REPORT_PREPARED_MAX_BYTES)
    _validate_prepared_state(state, prepared_path=prepared_target)
    _validate_summary_binding(state, summary_payload)
    result = _render_daily_usage_report_from_state(state, skill_summaries)
    result["intermediate_cleanup"] = _cleanup_report_intermediate_files(
        prepared_path,
        summary_file,
        cleanup_summary=cleanup_intermediates,
    )
    return result
