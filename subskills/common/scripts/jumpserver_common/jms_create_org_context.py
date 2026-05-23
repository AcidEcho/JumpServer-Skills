from __future__ import annotations

import argparse
from typing import Any, Callable

from .jms_runtime import CLIError, build_cli_guidance_payload
from .jms_text_utils import lower_text as _lower


ORG_NOT_ACCESSIBLE_REASON_CODE = "organization_not_accessible"
AMBIGUOUS_ORG_REASON_CODE = "ambiguous_organization"
AMBIGUOUS_ORG_SELECTOR_REASON_CODE = "ambiguous_organization_selector"


def _org_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip()


def _explicit_org_context(org_id: str) -> dict[str, Any]:
    effective_org = {"id": org_id, "name": "Unknown", "source": "command_explicit"}
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "当前创建范围固定为组织 ID %s；本次命令直接使用该组织请求头。" % org_id,
    }


def _org_name_preview_context(org_name: str) -> dict[str, Any]:
    return {
        "effective_org": {"id": "", "name": org_name, "source": "command_org_name_preview"},
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览组织名称 %s；追加 --confirm 后才查询组织、写入 .env 并创建。" % org_name,
    }


def _env_org_preview_context(current_runtime_values: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    org_id = str(current_runtime_values().get("JMS_ORG_ID") or "").strip()
    effective_org = {"id": org_id, "name": "Unknown", "source": "env_preview"} if org_id else None
    return {
        "effective_org": effective_org,
        "switchable_orgs": [],
        "switchable_org_count": 0,
        "org_context_hint": "dry-run 仅预览 payload；正式创建时未传组织将使用 .env JMS_ORG_ID。",
    }


def _build_org_context(selected_org: dict[str, Any], accessible_orgs: list[dict[str, Any]]) -> dict[str, Any]:
    effective_org = {**selected_org, "source": "command_explicit"}
    effective_org_id = _org_id(effective_org)
    switchable_orgs = [
        item
        for item in accessible_orgs
        if _org_id(item) and _org_id(item) != effective_org_id
    ]
    org_scope = "%s (%s)" % (
        str(effective_org.get("name") or "").strip() or "Unknown",
        effective_org_id or "<unknown-org-id>",
    )
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
        "org_context_hint": "当前创建范围固定为组织 %s；本次命令按该组织执行。" % org_scope,
    }


def _raise_org_selector_conflict() -> None:
    raise CLIError(
        "组织参数冲突。",
        payload=build_cli_guidance_payload(
            AMBIGUOUS_ORG_SELECTOR_REASON_CODE,
            user_message="创建命令只能传 `--org-id` 或 `--org-name` 其中一个。",
            action_hint="请保留一个组织定位参数后重试。",
            provided=["org_id", "org_name"],
        ),
    )


def _resolve_org_name_context(
    org_name: str,
    *,
    persist: bool,
    list_accessible_orgs: Callable[[], list[dict[str, Any]]],
    persist_selected_org: Callable[[str], Any],
) -> dict[str, Any]:
    accessible_orgs = list_accessible_orgs()
    wanted = _lower(org_name)
    matches = [
        item
        for item in accessible_orgs
        if isinstance(item, dict) and _lower(item.get("name")) == wanted
    ]
    if not matches:
        raise CLIError(
            "指定的组织当前不可访问。",
            payload=build_cli_guidance_payload(
                ORG_NOT_ACCESSIBLE_REASON_CODE,
                user_message="当前账号下找不到你指定的组织，请先从 `candidate_orgs` 里确认可访问组织。",
                action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试；匹配成功后会写入 `.env` 并创建。",
                org_name=org_name,
                candidate_orgs=accessible_orgs,
            ),
        )
    if len(matches) > 1:
        raise CLIError(
            "给定的组织名称匹配到多个候选组织。",
            payload=build_cli_guidance_payload(
                AMBIGUOUS_ORG_REASON_CODE,
                user_message="当前 `--org-name` 命中了多个组织，请改用更精确的名称。",
                action_hint="请从 candidate_orgs 中选择正确组织后，用准确的 `--org-name <selected-name>` 重试；匹配成功后会写入 `.env` 并创建。",
                org_name=org_name,
                candidate_orgs=matches[:10],
            ),
        )
    selected = dict(matches[0])
    selected_org_id = _org_id(selected)
    if persist:
        persist_selected_org(selected_org_id)
    return _build_org_context(selected, accessible_orgs)


def resolve_create_org_context(
    args: argparse.Namespace,
    *,
    persist_org_name: bool = False,
    ensure_selected_org_context: Callable[[], dict[str, Any]],
    list_accessible_orgs: Callable[[], list[dict[str, Any]]],
    persist_selected_org: Callable[[str], Any],
) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        _raise_org_selector_conflict()
    if requested_org_id:
        return _explicit_org_context(requested_org_id)
    if requested_org_name:
        return _resolve_org_name_context(
            requested_org_name,
            persist=persist_org_name,
            list_accessible_orgs=list_accessible_orgs,
            persist_selected_org=persist_selected_org,
        )
    return ensure_selected_org_context()


def preview_create_org_context(
    args: argparse.Namespace,
    *,
    current_runtime_values: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    requested_org_id = str(getattr(args, "org_id", None) or "").strip()
    requested_org_name = str(getattr(args, "org_name", None) or "").strip()
    if requested_org_id and requested_org_name:
        _raise_org_selector_conflict()
    if requested_org_id:
        return _explicit_org_context(requested_org_id)
    if requested_org_name:
        return _org_name_preview_context(requested_org_name)
    return _env_org_preview_context(current_runtime_values)
