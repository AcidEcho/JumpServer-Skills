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
    create_env_org_context,
    has_cli_value,
    is_uuid_like,
    merge_filter_args,
    org_context_output,
    org_id_from_context,
    parse_strict_bool,
    parse_json_arg,
    preview_create_org_context,
    raise_create_global_org_error,
    resolve_command_org_context,
    run_and_print,
)
from jumpserver_common.jms_acl_validation import (  # noqa: E402
    ASSET_ATTR_EXACT_FIELDS,
    ASSET_ATTR_M2M_FIELDS,
    ASSET_ATTR_TEXT_FIELDS,
    USER_ATTR_BOOL_FIELDS,
    USER_ATTR_ROLE_M2M_FIELDS,
    USER_ATTR_TEXT_FIELDS,
    validate_acl_accounts,
    validate_selector_attrs,
)
from jumpserver_common.jms_types import JumpServerAPIError  # noqa: E402


CREATE_COMMAND_GROUP_PATH = "/api/v1/acls/command-groups/"
CREATE_COMMAND_FILTER_RULE_PATH = "/api/v1/acls/command-filter-acls/"
CREATE_COMMAND_GROUP_FIELDS = frozenset({"type", "ignore_case", "name", "content", "comment"})
CREATE_COMMAND_FILTER_RULE_FIELDS = frozenset(
    {
        "priority",
        "accounts",
        "action",
        "is_active",
        "users",
        "assets",
        "command_groups",
        "name",
        "reviewers",
        "comment",
    }
)
COMMAND_GROUP_TYPES = frozenset({"command", "regex"})
COMMAND_FILTER_RULE_ACTIONS = frozenset({"review", "accept", "reject", "warning", "notice", "notify_and_warn"})
COMMAND_FILTER_RULE_REVIEWER_ACTIONS = frozenset({"review", "notice", "notify_and_warn"})
SELECTOR_TYPES = frozenset({"all", "ids", "attrs"})
CREATE_COMMAND_GROUP_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_command_acl.py create-command-group "
        "--name 禁止rm --type command --content rm"
    ),
    (
        "python3 subskills/create/scripts/jms_create_command_acl.py create-command-group "
        "--org-name Default --name 禁止rm --type command --content rm --confirm"
    ),
]
CREATE_COMMAND_FILTER_RULE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule "
        "--payload '<json>'"
    ),
    (
        "python3 subskills/create/scripts/jms_create_command_acl.py create-command-filter-rule "
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


def _normalize_pk_list(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            pk = item.get("pk")
        else:
            pk = item
        if has_cli_value(pk):
            normalized.append({"pk": pk})
    return normalized


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


def _normalize_reviewer_pk_list(value: Any) -> list[dict[str, Any]]:
    return [{"pk": item} for item in _normalize_identifier_list(value)]


def _normalize_int(value: Any) -> Any:
    text = _text(value)
    if text.isdigit():
        return int(text)
    return value


def _brief_command_group(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "type": item.get("type"),
        "ignore_case": item.get("ignore_case"),
        "comment": item.get("comment"),
    }


def _brief_command_filter_rule(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "priority": item.get("priority"),
        "action": item.get("action"),
        "is_active": item.get("is_active"),
    }


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


def _resolve_user_ids(discovery, values: list[str], *, reason_prefix: str) -> tuple[list[str], list[dict[str, Any]]]:
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
                        suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
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
                        suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
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
                        "command_filter_rule_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
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
                        "command_filter_rule_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
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


def _resolve_command_filter_rule_references(payload: dict[str, Any], *, org_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}

    users = resolved_payload.get("users")
    if isinstance(users, dict) and _text(users.get("type")) == "ids":
        user_ids, user_items = _resolve_user_ids(
            discovery,
            _normalize_identifier_list(users.get("ids")),
            reason_prefix="command_filter_rule",
        )
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
            reason_prefix="command_filter_rule_reviewer",
        )
        resolved_payload["reviewers"] = [{"pk": user_id} for user_id in reviewer_ids]
        resolved_refs["reviewers"] = reviewer_items

    return resolved_payload, resolved_refs


_GLOBAL_USER_MESSAGE = "创建命令组/命令过滤规则时，目标组织不能使用全局组织 ID。"


def _raise_global_target_org_error(org_id: str) -> None:
    raise_create_global_org_error(
        org_id,
        resource_name="命令组/命令过滤规则创建",
        user_message=_GLOBAL_USER_MESSAGE,
    )


def _env_org_context(resource_name: str) -> dict[str, Any]:
    return create_env_org_context(
        resource_name=resource_name,
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定%s创建组织。" % resource_name,
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="创建命令组/命令过滤规则",
        global_user_message=_GLOBAL_USER_MESSAGE,
    )


def _resolve_org_context(args: argparse.Namespace, resource_name: str) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context(resource_name)


def _merge_payload_args(args: argparse.Namespace, examples: list[str]) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=examples,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=examples)


def _reject_unknown_fields(payload: dict[str, Any], allowed_fields: frozenset[str], *, reason_code: str, examples: list[str]) -> None:
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                reason_code,
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(allowed_fields)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=examples,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(allowed_fields),
            ),
        )


def _build_command_group_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args, CREATE_COMMAND_GROUP_EXAMPLES)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.type):
        payload["type"] = args.type
    if has_cli_value(args.content):
        payload["content"] = args.content
    if getattr(args, "ignore_case", None) is not None:
        payload["ignore_case"] = args.ignore_case
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(
        payload,
        CREATE_COMMAND_GROUP_FIELDS,
        reason_code="invalid_create_command_group_payload_fields",
        examples=CREATE_COMMAND_GROUP_EXAMPLES,
    )
    if "ignore_case" in payload:
        payload["ignore_case"] = parse_strict_bool(payload.get("ignore_case"), field_name="ignore_case")
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_COMMAND_GROUP_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _build_command_filter_rule_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args, CREATE_COMMAND_FILTER_RULE_EXAMPLES)
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
    if getattr(args, "command_group", None):
        payload["command_groups"] = _normalize_pk_list(args.command_group)
    if getattr(args, "reviewer", None):
        payload["reviewers"] = _normalize_reviewer_pk_list(args.reviewer)
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_strict_bool(args.is_active, field_name="is_active")
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(
        payload,
        CREATE_COMMAND_FILTER_RULE_FIELDS,
        reason_code="invalid_create_command_filter_rule_payload_fields",
        examples=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
    )
    if not has_cli_value(payload.get("priority")):
        payload["priority"] = 50
    else:
        payload["priority"] = _normalize_int(payload.get("priority"))
    if not has_cli_value(payload.get("action")):
        payload["action"] = "reject"
    if "accounts" in payload:
        payload["accounts"] = _normalize_accounts(payload.get("accounts"))
    if not payload.get("accounts"):
        payload["accounts"] = ["@ALL"]
    if "command_groups" in payload:
        payload["command_groups"] = _normalize_pk_list(payload.get("command_groups"))
    if "reviewers" in payload:
        payload["reviewers"] = _normalize_reviewer_pk_list(payload.get("reviewers"))
    if "is_active" in payload:
        payload["is_active"] = parse_strict_bool(payload.get("is_active"), field_name="is_active")
    if "users" in payload:
        payload["users"] = _normalize_selector(payload.get("users"))
    if "assets" in payload:
        payload["assets"] = _normalize_selector(payload.get("assets"))
    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_COMMAND_FILTER_RULE_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_command_group_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("name", "type", "content") if not _text(payload.get(field))]
    if missing:
        raise CLIError(
            "创建命令组参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_command_group_fields",
                user_message="创建命令组缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --name、--type、--content 后重试。",
                suggested_commands=CREATE_COMMAND_GROUP_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("type")) not in COMMAND_GROUP_TYPES:
        raise CLIError(
            "命令组类型不支持。",
            payload=build_cli_guidance_payload(
                "invalid_command_group_type",
                user_message="`type` 只允许 command 或 regex。",
                action_hint="请改成 `--type command` 或 `--type regex` 后重试。",
                suggested_commands=CREATE_COMMAND_GROUP_EXAMPLES,
                type=payload.get("type"),
                allowed_types=sorted(COMMAND_GROUP_TYPES),
            ),
        )


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
                "invalid_command_filter_rule_selector_type",
                user_message="`%s.type` 只允许 all/ids/attrs。" % field,
                action_hint="请改成受支持的 selector 类型后重试。",
                suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
                selector=field,
                selector_type=selector.get("type"),
                allowed_types=sorted(SELECTOR_TYPES),
            ),
        )
    if selector_type == "ids" and not _normalize_identifier_list(selector.get("ids")):
        missing.append("%s.ids" % field)
    if selector_type == "attrs" and not isinstance(selector.get("attrs"), list):
        missing.append("%s.attrs" % field)


def _validate_command_filter_rule_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in ("name", "action"):
        if not _text(payload.get(field)):
            missing.append(field)
    _validate_selector(payload, "users", missing)
    _validate_selector(payload, "assets", missing)
    if not isinstance(payload.get("command_groups"), list) or not payload.get("command_groups"):
        missing.append("command_groups")
    if _text(payload.get("action")) in COMMAND_FILTER_RULE_REVIEWER_ACTIONS:
        reviewers = payload.get("reviewers")
        if not isinstance(reviewers, list) or not reviewers:
            missing.append("reviewers")
    if missing:
        raise CLIError(
            "创建命令过滤规则参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_command_filter_rule_fields",
                user_message="创建命令过滤规则缺少必填字段：%s。" % ", ".join(missing),
                action_hint="优先使用 --payload 传入完整 JSON，或补齐 --name、--action、--command-group 及 users/assets。",
                suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
                missing_fields=missing,
            ),
        )
    if _text(payload.get("action")) not in COMMAND_FILTER_RULE_ACTIONS:
        raise CLIError(
            "命令过滤规则动作不支持。",
            payload=build_cli_guidance_payload(
                "invalid_command_filter_rule_action",
                user_message="`action` 只允许 review/accept/reject/warning/notice/notify_and_warn。",
                action_hint="请改成受支持的 action 后重试。",
                suggested_commands=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
                action=payload.get("action"),
                allowed_actions=sorted(COMMAND_FILTER_RULE_ACTIONS),
            ),
        )
    validate_acl_accounts(
        payload.get("accounts"),
        reason_code="invalid_command_filter_rule_accounts",
        examples=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
        resource_label="命令过滤规则",
    )
    validate_selector_attrs(
        payload.get("users"),
        attr_scope="users",
        reason_prefix="command_filter_rule",
        examples=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
        resource_label="命令过滤规则",
        text_fields=USER_ATTR_TEXT_FIELDS,
        bool_fields=USER_ATTR_BOOL_FIELDS,
        m2m_fields=USER_ATTR_ROLE_M2M_FIELDS,
    )
    validate_selector_attrs(
        payload.get("assets"),
        attr_scope="assets",
        reason_prefix="command_filter_rule",
        examples=CREATE_COMMAND_FILTER_RULE_EXAMPLES,
        resource_label="命令过滤规则",
        text_fields=ASSET_ATTR_TEXT_FIELDS,
        m2m_fields=ASSET_ATTR_M2M_FIELDS,
        exact_fields=ASSET_ATTR_EXACT_FIELDS,
    )


def _selector_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": None, "id_count": 0, "attr_count": 0}
    return {
        "type": value.get("type"),
        "id_count": len(value.get("ids") or []) if isinstance(value.get("ids"), list) else 0,
        "attr_count": len(value.get("attrs") or []) if isinstance(value.get("attrs"), list) else 0,
    }


def _command_group_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "type": payload.get("type"),
        "content_sent": "content" in payload,
        "ignore_case_sent": "ignore_case" in payload,
        "comment_sent": "comment" in payload,
    }


def _command_filter_rule_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "priority": payload.get("priority"),
        "action": payload.get("action"),
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "users": _selector_summary(payload.get("users")),
        "assets": _selector_summary(payload.get("assets")),
        "command_group_count": len(payload.get("command_groups") or []) if isinstance(payload.get("command_groups"), list) else 0,
        "reviewer_count": len(payload.get("reviewers") or []) if isinstance(payload.get("reviewers"), list) else 0,
        "is_active_sent": "is_active" in payload,
        "comment_sent": "comment" in payload,
    }


def _create_command_group(args: argparse.Namespace):
    payload = _build_command_group_payload(args)
    _validate_command_group_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_COMMAND_GROUP_PATH,
            "payload": payload,
            "payload_summary": _command_group_payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args, "命令组")
    client = create_client(org_id=org_id_from_context(org_context))
    created = client.post(CREATE_COMMAND_GROUP_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_COMMAND_GROUP_PATH,
        "payload_summary": _command_group_payload_summary(payload),
        "created_command_group": _brief_command_group(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def _create_command_filter_rule(args: argparse.Namespace):
    payload = _build_command_filter_rule_payload(args)
    _validate_command_filter_rule_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_COMMAND_FILTER_RULE_PATH,
            "payload": payload,
            "payload_summary": _command_filter_rule_payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args, "命令过滤规则")
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references = _resolve_command_filter_rule_references(payload, org_id=org_id)
    created = client.post(CREATE_COMMAND_FILTER_RULE_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_COMMAND_FILTER_RULE_PATH,
        "payload_summary": _command_filter_rule_payload_summary(payload),
        "resolved_references": resolved_references,
        "created_command_filter_rule": _brief_command_filter_rule(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建命令组与命令过滤规则入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_COMMAND_GROUP_EXAMPLES + CREATE_COMMAND_FILTER_RULE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    command_group = subparsers.add_parser(
        "create-command-group",
        help="创建命令组。",
        description="POST /api/v1/acls/command-groups/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_COMMAND_GROUP_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    command_group.add_argument("--name")
    command_group.add_argument("--type")
    command_group.add_argument("--content")
    command_group.add_argument("--ignore-case", dest="ignore_case", nargs="?", const="true", default=None, help="是否忽略大小写：true/false；不传则不发送。")
    command_group.add_argument("--comment")
    command_group.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    command_group.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    command_group.add_argument("--confirm", action="store_true")
    command_group.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    add_filter_arguments(command_group)
    command_group.set_defaults(func=_create_command_group)

    command_filter_rule = subparsers.add_parser(
        "create-command-filter-rule",
        help="创建命令过滤规则。",
        description="POST /api/v1/acls/command-filter-acls/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_COMMAND_FILTER_RULE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    command_filter_rule.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    command_filter_rule.add_argument("--name")
    command_filter_rule.add_argument("--priority")
    command_filter_rule.add_argument("--action")
    command_filter_rule.add_argument("--account", action="append", help="账号值，可重复。")
    command_filter_rule.add_argument("--user", "--user-id", dest="user", action="append", help="用户 ID、用户名或姓名；可重复。")
    command_filter_rule.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    command_filter_rule.add_argument("--command-group", dest="command_group", action="append", help="命令组 pk，可重复。")
    command_filter_rule.add_argument("--reviewer", action="append", help="审批人或通知接收人用户 ID、用户名或姓名；可重复。")
    command_filter_rule.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    command_filter_rule.add_argument("--comment")
    command_filter_rule.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    command_filter_rule.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    command_filter_rule.add_argument("--confirm", action="store_true")
    add_filter_arguments(command_filter_rule)
    command_filter_rule.set_defaults(func=_create_command_filter_rule)

    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
