#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import re
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
from jumpserver_common.jms_types import JumpServerAPIError  # noqa: E402


CREATE_LOGIN_ASSET_ACL_PATH = "/api/v1/acls/login-asset-acls/"
CREATE_LOGIN_ASSET_ACL_FIELDS = frozenset(
    {"priority", "accounts", "rules", "action", "is_active", "users", "assets", "name", "comment", "reviewers"}
)
LOGIN_ASSET_ACL_ACTIONS = frozenset({"review", "accept", "reject", "notice", "face_verify", "face_online"})
SELECTOR_TYPES = frozenset({"all", "ids", "attrs"})
RULE_FIELDS = frozenset({"ip_group", "time_period"})
WEEKDAY_IDS = frozenset({0, 1, 2, 3, 4, 5, 6})
TIME_PERIOD_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d~(?:[01]\d|2[0-3]):[0-5]\d$")
TEXT_MATCHES = frozenset({"exact", "not", "endswith", "in", "startswith", "regex"})
M2M_MATCHES = frozenset({"m2m", "m2m_all"})
BOOL_MATCHES = frozenset({"exact", "not"})
USER_ATTR_TEXT_FIELDS = frozenset({"name", "username", "email", "comment"})
USER_ATTR_BOOL_FIELDS = frozenset({"is_active", "is_first_login"})
USER_ATTR_M2M_FIELDS = frozenset({"org_roles", "system_roles", "groups", "labels"})
ASSET_ATTR_TEXT_FIELDS = frozenset({"name", "address", "comment"})
ASSET_ATTR_M2M_FIELDS = frozenset({"nodes", "platform", "labels"})
ASSET_ATTR_EXACT_FIELDS = frozenset({"category", "type", "protocols"})
CREATE_LOGIN_ASSET_ACL_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_login_asset_acl.py create-login-asset-acl "
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


def _normalize_reviewer_pk_list(value: Any) -> list[dict[str, Any]]:
    return [{"pk": item} for item in _normalize_identifier_list(value)]


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
        usage_examples=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_LOGIN_ASSET_ACL_EXAMPLES)


def _reject_unknown_fields(payload: dict[str, Any]) -> None:
    unknown_fields = sorted(set(payload) - CREATE_LOGIN_ASSET_ACL_FIELDS)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_login_asset_acl_payload_fields",
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(CREATE_LOGIN_ASSET_ACL_FIELDS)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_LOGIN_ASSET_ACL_FIELDS),
            ),
        )


def _build_login_asset_acl_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.priority):
        payload["priority"] = _normalize_int(args.priority)
    if has_cli_value(args.action):
        payload["action"] = args.action
    if getattr(args, "account", None):
        payload["accounts"] = _normalize_accounts(args.account)
    if getattr(args, "user", None):
        payload["users"] = {"type": "ids", "ids": _normalize_identifier_list(args.user)}
    if getattr(args, "asset", None):
        payload["assets"] = {"type": "ids", "ids": _normalize_identifier_list(args.asset)}
    if getattr(args, "reviewer", None):
        payload["reviewers"] = _normalize_reviewer_pk_list(args.reviewer)
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_bool(args.is_active)
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(payload)
    if not has_cli_value(payload.get("priority")):
        payload["priority"] = 50
    else:
        payload["priority"] = _normalize_int(payload.get("priority"))
    if not has_cli_value(payload.get("action")):
        payload["action"] = "reject"
    if "accounts" in payload:
        payload["accounts"] = _normalize_accounts(payload.get("accounts"))
    if "reviewers" in payload:
        payload["reviewers"] = _normalize_reviewer_pk_list(payload.get("reviewers"))
    if "is_active" in payload:
        payload["is_active"] = parse_bool(payload.get("is_active"))
    if "users" in payload:
        payload["users"] = _normalize_selector(payload.get("users"))
    if "assets" in payload:
        payload["assets"] = _normalize_selector(payload.get("assets"))
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_LOGIN_ASSET_ACL_FIELDS
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
                "invalid_login_asset_acl_selector_type",
                user_message="`%s.type` 只允许 all/ids/attrs。" % field,
                action_hint="请改成受支持的 selector 类型后重试。",
                suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
                selector=field,
                selector_type=selector.get("type"),
                allowed_types=sorted(SELECTOR_TYPES),
            ),
        )
    if selector_type == "ids" and not _normalize_identifier_list(selector.get("ids")):
        missing.append("%s.ids" % field)
    if selector_type == "attrs" and not isinstance(selector.get("attrs"), list):
        missing.append("%s.attrs" % field)
    elif selector_type == "attrs" and not selector.get("attrs"):
        missing.append("%s.attrs" % field)


def _raise_invalid_login_asset_acl(reason_code: str, user_message: str, **details: Any) -> None:
    raise CLIError(
        "资产连接规则参数不合法。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=user_message,
            action_hint="请按 API.md 第 19 节修正 payload 后重试。",
            suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
            **details,
        ),
    )


def _validate_accounts(payload: dict[str, Any]) -> None:
    if "accounts" not in payload:
        return
    accounts = [_text(item) for item in _normalize_accounts(payload.get("accounts"))]
    if not accounts:
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_accounts",
            "`accounts` 不能为空；允许 [\"@ALL\"] 或 [\"@SPEC\", \"account\"]。",
            accounts=payload.get("accounts"),
        )
    if "@ALL" in accounts:
        if accounts != ["@ALL"]:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_accounts",
                "`@ALL` 只能单独使用，不能和其他账号混用。",
                accounts=accounts,
            )
        return
    if accounts[0] != "@SPEC":
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_accounts",
            "指定账号时，`accounts` 必须以 `@SPEC` 开头。",
            accounts=accounts,
        )
    account_names = accounts[1:]
    if not account_names or any(item.startswith("@") for item in account_names):
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_accounts",
            "`@SPEC` 后必须跟一个或多个账号名。",
            accounts=accounts,
        )


def _valid_ip_group_item(value: Any) -> bool:
    text = _text(value)
    if text == "*":
        return True
    if "-" in text:
        start, end = [part.strip() for part in text.split("-", 1)]
        try:
            start_ip = ipaddress.ip_address(start)
            end_ip = ipaddress.ip_address(end)
        except ValueError:
            return False
        return start_ip.version == end_ip.version and int(start_ip) <= int(end_ip)
    try:
        if "/" in text:
            ipaddress.ip_network(text, strict=False)
        else:
            ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _validate_rules(payload: dict[str, Any]) -> None:
    rules = payload.get("rules")
    if not isinstance(rules, dict) or not rules:
        return
    unknown_fields = sorted(set(rules) - RULE_FIELDS)
    if unknown_fields:
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_rules",
            "`rules` 只允许字段：ip_group, time_period。",
            invalid_fields=["rules.%s" % item for item in unknown_fields],
            allowed_fields=sorted(RULE_FIELDS),
        )
    if "ip_group" in rules:
        ip_group = rules.get("ip_group")
        if not isinstance(ip_group, list) or not ip_group:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_ip_group",
                "`rules.ip_group` 必须是非空列表。",
                ip_group=ip_group,
            )
        invalid_items = [item for item in ip_group if not _valid_ip_group_item(item)]
        if invalid_items:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_ip_group",
                "`rules.ip_group` 只允许 *、单 IP、CIDR 或 IP 范围。",
                invalid_ip_group_items=invalid_items,
            )
    if "time_period" in rules:
        periods = rules.get("time_period")
        if not isinstance(periods, list) or not periods:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_time_period",
                "`rules.time_period` 必须是非空列表。",
                time_period=periods,
            )
        seen_ids = set()
        invalid_periods = []
        for period in periods:
            if not isinstance(period, dict):
                invalid_periods.append(period)
                continue
            raw_id = period.get("id")
            period_id = int(raw_id) if isinstance(raw_id, str) and raw_id.isdigit() else raw_id
            value = _text(period.get("value"))
            if period_id not in WEEKDAY_IDS or period_id in seen_ids or not TIME_PERIOD_RE.fullmatch(value):
                invalid_periods.append(period)
                continue
            seen_ids.add(period_id)
        if invalid_periods:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_time_period",
                "`rules.time_period` 需要 {id,value}，id 只能是 0-6 且不能重复，value 格式为 HH:MM~HH:MM。",
                invalid_time_periods=invalid_periods,
            )


def _attr_value_is_scalar(value: Any) -> bool:
    return has_cli_value(value) and not isinstance(value, (list, dict))


def _attr_value_is_nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(has_cli_value(item) for item in value)


def _validate_attr_value(field: str, match: str, value: Any, *, attr_scope: str) -> None:
    if attr_scope == "users":
        if field in USER_ATTR_TEXT_FIELDS:
            allowed_matches = TEXT_MATCHES
            valid_value = _attr_value_is_nonempty_list(value) if match == "in" else _attr_value_is_scalar(value)
        elif field in USER_ATTR_BOOL_FIELDS:
            allowed_matches = BOOL_MATCHES
            valid_value = isinstance(value, bool)
        elif field in USER_ATTR_M2M_FIELDS:
            allowed_matches = M2M_MATCHES
            valid_value = _attr_value_is_nonempty_list(value)
        else:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_user_attrs",
                "`users.attrs.name` 不支持：%s。" % field,
                attr=field,
            )
            return
    else:
        if field in ASSET_ATTR_TEXT_FIELDS:
            allowed_matches = TEXT_MATCHES
            valid_value = _attr_value_is_nonempty_list(value) if match == "in" else _attr_value_is_scalar(value)
        elif field in ASSET_ATTR_M2M_FIELDS:
            allowed_matches = M2M_MATCHES
            valid_value = _attr_value_is_nonempty_list(value)
        elif field in ASSET_ATTR_EXACT_FIELDS:
            allowed_matches = BOOL_MATCHES
            valid_value = _attr_value_is_scalar(value)
        else:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_asset_attrs",
                "`assets.attrs.name` 不支持：%s。" % field,
                attr=field,
            )
            return
    if match not in allowed_matches:
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_%s_attrs" % attr_scope,
            "`%s.attrs` 字段 `%s` 不支持 match=%s。" % (attr_scope, field, match),
            attr=field,
            match=match,
            allowed_matches=sorted(allowed_matches),
        )
    if not valid_value:
        _raise_invalid_login_asset_acl(
            "invalid_login_asset_acl_%s_attrs" % attr_scope,
            "`%s.attrs` 字段 `%s` 的 value 类型不正确。" % (attr_scope, field),
            attr=field,
            match=match,
            value=value,
        )


def _validate_attrs(selector: Any, *, attr_scope: str) -> None:
    if not isinstance(selector, dict) or _text(selector.get("type")) != "attrs":
        return
    attrs = selector.get("attrs")
    if not isinstance(attrs, list) or not attrs:
        return
    for index, attr in enumerate(attrs):
        if not isinstance(attr, dict):
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_%s_attrs" % attr_scope,
                "`%s.attrs[%s]` 必须是对象。" % (attr_scope, index),
                attr_index=index,
                attr=attr,
            )
        field = _text(attr.get("name"))
        match = _text(attr.get("match"))
        if not field or not match or "value" not in attr:
            _raise_invalid_login_asset_acl(
                "invalid_login_asset_acl_%s_attrs" % attr_scope,
                "`%s.attrs[%s]` 必须包含 name、match、value。" % (attr_scope, index),
                attr_index=index,
                attr=attr,
            )
        _validate_attr_value(field, match, attr.get("value"), attr_scope=attr_scope)


def _validate_login_asset_acl_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in ("name", "action"):
        if not _text(payload.get(field)):
            missing.append(field)
    _validate_selector(payload, "users", missing)
    _validate_selector(payload, "assets", missing)
    if not isinstance(payload.get("rules"), dict) or not payload.get("rules"):
        missing.append("rules")
    if _text(payload.get("action")) in {"review", "notice"} and not payload.get("reviewers"):
        missing.append("reviewers")
    if missing:
        raise CLIError(
            "创建资产连接规则参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_login_asset_acl_fields",
                user_message="创建资产连接规则缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入完整 JSON，或补齐 --name、--action 及 users/assets/rules。",
                suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("action")) not in LOGIN_ASSET_ACL_ACTIONS:
        raise CLIError(
            "资产连接规则动作不支持。",
            payload=build_cli_guidance_payload(
                "invalid_login_asset_acl_action",
                user_message="`action` 只允许 review/accept/reject/notice/face_verify/face_online。",
                action_hint="请改成受支持的 action 后重试。",
                suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
                action=payload.get("action"),
                allowed_actions=sorted(LOGIN_ASSET_ACL_ACTIONS),
            ),
        )
    _validate_accounts(payload)
    _validate_rules(payload)
    _validate_attrs(payload.get("users"), attr_scope="users")
    _validate_attrs(payload.get("assets"), attr_scope="assets")


def _raise_global_target_org_error(org_id: str) -> None:
    raise CLIError(
        "目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建资产连接规则时，目标组织不能使用全局组织 ID。",
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
                user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定资产连接规则创建组织。",
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


def _resolve_user_ids(discovery, values: list[str], *, reason_prefix: str = "login_asset_acl") -> tuple[list[str], list[dict[str, Any]]]:
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
                        "%s_user_not_found" % reason_prefix,
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
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
                        "%s_user_not_found" % reason_prefix,
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
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
                        "login_asset_acl_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
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
                        "login_asset_acl_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_LOGIN_ASSET_ACL_EXAMPLES,
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

    reviewers = resolved_payload.get("reviewers")
    if isinstance(reviewers, list) and reviewers:
        reviewer_ids, reviewer_items = _resolve_user_ids(
            discovery,
            _normalize_identifier_list(reviewers),
            reason_prefix="login_asset_acl_reviewer",
        )
        resolved_payload["reviewers"] = [{"pk": user_id} for user_id in reviewer_ids]
        resolved_refs["reviewers"] = reviewer_items

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
        "action": payload.get("action"),
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "users": _selector_summary(payload.get("users")),
        "assets": _selector_summary(payload.get("assets")),
        "reviewer_count": len(payload.get("reviewers") or []) if isinstance(payload.get("reviewers"), list) else 0,
        "rules_sent": "rules" in payload,
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
    }


def _brief_login_asset_acl(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "priority": item.get("priority"),
        "action": item.get("action"),
        "is_active": item.get("is_active"),
    }


def _existing_by_name(client, *, name: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_LOGIN_ASSET_ACL_PATH, params={"search": name})
    if not isinstance(records, list):
        records = []
    wanted_name = _text(name)
    return [
        _brief_login_asset_acl(item)
        for item in records
        if isinstance(item, dict) and _text(item.get("name")) == wanted_name
    ]


def _create_login_asset_acl(args: argparse.Namespace):
    payload = _build_login_asset_acl_payload(args)
    _validate_login_asset_acl_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_LOGIN_ASSET_ACL_PATH,
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
            "资产连接规则已存在。",
            payload=build_cli_guidance_payload(
                "login_asset_acl_already_exists",
                user_message="目标组织内已存在同名资产连接规则，已阻止创建。",
                action_hint="请改用已有资产连接规则，或换一个名称。",
                duplicate_login_asset_acls=duplicates,
            ),
        )

    created = client.post(CREATE_LOGIN_ASSET_ACL_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_LOGIN_ASSET_ACL_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "created_login_asset_acl": _brief_login_asset_acl(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建资产连接规则入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LOGIN_ASSET_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_asset_acl = subparsers.add_parser(
        "create-login-asset-acl",
        help="创建资产连接规则。",
        description="POST /api/v1/acls/login-asset-acls/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_LOGIN_ASSET_ACL_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    login_asset_acl.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    login_asset_acl.add_argument("--name")
    login_asset_acl.add_argument("--priority")
    login_asset_acl.add_argument("--action")
    login_asset_acl.add_argument("--account", action="append", help="账号值，可重复。")
    login_asset_acl.add_argument("--user", "--user-id", dest="user", action="append", help="用户 ID、用户名或姓名；可重复。")
    login_asset_acl.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    login_asset_acl.add_argument("--reviewer", action="append", help="审批人或通知接收人用户 ID、用户名或姓名；可重复。")
    login_asset_acl.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    login_asset_acl.add_argument("--comment")
    login_asset_acl.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    login_asset_acl.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    login_asset_acl.add_argument("--confirm", action="store_true")
    add_filter_arguments(login_asset_acl)
    login_asset_acl.set_defaults(func=_create_login_asset_acl)

    return parser


def main() -> int:
    def _run_cli():
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
