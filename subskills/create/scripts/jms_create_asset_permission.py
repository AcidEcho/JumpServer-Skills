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
from jumpserver_common.jms_types import JumpServerAPIError  # noqa: E402


CREATE_ASSET_PERMISSION_PATH = "/api/v1/perms/asset-permissions/"
ASSET_PROTOCOLS_PATH = "/api/v1/assets/protocols/"
CREATE_ASSET_PERMISSION_FIELDS = frozenset(
    {
        "assets",
        "nodes",
        "accounts",
        "protocols",
        "actions",
        "is_active",
        "date_start",
        "date_expired",
        "name",
        "users",
        "user_groups",
        "comment",
    }
)
ACTION_LABELS = {
    "connect": "连接 (所有协议)",
    "upload": "上传 (RDP, SFTP)",
    "download": "下载 (RDP, SFTP)",
    "copy": "复制 (RDP, VNC)",
    "paste": "粘贴 (RDP, VNC)",
    "delete": "删除 (SFTP)",
    "share": "分享 (Web SSH, Web RDP, Web VNC)",
}
DEFAULT_ACTIONS = ["connect", "upload", "download", "copy", "paste", "delete", "share"]
VIRTUAL_ACCOUNTS = frozenset({"@INPUT", "@USER", "@ANON"})
BASE_ACCOUNT_MARKERS = frozenset({"@ALL", "@SPEC"})
CREATE_ASSET_PERMISSION_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission "
        "--org-name Default --name 生产资产授权 --user alice --asset prod-host --confirm"
    ),
    (
        "python3 subskills/create/scripts/jms_create_asset_permission.py create-asset-permission "
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
                or item.get("full_value")
            )
        else:
            candidate = item
        text = _text(candidate)
        if text:
            identifiers.append(text)
    return identifiers


def _normalize_pk_list(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            pk = item.get("pk") or item.get("id") or item.get("value") or item.get("name") or item.get("username")
        else:
            pk = item
        if has_cli_value(pk):
            normalized.append({"pk": pk})
    return normalized


def _normalize_accounts(value: Any) -> list[str]:
    return [_text(item) for item in _as_list(value) if has_cli_value(item)]


def _normalize_protocols(value: Any) -> list[str]:
    protocols = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = item.get("value") or item.get("name") or item.get("label")
        else:
            candidate = item
        text = _text(candidate)
        if text:
            protocols.append(text)
    return protocols


def _normalize_actions(value: Any) -> list[str]:
    actions = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = item.get("value")
        else:
            candidate = item
        text = _text(candidate)
        if text and text not in actions:
            actions.append(text)
    return actions


def _account_is_virtual(value: str) -> bool:
    return value in VIRTUAL_ACCOUNTS


def _brief_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
        "email": item.get("email"),
    }


def _brief_user_group(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
    }


def _brief_asset(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "address": item.get("address"),
        "platform": platform.get("name") if isinstance(platform, dict) else platform,
    }


def _brief_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "value": item.get("value"),
        "full_value": item.get("full_value"),
    }


def _brief_protocol(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": item.get("value") or item.get("name"),
        "label": item.get("label") or item.get("name") or item.get("value"),
    }


def _brief_asset_permission(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "is_active": item.get("is_active"),
        "date_start": item.get("date_start"),
        "date_expired": item.get("date_expired"),
    }


def _item_id(item: dict[str, Any]) -> str:
    return _text(item.get("id") or item.get("pk"))


def _find_item_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    wanted = _text(item_id)
    for item in items:
        if _item_id(item) == wanted:
            return item
    return None


def _merge_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json_arg(
        getattr(args, "payload", None),
        default={},
        source="--payload",
        usage_examples=CREATE_ASSET_PERMISSION_EXAMPLES,
    )
    return merge_filter_args(args, default=payload, explicit_fields=(), usage_examples=CREATE_ASSET_PERMISSION_EXAMPLES)


def _reject_unknown_fields(payload: dict[str, Any]) -> None:
    unknown_fields = sorted(set(payload) - CREATE_ASSET_PERMISSION_FIELDS)
    if unknown_fields:
        raise CLIError(
            "payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_asset_permission_payload_fields",
                user_message="payload 只允许字段：%s。" % ", ".join(sorted(CREATE_ASSET_PERMISSION_FIELDS)),
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_ASSET_PERMISSION_FIELDS),
            ),
        )


def _raise_invalid_accounts(message: str, *, accounts: list[str]) -> None:
    raise CLIError(
        "资产授权账号规则不合法。",
        payload=build_cli_guidance_payload(
            "invalid_asset_permission_accounts",
            user_message=message,
            action_hint="基础账号模式只能在 @ALL、@SPEC+账号名、!排除账号、无账号中选择一种；@INPUT/@USER/@ANON 可叠加。",
            suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
            accounts=accounts,
            virtual_accounts=sorted(VIRTUAL_ACCOUNTS),
        ),
    )


def _validate_no_account_cli(args: argparse.Namespace) -> None:
    if not getattr(args, "no_account", False):
        return
    accounts = _normalize_accounts(getattr(args, "account", None))
    invalid = [item for item in accounts if not _account_is_virtual(item)]
    if invalid:
        _raise_invalid_accounts(
            "`--no-account` 只能与虚拟账号 @INPUT/@USER/@ANON 组合，不能与基础账号模式混用。",
            accounts=accounts,
        )


def _build_asset_permission_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _merge_payload_args(args)
    if has_cli_value(args.name):
        payload["name"] = args.name
    if getattr(args, "asset", None):
        payload["assets"] = _normalize_identifier_list(args.asset)
    if getattr(args, "node", None):
        payload["nodes"] = _normalize_pk_list(args.node)
    if getattr(args, "user", None):
        payload["users"] = _normalize_pk_list(args.user)
    if getattr(args, "user_group", None):
        payload["user_groups"] = _normalize_pk_list(args.user_group)
    if getattr(args, "no_account", False):
        _validate_no_account_cli(args)
        payload["accounts"] = _normalize_accounts(getattr(args, "account", None))
    elif getattr(args, "account", None):
        payload["accounts"] = _normalize_accounts(args.account)
    if getattr(args, "protocol", None):
        payload["protocols"] = _normalize_protocols(args.protocol)
    if getattr(args, "action", None):
        payload["actions"] = _normalize_actions(args.action)
    if has_cli_value(args.is_active):
        payload["is_active"] = parse_bool(args.is_active)
    if has_cli_value(args.date_start):
        payload["date_start"] = args.date_start
    if has_cli_value(args.date_expired):
        payload["date_expired"] = args.date_expired
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    _reject_unknown_fields(payload)

    if "assets" in payload:
        payload["assets"] = _normalize_identifier_list(payload.get("assets"))
    if "nodes" in payload:
        payload["nodes"] = _normalize_pk_list(payload.get("nodes"))
    if "users" in payload:
        payload["users"] = _normalize_pk_list(payload.get("users"))
    if "user_groups" in payload:
        payload["user_groups"] = _normalize_pk_list(payload.get("user_groups"))
    if "accounts" in payload:
        payload["accounts"] = _normalize_accounts(payload.get("accounts"))
    else:
        payload["accounts"] = ["@ALL"]
    if "protocols" in payload:
        payload["protocols"] = _normalize_protocols(payload.get("protocols"))
    else:
        payload["protocols"] = ["all"]
    if "actions" in payload:
        payload["actions"] = _normalize_actions(payload.get("actions"))
    else:
        payload["actions"] = list(DEFAULT_ACTIONS)
    if "is_active" in payload:
        payload["is_active"] = parse_bool(payload.get("is_active"))

    return {
        key: value
        for key, value in payload.items()
        if key in CREATE_ASSET_PERMISSION_FIELDS
        and value is not None
        and not (isinstance(value, str) and value == "")
    }


def _validate_accounts(accounts: Any) -> None:
    if not isinstance(accounts, list):
        _raise_invalid_accounts("`accounts` 必须是列表。", accounts=_as_list(accounts))
    normalized = [_text(item) for item in accounts if has_cli_value(item)]
    if len(normalized) != len(accounts):
        _raise_invalid_accounts("`accounts` 不能包含空值。", accounts=normalized)

    all_mode = "@ALL" in normalized
    spec_mode = "@SPEC" in normalized
    exclude_values = [item for item in normalized if item.startswith("!")]
    unknown_markers = [
        item
        for item in normalized
        if item.startswith("@") and item not in BASE_ACCOUNT_MARKERS and item not in VIRTUAL_ACCOUNTS
    ]
    if unknown_markers:
        _raise_invalid_accounts("`accounts` 包含不支持的账号标记：%s。" % ", ".join(unknown_markers), accounts=normalized)

    plain_names = [
        item
        for item in normalized
        if item
        and item not in BASE_ACCOUNT_MARKERS
        and item not in VIRTUAL_ACCOUNTS
        and not item.startswith("!")
    ]
    base_mode_count = sum([1 if all_mode else 0, 1 if spec_mode else 0, 1 if exclude_values else 0])
    if base_mode_count > 1:
        _raise_invalid_accounts("所有账号、指定账号、排除账号三种基础账号模式不能混用。", accounts=normalized)
    if all_mode and plain_names:
        _raise_invalid_accounts("`@ALL` 不能与具体账号名混用。", accounts=normalized)
    if spec_mode:
        if not plain_names:
            _raise_invalid_accounts("`@SPEC` 后必须至少包含一个账号名。", accounts=normalized)
        return
    if exclude_values:
        invalid_excludes = [item for item in exclude_values if not _text(item[1:])]
        if invalid_excludes:
            _raise_invalid_accounts("排除账号必须写成 `!账号名`。", accounts=normalized)
        if plain_names:
            _raise_invalid_accounts("排除账号模式不能与普通账号名混用。", accounts=normalized)
        return
    if plain_names:
        _raise_invalid_accounts("指定具体账号名前必须先传 `@SPEC`。", accounts=normalized)


def _validate_protocols(protocols: Any) -> None:
    if not isinstance(protocols, list) or not protocols:
        raise CLIError(
            "资产授权协议不合法。",
            payload=build_cli_guidance_payload(
                "invalid_asset_permission_protocols",
                user_message="`protocols` 必须是非空列表；默认使用 [\"all\"]。",
                action_hint="移除空协议，或传 `--protocol all` 表示所有协议。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                protocols=protocols,
            ),
        )
    if "all" in protocols and len(protocols) > 1:
        raise CLIError(
            "资产授权协议不合法。",
            payload=build_cli_guidance_payload(
                "invalid_asset_permission_protocols",
                user_message="`all` 表示所有协议，不能与其他协议混用。",
                action_hint="只保留 `all`，或改成具体协议列表。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                protocols=protocols,
            ),
        )


def _validate_actions(actions: Any) -> None:
    if not isinstance(actions, list) or not actions:
        raise CLIError(
            "资产授权动作不合法。",
            payload=build_cli_guidance_payload(
                "invalid_asset_permission_actions",
                user_message="`actions` 必须是非空列表。",
                action_hint="请传入 connect/upload/download/copy/paste/delete/share 中的一个或多个。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                actions=actions,
                allowed_actions=list(DEFAULT_ACTIONS),
            ),
        )
    invalid = [item for item in actions if item not in ACTION_LABELS]
    if invalid:
        raise CLIError(
            "资产授权动作不支持。",
            payload=build_cli_guidance_payload(
                "invalid_asset_permission_actions",
                user_message="`actions` 只允许 connect/upload/download/copy/paste/delete/share。",
                action_hint="请改成受支持的 action value 后重试。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                actions=actions,
                invalid_actions=invalid,
                allowed_actions=list(DEFAULT_ACTIONS),
            ),
        )


def _validate_asset_permission_payload(payload: dict[str, Any]) -> None:
    missing = []
    if not _text(payload.get("name")):
        missing.append("name")
    if not isinstance(payload.get("assets"), list) and not isinstance(payload.get("nodes"), list):
        missing.append("assets_or_nodes")
    elif not (payload.get("assets") or payload.get("nodes")):
        missing.append("assets_or_nodes")
    if not isinstance(payload.get("users"), list) and not isinstance(payload.get("user_groups"), list):
        missing.append("users_or_user_groups")
    elif not (payload.get("users") or payload.get("user_groups")):
        missing.append("users_or_user_groups")
    if "accounts" not in payload or not isinstance(payload.get("accounts"), list):
        missing.append("accounts")
    if not isinstance(payload.get("protocols"), list) or not payload.get("protocols"):
        missing.append("protocols")
    if not isinstance(payload.get("actions"), list) or not payload.get("actions"):
        missing.append("actions")
    if missing:
        raise CLIError(
            "创建资产授权规则参数不完整。",
            payload=build_cli_guidance_payload(
                "missing_create_asset_permission_fields",
                user_message="创建资产授权规则缺少必填字段：%s。" % ", ".join(missing),
                action_hint="补齐 --name，并至少指定一个授权对象 assets/nodes 与一个授权主体 users/user_groups。",
                suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                missing_fields=missing,
            ),
        )
    _validate_accounts(payload.get("accounts"))
    _validate_protocols(payload.get("protocols"))
    _validate_actions(payload.get("actions"))


def _raise_global_target_org_error(org_id: str) -> None:
    raise CLIError(
        "目标组织不能是全局组织。",
        payload=build_cli_guidance_payload(
            "organization_not_accessible",
            user_message="创建资产授权规则时，目标组织不能使用全局组织 ID。",
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
                user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定资产授权规则创建组织。",
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
        raise CLIError(
            "组织参数冲突。",
            payload=build_cli_guidance_payload(
                "ambiguous_organization_selector",
                user_message="命令只能传 `--org-id` 或 `--org-name` 其中一个。",
                action_hint="请保留一个组织定位参数后重试。",
                provided=["org_id", "org_name"],
            ),
        )
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
                        "asset_permission_user_not_found",
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
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
                        "asset_permission_user_not_found",
                        user_message="当前组织下找不到用户：%s。" % value,
                        action_hint="请先用 query resolve 确认用户 ID、用户名或姓名后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
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


def _resolve_group_ids(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    groups = [item for item in discovery.list_user_groups() if isinstance(item, dict)]
    resolved_ids = []
    resolved_items = []
    seen = set()
    for value in values:
        if is_uuid_like(value):
            group = _find_item_by_id(groups, value)
            if not group:
                raise CLIError(
                    "无法解析用户组 ID。",
                    payload=build_cli_guidance_payload(
                        "asset_permission_user_group_not_found",
                        user_message="当前组织下找不到用户组：%s。" % value,
                        action_hint="请先用 query resolve 确认用户组 ID 或名称后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                        user_group=value,
                        candidate_user_groups=[_brief_user_group(item) for item in groups[:20]],
                    ),
                )
            group_id = _item_id(group)
        else:
            try:
                resolved = discovery.resolve_group_ids([value])
            except JumpServerAPIError as exc:
                raise CLIError(
                    "无法解析用户组标识。",
                    payload=build_cli_guidance_payload(
                        "asset_permission_user_group_not_found",
                        user_message="当前组织下找不到用户组：%s。" % value,
                        action_hint="请先用 query resolve 确认用户组 ID 或名称后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                        user_group=value,
                        candidate_user_groups=[_brief_user_group(item) for item in groups[:20]],
                    ),
                ) from exc
            group_id = _text((resolved or [""])[0])
            group = _find_item_by_id(groups, group_id) or {"id": group_id}
        if group_id and group_id not in seen:
            seen.add(group_id)
            resolved_ids.append(group_id)
            resolved_items.append(_brief_user_group(group))
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
                        "asset_permission_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
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
                        "asset_permission_asset_not_found",
                        user_message="当前组织下找不到资产：%s。" % value,
                        action_hint="请先用 query resolve 确认资产 ID、名称或地址后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
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


def _resolve_node_ids(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    nodes = [item for item in discovery.list_nodes() if isinstance(item, dict)]
    resolved_ids = []
    resolved_items = []
    seen = set()
    for value in values:
        if is_uuid_like(value):
            node = _find_item_by_id(nodes, value)
            if not node:
                raise CLIError(
                    "无法解析节点 ID。",
                    payload=build_cli_guidance_payload(
                        "asset_permission_node_not_found",
                        user_message="当前组织下找不到节点：%s。" % value,
                        action_hint="请先用 query resolve 确认节点 ID、名称或 full_value 后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                        node=value,
                        candidate_nodes=[_brief_node(item) for item in nodes[:20]],
                    ),
                )
            node_id = _item_id(node)
        else:
            try:
                resolved = discovery.resolve_node_ids([value])
            except JumpServerAPIError as exc:
                raise CLIError(
                    "无法解析节点标识。",
                    payload=build_cli_guidance_payload(
                        "asset_permission_node_not_found",
                        user_message="当前组织下找不到节点：%s。" % value,
                        action_hint="请先用 query resolve 确认节点 ID、名称或 full_value 后重试。",
                        suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                        node=value,
                        candidate_nodes=[_brief_node(item) for item in nodes[:20]],
                    ),
                ) from exc
            node_id = _text((resolved or [""])[0])
            node = _find_item_by_id(nodes, node_id) or {"id": node_id}
        if node_id and node_id not in seen:
            seen.add(node_id)
            resolved_ids.append(node_id)
            resolved_items.append(_brief_node(node))
    return resolved_ids, resolved_items


def _protocol_candidates(discovery) -> list[dict[str, Any]]:
    client = getattr(discovery, "client", None)
    if client is not None and hasattr(client, "list_paginated"):
        records = client.list_paginated(ASSET_PROTOCOLS_PATH, params={"search": "", "offset": 0, "limit": 10})
    else:
        records = discovery.list_protocols()
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _resolve_protocols(discovery, values: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    if values == ["all"]:
        return values, [{"value": "all", "label": "所有协议"}]

    candidates = _protocol_candidates(discovery)
    resolved = []
    resolved_items = []
    seen = set()
    for value in values:
        wanted = _text(value).lower()
        match = None
        for item in candidates:
            item_value = _text(item.get("value") or item.get("name"))
            item_label = _text(item.get("label") or item.get("name") or item.get("value"))
            if wanted in {item_value.lower(), item_label.lower()}:
                match = item
                break
        if not match:
            raise CLIError(
                "无法解析协议。",
                payload=build_cli_guidance_payload(
                    "asset_permission_protocol_not_found",
                    user_message="协议不存在或不可用：%s。" % value,
                    action_hint="请使用协议 value，或按候选协议 label 选择后重试。",
                    suggested_commands=CREATE_ASSET_PERMISSION_EXAMPLES,
                    protocol=value,
                    candidate_protocols=[_brief_protocol(item) for item in candidates[:20]],
                ),
            )
        protocol_value = _text(match.get("value") or match.get("name"))
        if protocol_value and protocol_value not in seen:
            seen.add(protocol_value)
            resolved.append(protocol_value)
            resolved_items.append(_brief_protocol(match))
    return resolved, resolved_items


def _resolved_actions(actions: list[str]) -> list[dict[str, str]]:
    return [{"value": value, "label": ACTION_LABELS[value]} for value in actions if value in ACTION_LABELS]


def _resolve_references(payload: dict[str, Any], *, org_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    discovery = create_discovery(org_id=org_id)
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}

    assets = _normalize_identifier_list(resolved_payload.get("assets"))
    if assets:
        asset_ids, asset_items = _resolve_asset_ids(discovery, assets)
        resolved_payload["assets"] = asset_ids
        resolved_refs["assets"] = asset_items

    nodes = _normalize_identifier_list(resolved_payload.get("nodes"))
    if nodes:
        node_ids, node_items = _resolve_node_ids(discovery, nodes)
        resolved_payload["nodes"] = [{"pk": item_id} for item_id in node_ids]
        resolved_refs["nodes"] = node_items

    users = _normalize_identifier_list(resolved_payload.get("users"))
    if users:
        user_ids, user_items = _resolve_user_ids(discovery, users)
        resolved_payload["users"] = [{"pk": item_id} for item_id in user_ids]
        resolved_refs["users"] = user_items

    user_groups = _normalize_identifier_list(resolved_payload.get("user_groups"))
    if user_groups:
        group_ids, group_items = _resolve_group_ids(discovery, user_groups)
        resolved_payload["user_groups"] = [{"pk": item_id} for item_id in group_ids]
        resolved_refs["user_groups"] = group_items

    protocols, resolved_protocols = _resolve_protocols(discovery, _normalize_protocols(resolved_payload.get("protocols")))
    resolved_payload["protocols"] = protocols
    return resolved_payload, resolved_refs, resolved_protocols, _resolved_actions(_normalize_actions(resolved_payload.get("actions")))


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "asset_count": len(payload.get("assets") or []) if isinstance(payload.get("assets"), list) else 0,
        "node_count": len(payload.get("nodes") or []) if isinstance(payload.get("nodes"), list) else 0,
        "user_count": len(payload.get("users") or []) if isinstance(payload.get("users"), list) else 0,
        "user_group_count": len(payload.get("user_groups") or []) if isinstance(payload.get("user_groups"), list) else 0,
        "account_count": len(payload.get("accounts") or []) if isinstance(payload.get("accounts"), list) else 0,
        "protocols": list(payload.get("protocols") or []) if isinstance(payload.get("protocols"), list) else [],
        "actions": _resolved_actions(_normalize_actions(payload.get("actions"))),
        "is_active_sent": "is_active" in payload,
        "date_start_sent": "date_start" in payload,
        "date_expired_sent": "date_expired" in payload,
        "comment_sent": "comment" in payload,
    }


def _existing_by_name(client, *, name: str) -> list[dict[str, Any]]:
    records = client.list_paginated(CREATE_ASSET_PERMISSION_PATH, params={"search": name})
    if not isinstance(records, list):
        records = []
    wanted_name = _text(name)
    return [
        _brief_asset_permission(item)
        for item in records
        if isinstance(item, dict) and _text(item.get("name")) == wanted_name
    ]


def _create_asset_permission(args: argparse.Namespace):
    payload = _build_asset_permission_payload(args)
    _validate_asset_permission_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_ASSET_PERMISSION_PATH,
            "payload": payload,
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_org_context(args)
    org_id = org_id_from_context(org_context)
    client = create_client(org_id=org_id)
    payload, resolved_references, resolved_protocols, resolved_actions = _resolve_references(payload, org_id=org_id)
    duplicates = _existing_by_name(client, name=str(payload.get("name") or ""))
    if duplicates:
        raise CLIError(
            "资产授权规则已存在。",
            payload=build_cli_guidance_payload(
                "asset_permission_already_exists",
                user_message="目标组织内已存在同名资产授权规则，已阻止创建。",
                action_hint="请改用已有资产授权规则，或换一个名称。",
                duplicate_asset_permissions=duplicates,
            ),
        )

    created = client.post(CREATE_ASSET_PERMISSION_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_ASSET_PERMISSION_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "resolved_protocols": resolved_protocols,
        "resolved_actions": resolved_actions,
        "created_asset_permission": _brief_asset_permission(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建资产授权规则入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ASSET_PERMISSION_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    asset_permission = subparsers.add_parser(
        "create-asset-permission",
        help="创建资产授权规则。",
        description="POST /api/v1/perms/asset-permissions/；无 --confirm 只预览，追加 --confirm 才创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ASSET_PERMISSION_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    asset_permission.add_argument("--payload", help="JSON 对象 payload；显式参数会覆盖同名字段。")
    asset_permission.add_argument("--name")
    asset_permission.add_argument("--asset", "--asset-id", dest="asset", action="append", help="资产 ID、名称或地址；可重复。")
    asset_permission.add_argument("--node", "--node-id", dest="node", action="append", help="节点 ID、名称或 full_value；可重复。")
    asset_permission.add_argument("--user", "--user-id", dest="user", action="append", help="用户 ID、用户名或姓名；可重复。")
    asset_permission.add_argument("--user-group", "--user-group-id", dest="user_group", action="append", help="用户组 ID 或名称；可重复。")
    asset_permission.add_argument("--account", action="append", help="账号值，可重复。支持 @ALL、@SPEC、!name、@INPUT、@USER、@ANON。")
    asset_permission.add_argument("--no-account", dest="no_account", action="store_true", help="基础账号模式为无账号；可与 @INPUT/@USER/@ANON 组合。")
    asset_permission.add_argument("--protocol", action="append", help="协议 value 或 label；可重复。不传默认 all。")
    asset_permission.add_argument("--action", action="append", help="动作 value；可重复。不传默认全部动作。")
    asset_permission.add_argument("--is-active", dest="is_active", help="是否启用：true/false。")
    asset_permission.add_argument("--date-start", dest="date_start", help="生效开始时间。")
    asset_permission.add_argument("--date-expired", dest="date_expired", help="过期时间。")
    asset_permission.add_argument("--comment")
    asset_permission.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    asset_permission.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    asset_permission.add_argument("--confirm", action="store_true")
    add_filter_arguments(asset_permission)
    asset_permission.set_defaults(func=_create_asset_permission)

    return parser


def main() -> int:
    def _run_cli():
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
