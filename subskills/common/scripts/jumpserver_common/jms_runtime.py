"""JumpServer 公共运行时模块。

按下面的逻辑分节阅读：

- Constants & flags      : 顶部常量、reason code、env key 白名单
- Sensitive redaction    : `mask_secret` / `redact_sensitive` 系列
- CLI guidance & filters : `CLIError`、`build_cli_guidance_payload`、filter 解析
- Local env I/O          : `.env` 读写、`config-status`、`get_config_status`
- Client/discovery build : `build_config`、`create_client`、`create_discovery`
- Organization context   : 可访问组织、当前组织、显式 / 预览 / 解析组织
- Platform resolve       : `resolve_platform_reference`
- Output serialization   : `serialize`、`print_json`、`run_and_print`

所有调用方都通过 `from jumpserver_common.jms_runtime import ...` 拿到所需名字，分节
注释只是为了让长文件更易导航；不要把任何分节当成"独立模块"。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .jms_constants import DEFAULT_PAGE_SIZE, DEFAULT_TIMEOUT
from .jms_types import JumpServerAPIError, JumpServerConfig, PlatformSpec

if TYPE_CHECKING:
    from .jms_api_client import JumpServerClient
    from .jms_discovery import JumpServerDiscovery


SKILL_DIR = Path(__file__).resolve().parents[4]
LOCAL_ENV_FILE = SKILL_DIR / ".env"
GLOBAL_ORG_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000002"
RESERVED_INTERNAL_ORG_ID = "00000000-0000-0000-0000-000000000004"
# JumpServer V4.10 保留组织 UUID 约定。若部署环境的 Default/System 组织 UUID 不同，
# 这里的集合需要同步修改，否则自动选中逻辑会失效。
RESERVED_AUTO_SELECT_ORG_SETS = frozenset(
    {
        frozenset({DEFAULT_ORG_ID}),
        frozenset({DEFAULT_ORG_ID, RESERVED_INTERNAL_ORG_ID}),
    }
)
UUID_LIKE_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)
ENV_KEYS = (
    "JMS_API_URL",
    "JMS_ACCESS_KEY_ID",
    "JMS_ACCESS_KEY_SECRET",
    "JMS_USERNAME",
    "JMS_PASSWORD",
    "JMS_ORG_ID",
    "JMS_TIMEOUT",
    "JMS_VERIFY_TLS",
)
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "access_key",
        "access_key_secret",
        "api_key",
        "jms_access_key_id",
        "jms_access_key_secret",
        "jms_password",
        "passphrase",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "token",
    }
)
WRITEABLE_ENV_KEYS = frozenset(ENV_KEYS)
NONSECRET_ENV_KEYS = (
    "JMS_API_URL",
    "JMS_USERNAME",
    "JMS_ORG_ID",
    "JMS_TIMEOUT",
    "JMS_VERIFY_TLS",
)
ORG_LIST_PATH = "/api/v1/orgs/orgs/"
ORG_CURRENT_PATH = "/api/v1/orgs/orgs/current/"
USER_PROFILE_PATH = "/api/v1/users/profile/"
ORG_SELECTION_NEXT_STEP = (
    "python3 subskills/common/scripts/jms_common.py select-org --org-id <org-id>"
)
ORG_SELECTION_REQUIRED_REASON_CODE = "organization_selection_required"
ORG_SELECTION_POLICY = "required_before_query_when_multiple_accessible_orgs"
AMBIGUOUS_ORG_SELECTOR_REASON_CODE = "ambiguous_organization_selector"
ORG_NOT_ACCESSIBLE_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
INVALID_JSON_PAYLOAD_REASON_CODE = "invalid_json_payload"
INVALID_FILTER_ASSIGNMENT_REASON_CODE = "invalid_filter_assignment"
CONFIRMATION_REQUIRED_REASON_CODE = "confirmation_required"
DEPRECATED_PAGINATION_REASON_CODE = "deprecated_pagination_args"
_GLOBAL_ORG_PROBE_ATTEMPTED = False
_GLOBAL_ORG_PROBE_RESULT: dict[str, Any] | None = None
ENTRYPOINT_SCRIPT_REFS = {
    "jms_query.py": "subskills/query/scripts/jms_query.py",
    "jms_access.py": "subskills/query/scripts/jms_access.py",
    "jms_permissions.py": "subskills/query/scripts/jms_permissions.py",
    "jms_audit.py": "subskills/query/scripts/jms_audit.py",
    "jms_inspect.py": "subskills/query/scripts/jms_inspect.py",
    "jms_common.py": "subskills/common/scripts/jms_common.py",
    "jms_runtime_query.py": "subskills/query/scripts/jms_runtime_query.py",
    "jms_report.py": "subskills/query/scripts/jms_report.py",
    "jms_create_user.py": "subskills/create/scripts/jms_create_user.py",
    "jms_create_user_group.py": "subskills/create/scripts/jms_create_user_group.py",
    "jms_create_org.py": "subskills/create/scripts/jms_create_org.py",
    "jms_create_label.py": "subskills/create/scripts/jms_create_label.py",
    "jms_create_node.py": "subskills/create/scripts/jms_create_node.py",
    "jms_create_asset.py": "subskills/create/scripts/jms_create_asset.py",
    "jms_create_account_template.py": "subskills/create/scripts/jms_create_account_template.py",
    "jms_asset_account_bulk.py": "subskills/create/scripts/jms_asset_account_bulk.py",
    "jms_create_zone_gateway.py": "subskills/create/scripts/jms_create_zone_gateway.py",
    "jms_create_command_acl.py": "subskills/create/scripts/jms_create_command_acl.py",
    "jms_create_login_acl.py": "subskills/create/scripts/jms_create_login_acl.py",
    "jms_create_connect_method_acl.py": "subskills/create/scripts/jms_create_connect_method_acl.py",
    "jms_create_asset_permission.py": "subskills/create/scripts/jms_create_asset_permission.py",
    "jms_create_login_asset_acl.py": "subskills/create/scripts/jms_create_login_asset_acl.py",
    "jms_create_data_masking_rule.py": "subskills/create/scripts/jms_create_data_masking_rule.py",
    "jms_invite_user.py": "subskills/create/scripts/jms_invite_user.py",
    "jms_add_user_to_group.py": "subskills/create/scripts/jms_add_user_to_group.py",
}


def _script_ref(script_name: str) -> str:
    return ENTRYPOINT_SCRIPT_REFS.get(str(script_name or "").strip(), str(script_name or "").strip())


# ---------------------------------------------------------------------------
# Section: CLI guidance & filters
# ---------------------------------------------------------------------------
class CLIHelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    """Argparse formatter that keeps example newlines while still showing defaults."""


class CLIError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = dict(payload or {})


def is_uuid_like(value: Any) -> bool:
    return bool(UUID_LIKE_RE.fullmatch(str(value or "").strip()))


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


# ---------------------------------------------------------------------------
# Section: Sensitive redaction
# ---------------------------------------------------------------------------
def mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return "%s***%s" % (text[:4], text[-2:])


def _sensitive_field_name(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized in SENSITIVE_FIELD_NAMES


def _redact_sensitive_text(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return "%s%s%s" % (match.group(1), mask_secret(match.group(2)), match.group(3) or "")

    field_names = "|".join(re.escape(item) for item in sorted(SENSITIVE_FIELD_NAMES, key=len, reverse=True))
    return re.sub(
        r"(?i)([\"']?(?:%s)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)([\"']?)" % field_names,
        replace,
        value,
    )


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _sensitive_field_name(key):
                redacted[str(key)] = mask_secret(_redact_sensitive_text(str(item or "")))
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def has_cli_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def build_cli_guidance_payload(
    reason_code: str,
    *,
    user_message: str,
    action_hint: str | None = None,
    suggested_commands: list[str] | None = None,
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason_code": reason_code,
        "user_message": user_message,
        "action_hint": action_hint,
        "suggested_commands": [item for item in (suggested_commands or []) if str(item or "").strip()],
    }
    for key, value in details.items():
        if value is not None:
            payload[key] = value
    return payload


def _parse_cli_scalar(value: str) -> Any:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if re.fullmatch(r"-?(?:0|[1-9]\d*)", text):
        return int(text)
    if re.fullmatch(r"-?(?:0|[1-9]\d*)\.\d+", text):
        return float(text)
    return text


def parse_filter_assignments(
    values: list[str] | None,
    *,
    usage_examples: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for raw_item in values or []:
        item = str(raw_item or "").strip()
        if not item or "=" not in item:
            raise CLIError(
                "无法解析 --filter 参数。",
                payload=build_cli_guidance_payload(
                    INVALID_FILTER_ASSIGNMENT_REASON_CODE,
                    user_message="`--filter` 需要使用 `key=value` 形式，例如 `--filter name=Default`。",
                    action_hint="优先使用显式参数；如果需要补充高级筛选，再重复传入 `--filter key=value`。",
                    suggested_commands=usage_examples,
                    invalid_filter=item or None,
                ),
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CLIError(
                "无法解析 --filter 参数。",
                payload=build_cli_guidance_payload(
                    INVALID_FILTER_ASSIGNMENT_REASON_CODE,
                    user_message="`--filter` 的 key 不能为空，例如 `--filter name=Default`。",
                    action_hint="请把 `=` 左侧改成实际字段名。",
                    suggested_commands=usage_examples,
                    invalid_filter=item,
                ),
            )
        payload[key] = _parse_cli_scalar(value)
    return payload


# ---------------------------------------------------------------------------
# Section: Local env I/O
# ---------------------------------------------------------------------------
def read_local_env(path: Path | None = None) -> dict[str, str]:
    env_path = Path(path or LOCAL_ENV_FILE)
    if not env_path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            payload[key] = _strip_wrapping_quotes(value.strip())
    return payload


def load_local_env(path: Path | None = None) -> None:
    env_path = Path(path or LOCAL_ENV_FILE)
    for key, value in read_local_env(env_path).items():
        if key in ENV_KEYS and not os.getenv(key):
            os.environ[key] = value


def current_runtime_values(path: Path | None = None) -> dict[str, str]:
    values = read_local_env(path)
    for key in ENV_KEYS:
        if key in os.environ and os.environ[key] != "":
            values[key] = os.environ[key]
    return values


def write_local_env_config(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    env_path = Path(path or LOCAL_ENV_FILE)
    final: dict[str, str] = {}
    current = read_local_env(env_path)
    final.update({key: value for key, value in current.items() if key not in WRITEABLE_ENV_KEYS})

    for key in WRITEABLE_ENV_KEYS:
        value = payload.get(key)
        if value is None:
            if key in current:
                final[key] = current[key]
            continue
        final[key] = str(value)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key in sorted(final):
        value = final[key]
        if value is None:
            continue
        lines.append('%s="%s"' % (key, str(value).replace('"', '\\"')))
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    for key in WRITEABLE_ENV_KEYS:
        if key in final:
            os.environ[key] = str(final[key])
    return {
        "env_file_path": str(env_path),
        "current_nonsecret": current_nonsecret_view(current_runtime_values(env_path)),
    }


def current_nonsecret_view(values: dict[str, str] | None = None) -> dict[str, str]:
    payload = dict(values or current_runtime_values())
    return {key: payload[key] for key in NONSECRET_ENV_KEYS if key in payload and payload[key] != ""}


def get_config_status(path: Path | None = None) -> dict[str, Any]:
    values = current_runtime_values(path)
    missing = []
    invalid_fields = []
    partial_auth_fields = []
    has_url = bool(values.get("JMS_API_URL"))
    has_ak = bool(values.get("JMS_ACCESS_KEY_ID"))
    has_sk = bool(values.get("JMS_ACCESS_KEY_SECRET"))
    has_username = bool(values.get("JMS_USERNAME"))
    has_password = bool(values.get("JMS_PASSWORD"))
    has_aksk = has_ak and has_sk
    has_password_auth = has_username and has_password

    api_url = str(values.get("JMS_API_URL") or "").strip()
    if not api_url:
        missing.append("JMS_API_URL")
    else:
        parsed_url = urlparse(api_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            invalid_fields.append("JMS_API_URL")
    if has_ak != has_sk:
        if not has_ak:
            partial_auth_fields.append("JMS_ACCESS_KEY_ID")
        if not has_sk:
            partial_auth_fields.append("JMS_ACCESS_KEY_SECRET")
    if has_username != has_password:
        if not has_username:
            partial_auth_fields.append("JMS_USERNAME")
        if not has_password:
            partial_auth_fields.append("JMS_PASSWORD")
    if not has_aksk and not has_password_auth:
        if partial_auth_fields:
            missing.extend(partial_auth_fields)
        else:
            missing.append("JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET or JMS_USERNAME/JMS_PASSWORD")

    auth_mode = "none"
    if has_aksk:
        auth_mode = "aksk"
    elif has_password_auth:
        auth_mode = "password"

    timeout_value = str(values.get("JMS_TIMEOUT") or "").strip()
    if timeout_value:
        try:
            if int(timeout_value) <= 0:
                invalid_fields.append("JMS_TIMEOUT")
        except ValueError:
            invalid_fields.append("JMS_TIMEOUT")

    return {
        "env_file_path": str(Path(path or LOCAL_ENV_FILE)),
        "exists": Path(path or LOCAL_ENV_FILE).exists(),
        "complete": not missing and not invalid_fields,
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "auth_mode": auth_mode,
        "current_nonsecret": current_nonsecret_view(values),
    }


def parse_json_arg(
    value: str | None,
    *,
    default: dict[str, Any] | None = None,
    source: str = "--filters",
    usage_examples: list[str] | None = None,
) -> dict[str, Any]:
    if value in {None, ""}:
        return dict(default or {})
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CLIError(
            "无法解析 %s 参数。" % source,
            payload=build_cli_guidance_payload(
                INVALID_JSON_PAYLOAD_REASON_CODE,
                user_message="%s 需要传入 JSON 对象字符串，例如 '{\"name\": \"Default\"}'。" % source,
                action_hint="优先改用显式参数或重复的 `--filter key=value`；如果继续使用 JSON，请检查引号、逗号和花括号。",
                suggested_commands=usage_examples,
                input_name=source,
                parser_error=exc.msg,
                raw_value=value,
            ),
        ) from exc
    if not isinstance(payload, dict):
        raise CLIError(
            "%s 必须是 JSON 对象。" % source,
            payload=build_cli_guidance_payload(
                INVALID_JSON_PAYLOAD_REASON_CODE,
                user_message="%s 需要传入 JSON 对象，而不是数组或普通字符串。" % source,
                action_hint="请改成 `{\"key\": \"value\"}` 这种对象形式，或直接使用显式参数 / `--filter key=value`。",
                suggested_commands=usage_examples,
                input_name=source,
                raw_value=value,
            ),
        )
    return payload


def merge_filter_args(
    args: argparse.Namespace,
    *,
    default: dict[str, Any] | None = None,
    explicit_fields: dict[str, str] | list[str] | tuple[str, ...] = (),
    forbidden_fields: list[str] | tuple[str, ...] = (),
    usage_examples: list[str] | None = None,
) -> dict[str, Any]:
    filters = parse_json_arg(
        getattr(args, "filters", None),
        default=default,
        source="--filters",
        usage_examples=usage_examples,
    )
    filters.update(parse_filter_assignments(getattr(args, "filter", None), usage_examples=usage_examples))
    if isinstance(explicit_fields, dict):
        field_map = dict(explicit_fields)
    else:
        field_map = {field: field for field in explicit_fields}
    for attr_name, filter_key in field_map.items():
        if not hasattr(args, attr_name):
            continue
        value = getattr(args, attr_name)
        if has_cli_value(value):
            filters[filter_key] = value
    if forbidden_fields:
        active_forbidden = {
            field: filters[field]
            for field in forbidden_fields
            if field in filters and has_cli_value(filters[field])
        }
        if active_forbidden:
            raise CLIError(
                "分页参数已废弃。",
                payload=build_cli_guidance_payload(
                    DEPRECATED_PAGINATION_REASON_CODE,
                    user_message="该 skill 已改为全量抓取并全量返回，不再支持 `--limit/--offset` 或等价分页过滤。",
                    action_hint="请直接移除这些分页参数后重试；当前命令会自动翻页抓取查询范围内的全部数据。",
                    suggested_commands=usage_examples,
                    deprecated_fields=sorted(active_forbidden),
                    deprecated_values=active_forbidden,
                ),
            )
    return filters


def _pagination_arg_names(tokens: list[str]) -> list[str]:
    names: list[str] = []
    for token in tokens:
        if token in {"--limit", "--offset"}:
            names.append(token)
            continue
        if token.startswith("--limit="):
            names.append("--limit")
            continue
        if token.startswith("--offset="):
            names.append("--offset")
    seen: list[str] = []
    for item in names:
        if item not in seen:
            seen.append(item)
    return seen


def _strip_pagination_tokens(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--limit=") or token.startswith("--offset="):
            index += 1
            continue
        if token in {"--limit", "--offset"}:
            index += 1
            if index < len(tokens) and not str(tokens[index]).startswith("--"):
                index += 1
            continue
        cleaned.append(token)
        index += 1
    return cleaned


def reject_deprecated_pagination_cli_args(
    argv: list[str],
    *,
    script_name: str,
    deprecated_commands: set[str],
    usage_examples_by_command: dict[str, list[str]] | None = None,
) -> None:
    if not argv:
        return
    command = str(argv[0] or "").strip()
    if command not in deprecated_commands:
        return
    deprecated_args = _pagination_arg_names(argv[1:])
    if not deprecated_args:
        return
    cleaned_args = _strip_pagination_tokens(argv)
    suggested_commands: list[str] = []
    if cleaned_args:
        suggested_commands.append(
            "python3 %s %s" % (_script_ref(script_name), " ".join(cleaned_args))
        )
    for item in (usage_examples_by_command or {}).get(command, []):
        if item not in suggested_commands:
            suggested_commands.append(item)
    raise CLIError(
        "分页参数已废弃。",
        payload=build_cli_guidance_payload(
            DEPRECATED_PAGINATION_REASON_CODE,
            user_message="该 skill 已改为全量抓取并全量返回，不再支持 `--limit/--offset`。",
            action_hint="请直接移除这些参数后重试；当前命令会自动翻页抓取查询范围内的全部数据。",
            suggested_commands=suggested_commands,
            command=command,
            deprecated_args=deprecated_args,
        ),
    )


def add_filter_arguments(parser: argparse.ArgumentParser, *, include_legacy_json: bool = True) -> None:
    parser.add_argument(
        "--filter",
        action="append",
        metavar="KEY=VALUE",
        help="推荐的高级补充筛选写法，可重复传入，例如 `--filter user=example.user --filter protocol=ssh`。",
    )
    if include_legacy_json:
        parser.add_argument(
            "--filters",
            help="兼容模式的 JSON 对象字符串。推荐优先使用显式参数或重复的 `--filter key=value`。",
        )


def require_confirmation(args: argparse.Namespace) -> None:
    if not getattr(args, "confirm", False):
        raise CLIError(
            "当前操作需要显式确认。",
            payload=build_cli_guidance_payload(
                CONFIRMATION_REQUIRED_REASON_CODE,
                user_message="这个命令会改写本地运行时配置，继续前必须追加 `--confirm`。",
                action_hint="先查看当前返回的预览结果，确认无误后再重跑一次并加上 `--confirm`。",
            ),
        )


# ---------------------------------------------------------------------------
# Section: Client / discovery build
# ---------------------------------------------------------------------------
def build_config(*, org_id: str | None = None) -> JumpServerConfig:
    load_local_env()
    values = current_runtime_values()
    base_url = values.get("JMS_API_URL")
    config_status = get_config_status()
    if not config_status.get("complete"):
        raise CLIError(
            "Runtime configuration validation failed.",
            payload={"config_status": config_status},
        )

    if not base_url:
        raise CLIError(
            "JMS_API_URL is required.",
            payload={"config_status": config_status},
        )

    access_key = values.get("JMS_ACCESS_KEY_ID") or ""
    secret_key = values.get("JMS_ACCESS_KEY_SECRET") or ""
    username = values.get("JMS_USERNAME") or ""
    password = values.get("JMS_PASSWORD") or ""

    has_aksk = bool(access_key and secret_key)
    has_password_auth = bool(username and password)
    if not has_aksk and not has_password_auth:
        raise CLIError(
            "Provide JMS_ACCESS_KEY_ID/JMS_ACCESS_KEY_SECRET or JMS_USERNAME/JMS_PASSWORD before running business commands.",
            payload={"config_status": get_config_status()},
        )

    if has_aksk:
        username = ""
        password = ""

    return JumpServerConfig(
        base_url=base_url,
        access_key=access_key,
        secret_key=secret_key,
        username=username,
        password=password,
        org_id=org_id if org_id is not None else values.get("JMS_ORG_ID", ""),
        verify_tls=parse_bool(values.get("JMS_VERIFY_TLS"), default=False),
    ).validate(require_org_id=False)


def create_client(*, org_id: str | None = None) -> JumpServerClient:
    from .jms_api_client import JumpServerClient

    config = build_config(org_id=org_id)
    timeout = current_runtime_values().get("JMS_TIMEOUT")
    return JumpServerClient(
        config=config,
        timeout=int(timeout or DEFAULT_TIMEOUT),
    )


def create_discovery(*, org_id: str | None = None) -> JumpServerDiscovery:
    from .jms_discovery import JumpServerDiscovery

    return JumpServerDiscovery(create_client(org_id=org_id))


# ---------------------------------------------------------------------------
# Section: Organization context
# ---------------------------------------------------------------------------
def _global_org_probe_error(exc: JumpServerAPIError) -> bool:
    if exc.status_code in {403, 404}:
        return True
    text = " ".join(
        [
            str(exc.message or ""),
            str(exc.details or ""),
        ]
    ).lower()
    return any(
        keyword in text
        for keyword in (
            "forbidden",
            "denied",
            "permission",
            "not accessible",
            "not found",
            "无权限",
            "拒绝",
            "不可访问",
            "不存在",
        )
    )


def _global_org_candidate() -> dict[str, Any] | None:
    global _GLOBAL_ORG_PROBE_ATTEMPTED, _GLOBAL_ORG_PROBE_RESULT
    if _GLOBAL_ORG_PROBE_ATTEMPTED:
        return dict(_GLOBAL_ORG_PROBE_RESULT) if _GLOBAL_ORG_PROBE_RESULT else None

    _GLOBAL_ORG_PROBE_ATTEMPTED = True
    try:
        payload = create_client(org_id=GLOBAL_ORG_ID).get(ORG_CURRENT_PATH)
    except JumpServerAPIError as exc:
        if _global_org_probe_error(exc):
            _GLOBAL_ORG_PROBE_RESULT = None
            return None
        raise

    if isinstance(payload, dict):
        candidate = dict(payload)
        reported_id = str(candidate.get("id") or "").strip()
        if reported_id and reported_id != GLOBAL_ORG_ID:
            _GLOBAL_ORG_PROBE_RESULT = None
            return None
        if not reported_id:
            candidate["id"] = GLOBAL_ORG_ID
            candidate["name"] = str(candidate.get("name") or "").strip() or "Global"
    else:
        candidate = {"id": GLOBAL_ORG_ID, "name": "Global"}

    candidate["source"] = str(candidate.get("source") or "").strip() or "global_org_probe"
    _GLOBAL_ORG_PROBE_RESULT = candidate
    return dict(candidate)


def list_accessible_orgs(*, include_global_probe: bool = True) -> list[dict[str, Any]]:
    client = create_client(org_id="")
    result = client.list_paginated(ORG_LIST_PATH)
    if not isinstance(result, list):
        raise CLIError("Organization list API did not return a list.")
    accessible_orgs = [dict(item) for item in result if isinstance(item, dict)]
    if not include_global_probe:
        return accessible_orgs

    known_ids = {
        str(item.get("id") or "").strip()
        for item in accessible_orgs
        if isinstance(item, dict)
    }
    if GLOBAL_ORG_ID not in known_ids:
        global_candidate = _global_org_candidate()
        if global_candidate:
            accessible_orgs.append(global_candidate)
    return accessible_orgs


def _switchable_orgs(accessible_orgs: list[dict[str, Any]], effective_org: dict[str, Any] | None) -> list[dict[str, Any]]:
    effective_org_id = str((effective_org or {}).get("id") or "").strip()
    if not effective_org_id:
        return []
    return [
        item
        for item in accessible_orgs
        if isinstance(item, dict) and str(item.get("id") or "").strip() and str(item.get("id") or "").strip() != effective_org_id
    ]


def _org_scope_label(effective_org: dict[str, Any] | None) -> str:
    payload = dict(effective_org or {})
    org_id = str(payload.get("id") or "").strip() or "<unknown-org-id>"
    org_name = str(payload.get("name") or "").strip() or "Unknown"
    return "%s (%s)" % (org_name, org_id)


def _org_context_hint(effective_org: dict[str, Any] | None, switchable_orgs: list[dict[str, Any]]) -> str | None:
    if not effective_org or not switchable_orgs:
        return None
    org_scope = _org_scope_label(effective_org)
    source = str(effective_org.get("source") or "").strip()
    if source == "reserved_auto_select":
        return "当前查询范围按保留组织规则固定为组织 %s；如需改查其他组织，请先切换组织。" % org_scope
    return "当前查询范围固定为组织 %s；如需切换查询范围，请先切换组织。" % org_scope


def build_org_selection_required_payload(context: dict[str, Any]) -> dict[str, Any]:
    candidate_orgs = context.get("candidate_orgs")
    if not isinstance(candidate_orgs, list):
        candidate_orgs = []
    suggested_commands = [
        "python3 subskills/common/scripts/jms_common.py select-org --org-id %s --confirm"
        % str(item.get("id") or "").strip()
        for item in candidate_orgs[:3]
        if str(item.get("id") or "").strip()
    ]
    return {
        "selection_required": True,
        "candidate_orgs": candidate_orgs,
        "candidate_org_count": len(candidate_orgs),
        "next_step": ORG_SELECTION_NEXT_STEP,
        "reserved_org_auto_select_eligible": bool(context.get("reserved_org_auto_select_eligible")),
        "reason_code": ORG_SELECTION_REQUIRED_REASON_CODE,
        "user_message": "检测到多个可访问组织，继续前必须先选择一个组织。",
        "action_hint": (
            "请从 candidate_orgs 中选择 1 个 org_id，然后执行 %s。"
            % ORG_SELECTION_NEXT_STEP
        ),
        "suggested_commands": suggested_commands,
        "org_selection_policy": ORG_SELECTION_POLICY,
        **org_context_output(context),
    }


def org_context_output(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "effective_org": context.get("effective_org"),
        "switchable_orgs": context.get("switchable_orgs") or [],
        "switchable_org_count": int(context.get("switchable_org_count") or 0),
        "org_context_hint": context.get("org_context_hint"),
    }


def _org_name(value: dict[str, Any] | None) -> str:
    return str((value or {}).get("name") or "").strip()


def _org_id(value: dict[str, Any] | None) -> str:
    return str((value or {}).get("id") or "").strip()


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _command_explicit_org_context(org_id: str, *, allow_global: bool = True) -> dict[str, Any]:
    org_id = str(org_id or "").strip()
    name = "Global" if allow_global and org_id == GLOBAL_ORG_ID else "Unknown"
    effective_org = {"id": org_id, "name": name, "source": "command_explicit"}
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前命令范围固定为组织 %s (%s)；不写入 .env。" % (name, org_id),
    }


def _command_named_org_context(selected_org: dict[str, Any], accessible_orgs: list[dict[str, Any]]) -> dict[str, Any]:
    effective_org = dict(selected_org)
    effective_org["source"] = "command_explicit"
    switchable_orgs = _switchable_orgs(accessible_orgs, effective_org)
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
        "org_context_hint": "当前命令范围固定为组织 %s (%s)；不写入 .env。" % (
            _org_name(effective_org) or "Unknown",
            _org_id(effective_org) or "<unknown-org-id>",
        ),
    }


def resolve_command_org_context(
    args: argparse.Namespace,
    *,
    allow_global: bool = True,
    fallback_to_selected: bool = True,
) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_SELECTOR_REASON_CODE,
                user_message="命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                provided=["org_id", "org_name"],
            ),
        )
    if requested_org_id:
        if requested_org_id == GLOBAL_ORG_ID and not allow_global:
            raise CLIError(
                "当前命令不支持全局组织。",
                payload=build_cli_guidance_payload(
                    ORG_NOT_ACCESSIBLE_REASON_CODE,
                    user_message="当前命令不允许使用全局组织 ID。",
                    action_hint="请改用具体组织 ID 或组织名称。",
                    org_id=requested_org_id,
                ),
            )
        return _command_explicit_org_context(requested_org_id, allow_global=allow_global)
    if requested_org_name:
        accessible_orgs = list_accessible_orgs(include_global_probe=allow_global)
        wanted = _lower_text(requested_org_name)
        matches = [
            item
            for item in accessible_orgs
            if isinstance(item, dict) and _lower_text(item.get("name")) == wanted
        ]
        if not matches:
            raise CLIError(
                "指定的组织当前不可访问。",
                payload=build_cli_guidance_payload(
                    ORG_NOT_ACCESSIBLE_REASON_CODE,
                    user_message="当前账号下找不到你指定的组织，请先从 `candidate_orgs` 里确认可访问组织。",
                    action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试。",
                    org_name=requested_org_name,
                    candidate_orgs=accessible_orgs,
                ),
            )
        if len(matches) > 1:
            raise CLIError(
                "给定的组织名称匹配到多个候选组织。",
                payload=build_cli_guidance_payload(
                    AMBIGUOUS_ORG_REASON_CODE,
                    user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称。",
                    action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试。",
                    org_name=requested_org_name,
                    candidate_orgs=matches[:10],
                ),
            )
        return _command_named_org_context(dict(matches[0]), accessible_orgs)
    if fallback_to_selected:
        return ensure_selected_org_context()
    return _command_explicit_org_context("")


def raise_create_global_org_error(
    org_id: str,
    *,
    resource_name: str,
    user_message: str | None = None,
) -> None:
    raise CLIError(
        "目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            ORG_NOT_ACCESSIBLE_REASON_CODE,
            user_message=user_message or "%s时，目标组织不能使用全局组织 ID。" % resource_name,
            action_hint="请改用具体目标组织 ID 或 `--org-name <target-org>`。",
            org_id=org_id,
        ),
    )


def create_env_org_context(
    *,
    resource_name: str,
    missing_user_message: str | None = None,
    global_user_message: str | None = None,
) -> dict[str, Any]:
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    if not org_id:
        raise CLIError(
            "未选择目标组织。",
            payload=build_cli_guidance_payload(
                ORG_SELECTION_REQUIRED_REASON_CODE,
                user_message=missing_user_message
                or "未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定%s组织。" % resource_name,
                action_hint="请传入 `--org-id <org-id>` 或 `--org-name <name>`，或先用 common 子 skill 选择当前组织。",
            ),
        )
    if org_id == GLOBAL_ORG_ID:
        raise_create_global_org_error(org_id, resource_name=resource_name, user_message=global_user_message)
    return {
        "effective_org": {"id": org_id, "name": "Unknown", "source": "env"},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前命令范围使用 .env JMS_ORG_ID=%s；不写入 .env。" % org_id,
    }


def preview_create_org_context(
    args: argparse.Namespace,
    *,
    resource_name: str,
    confirm_action: str = "创建",
    no_org_hint: str | None = None,
    global_user_message: str | None = None,
) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_SELECTOR_REASON_CODE,
                user_message="命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                provided=["org_id", "org_name"],
            ),
        )
    if requested_org_id == GLOBAL_ORG_ID:
        raise_create_global_org_error(
            requested_org_id,
            resource_name=resource_name,
            user_message=global_user_message,
        )
    if requested_org_id:
        return {
            "effective_org": {"id": requested_org_id, "name": "Unknown", "source": "command_explicit_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织 ID %s；追加 --confirm 后才解析组织并%s。" % (
                requested_org_id,
                confirm_action,
            ),
        }
    if requested_org_name:
        return {
            "effective_org": {"id": "", "name": requested_org_name, "source": "command_org_name_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织并%s。" % (
                requested_org_name,
                confirm_action,
            ),
        }
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    if org_id == GLOBAL_ORG_ID:
        raise_create_global_org_error(org_id, resource_name=resource_name, user_message=global_user_message)
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": no_org_hint or "dry-run 仅预览 payload；正式创建时未传组织将使用 .env JMS_ORG_ID。",
    }


def current_org(client: JumpServerClient | None = None) -> dict[str, Any]:
    active_client = client or create_client()
    result = active_client.get(ORG_CURRENT_PATH)
    if isinstance(result, dict):
        return result
    return {}


def user_profile(client: JumpServerClient | None = None) -> dict[str, Any]:
    active_client = client or create_client()
    result = active_client.get(USER_PROFILE_PATH)
    if isinstance(result, dict):
        return result
    return {}


def persist_selected_org(org_id: str) -> dict[str, Any]:
    values = current_runtime_values()
    values["JMS_ORG_ID"] = org_id
    return write_local_env_config(values)


def resolve_effective_org_context(*, auto_select: bool = True) -> dict[str, Any]:
    values = current_runtime_values()
    selected_org_id = str(values.get("JMS_ORG_ID") or "").strip()
    accessible_orgs = list_accessible_orgs()
    by_id = {str(item.get("id") or ""): item for item in accessible_orgs if isinstance(item, dict)}
    accessible_ids = frozenset([key for key in by_id if key])
    selected_org = by_id.get(selected_org_id) if selected_org_id else None
    reserved_auto_select_eligible = accessible_ids in RESERVED_AUTO_SELECT_ORG_SETS

    if selected_org:
        effective_org = dict(selected_org)
        effective_org["source"] = "env"
        switchable_orgs = _switchable_orgs(accessible_orgs, effective_org)
        return {
            "accessible_orgs": accessible_orgs,
            "candidate_orgs": accessible_orgs,
            "effective_org": effective_org,
            "multiple_accessible_orgs": len(accessible_orgs) > 1,
            "selection_required": False,
            "reserved_org_auto_select_eligible": reserved_auto_select_eligible,
            "selected_org_accessible": True,
            "switchable_orgs": switchable_orgs,
            "switchable_org_count": len(switchable_orgs),
            "org_context_hint": _org_context_hint(effective_org, switchable_orgs),
        }

    if reserved_auto_select_eligible and auto_select:
        persist_selected_org(DEFAULT_ORG_ID)
        auto_selected = dict(by_id.get(DEFAULT_ORG_ID) or {"id": DEFAULT_ORG_ID, "name": "Default"})
        auto_selected["source"] = "reserved_auto_select"
        switchable_orgs = _switchable_orgs(accessible_orgs, auto_selected)
        return {
            "accessible_orgs": accessible_orgs,
            "candidate_orgs": accessible_orgs,
            "effective_org": auto_selected,
            "multiple_accessible_orgs": len(accessible_orgs) > 1,
            "selection_required": False,
            "reserved_org_auto_select_eligible": True,
            "selected_org_accessible": True,
            "switchable_orgs": switchable_orgs,
            "switchable_org_count": len(switchable_orgs),
            "org_context_hint": _org_context_hint(auto_selected, switchable_orgs),
        }

    return {
        "accessible_orgs": accessible_orgs,
        "candidate_orgs": accessible_orgs,
        "effective_org": None,
        "multiple_accessible_orgs": len(accessible_orgs) > 1,
        "selection_required": True,
        "reserved_org_auto_select_eligible": reserved_auto_select_eligible,
        "selected_org_accessible": False,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": None,
    }


def ensure_selected_org_context() -> dict[str, Any]:
    context = resolve_effective_org_context()
    if context["selection_required"]:
        raise CLIError(
            "需要先选择组织后才能继续查询。",
            payload=build_org_selection_required_payload(context),
        )
    return context


def org_id_from_context(context: dict[str, Any] | None, *, default: str = "") -> str:
    value = str(((context or {}).get("effective_org") or {}).get("id") or "").strip()
    return value or default


# ---------------------------------------------------------------------------
# Section: Platform resolve
# ---------------------------------------------------------------------------
def resolve_platform_reference(value: str, *, discovery: JumpServerDiscovery | None = None) -> dict[str, Any]:
    active_discovery = discovery or create_discovery()
    wanted = str(value or "").strip().lower()
    exact = []
    category_matches = []
    for item in active_discovery.list_platforms():
        payload = item.to_dict()
        names = {str(payload.get("name", "")).lower(), str(payload.get("slug", "")).lower()}
        if wanted in names:
            exact.append(payload)
            continue
        if wanted and wanted == str(payload.get("category", "")).lower():
            category_matches.append(payload)
    if len(exact) == 1:
        return {"status": "resolved", "resolved": exact[0], "candidates": exact}
    if len(exact) > 1:
        return {"status": "ambiguous", "resolved": None, "candidates": exact}
    return {"status": "candidate_only", "resolved": None, "candidates": category_matches}


# ---------------------------------------------------------------------------
# Section: Output serialization
# ---------------------------------------------------------------------------
def serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, PlatformSpec):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    return value


def print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def run_and_print(func, args: argparse.Namespace | None = None) -> int:
    try:
        result = func(args) if args is not None else func()
        print_json(redact_sensitive({"ok": True, "result": serialize(result)}))
        return 0
    except CLIError as exc:
        payload = {"ok": False, "error": redact_sensitive(str(exc))}
        if exc.payload:
            payload["details"] = serialize(exc.payload)
        print_json(redact_sensitive(payload))
        return 1
    except JumpServerAPIError as exc:
        payload = {
            "ok": False,
            "error": redact_sensitive(exc.message),
            "details": serialize(
                {
                    "status_code": exc.status_code,
                    "method": exc.method,
                    "path": exc.path,
                    "details": exc.details,
                }
            ),
        }
        print_json(redact_sensitive(payload))
        return 1
    except Exception as exc:  # noqa: BLE001
        print_json(redact_sensitive({"ok": False, "error": str(exc)}))
        return 1
