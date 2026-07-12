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
import tempfile
from contextlib import contextmanager
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
ENV_FORMAT_PREFIX = "# jumpserver-skills-env-format:"
ENV_FORMAT_VERSION = 1
ENV_FORMAT_HEADER = "%s %s" % (ENV_FORMAT_PREFIX, ENV_FORMAT_VERSION)
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RECOVERABLE_ENV_REASON_CODES = frozenset(
    {"invalid_env_encoding", "invalid_env_format", "invalid_env_value"}
)
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


def parse_strict_bool(value: Any, *, field_name: str = "value", default: bool | None = None) -> bool:
    if value is None or value == "":
        if default is not None:
            return bool(default)
        normalized = ""
    elif isinstance(value, bool):
        return value
    else:
        normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    raise CLIError(
        "Invalid boolean value for %s." % field_name,
        payload=build_cli_guidance_payload(
            "invalid_boolean_value",
            user_message="`%s` 只接受 true/false、1/0、yes/no、on/off 或 y/n。" % field_name,
            action_hint="请修正布尔值后重试；未知值不会自动按 false 处理。",
            field=field_name,
            invalid_value=value,
        ),
    )


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


def _invalid_env_format_error(
    env_path: Path,
    *,
    line_number: int | None = None,
    field: str | None = None,
) -> CLIError:
    return CLIError(
        "Invalid .env format.",
        payload=build_cli_guidance_payload(
            "invalid_env_format",
            user_message="`.env` 格式无效，无法安全读取运行时配置。",
            action_hint="请备份并修正对应行；若无法修复，先移走损坏文件，再用 `config-write --confirm` 重新生成。",
            env_file_path=str(env_path),
            line_number=line_number,
            field=field,
        ),
    )


def _validate_env_value(value: Any, *, field: str, line_number: int | None = None) -> str:
    text = str(value)
    invalid_controls = [
        name
        for name, marker in (("CR", "\r"), ("LF", "\n"), ("NUL", "\x00"))
        if marker in text
    ]
    unicode_valid = True
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        unicode_valid = False
    if not unicode_valid:
        raise CLIError(
            "Invalid Unicode value in .env field %s." % field,
            payload=build_cli_guidance_payload(
                "invalid_env_value",
                user_message="`.env` 字段 `%s` 包含无法编码为 UTF-8 的字符。" % field,
                action_hint="请重新输入该字段；错误信息不会回显原值。",
                field=field,
                line_number=line_number,
                invalid_character_types=["invalid_unicode"],
            ),
        )
    if invalid_controls:
        raise CLIError(
            "Invalid control character in .env field %s." % field,
            payload=build_cli_guidance_payload(
                "invalid_env_value",
                user_message="`.env` 字段 `%s` 只能保存单行值。" % field,
                action_hint="请移除 CR、LF 或 NUL 控制字符后重试。",
                field=field,
                line_number=line_number,
                invalid_character_types=invalid_controls,
            ),
        )
    return text


def _decode_env_value(
    value: str,
    *,
    format_version: int,
    env_path: Path,
    line_number: int,
    field: str,
) -> str:
    raw_value = value.strip()
    if format_version == 0:
        if raw_value[:1] in {"'", '"'} and (len(raw_value) < 2 or raw_value[-1] != raw_value[0]):
            raise _invalid_env_format_error(env_path, line_number=line_number, field=field)
        decoded = _strip_wrapping_quotes(raw_value)
    else:
        decoded_valid = True
        try:
            decoded = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            decoded_valid = False
            decoded = None
        if not decoded_valid or not isinstance(decoded, str):
            raise _invalid_env_format_error(env_path, line_number=line_number, field=field)
    return _validate_env_value(decoded, field=field, line_number=line_number)


def _serialize_env_config(values: dict[str, str], env_path: Path) -> bytes:
    lines = [ENV_FORMAT_HEADER]
    for key in sorted(values):
        if not ENV_KEY_RE.fullmatch(key):
            raise _invalid_env_format_error(env_path)
        value = _validate_env_value(values[key], field=key)
        lines.append("%s=%s" % (key, json.dumps(value, ensure_ascii=False)))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _prepare_env_temp(env_path: Path, payload: bytes) -> Path:
    temp_path: Path | None = None
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=".%s." % env_path.name,
            suffix=".tmp",
            dir=str(env_path.parent),
        )
        temp_path = Path(temp_name)
        with os.fdopen(file_descriptor, "wb") as handle:
            fchmod = getattr(os, "fchmod", None)
            if callable(fchmod):
                fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temp_path
    except OSError:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise CLIError(
            "Failed to write local .env configuration.",
            payload=build_cli_guidance_payload(
                "env_write_failed",
                user_message="本地 `.env` 写入失败，原文件已保留。",
                action_hint="请检查目录权限和可用空间后重试。",
                env_file_path=str(env_path),
            ),
        )


def _atomic_write_env(env_path: Path, payload: bytes) -> None:
    temp_path = _prepare_env_temp(env_path, payload)
    try:
        os.replace(temp_path, env_path)
    except OSError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise CLIError(
            "Failed to write local .env configuration.",
            payload=build_cli_guidance_payload(
                "env_write_failed",
                user_message="本地 `.env` 写入失败，原文件已保留。",
                action_hint="请检查目录权限和可用空间后重试。",
                env_file_path=str(env_path),
            ),
        )


def _env_stat_signature(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def _env_recovery_not_required_error(env_path: Path) -> CLIError:
    return CLIError(
        "Invalid .env recovery is not required.",
        payload=build_cli_guidance_payload(
            "env_recovery_not_required",
            user_message="`--recover-invalid-env` 只用于恢复现存且无法解析的 `.env`。",
            action_hint="文件缺失时去掉恢复参数直接创建；文件正常时使用普通 `config-write --confirm`。",
            env_file_path=str(env_path),
        ),
    )


def _read_env_recovery_snapshot(env_path: Path) -> tuple[bytes, tuple[int, int, int, int]]:
    file_descriptor: int | None = None
    try:
        before = os.lstat(env_path)
    except FileNotFoundError:
        raise _env_recovery_not_required_error(env_path)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CLIError(
            "Unsafe .env recovery path.",
            payload=build_cli_guidance_payload(
                "unsafe_env_recovery_path",
                user_message="损坏配置恢复只接受普通 `.env` 文件，不处理符号链接或其他文件类型。",
                action_hint="请先确认实际文件路径并手工处理链接或特殊文件。",
                env_file_path=str(env_path),
            ),
        )
    try:
        flags = os.O_RDONLY
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        file_descriptor = os.open(env_path, flags)
        opened = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened.st_mode) or _env_stat_signature(opened) != _env_stat_signature(before):
            raise OSError(".env changed before recovery snapshot")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            raw = handle.read()
            after = os.fstat(handle.fileno())
    except OSError:
        if file_descriptor is not None:
            os.close(file_descriptor)
        raise CLIError(
            "Failed to read invalid .env for recovery.",
            payload=build_cli_guidance_payload(
                "env_recovery_read_failed",
                user_message="无法读取待恢复 `.env` 的原始字节。",
                action_hint="请检查文件权限和路径后重试。",
                env_file_path=str(env_path),
            ),
        )
    signature = _env_stat_signature(before)
    if signature != _env_stat_signature(after) or len(raw) != after.st_size:
        raise CLIError(
            "The invalid .env changed during recovery.",
            payload=build_cli_guidance_payload(
                "env_recovery_conflict",
                user_message="待恢复 `.env` 在读取期间发生变化，已停止替换。",
                action_hint="确认没有其他进程修改该文件后重试。",
                env_file_path=str(env_path),
            ),
        )
    return raw, signature


@contextmanager
def _local_env_write_lock(env_path: Path):
    lock_path = env_path.with_name("%s.lock" % env_path.name)
    file_descriptor: int | None = None
    locked = False
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing_lock = os.lstat(lock_path)
        except FileNotFoundError:
            existing_lock = None
        if existing_lock is not None and (
            stat.S_ISLNK(existing_lock.st_mode) or not stat.S_ISREG(existing_lock.st_mode)
        ):
            raise OSError("unsafe .env lock path")
        flags = os.O_RDWR | os.O_CREAT
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        file_descriptor = os.open(lock_path, flags, stat.S_IRUSR | stat.S_IWUSR)
        opened_lock = os.fstat(file_descriptor)
        current_lock = os.lstat(lock_path)
        if (
            not stat.S_ISREG(opened_lock.st_mode)
            or stat.S_ISLNK(current_lock.st_mode)
            or not os.path.samestat(opened_lock, current_lock)
        ):
            raise OSError("unsafe .env lock file")
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(file_descriptor, stat.S_IRUSR | stat.S_IWUSR)
        if os.name == "nt":
            import msvcrt

            if os.fstat(file_descriptor).st_size == 0:
                os.write(file_descriptor, b"\0")
                os.fsync(file_descriptor)
            os.lseek(file_descriptor, 0, os.SEEK_SET)
            msvcrt.locking(file_descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(file_descriptor, fcntl.LOCK_EX)
        current_lock = os.lstat(lock_path)
        if stat.S_ISLNK(current_lock.st_mode) or not os.path.samestat(os.fstat(file_descriptor), current_lock):
            raise OSError(".env lock path changed during acquisition")
        locked = True
    except OSError:
        if file_descriptor is not None:
            os.close(file_descriptor)
        raise CLIError(
            "Failed to lock local .env configuration.",
            payload=build_cli_guidance_payload(
                "env_lock_failed",
                user_message="无法获取本地 `.env` 写锁，配置未修改。",
                action_hint="请确认目录可写且没有异常锁占用后重试。",
                env_file_path=str(env_path),
                lock_file_path=str(lock_path),
            ),
        )

    try:
        yield lock_path
    finally:
        if file_descriptor is not None:
            try:
                try:
                    if locked and os.name == "nt":
                        import msvcrt

                        os.lseek(file_descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
                    elif locked:
                        import fcntl

                        fcntl.flock(file_descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
            finally:
                try:
                    os.close(file_descriptor)
                except OSError:
                    pass


def _ensure_env_recovery_snapshot_unchanged(
    env_path: Path,
    raw: bytes,
    signature: tuple[int, int, int, int],
) -> None:
    try:
        current_raw, current_signature = _read_env_recovery_snapshot(env_path)
        unchanged = current_signature == signature and current_raw == raw
    except CLIError:
        unchanged = False
    if not unchanged:
        raise CLIError(
            "The invalid .env changed during recovery.",
            payload=build_cli_guidance_payload(
                "env_recovery_conflict",
                user_message="待恢复 `.env` 在备份或替换前发生变化，原文件未被覆盖。",
                action_hint="确认没有其他进程修改该文件后重试。",
                env_file_path=str(env_path),
            ),
        )


def _backup_invalid_env(env_path: Path, raw: bytes) -> Path:
    backup_path: Path | None = None
    try:
        file_descriptor, backup_name = tempfile.mkstemp(
            prefix="%s.recovery-" % env_path.name,
            suffix=".bak",
            dir=str(env_path.parent),
        )
        backup_path = Path(backup_name)
        with os.fdopen(file_descriptor, "wb") as handle:
            fchmod = getattr(os, "fchmod", None)
            if callable(fchmod):
                fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return backup_path
    except OSError:
        if backup_path is not None:
            try:
                backup_path.unlink()
            except OSError:
                pass
        raise CLIError(
            "Failed to back up invalid .env.",
            payload=build_cli_guidance_payload(
                "env_backup_failed",
                user_message="损坏 `.env` 备份失败，原文件未被替换。",
                action_hint="请检查目录权限和可用空间后重试。",
                env_file_path=str(env_path),
            ),
        )


def _verify_recovery_hardlink_support(env_path: Path) -> None:
    source_path: Path | None = None
    destination_path: Path | None = None
    try:
        source_fd, source_name = tempfile.mkstemp(
            prefix="%s.recovery-preflight-" % env_path.name,
            suffix=".tmp",
            dir=str(env_path.parent),
        )
        source_path = Path(source_name)
        os.close(source_fd)
        destination_fd, destination_name = tempfile.mkstemp(
            prefix="%s.recovery-preflight-" % env_path.name,
            suffix=".link",
            dir=str(env_path.parent),
        )
        destination_path = Path(destination_name)
        os.close(destination_fd)
        destination_path.unlink()
        os.link(source_path, destination_path)
    except OSError:
        raise CLIError(
            "Filesystem does not support safe damaged .env recovery.",
            payload=build_cli_guidance_payload(
                "env_recovery_hardlink_unsupported",
                user_message="当前目录不支持恢复所需的同目录硬链接，原 `.env` 未移动。",
                action_hint="请先把 skill 目录移到支持硬链接的本地文件系统，或手工备份并重建 `.env`。",
                env_file_path=str(env_path),
            ),
        )
    finally:
        for candidate in (destination_path, source_path):
            if candidate is not None:
                try:
                    candidate.unlink()
                except OSError:
                    pass


def _reserve_recovery_stage_path(env_path: Path) -> Path:
    stage_path: Path | None = None
    try:
        file_descriptor, stage_name = tempfile.mkstemp(
            prefix="%s.recovery-" % env_path.name,
            suffix=".stage",
            dir=str(env_path.parent),
        )
        stage_path = Path(stage_name)
        os.close(file_descriptor)
        return stage_path
    except OSError:
        if stage_path is not None:
            try:
                stage_path.unlink()
            except OSError:
                pass
        raise CLIError(
            "Failed to prepare damaged .env recovery.",
            payload=build_cli_guidance_payload(
                "env_write_failed",
                user_message="无法准备损坏 `.env` 的安全替换步骤，原文件未修改。",
                action_hint="请检查目录权限和文件系统能力后重试。",
                env_file_path=str(env_path),
            ),
        )


def _restore_recovery_stage(stage_path: Path, env_path: Path) -> bool:
    try:
        os.link(stage_path, env_path)
    except OSError:
        return False
    try:
        stage_path.unlink()
    except OSError:
        pass
    return True


def _recovery_commit_error(
    reason_code: str,
    env_path: Path,
    backup_path: Path,
    stage_path: Path,
    *,
    restored: bool,
) -> CLIError:
    return CLIError(
        "Damaged .env recovery could not be committed safely.",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=(
                "待恢复 `.env` 在提交期间发生变化，未覆盖并发写入。"
                if reason_code == "env_recovery_conflict"
                else "新 `.env` 安装失败，旧文件已尽可能恢复。"
            ),
            action_hint="确认没有其他进程修改 `.env`，检查文件系统是否支持同目录硬链接后重试。",
            env_file_path=str(env_path),
            backup_file_path=str(backup_path),
            staged_file_path=str(stage_path) if stage_path.exists() else None,
            original_restored=restored,
        ),
    )


def _commit_recovered_env(
    env_path: Path,
    payload: bytes,
    recovery_raw: bytes,
    recovery_signature: tuple[int, int, int, int],
    backup_path: Path,
) -> Path | None:
    stage_path = _reserve_recovery_stage_path(env_path)
    moved = False
    try:
        os.replace(env_path, stage_path)
        moved = True
        stage_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        if moved:
            restored = _restore_recovery_stage(stage_path, env_path)
        else:
            restored = env_path.exists()
            try:
                stage_path.unlink()
            except OSError:
                pass
        raise _recovery_commit_error(
            "env_write_failed",
            env_path,
            backup_path,
            stage_path,
            restored=restored,
        )

    try:
        staged_raw, staged_signature = _read_env_recovery_snapshot(stage_path)
    except CLIError:
        restored = _restore_recovery_stage(stage_path, env_path)
        raise _recovery_commit_error(
            "env_recovery_conflict",
            env_path,
            backup_path,
            stage_path,
            restored=restored,
        )
    if staged_signature != recovery_signature or staged_raw != recovery_raw:
        restored = _restore_recovery_stage(stage_path, env_path)
        raise _recovery_commit_error(
            "env_recovery_conflict",
            env_path,
            backup_path,
            stage_path,
            restored=restored,
        )

    try:
        temp_path = _prepare_env_temp(env_path, payload)
    except CLIError as exc:
        restored = _restore_recovery_stage(stage_path, env_path)
        exc.payload["backup_file_path"] = str(backup_path)
        exc.payload["staged_file_path"] = str(stage_path) if stage_path.exists() else None
        exc.payload["original_restored"] = restored
        raise

    try:
        os.link(temp_path, env_path)
    except FileExistsError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        restored = _restore_recovery_stage(stage_path, env_path)
        raise _recovery_commit_error(
            "env_recovery_conflict",
            env_path,
            backup_path,
            stage_path,
            restored=restored,
        )
    except OSError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        restored = _restore_recovery_stage(stage_path, env_path)
        raise _recovery_commit_error(
            "env_write_failed",
            env_path,
            backup_path,
            stage_path,
            restored=restored,
        )

    try:
        temp_path.unlink()
    except OSError:
        pass
    try:
        stage_path.unlink()
    except OSError:
        return stage_path
    return None


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
def _parse_local_env_bytes(raw: bytes, env_path: Path) -> dict[str, str]:
    decode_valid = True
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        decode_valid = False
        text = ""
    if not decode_valid:
        raise CLIError(
            "Local .env must use UTF-8 encoding.",
            payload=build_cli_guidance_payload(
                "invalid_env_encoding",
                user_message="本地 `.env` 不是有效 UTF-8 文件。",
                action_hint="请把文件转换为 UTF-8（允许 BOM）后重试；不要使用忽略错误或自动猜测编码。",
                env_file_path=str(env_path),
            ),
        )

    raw_lines = text.split("\n")
    format_version = 0
    header_lines = [
        index
        for index, raw_line in enumerate(raw_lines)
        if raw_line.strip().startswith(ENV_FORMAT_PREFIX)
    ]
    if header_lines:
        if header_lines != [0]:
            raise _invalid_env_format_error(env_path, line_number=header_lines[0] + 1)
        version = raw_lines[0].strip()[len(ENV_FORMAT_PREFIX) :].strip()
        if version != str(ENV_FORMAT_VERSION):
            raise _invalid_env_format_error(env_path, line_number=1)
        format_version = ENV_FORMAT_VERSION

    payload: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            if format_version:
                raise _invalid_env_format_error(env_path, line_number=line_number)
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or (format_version and not ENV_KEY_RE.fullmatch(key)):
            if format_version:
                raise _invalid_env_format_error(env_path, line_number=line_number)
            continue
        payload[key] = _decode_env_value(
            value,
            format_version=format_version,
            env_path=env_path,
            line_number=line_number,
            field=key,
        )
    return payload


def read_local_env(path: Path | None = None) -> dict[str, str]:
    env_path = Path(path or LOCAL_ENV_FILE)
    if not env_path.exists():
        return {}
    return _parse_local_env_bytes(env_path.read_bytes(), env_path)


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


def _build_config_status(
    values: dict[str, str],
    env_path: Path,
    *,
    exists: bool,
) -> dict[str, Any]:
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

    verify_tls_value = values.get("JMS_VERIFY_TLS")
    if verify_tls_value not in {None, ""}:
        try:
            parse_strict_bool(verify_tls_value, field_name="JMS_VERIFY_TLS")
        except CLIError:
            invalid_fields.append("JMS_VERIFY_TLS")

    return {
        "env_file_path": str(env_path),
        "exists": exists,
        "complete": not missing and not invalid_fields,
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "auth_mode": auth_mode,
        "current_nonsecret": current_nonsecret_view(values),
    }


def _write_local_env_config_locked(
    payload: dict[str, Any],
    env_path: Path,
    *,
    recover_invalid: bool = False,
) -> dict[str, Any]:
    recovery_reason_code: str | None = None
    recovery_raw: bytes | None = None
    recovery_signature: tuple[int, int, int, int] | None = None
    backup_path: Path | None = None
    recovery_stage_path: Path | None = None

    if recover_invalid:
        recovery_raw, recovery_signature = _read_env_recovery_snapshot(env_path)
        try:
            _parse_local_env_bytes(recovery_raw, env_path)
        except CLIError as exc:
            reason_code = str(exc.payload.get("reason_code") or "")
            if reason_code not in RECOVERABLE_ENV_REASON_CODES:
                raise
            recovery_reason_code = reason_code
        else:
            raise _env_recovery_not_required_error(env_path)
        _ensure_env_recovery_snapshot_unchanged(env_path, recovery_raw, recovery_signature)
        current: dict[str, str] = {}
    else:
        current = read_local_env(env_path)

    final: dict[str, str] = {}
    final.update({key: value for key, value in current.items() if key not in WRITEABLE_ENV_KEYS})

    for key in WRITEABLE_ENV_KEYS:
        value = payload.get(key)
        if value is None:
            if key in current:
                final[key] = current[key]
            continue
        if key == "JMS_VERIFY_TLS":
            final[key] = "true" if parse_strict_bool(value, field_name=key) else "false"
        else:
            final[key] = str(value)

    encoded = _serialize_env_config(final, env_path)
    if recover_invalid:
        unknown_fields = sorted(str(key) for key in payload if key not in WRITEABLE_ENV_KEYS)
        replacement_status = _build_config_status(final, env_path, exists=True)
        if unknown_fields or not replacement_status["complete"]:
            raise CLIError(
                "Invalid replacement payload for damaged .env.",
                payload=build_cli_guidance_payload(
                    "invalid_env_recovery_payload",
                    user_message="恢复损坏 `.env` 必须显式提供一份完整且合法的新配置。",
                    action_hint="请提供 JMS_API_URL 和至少一套完整认证；修正未知、缺失或非法字段后重试。",
                    env_file_path=str(env_path),
                    unknown_fields=unknown_fields,
                    missing_fields=replacement_status["missing_fields"],
                    invalid_fields=replacement_status["invalid_fields"],
                ),
            )
        _verify_recovery_hardlink_support(env_path)
        backup_path = _backup_invalid_env(env_path, recovery_raw)
        try:
            recovery_stage_path = _commit_recovered_env(
                env_path,
                encoded,
                recovery_raw,
                recovery_signature,
                backup_path,
            )
        except CLIError as exc:
            exc.payload["backup_file_path"] = str(backup_path)
            raise
    else:
        _atomic_write_env(env_path, encoded)

    if recover_invalid:
        for key in WRITEABLE_ENV_KEYS:
            os.environ.pop(key, None)
    for key in WRITEABLE_ENV_KEYS:
        if key in final:
            os.environ[key] = str(final[key])

    result = {
        "env_file_path": str(env_path),
        "current_nonsecret": current_nonsecret_view(current_runtime_values(env_path)),
    }
    if recover_invalid:
        result.update(
            {
                "recovered_invalid_env": True,
                "recovery_reason_code": recovery_reason_code,
                "backup_file_path": str(backup_path),
                "staged_file_path": str(recovery_stage_path) if recovery_stage_path is not None else None,
            }
        )
    return result


def write_local_env_config(
    payload: dict[str, Any],
    path: Path | None = None,
    *,
    recover_invalid: bool = False,
) -> dict[str, Any]:
    env_path = Path(path or LOCAL_ENV_FILE)
    if recover_invalid:
        recovery_raw, _ = _read_env_recovery_snapshot(env_path)
        try:
            _parse_local_env_bytes(recovery_raw, env_path)
        except CLIError as exc:
            if str(exc.payload.get("reason_code") or "") not in RECOVERABLE_ENV_REASON_CODES:
                raise
        else:
            raise _env_recovery_not_required_error(env_path)
    with _local_env_write_lock(env_path):
        return _write_local_env_config_locked(
            payload,
            env_path,
            recover_invalid=recover_invalid,
        )


def current_nonsecret_view(values: dict[str, str] | None = None) -> dict[str, str]:
    payload = dict(values or current_runtime_values())
    return {key: payload[key] for key in NONSECRET_ENV_KEYS if key in payload and payload[key] != ""}


def get_config_status(path: Path | None = None) -> dict[str, Any]:
    env_path = Path(path or LOCAL_ENV_FILE)
    return _build_config_status(
        current_runtime_values(path),
        env_path,
        exists=env_path.exists(),
    )


def parse_json_arg(
    value: str | None,
    *,
    default: dict[str, Any] | None = None,
    source: str = "--filters",
    usage_examples: list[str] | None = None,
    include_raw_value: bool = True,
) -> dict[str, Any]:
    if value in {None, ""}:
        return dict(default or {})
    parser_error = None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        parser_error = exc.msg
        payload = None
    if parser_error is not None:
        details = {
            "input_name": source,
            "parser_error": parser_error,
        }
        if include_raw_value:
            details["raw_value"] = value
        raise CLIError(
            "无法解析 %s 参数。" % source,
            payload=build_cli_guidance_payload(
                INVALID_JSON_PAYLOAD_REASON_CODE,
                user_message="%s 需要传入 JSON 对象字符串，例如 '{\"name\": \"Default\"}'。" % source,
                action_hint="优先改用显式参数或重复的 `--filter key=value`；如果继续使用 JSON，请检查引号、逗号和花括号。",
                suggested_commands=usage_examples,
                **details,
            ),
        )
    if not isinstance(payload, dict):
        details = {"input_name": source}
        if include_raw_value:
            details["raw_value"] = value
        raise CLIError(
            "%s 必须是 JSON 对象。" % source,
            payload=build_cli_guidance_payload(
                INVALID_JSON_PAYLOAD_REASON_CODE,
                user_message="%s 需要传入 JSON 对象，而不是数组或普通字符串。" % source,
                action_hint="请改成 `{\"key\": \"value\"}` 这种对象形式，或直接使用显式参数 / `--filter key=value`。",
                suggested_commands=usage_examples,
                **details,
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
        verify_tls=parse_strict_bool(values.get("JMS_VERIFY_TLS"), field_name="JMS_VERIFY_TLS", default=False),
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
