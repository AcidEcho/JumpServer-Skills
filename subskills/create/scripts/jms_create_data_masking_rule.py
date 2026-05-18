#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIError,
    CLIHelpFormatter,
    GLOBAL_ORG_ID,
    add_filter_arguments,
    build_cli_guidance_payload,
    create_client,
    create_discovery,
    current_runtime_values,
    has_cli_value,
    is_uuid_like,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    parse_bool,
    parse_json_arg,
    resolve_command_org_context,
    run_and_print,
)
from jumpserver_common.jms_acl_validation import (  # noqa: E402
    ASSET_ATTR_EXACT_FIELDS,
    ASSET_ATTR_M2M_FIELDS,
    ASSET_ATTR_TEXT_FIELDS,
    USER_ATTR_BOOL_FIELDS,
    USER_ATTR_EXTENDED_M2M_FIELDS,
    USER_ATTR_TEXT_FIELDS,
    validate_acl_accounts,
    validate_selector_attrs,
)
from jumpserver_common.jms_types import JumpServerAPIError  # noqa: E402


CREATE_DATA_MASKING_RULE_PATH = "/api/v1/acls/data-masking-rules/"
CREATE_DATA_MASKING_RULE_FIELDS = frozenset(
    {
        "name",
        "priority",
        "users",
        "assets",
        "accounts",
        "fields_pattern",
        "masking_method",
        "mask_pattern",
        "is_active",
        "comment",
    }
)
MASKING_METHODS = frozenset({"fixed_char", "hide_middle", "keep_prefix", "keep_suffix"})
SELECTOR_TYPES = frozenset({"all", "ids", "attrs"})
CREATE_DATA_MASKING_RULE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_data_masking_rule.py create-data-masking-rule "
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


def _normalize_int(value: Any) -> Any:
    text = _text(value)
    if text.isdigit():
        return int(text)
    return value


def _normalize_accounts(value: Any) -> list[Any]:
    return [item for item in _as_list(value) if has_cli_value(item)]


def _normalize_identifier_list(value: Any) -> list[str]:
    identifiers = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = (
                item.get("id")
                or item.get("pk")
                or item.get("value")
                or item.get("username")
                or item.get("name")
                or item.get("address")
            )
        else:
            candidate = item
        text = _text(candidate)
        if text:
            identifiers.append(text)
    return identifiers


def _normalize_selector(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    selector = dict(value)
    selector_type = _text(selector.get("type"))
    if selector_type:
        selector["type"] = selector_type
    if selector_type == "ids":
        selector["ids"] = _normalize_identifier_list(selector.get("ids"))
    return selector


def _merge_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=CREATE_DATA_MASKING_RULE_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_DATA_MASKING_RULE_EXAMPLES)


def _reject_unknown_fields(payload: dict[str, Any]) -> None:
    unknown_fields = sorted(set(payload) - CREATE_DATA_MASKING_RULE_FIELDS)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_data_masking_rule_payload_fields",
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(CREATE_DATA_MASKING_RULE_FIELDS)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_DATA_MASKING_RULE_FIELDS),
            ),
        )


def _build_data_masking_rule_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.priority):
        payload["priority"] = _normalize_int(args.priority)
    if getattr(args, "account", None):
        payload["accounts"] = _normalize_accounts(args.account)
    if getattr(args, "user", None):
        payload["users"] = {"type": "ids", "ids": _normalize_identifier_list(args.user)}
    if getattr(args, "asset", None):
        payload["assets"] = {"type": "ids", "ids": _normalize_identifier_list(args.asset)}
    if has_cli_value(args.fields_pattern):
        payload["fields_pattern"] = args.fields_pattern
    if has_cli_value(args.masking_method):
        payload["masking_method"] = args.masking_method
    if has_cli_value(args.mask_pattern):
        payload["mask_pattern"] = args.mask_pattern
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_bool(args.is_active)
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(payload)
    if not has_cli_value(payload.get("priority")):
        payload["priority"] = 50
    else:
        payload["priority"] = _normalize_int(payload.get("priority"))
    if "accounts" in payload:
        payload["accounts"] = _normalize_accounts(payload.get("accounts"))
    else:
        payload["accounts"] = ["@ALL"]
    if "users" in payload:
        payload["users"] = _normalize_selector(payload.get("users"))
    if "assets" in payload:
        payload["assets"] = _normalize_selector(payload.get("assets"))
    if "is_active" in payload:
        payload["is_active"] = parse_bool(payload.get("is_active"))
    if _text(payload.get("masking_method")) == "fixed_char" and not has_cli_value(payload.get("mask_pattern")):
        payload["mask_pattern"] = "######"
    if not has_cli_value(payload.get("fields_pattern")):
        payload["fields_pattern"] = "password"
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_DATA_MASKING_RULE_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_selector(payload: dict[str, Any], field: str, missing: list[str]) -> None:
    selector = payload.get(field)
    if not isinstance(selector, dict):
        missing.append(field)
        return
    selector_type = _text(selector.get("type"))
    if selector_type not in SELECTOR_TYPES:
        raise CLIError(
            "选择器类型不支持。",
            payload=build_cli_guidance_payload(
                "invalid_data_masking_rule_selector_type",
                user_message="`%s.type` 只允许 all/ids/attrs。" % field,
                action_hint="请改成受支持的 selector 类型后重试。",
                suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                selector=field,
                selector_type=selector.get("type"),
                allowed_types=sorted(SELECTOR_TYPES),
            ),
        )
    if selector_type == "ids" and not _normalize_identifier_list(selector.get("ids")):
        missing.append("%s.ids" % field)
    if selector_type == "attrs" and not isinstance(selector.get("attrs"), list):
        missing.append("%s.attrs" % field)


def _validate_data_masking_rule_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in ("name", "masking_method", "fields_pattern"):
        if not _text(payload.get(field)):
            missing.append(field)
    _validate_selector(payload, "users", missing)
    _validate_selector(payload, "assets", missing)
    if not isinstance(payload.get("accounts"), list) or not payload.get("accounts"):
        missing.append("accounts")
    if missing:
        raise CLIError(
            "创建数据脱敏过滤规则参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_data_masking_rule_fields",
                user_message="创建数据脱敏过滤规则缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入完整 JSON，或补齐 --name、--account、--masking-method 及 users/assets。",
                suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("masking_method")) not in MASKING_METHODS:
        raise CLIError(
            "脱敏方式不支持。",
            payload=build_cli_guidance_payload(
                "invalid_data_masking_method",
                user_message="`masking_method` 只允许 fixed_char/hide_middle/keep_prefix/keep_suffix。",
                action_hint="请改成受支持的 masking_method 后重试。",
                suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                masking_method=payload.get("masking_method"),
                allowed_methods=sorted(MASKING_METHODS),
            ),
        )
    validate_acl_accounts(
        payload.get("accounts"),
        reason_code="invalid_data_masking_rule_accounts",
        examples=CREATE_DATA_MASKING_RULE_EXAMPLES,
        resource_label="数据脱敏过滤规则",
    )
    validate_selector_attrs(
        payload.get("users"),
        attr_scope="users",
        reason_prefix="data_masking_rule",
        examples=CREATE_DATA_MASKING_RULE_EXAMPLES,
        resource_label="数据脱敏过滤规则",
        text_fields=USER_ATTR_TEXT_FIELDS,
        bool_fields=USER_ATTR_BOOL_FIELDS,
        m2m_fields=USER_ATTR_EXTENDED_M2M_FIELDS,
    )
    validate_selector_attrs(
        payload.get("assets"),
        attr_scope="assets",
        reason_prefix="data_masking_rule",
        examples=CREATE_DATA_MASKING_RULE_EXAMPLES,
        resource_label="数据脱敏过滤规则",
        text_fields=ASSET_ATTR_TEXT_FIELDS,
        m2m_fields=ASSET_ATTR_M2M_FIELDS,
        exact_fields=ASSET_ATTR_EXACT_FIELDS,
    )


def _raise_global_target_org_error(org_id: str) -> None:
    raise CLIError(
        "目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建数据脱敏过滤规则时，目标组织不能使用全局组织 ID。",
            action_hint="请改用具体目标组织 ID 或 `--org-name <target-org>`。",
            org_id=org_id,
        ),
    )


def _env_org_context() -> dict[str, Any]:
    org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
    if not org_id:
        raise CLIError(
            "未选择目标组织。",
            payload=build_cli_guidance_payload(
                "organization_selection_required",
                user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定数据脱敏过滤规则创建组织。",
                action_hint="请传入 `--org-id <org-id>` 或 `--org-name <name>`，或先用 common 子 skill 选择当前组织。",
            ),
        )
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)
    return {
        "effective_org": {"id": org_id, "name": "Unknown", "source": "env"},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前命令范围使用 .env JMS_ORG_ID=%s；不写入 .env。" % org_id,
    }


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id and requested_org_name:
        resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    if requested_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(requested_org_id)
    if requested_org_id:
        return {
            "effective_org": {"id": requested_org_id, "name": "Unknown", "source": "command_explicit_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织 ID %s；追加 --confirm 后才解析组织并创建。" % requested_org_id,
        }
    if requested_org_name:
        return {
            "effective_org": {"id": "", "name": requested_org_name, "source": "command_org_name_preview"},
            "switchable_orgs": [],
            "switchable_org_count": 0,
            "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织并创建。" % requested_org_name,
        }
    org_id = _text(current_runtime_values().get("JMS_ORG_ID"))
    if org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(org_id)
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式创建时未传组织将使用 .env JMS_ORG_ID。",
    }


def _resolve_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context()


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
        "email": item.get("email"),
    }


def _brief_asset(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "address": item.get("address"),
        "platform": platform.get("name") if isinstance(platform, dict) else platform,
    }


def _item_id(item: dict[str, Any]) -> str:
    return _text(item.get("id") or item.get("pk"))


def _find_item_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    wanted = _text(item_id)
    for item in items:
        if _item_id(item) == wanted:
            return item
    return None


def _resolve_user_ids(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    users = [item for item in discovery.list_users() if isinstance(item, dict)]
    resolved_ids = []
    resolved_items = []
    seen = set()
    for value in values:
        if is_uuid_like(value):
            user = _find_item_by_id(users, value)
            if not user:
                raise CLIError(
                    "无法解析用户 ID。",
                    payload=build_cli_guidance_payload(
                        "data_masking_rule_user_not_found",
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                        user=value,
                        candidate_users=[_brief_user(item) for item in users[:20]],
                    ),
                )
            user_id = _item_id(user)
        else:
            try:
                resolved = discovery.resolve_user_ids([value])
            except JumpServerAPIError as exc:
                raise CLIError(
                    "无法解析用户标识。",
                    payload=build_cli_guidance_payload(
                        "data_masking_rule_user_not_found",
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                        user=value,
                        candidate_users=[_brief_user(item) for item in users[:20]],
                    ),
                ) from exc
            user_id = _text((resolved or [""])[0])
            user = _find_item_by_id(users, user_id) or {"id": user_id}
        if user_id and user_id not in seen:
            seen.add(user_id)
            resolved_ids.append(user_id)
            resolved_items.append(_brief_user(user))
    return resolved_ids, resolved_items


def _resolve_asset_ids(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    assets = [item for item in discovery.list_assets() if isinstance(item, dict)]
    resolved_ids = []
    resolved_items = []
    seen = set()
    for value in values:
        if is_uuid_like(value):
            asset = _find_item_by_id(assets, value)
            if not asset:
                raise CLIError(
                    "无法解析资产 ID。",
                    payload=build_cli_guidance_payload(
                        "data_masking_rule_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                        asset=value,
                        candidate_assets=[_brief_asset(item) for item in assets[:20]],
                    ),
                )
            asset_id = _item_id(asset)
        else:
            try:
                resolved = discovery.resolve_asset_ids([value])
            except JumpServerAPIError as exc:
                raise CLIError(
                    "无法解析资产标识。",
                    payload=build_cli_guidance_payload(
                        "data_masking_rule_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_DATA_MASKING_RULE_EXAMPLES,
                        asset=value,
                        candidate_assets=[_brief_asset(item) for item in assets[:20]],
                    ),
                ) from exc
            asset_id = _text((resolved or [""])[0])
            asset = _find_item_by_id(assets, asset_id) or {"id": asset_id}
        if asset_id and asset_id not in seen:
            seen.add(asset_id)
            resolved_ids.append(asset_id)
            resolved_items.append(_brief_asset(asset))
    return resolved_ids, resolved_items


def _resolve_id_selectors(payload: dict[str, Any], *, org_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}

    users = resolved_payload.get("users")
    if isinstance(users, dict) and _text(users.get("type")) == "ids":
        user_ids, user_items = _resolve_user_ids(discovery, _normalize_identifier_list(users.get("ids")))
        resolved_payload["users"] = {**users, "ids": user_ids}
        resolved_refs["users"] = user_items

    assets = resolved_payload.get("assets")
    if isinstance(assets, dict) and _text(assets.get("type")) == "ids":
        asset_ids, asset_items = _resolve_asset_ids(discovery, _normalize_identifier_list(assets.get("ids")))
        resolved_payload["assets"] = {**assets, "ids": asset_ids}
        resolved_refs["assets"] = asset_items

    return resolved_payload, resolved_refs


def _selector_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": None, "id_count": 0, "attr_count": 0}
    return {
        "type": value.get("type"),
        "id_count": len(value.get("ids") or []) if isinstance(value.get("ids"), list) else 0,
        "attr_count": len(value.get("attrs") or []) if isinstance(value.get("attrs"), list) else 0,
    }


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "priority": payload.get("priority"),
        "masking_method": payload.get("masking_method"),
        "fields_pattern": payload.get("fields_pattern"),
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "users": _selector_summary(payload.get("users")),
        "assets": _selector_summary(payload.get("assets")),
        "mask_pattern_sent": "mask_pattern" in payload,
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
    }


def _brief_data_masking_rule(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "priority": item.get("priority"),
        "masking_method": item.get("masking_method"),
        "is_active": item.get("is_active"),
    }


def _existing_by_name(client, *, name: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_DATA_MASKING_RULE_PATH, params={"search": name})
    if not isinstance(records, list):
        records = []
    wanted_name = _text(name)
    return [
        _brief_data_masking_rule(item)
        for item in records
        if isinstance(item, dict) and _text(item.get("name")) == wanted_name
    ]


def _create_data_masking_rule(args: argparse.Namespace):
    payload = _build_data_masking_rule_payload(args)
    _validate_data_masking_rule_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_DATA_MASKING_RULE_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args)
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references = _resolve_id_selectors(payload, org_id=org_id)
    duplicates = _existing_by_name(client, name=str(payload.get("name") or ""))
    if duplicates:
        raise CLIError(
            "数据脱敏过滤规则已存在。",
            payload=build_cli_guidance_payload(
                "data_masking_rule_already_exists",
                user_message="目标组织内已存在同名数据脱敏过滤规则，已阻止创建。",
                action_hint="请改用已有数据脱敏过滤规则，或换一个名称。",
                duplicate_data_masking_rules=duplicates,
            ),
        )

    created = client.post(CREATE_DATA_MASKING_RULE_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_DATA_MASKING_RULE_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "created_data_masking_rule": _brief_data_masking_rule(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建数据脱敏过滤规则入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_DATA_MASKING_RULE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    data_masking_rule = subparsers.add_parser(
        "create-data-masking-rule",
        help="创建数据脱敏过滤规则。",
        description="POST /api/v1/acls/data-masking-rules/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_DATA_MASKING_RULE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    data_masking_rule.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    data_masking_rule.add_argument("--name")
    data_masking_rule.add_argument("--priority")
    data_masking_rule.add_argument("--account", action="append", help="账号值，可重复。")
    data_masking_rule.add_argument("--user", "--user-id", dest="user", action="append", help="用户 ID、用户名或姓名；可重复。")
    data_masking_rule.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    data_masking_rule.add_argument("--fields-pattern", dest="fields_pattern", help="遮盖列名匹配，默认 password。")
    data_masking_rule.add_argument("--masking-method", dest="masking_method", choices=sorted(MASKING_METHODS))
    data_masking_rule.add_argument("--mask-pattern", dest="mask_pattern", help="fixed_char 时的遮盖字符，默认 ######。")
    data_masking_rule.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    data_masking_rule.add_argument("--comment")
    data_masking_rule.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    data_masking_rule.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    data_masking_rule.add_argument("--confirm", action="store_true")
    add_filter_arguments(data_masking_rule)
    data_masking_rule.set_defaults(func=_create_data_masking_rule)

    return parser


def main() -> int:
    def _run_cli():
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
