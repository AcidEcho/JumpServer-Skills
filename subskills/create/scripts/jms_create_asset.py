#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_discovery import CORE_ENDPOINTS  # noqa: E402
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_env_org_context,
    create_client,
    create_discovery,
    has_cli_value,
    mask_secret,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    parse_bool,
    parse_json_arg,
    preview_create_org_context,
    resolve_command_org_context,
    run_and_print,
)
from jumpserver_common.jms_types import PlatformSpec  # noqa: E402


HOST_ASSET_PATH = "/api/v1/assets/hosts/"
DEVICE_ASSET_PATH = "/api/v1/assets/devices/"
DATABASE_ASSET_PATH = "/api/v1/assets/database/"
WEB_ASSET_PATH = "/api/v1/assets/webs/"
LABEL_PATH = "/api/v1/labels/labels/"
ZONE_PATH = "/api/v1/assets/zones/"

ASSET_TYPES = {
    "host": {
        "command": "create-host-asset",
        "resource_name": "主机资产",
        "api_path": HOST_ASSET_PATH,
        "platform_category": "host",
        "extra_fields": frozenset(),
    },
    "device": {
        "command": "create-device-asset",
        "resource_name": "网络设备资产",
        "api_path": DEVICE_ASSET_PATH,
        "platform_category": "device",
        "extra_fields": frozenset(),
    },
    "database": {
        "command": "create-database-asset",
        "resource_name": "数据库资产",
        "api_path": DATABASE_ASSET_PATH,
        "platform_category": "database",
        "extra_fields": frozenset({"use_ssl", "allow_invalid_cert", "db_name"}),
    },
    "web": {
        "command": "create-web-asset",
        "resource_name": "Web 资产",
        "api_path": WEB_ASSET_PATH,
        "platform_category": "web",
        "extra_fields": frozenset(
            {
                "autofill",
                "username_selector",
                "password_selector",
                "submit_selector",
                "script",
                "directory_services",
            }
        ),
    },
}
COMMON_ASSET_FIELDS = frozenset(
    {
        "platform",
        "nodes",
        "protocols",
        "labels",
        "is_active",
        "name",
        "address",
        "accounts",
        "zone",
        "comment",
    }
)
ACCOUNT_SECRET_TYPES = frozenset({"password", "ssh_key"})
ACCOUNT_ON_INVALID = frozenset({"skip", "update", "error"})
WEB_AUTOFILL_VALUES = frozenset({"no", "basic", "script"})
SENSITIVE_FIELDS = frozenset({"secret", "passphrase"})
CREATE_ASSET_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_asset.py create-host-asset "
        "--org-name Default --name Linux --address 1.1.1.1 --platform Linux --node /Default --zone Default --confirm"
    ),
    (
        "python3 subskills/create/scripts/jms_create_asset.py create-database-asset "
        "--org-name Default --payload '<json>' --confirm"
    ),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _allowed_fields(asset_type: str) -> frozenset[str]:
    return COMMON_ASSET_FIELDS | ASSET_TYPES[asset_type]["extra_fields"]


def _api_path(asset_type: str) -> str:
    return str(ASSET_TYPES[asset_type]["api_path"])


def _resource_name(asset_type: str) -> str:
    return str(ASSET_TYPES[asset_type]["resource_name"])


def _normalize_platform_pk(value: Any) -> Any:
    if isinstance(value, dict):
        value = value.get("pk") or value.get("id") or value.get("name") or value.get("slug") or value.get("value")
    text = _text(value)
    if text.isdigit():
        return int(text)
    return value


def _normalize_platform(value: Any) -> dict[str, Any] | None:
    pk = _normalize_platform_pk(value)
    if has_cli_value(pk):
        return {"pk": pk}
    return None


def _normalize_pk_list(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            pk = (
                item.get("pk")
                or item.get("id")
                or item.get("value")
                or item.get("name")
                or item.get("full_value")
            )
        else:
            pk = item
        if has_cli_value(pk):
            normalized.append({"pk": pk})
    return normalized


def _normalize_zone(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("id") or value.get("pk") or value.get("name") or value.get("value")
    return value


def _parse_json_object(value: str, *, source: str) -> dict[str, Any]:
    return parse_json_arg(
        value,
        default={},
        source=source,
        usage_examples=CREATE_ASSET_EXAMPLES,
    )


def _parse_protocol(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        name = _text(value.get("name"))
        port = value.get("port")
    else:
        text = _text(value)
        if ":" not in text:
            raise CLIError(
                "无法解析协议参数。",
                payload=build_cli_guidance_payload(
                    "invalid_asset_protocol",
                    user_message="`--protocol` 需要使用 `name:port` 形式，例如 `ssh:22`。",
                    action_hint="请改成 `--protocol ssh:22` 后重试。",
                    suggested_commands=CREATE_ASSET_EXAMPLES,
                    protocol=value,
                ),
            )
        name, port = text.split(":", 1)
        name = _text(name)
    if not name:
        raise CLIError(
            "无法解析协议参数。",
            payload=build_cli_guidance_payload(
                "invalid_asset_protocol",
                user_message="协议名称不能为空。",
                action_hint="请使用 `name:port`，例如 `ssh:22`。",
                suggested_commands=CREATE_ASSET_EXAMPLES,
                protocol=value,
            ),
        )
    if isinstance(port, str):
        port_text = _text(port)
        if not port_text.isdigit():
            raise CLIError(
                "无法解析协议参数。",
                payload=build_cli_guidance_payload(
                    "invalid_asset_protocol",
                    user_message="协议端口必须是数字。",
                    action_hint="请使用 `name:port`，例如 `ssh:22`。",
                    suggested_commands=CREATE_ASSET_EXAMPLES,
                    protocol=value,
                ),
            )
        port = int(port_text)
    if not isinstance(port, int) or port <= 0:
        raise CLIError(
            "无法解析协议参数。",
            payload=build_cli_guidance_payload(
                "invalid_asset_protocol",
                user_message="协议端口必须是大于 0 的数字。",
                action_hint="请使用 `name:port`，例如 `ssh:22`。",
                suggested_commands=CREATE_ASSET_EXAMPLES,
                protocol=value,
            ),
        )
    return {"name": name, "port": port}


def _normalize_protocols(value: Any) -> list[dict[str, Any]]:
    return [_parse_protocol(item) for item in _as_list(value)]


def _merge_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=CREATE_ASSET_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_ASSET_EXAMPLES)


def _clean_payload(payload: dict[str, Any], *, asset_type: str) -> dict[str, Any]:
    allowed_fields = _allowed_fields(asset_type)
    return {
        key: value
        for key, value in payload.items()
        if key in allowed_fields
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _reject_unknown_fields(payload: dict[str, Any], *, asset_type: str) -> None:
    allowed_fields = _allowed_fields(asset_type)
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_create_asset_payload_fields",
                user_message="%s payload 只允许字段：%s。" % (_resource_name(asset_type), ", ".join(sorted(allowed_fields))),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_ASSET_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(allowed_fields),
            ),
        )


def _build_asset_payload(args: argparse.Namespace, *, asset_type: str) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.address):
        payload["address"] = args.address
    if has_cli_value(getattr(args, "platform", None)):
        payload["platform"] = _normalize_platform(args.platform)
    if has_cli_value(getattr(args, "platform_pk", None)):
        payload["platform"] = _normalize_platform(args.platform_pk)
    if getattr(args, "node", None):
        payload["nodes"] = _normalize_pk_list(args.node)
    if getattr(args, "label", None):
        payload["labels"] = _normalize_pk_list(args.label)
    if has_cli_value(getattr(args, "zone", None)):
        payload["zone"] = _normalize_zone(args.zone)
    if getattr(args, "protocol", None):
        payload["protocols"] = [_parse_protocol(item) for item in args.protocol]
    if args.is_active is not None:
        payload["is_active"] = bool(args.is_active)
    if has_cli_value(args.comment):
        payload["comment"] = args.comment

    accounts = list(_as_list(payload.get("accounts"))) if "accounts" in payload else []
    for template in getattr(args, "account_template", None) or []:
        accounts.append({"template": template})
    for raw_account in getattr(args, "account_json", None) or []:
        accounts.append(_parse_json_object(raw_account, source="--account-json"))
    if accounts:
        payload["accounts"] = accounts

    if asset_type == "database":
        if has_cli_value(getattr(args, "db_name", None)):
            payload["db_name"] = args.db_name
        if args.use_ssl is not None:
            payload["use_ssl"] = bool(args.use_ssl)
        elif "use_ssl" not in payload:
            payload["use_ssl"] = False
        if args.allow_invalid_cert is not None:
            payload["allow_invalid_cert"] = bool(args.allow_invalid_cert)
        elif "allow_invalid_cert" not in payload:
            payload["allow_invalid_cert"] = False

    if asset_type == "web":
        if has_cli_value(getattr(args, "autofill", None)):
            payload["autofill"] = args.autofill
        elif "autofill" not in payload:
            payload["autofill"] = "no"
        if has_cli_value(getattr(args, "username_selector", None)):
            payload["username_selector"] = args.username_selector
        if has_cli_value(getattr(args, "password_selector", None)):
            payload["password_selector"] = args.password_selector
        if has_cli_value(getattr(args, "submit_selector", None)):
            payload["submit_selector"] = args.submit_selector
        scripts = list(_as_list(payload.get("script"))) if "script" in payload else []
        for raw_script in getattr(args, "script_json", None) or []:
            scripts.append(_parse_json_object(raw_script, source="--script-json"))
        if scripts:
            payload["script"] = scripts
        if "directory_services" not in payload:
            payload["directory_services"] = []

    _reject_unknown_fields(payload, asset_type=asset_type)
    if "platform" in payload:
        payload["platform"] = _normalize_platform(payload.get("platform"))
    if "nodes" in payload:
        payload["nodes"] = _normalize_pk_list(payload.get("nodes"))
    if "labels" in payload:
        payload["labels"] = _normalize_pk_list(payload.get("labels"))
    if "zone" in payload:
        payload["zone"] = _normalize_zone(payload.get("zone"))
    if "protocols" in payload:
        payload["protocols"] = _normalize_protocols(payload.get("protocols"))
    if "is_active" in payload:
        payload["is_active"] = parse_bool(payload.get("is_active"))
    if asset_type == "database":
        if "use_ssl" in payload:
            payload["use_ssl"] = parse_bool(payload.get("use_ssl"))
        if "allow_invalid_cert" in payload:
            payload["allow_invalid_cert"] = parse_bool(payload.get("allow_invalid_cert"))
    return _clean_payload(payload, asset_type=asset_type)


def _mask_payload(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if key in SENSITIVE_FIELDS:
                masked[key] = mask_secret(item)
            else:
                masked[key] = _mask_payload(item)
        return masked
    if isinstance(value, list):
        return [_mask_payload(item) for item in value]
    return value


def _raise_validation_error(
    reason_code: str,
    message: str,
    *,
    missing_fields: list[str] | None = None,
    invalid_fields: list[str] | None = None,
    **details: Any,
) -> None:
    raise CLIError(
        "创建资产参数不合法。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=message,
            action_hint="请按 API.md 第 8-11 节修正参数后重试。",
            suggested_commands=CREATE_ASSET_EXAMPLES,
            missing_fields=missing_fields,
            invalid_fields=invalid_fields,
            **details,
        ),
    )


def _validate_protocol_list(protocols: Any, *, require_protocols: bool) -> None:
    if protocols is None and not require_protocols:
        return
    if not isinstance(protocols, list) or not protocols:
        _raise_validation_error(
            "missing_create_asset_protocols",
            "`protocols` 为空；dry-run 可省略，--confirm 时会从平台默认协议补齐。",
            missing_fields=["protocols"],
        )
    invalid_fields = []
    for index, protocol in enumerate(protocols):
        if not isinstance(protocol, dict):
            invalid_fields.append("protocols[%s]" % index)
            continue
        if not _text(protocol.get("name")):
            invalid_fields.append("protocols[%s].name" % index)
        if not isinstance(protocol.get("port"), int) or protocol.get("port") <= 0:
            invalid_fields.append("protocols[%s].port" % index)
    if invalid_fields:
        _raise_validation_error(
            "invalid_create_asset_protocols",
            "`protocols` 中每一项都必须包含 name 和正整数 port。",
            invalid_fields=invalid_fields,
        )


def _validate_accounts(accounts: Any) -> None:
    if accounts is None:
        return
    if not isinstance(accounts, list):
        _raise_validation_error(
            "invalid_create_asset_accounts",
            "`accounts` 必须是数组。",
            invalid_fields=["accounts"],
            accounts=_mask_payload(accounts),
        )
    invalid_fields = []
    normalized_accounts = []
    for index, account in enumerate(accounts):
        prefix = "accounts[%s]" % index
        if not isinstance(account, dict):
            invalid_fields.append(prefix)
            continue
        normalized = dict(account)
        if has_cli_value(account.get("template")):
            normalized_accounts.append(normalized)
            continue
        for field in ("name", "username", "secret_type", "secret"):
            if not has_cli_value(account.get(field)):
                invalid_fields.append("%s.%s" % (prefix, field))
        secret_type = _text(account.get("secret_type"))
        if secret_type and secret_type not in ACCOUNT_SECRET_TYPES:
            invalid_fields.append("%s.secret_type" % prefix)
        on_invalid = _text(account.get("on_invalid"))
        if on_invalid and on_invalid not in ACCOUNT_ON_INVALID:
            invalid_fields.append("%s.on_invalid" % prefix)
        for field, default in (
            ("privileged", False),
            ("secret_reset", True),
            ("push_now", False),
            ("is_active", True),
        ):
            if field in normalized and not isinstance(normalized.get(field), bool):
                invalid_fields.append("%s.%s" % (prefix, field))
            elif field not in normalized:
                normalized[field] = default
        if "on_invalid" not in normalized:
            normalized["on_invalid"] = "error"
        normalized_accounts.append(normalized)
    if invalid_fields:
        _raise_validation_error(
            "invalid_create_asset_accounts",
            "`accounts` 缺少必填字段，或字段类型/取值不合法。",
            invalid_fields=invalid_fields,
            accounts=_mask_payload(accounts),
            allowed_secret_types=sorted(ACCOUNT_SECRET_TYPES),
            allowed_on_invalid=sorted(ACCOUNT_ON_INVALID),
        )
    accounts[:] = normalized_accounts


def _validate_web_payload(payload: dict[str, Any]) -> None:
    autofill = _text(payload.get("autofill") or "no")
    if autofill not in WEB_AUTOFILL_VALUES:
        _raise_validation_error(
            "invalid_create_web_asset_autofill",
            "`autofill` 只允许 no/basic/script。",
            invalid_fields=["autofill"],
            allowed_values=sorted(WEB_AUTOFILL_VALUES),
        )
    script = payload.get("script")
    if autofill == "script" and (not isinstance(script, list) or not script):
        _raise_validation_error(
            "missing_create_web_asset_script",
            "`autofill=script` 时必须配置 `script`。",
            missing_fields=["script"],
        )
    if script is None:
        return
    if not isinstance(script, list):
        _raise_validation_error(
            "invalid_create_web_asset_script",
            "`script` 必须是数组。",
            invalid_fields=["script"],
        )
    invalid_fields = []
    for index, step in enumerate(script):
        prefix = "script[%s]" % index
        if not isinstance(step, dict):
            invalid_fields.append(prefix)
            continue
        for field in ("step", "value", "target", "command"):
            if field not in step:
                invalid_fields.append("%s.%s" % (prefix, field))
    if invalid_fields:
        _raise_validation_error(
            "invalid_create_web_asset_script",
            "`script` 中每一步都必须包含 step/value/target/command。",
            invalid_fields=invalid_fields,
        )


def _validate_asset_payload(payload: dict[str, Any], *, asset_type: str, require_protocols: bool) -> None:
    missing = []
    if not _text(payload.get("name")):
        missing.append("name")
    if not _text(payload.get("address")):
        missing.append("address")
    if not isinstance(payload.get("platform"), dict) or not has_cli_value(payload["platform"].get("pk")):
        missing.append("platform.pk")
    if not isinstance(payload.get("nodes"), list) or not payload.get("nodes"):
        missing.append("nodes")
    if missing:
        _raise_validation_error(
            "missing_create_asset_fields",
            "%s 缺少必填字段：%s。" % (_resource_name(asset_type), ", ".join(missing)),
            missing_fields=missing,
        )
    _validate_protocol_list(payload.get("protocols"), require_protocols=require_protocols)
    _validate_accounts(payload.get("accounts"))
    if asset_type == "database":
        for field in ("use_ssl", "allow_invalid_cert"):
            if field in payload and not isinstance(payload.get(field), bool):
                _raise_validation_error(
                    "invalid_create_database_asset_boolean",
                    "`%s` 必须是布尔值 true/false。" % field,
                    invalid_fields=[field],
                )
    if asset_type == "web":
        if "directory_services" in payload and not isinstance(payload.get("directory_services"), list):
            _raise_validation_error(
                "invalid_create_web_asset_directory_services",
                "`directory_services` 必须是数组。",
                invalid_fields=["directory_services"],
            )
        _validate_web_payload(payload)


def _brief_platform(item: dict[str, Any]) -> dict[str, Any]:
    category = _field_value(item, "category.value") or item.get("category")
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "slug": item.get("slug") or _field_value(item, "type.value") or _field_value(item, "raw.type.value"),
        "category": _text(category) if not isinstance(category, dict) else category.get("value"),
    }


def _brief_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
        "full_value": item.get("full_value"),
    }


def _brief_label(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
    }


def _brief_zone(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "comment": item.get("comment"),
    }


def _brief_account_template(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
        "secret_type": item.get("secret_type"),
        "privileged": item.get("privileged"),
    }


def _brief_asset(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "address": item.get("address"),
        "platform": platform.get("name") if isinstance(platform, dict) else platform,
        "is_active": item.get("is_active"),
    }


def _item_id(item: dict[str, Any]) -> Any:
    return item.get("id") or item.get("pk")


def _field_value(item: dict[str, Any], field: str) -> Any:
    value: Any = item
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _value_matches(candidate: Any, requested: Any) -> bool:
    return _text(candidate).lower() == _text(requested).lower()


def _platform_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        payload = item.to_dict()
        raw = payload.get("raw")
        if isinstance(raw, dict) and raw.get("id") is not None:
            payload["id"] = raw.get("id")
        return payload
    if isinstance(item, dict):
        return item
    return {}


def _find_unique_reference(
    items: list[dict[str, Any]],
    requested: Any,
    *,
    fields: tuple[str, ...],
    reason_code: str,
    not_found_message: str,
    ambiguous_message: str,
    candidate_key: str,
    brief_func,
) -> tuple[dict[str, Any], dict[str, Any]]:
    wanted = _text(requested)
    matches = []
    for item in items:
        if any(_value_matches(_field_value(item, field), wanted) for field in fields):
            matches.append(item)
    if len(matches) == 1:
        item = matches[0]
        return item, brief_func(item)
    if len(matches) > 1:
        raise CLIError(
            "对象匹配到多个结果。",
            payload=build_cli_guidance_payload(
                reason_code,
                user_message=ambiguous_message % wanted,
                action_hint="请从候选对象中选择准确 ID 后重试。",
                suggested_commands=CREATE_ASSET_EXAMPLES,
                requested=wanted,
                **{candidate_key: [brief_func(item) for item in matches[:20]]},
            ),
        )
    raise CLIError(
        "对象不存在。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=not_found_message % wanted,
            action_hint="请从候选对象中选择准确 ID、名称或值后重试。",
            suggested_commands=CREATE_ASSET_EXAMPLES,
            requested=wanted,
            **{candidate_key: [brief_func(item) for item in items[:20]]},
        ),
    )


def _resolve_pk_list(
    values: list[dict[str, Any]],
    *,
    items: list[dict[str, Any]],
    fields: tuple[str, ...],
    reason_code: str,
    not_found_message: str,
    ambiguous_message: str,
    candidate_key: str,
    brief_func,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved = []
    refs = []
    seen = set()
    for raw in values:
        requested = raw.get("pk") if isinstance(raw, dict) else raw
        item, brief = _find_unique_reference(
            items,
            requested,
            fields=fields,
            reason_code=reason_code,
            not_found_message=not_found_message,
            ambiguous_message=ambiguous_message,
            candidate_key=candidate_key,
            brief_func=brief_func,
        )
        item_id = _item_id(item)
        if _text(item_id) in seen:
            continue
        seen.add(_text(item_id))
        resolved.append({"pk": item_id})
        refs.append(brief)
    return resolved, refs


def _platform_category(item: dict[str, Any]) -> str:
    category = _field_value(item, "category.value")
    if category is None:
        category = item.get("category")
    if isinstance(category, dict):
        category = category.get("value") or category.get("name")
    return _text(category).lower()


def _platform_slug(item: dict[str, Any]) -> str:
    return _text(item.get("slug") or _field_value(item, "type.value") or _field_value(item, "raw.type.value")).lower()


def _platform_spec(item: dict[str, Any]) -> PlatformSpec:
    return PlatformSpec(
        platform_id=_item_id(item),
        name=_text(item.get("name")),
        slug=_platform_slug(item),
        category=_platform_category(item),
        protocols=item.get("protocols") or _field_value(item, "raw.protocols") or [],
        automation=item.get("automation") or _field_value(item, "raw.automation") or {},
        raw=item.get("raw") if isinstance(item.get("raw"), dict) else item,
    )


def _raise_platform_category_mismatch(
    platform: dict[str, Any],
    *,
    asset_type: str,
    platform_items: list[dict[str, Any]],
) -> None:
    expected = str(ASSET_TYPES[asset_type]["platform_category"])
    candidates = [item for item in platform_items if _platform_category(item) == expected]
    raise CLIError(
        "平台类型不匹配。",
        payload=build_cli_guidance_payload(
            "asset_platform_category_mismatch",
            user_message="%s 需要 category=%s 的平台，当前平台 category=%s。" % (
                _resource_name(asset_type),
                expected,
                _platform_category(platform) or "unknown",
            ),
            action_hint="请改用对应类型的平台 ID、名称或 slug。",
            suggested_commands=CREATE_ASSET_EXAMPLES,
            requested_platform=_brief_platform(platform),
            candidate_platforms=[_brief_platform(item) for item in candidates[:20]],
        ),
    )


def _resolve_platform(
    platform_ref: dict[str, Any],
    *,
    discovery,
    asset_type: str,
) -> tuple[dict[str, Any], dict[str, Any], PlatformSpec]:
    platform_items = [_platform_to_dict(item) for item in discovery.list_platforms()]
    platform_items = [item for item in platform_items if item]
    platform, brief = _find_unique_reference(
        platform_items,
        platform_ref.get("pk"),
        fields=("id", "pk", "name", "slug", "type.value", "raw.type.value"),
        reason_code="asset_platform_not_found",
        not_found_message="找不到平台：%s。",
        ambiguous_message="平台 `%s` 匹配到多个结果。",
        candidate_key="candidate_platforms",
        brief_func=_brief_platform,
    )
    category = _platform_category(platform)
    expected = str(ASSET_TYPES[asset_type]["platform_category"])
    if category and category != expected:
        _raise_platform_category_mismatch(platform, asset_type=asset_type, platform_items=platform_items)
    spec = _platform_spec(platform)
    return {"pk": _item_id(platform)}, brief, spec


def _normalize_default_protocols(protocols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in protocols:
        try:
            normalized.append(_parse_protocol(item))
        except CLIError:
            continue
    return normalized


def _resolve_account_templates(
    payload: dict[str, Any],
    *,
    discovery,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return accounts or [], []
    template_items = discovery.client.list_paginated(CORE_ENDPOINTS["account_templates"])
    template_items = [item for item in template_items if isinstance(item, dict)] if isinstance(template_items, list) else []
    resolved_accounts = []
    refs = []
    seen_templates = set()
    for account in accounts:
        if not isinstance(account, dict) or not has_cli_value(account.get("template")):
            resolved_accounts.append(account)
            continue
        template, brief = _find_unique_reference(
            template_items,
            account.get("template"),
            fields=("id", "pk", "name"),
            reason_code="asset_account_template_not_found",
            not_found_message="找不到账号模板：%s。",
            ambiguous_message="账号模板 `%s` 匹配到多个结果。",
            candidate_key="candidate_account_templates",
            brief_func=_brief_account_template,
        )
        next_account = dict(account)
        next_account["template"] = _item_id(template)
        resolved_accounts.append(next_account)
        template_id = _text(_item_id(template))
        if template_id not in seen_templates:
            seen_templates.add(template_id)
            refs.append(brief)
    return resolved_accounts, refs


def _resolve_asset_references(
    payload: dict[str, Any],
    *,
    client,
    org_id: str,
    asset_type: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = copy.deepcopy(payload)
    resolved_refs: dict[str, Any] = {}
    resolved_defaults: dict[str, Any] = {}
    platform_spec = None

    platform_ref = resolved_payload.get("platform")
    if isinstance(platform_ref, dict) and has_cli_value(platform_ref.get("pk")):
        platform_payload, platform_brief, platform_spec = _resolve_platform(
            platform_ref,
            discovery=discovery,
            asset_type=asset_type,
        )
        resolved_payload["platform"] = platform_payload
        resolved_refs["platform"] = platform_brief

    if "protocols" not in resolved_payload and platform_spec is not None:
        protocols = _normalize_default_protocols(platform_spec.default_protocols())
        if not protocols:
            _raise_validation_error(
                "missing_create_asset_protocols",
                "平台未提供可用默认协议，无法自动补齐 `protocols`。",
                missing_fields=["protocols"],
                platform=platform_spec.to_dict(),
            )
        resolved_payload["protocols"] = protocols
        resolved_defaults["protocols"] = protocols

    if asset_type == "database" and not has_cli_value(resolved_payload.get("db_name")) and platform_spec is not None:
        db_name = platform_spec.default_database_name()
        if db_name:
            resolved_payload["db_name"] = db_name
            resolved_defaults["db_name"] = db_name

    if asset_type == "database":
        for field, default in (("use_ssl", False), ("allow_invalid_cert", False)):
            if field not in resolved_payload:
                resolved_payload[field] = default
                resolved_defaults[field] = default

    if asset_type == "web":
        if "autofill" not in resolved_payload:
            resolved_payload["autofill"] = "no"
            resolved_defaults["autofill"] = "no"
        if "directory_services" not in resolved_payload:
            resolved_payload["directory_services"] = []
            resolved_defaults["directory_services"] = []

    if isinstance(resolved_payload.get("nodes"), list) and resolved_payload.get("nodes"):
        nodes = [item for item in discovery.list_nodes() if isinstance(item, dict)]
        node_refs, node_items = _resolve_pk_list(
            resolved_payload["nodes"],
            items=nodes,
            fields=("id", "pk", "name", "value", "full_value"),
            reason_code="asset_node_not_found",
            not_found_message="找不到节点：%s。",
            ambiguous_message="节点 `%s` 匹配到多个结果。",
            candidate_key="candidate_nodes",
            brief_func=_brief_node,
        )
        resolved_payload["nodes"] = node_refs
        resolved_refs["nodes"] = node_items

    if isinstance(resolved_payload.get("labels"), list) and resolved_payload.get("labels"):
        labels = client.list_paginated(LABEL_PATH)
        labels = [item for item in labels if isinstance(item, dict)] if isinstance(labels, list) else []
        label_refs, label_items = _resolve_pk_list(
            resolved_payload["labels"],
            items=labels,
            fields=("id", "pk", "name", "value"),
            reason_code="asset_label_not_found",
            not_found_message="找不到标签：%s。",
            ambiguous_message="标签 `%s` 匹配到多个结果。",
            candidate_key="candidate_labels",
            brief_func=_brief_label,
        )
        resolved_payload["labels"] = label_refs
        resolved_refs["labels"] = label_items

    if has_cli_value(resolved_payload.get("zone")):
        zones = client.list_paginated(ZONE_PATH)
        zones = [item for item in zones if isinstance(item, dict)] if isinstance(zones, list) else []
        zone, zone_brief = _find_unique_reference(
            zones,
            resolved_payload.get("zone"),
            fields=("id", "pk", "name"),
            reason_code="asset_zone_not_found",
            not_found_message="找不到网域：%s。",
            ambiguous_message="网域 `%s` 匹配到多个结果。",
            candidate_key="candidate_zones",
            brief_func=_brief_zone,
        )
        resolved_payload["zone"] = _item_id(zone)
        resolved_refs["zone"] = zone_brief

    resolved_accounts, template_refs = _resolve_account_templates(resolved_payload, discovery=discovery)
    if template_refs:
        resolved_payload["accounts"] = resolved_accounts
        resolved_refs["account_templates"] = template_refs

    return resolved_payload, resolved_refs, resolved_defaults


def _env_org_context(resource_name: str) -> dict[str, Any]:
    return create_env_org_context(
        resource_name="%s创建" % resource_name,
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定%s创建组织。" % resource_name,
        global_user_message="创建资产时，目标组织不能使用全局组织 ID。",
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="创建资产",
        global_user_message="创建资产时，目标组织不能使用全局组织 ID。",
    )


def _resolve_org_context(args: argparse.Namespace, resource_name: str) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context(resource_name)


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "address": payload.get("address"),
        "platform_pk": (payload.get("platform") or {}).get("pk") if isinstance(payload.get("platform"), dict) else None,
        "node_count": len(payload.get("nodes") or []) if isinstance(payload.get("nodes"), list) else 0,
        "protocol_count": len(payload.get("protocols") or []) if isinstance(payload.get("protocols"), list) else 0,
        "label_count": len(payload.get("labels") or []) if isinstance(payload.get("labels"), list) else 0,
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "zone": payload.get("zone"),
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
        "secret_sent": any(isinstance(item, dict) and "secret" in item for item in payload.get("accounts") or []),
        "passphrase_sent": any(isinstance(item, dict) and "passphrase" in item for item in payload.get("accounts") or []),
    }


def _create_asset(args: argparse.Namespace, *, asset_type: str) -> dict[str, Any]:
    payload = _build_asset_payload(args, asset_type=asset_type)
    _validate_asset_payload(payload, asset_type=asset_type, require_protocols=False)
    protocols_will_resolve = "protocols" not in payload

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": _api_path(asset_type),
            "payload": _mask_payload(payload),
            "payload_summary": _payload_summary(payload),
            "protocols_will_resolve_from_platform": protocols_will_resolve,
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args, _resource_name(asset_type))
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references, resolved_defaults = _resolve_asset_references(
        payload,
        client=client,
        org_id=org_id,
        asset_type=asset_type,
    )
    _validate_asset_payload(payload, asset_type=asset_type, require_protocols=True)

    if asset_type == "database":
        platform_slug = _text((resolved_references.get("platform") or {}).get("slug")).lower()
        if platform_slug in {"mongodb", "postgresql"} and not has_cli_value(payload.get("db_name")):
            _raise_validation_error(
                "missing_create_database_asset_db_name",
                "`MongoDB/PostgreSQL` 数据库资产必须填写 `db_name`。",
                missing_fields=["db_name"],
            )

    created = client.post(_api_path(asset_type), json_body=payload)
    return {
        "dry_run": False,
        "api_path": _api_path(asset_type),
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "resolved_defaults": resolved_defaults,
        "created_asset": _brief_asset(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def _add_bool_pair(parser: argparse.ArgumentParser, name: str, dest: str, help_text: str) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--%s" % name, dest=dest, action="store_true", default=None, help=help_text)
    group.add_argument("--no-%s" % name, dest=dest, action="store_false", default=None, help="禁用：%s" % help_text)


def _add_common_asset_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    parser.add_argument("--name")
    parser.add_argument("--address")
    parser.add_argument("--platform", help="平台 ID、名称或 slug；--confirm 时解析。")
    parser.add_argument("--platform-pk", dest="platform_pk", help="平台 pk；等同平台 ID。")
    parser.add_argument("--node", action="append", help="节点 ID、名称、value 或 full_value；可重复。")
    parser.add_argument("--label", action="append", help="标签 ID、名称或 value；可重复。")
    parser.add_argument("--zone", help="网域 ID 或名称；--confirm 时解析。")
    parser.add_argument("--protocol", action="append", help="协议，格式 name:port，例如 ssh:22；可重复。不传时 --confirm 后按平台默认协议补齐。")
    parser.add_argument("--account-template", dest="account_template", action="append", help="账号模板 ID 或名称；可重复。")
    parser.add_argument("--account-json", dest="account_json", action="append", help="单个账号 JSON 对象；可重复。")
    _add_bool_pair(parser, "is-active", "is_active", "是否启用资产。")
    parser.add_argument("--comment")
    parser.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    parser.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    parser.add_argument("--confirm", action="store_true")
    add_filter_arguments(parser)


def _make_asset_handler(asset_type: str):
    def _handler(args: argparse.Namespace) -> dict[str, Any]:
        return _create_asset(args, asset_type=asset_type)

    return _handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建主机、网络设备、数据库与 Web 资产入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ASSET_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for asset_type in ("host", "device", "database", "web"):
        spec = ASSET_TYPES[asset_type]
        subparser = subparsers.add_parser(
            str(spec["command"]),
            help="创建 %s。" % spec["resource_name"] if asset_type == "web" else "创建%s。" % spec["resource_name"],
            description="POST %s；无 --confirm 只预览，追加 --confirm 才解析引用并创建。" % spec["api_path"],
            epilog="Examples:\n  " + "\n  ".join(CREATE_ASSET_EXAMPLES),
            formatter_class=CLIHelpFormatter,
        )
        _add_common_asset_args(subparser)
        if asset_type == "database":
            subparser.add_argument("--db-name", dest="db_name", help="默认数据库名；未传时 --confirm 后按平台默认值补齐。")
            _add_bool_pair(subparser, "use-ssl", "use_ssl", "是否启用 SSL。")
            _add_bool_pair(subparser, "allow-invalid-cert", "allow_invalid_cert", "是否允许无效证书。")
        if asset_type == "web":
            subparser.add_argument("--autofill", choices=sorted(WEB_AUTOFILL_VALUES), help="代填方式。")
            subparser.add_argument("--username-selector", dest="username_selector")
            subparser.add_argument("--password-selector", dest="password_selector")
            subparser.add_argument("--submit-selector", dest="submit_selector")
            subparser.add_argument("--script-json", dest="script_json", action="append", help="单个脚本步骤 JSON 对象；可重复。")
        subparser.set_defaults(func=_make_asset_handler(asset_type))

    return parser


def main() -> int:
    def _run_cli():
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
