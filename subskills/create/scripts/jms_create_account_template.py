#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    build_cli_guidance_payload,
    create_env_org_context,
    create_client,
    create_discovery,
    has_cli_value,
    mask_secret,
    org_context_output,
    org_id_from_context,
    preview_create_org_context,
    raise_create_global_org_error,
    resolve_command_org_context,
    run_and_print,
)


CREATE_ACCOUNT_TEMPLATE_PATH = "/api/v1/accounts/account-templates/"
CREATE_ACCOUNT_TEMPLATE_SU_FROM_PATH = "/api/v1/accounts/account-templates/su-from-account-templates/"
CREATE_ACCOUNT_TEMPLATE_FIELDS = frozenset(
    {
        "privileged",
        "secret_type",
        "secret_strategy",
        "password_rules",
        "auto_push",
        "push_params",
        "name",
        "username",
        "su_from",
        "secret",
        "platforms",
        "comment",
    }
)
PASSWORD_RULE_FIELDS = frozenset(
    {
        "length",
        "lowercase",
        "uppercase",
        "digit",
        "symbol",
        "exclude_symbols",
    }
)
SECRET_TYPES = frozenset({"ssh_key", "password", "token", "access_key", "api_key"})
STRATEGY_SECRET_TYPES = frozenset({"password", "ssh_key"})
SECRET_STRATEGIES = frozenset({"random", "specific"})
CREATE_ACCOUNT_TEMPLATE_EXAMPLES = [
    (
        "python3 subskills/create/scripts/jms_create_account_template.py create-account-template "
        "--name root-template --username root --secret-type password --secret-strategy random"
    ),
    (
        "python3 subskills/create/scripts/jms_create_account_template.py create-account-template "
        "--payload '{\"name\":\"root-template\",\"username\":\"root\",\"secret_type\":\"password\","
        "\"secret_strategy\":\"specific\",\"secret\":\"change-me\"}' --confirm"
    ),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool_arg(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _brief_account_template(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "username": item.get("username"),
        "secret_type": item.get("secret_type"),
        "secret_strategy": item.get("secret_strategy"),
        "privileged": item.get("privileged"),
        "auto_push": item.get("auto_push"),
        "platform_count": len(item.get("platforms") or []) if isinstance(item.get("platforms"), list) else None,
        "comment": item.get("comment"),
    }


def _brief_platform(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("pk"),
        "name": item.get("name"),
        "slug": item.get("slug") or item.get("type"),
        "category": item.get("category"),
    }


def _item_id(item: dict[str, Any]) -> Any:
    return item.get("id") or item.get("pk")


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


def _value_matches(candidate: Any, requested: str) -> bool:
    return _text(candidate).lower() == _text(requested).lower()


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
        for field in fields:
            value = item
            for part in field.split("."):
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)
            if _value_matches(value, wanted):
                matches.append(item)
                break
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
                suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
                requested=wanted,
                **{candidate_key: [brief_func(item) for item in matches[:20]]},
            ),
        )
    raise CLIError(
        "对象不存在。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=not_found_message % wanted,
            action_hint="请从候选对象中选择准确 ID、名称或 slug 后重试。",
            suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
            requested=wanted,
            **{candidate_key: [brief_func(item) for item in items[:20]]},
        ),
    )


def _raise_global_target_org_error(org_id: str) -> None:
    raise_create_global_org_error(
        org_id,
        resource_name="创建账号模板",
        user_message="创建账号模板时，目标组织不能使用全局组织 ID。",
    )


def _env_org_context() -> dict[str, Any]:
    return create_env_org_context(
        resource_name="账号模板创建",
        missing_user_message="未传 `--org-id/--org-name`，且 `.env JMS_ORG_ID` 为空，无法确定账号模板创建组织。",
        global_user_message="创建账号模板时，目标组织不能使用全局组织 ID。",
    )


def _preview_org_context(args: argparse.Namespace) -> dict[str, Any]:
    return preview_create_org_context(
        args,
        resource_name="创建账号模板",
        global_user_message="创建账号模板时，目标组织不能使用全局组织 ID。",
    )


def _resolve_account_template_org_context(args: argparse.Namespace) -> dict[str, Any]:
    requested_org_id = _text(getattr(args, "org_id", None))
    requested_org_name = _text(getattr(args, "org_name", None))
    if requested_org_id or requested_org_name:
        return resolve_command_org_context(args, allow_global=False, fallback_to_selected=False)
    return _env_org_context()


def _parse_payload(raw_payload: str | None) -> dict[str, Any]:
    if not has_cli_value(raw_payload):
        return {}
    try:
        payload = json.loads(str(raw_payload))
    except json.JSONDecodeError as exc:
        raise CLIError(
            "无法解析 --payload 参数。",
            payload=build_cli_guidance_payload(
                "invalid_json_payload",
                user_message="`--payload` 需要传入 JSON 对象字符串。",
                action_hint="请检查 JSON 引号、逗号和花括号；不要在错误回显中暴露 secret。",
                suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
                input_name="--payload",
                parser_error=exc.msg,
            ),
        ) from exc
    if not isinstance(payload, dict):
        raise CLIError(
            "--payload 必须是 JSON 对象。",
            payload=build_cli_guidance_payload(
                "invalid_json_payload",
                user_message="`--payload` 需要传入 JSON 对象，而不是数组或普通字符串。",
                action_hint="请改成 `{\"key\": \"value\"}` 这种对象形式。",
                suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
                input_name="--payload",
            ),
        )
    return payload


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None and not (isinstance(value, str) and value == "")
    }


def _parse_platform_pk(value: str) -> Any:
    text = _text(value)
    if text.isdigit():
        return int(text)
    return text


def _build_create_account_template_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _parse_payload(getattr(args, "payload", None))
    unknown_fields = sorted(set(payload) - CREATE_ACCOUNT_TEMPLATE_FIELDS)
    if unknown_fields:
        raise CLIError(
            "创建账号模板 payload 包含不支持字段。",
            payload=build_cli_guidance_payload(
                "invalid_create_account_template_payload_fields",
                user_message="创建账号模板 payload 只允许 API.md 第 17 项列出的字段。",
                action_hint="移除不支持字段后重试。",
                suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
                invalid_fields=unknown_fields,
                allowed_fields=sorted(CREATE_ACCOUNT_TEMPLATE_FIELDS),
            ),
        )

    if has_cli_value(args.name):
        payload["name"] = args.name
    if has_cli_value(args.username):
        payload["username"] = args.username
    if has_cli_value(args.secret_type):
        payload["secret_type"] = args.secret_type
    if has_cli_value(args.secret_strategy):
        payload["secret_strategy"] = args.secret_strategy
    if has_cli_value(args.secret):
        payload["secret"] = args.secret
    if has_cli_value(args.su_from):
        payload["su_from"] = args.su_from
    if has_cli_value(args.comment):
        payload["comment"] = args.comment
    if args.privileged is not None:
        payload["privileged"] = args.privileged
    if args.auto_push is not None:
        payload["auto_push"] = args.auto_push
    platform_refs = [_parse_platform_pk(item) for item in getattr(args, "platform_pk", None) or [] if _text(item)]
    platform_refs.extend(_parse_platform_pk(item) for item in getattr(args, "platform", None) or [] if _text(item))
    if platform_refs:
        payload["platforms"] = [{"pk": item} for item in platform_refs]

    return _clean_payload(payload)


def _validation_error(reason_code: str, message: str, *, missing_fields=None, invalid_fields=None, **details: Any) -> None:
    raise CLIError(
        "创建账号模板参数不合法。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=message,
            action_hint="请按 API.md 第 17 项修正参数后重试。",
            suggested_commands=CREATE_ACCOUNT_TEMPLATE_EXAMPLES,
            missing_fields=missing_fields,
            invalid_fields=invalid_fields,
            **details,
        ),
    )


def _validate_password_rules(payload: dict[str, Any]) -> None:
    rules = payload.get("password_rules")
    if rules is None:
        return
    if not isinstance(rules, dict):
        _validation_error(
            "invalid_account_template_password_rules",
            "`password_rules` 必须是 JSON 对象。",
            invalid_fields=["password_rules"],
        )
    unknown_fields = sorted(set(rules) - PASSWORD_RULE_FIELDS)
    if unknown_fields:
        _validation_error(
            "invalid_account_template_password_rules",
            "`password_rules` 包含不支持字段。",
            invalid_fields=["password_rules.%s" % item for item in unknown_fields],
            allowed_password_rule_fields=sorted(PASSWORD_RULE_FIELDS),
        )
    if "length" in rules and (not isinstance(rules.get("length"), int) or rules.get("length") < 1):
        _validation_error(
            "invalid_account_template_password_rules",
            "`password_rules.length` 必须是大于 0 的整数。",
            invalid_fields=["password_rules.length"],
        )
    for field in ("lowercase", "uppercase", "digit", "symbol"):
        if field in rules and not isinstance(rules.get(field), bool):
            _validation_error(
                "invalid_account_template_password_rules",
                "`password_rules.%s` 必须是布尔值 true/false。" % field,
                invalid_fields=["password_rules.%s" % field],
            )
    if "exclude_symbols" in rules and not isinstance(rules.get("exclude_symbols"), str):
        _validation_error(
            "invalid_account_template_password_rules",
            "`password_rules.exclude_symbols` 必须是字符串。",
            invalid_fields=["password_rules.exclude_symbols"],
        )


def _validate_platforms(payload: dict[str, Any]) -> None:
    platforms = payload.get("platforms")
    if platforms is None:
        return
    if not isinstance(platforms, list):
        _validation_error(
            "invalid_account_template_platforms",
            "`platforms` 必须是数组，例如 `[{\"pk\": 1}]`。",
            invalid_fields=["platforms"],
        )
    invalid_indexes = []
    for index, item in enumerate(platforms):
        if not isinstance(item, dict) or not has_cli_value(item.get("pk")):
            invalid_indexes.append(index)
    if invalid_indexes:
        _validation_error(
            "invalid_account_template_platforms",
            "`platforms` 中每一项都必须是包含 pk 的对象。",
            invalid_fields=["platforms[%s]" % item for item in invalid_indexes],
        )


def _validate_create_account_template_payload(payload: dict[str, Any]) -> None:
    missing = [field for field in ("name", "username", "secret_type") if not _text(payload.get(field))]
    if missing:
        _validation_error(
            "missing_create_account_template_fields",
            "创建账号模板缺少必填字段：%s。" % ", ".join(missing),
            missing_fields=missing,
        )

    secret_type = _text(payload.get("secret_type"))
    if secret_type not in SECRET_TYPES:
        _validation_error(
            "invalid_account_template_secret_type",
            "`secret_type` 必须是 ssh_key/password/token/access_key/api_key 之一。",
            invalid_fields=["secret_type"],
            allowed_values=sorted(SECRET_TYPES),
        )

    secret_strategy = _text(payload.get("secret_strategy"))
    if secret_type in STRATEGY_SECRET_TYPES:
        if not secret_strategy:
            _validation_error(
                "missing_account_template_secret_strategy",
                "`secret_type=%s` 时必须填写 `secret_strategy`。" % secret_type,
                missing_fields=["secret_strategy"],
            )
        if secret_strategy not in SECRET_STRATEGIES:
            _validation_error(
                "invalid_account_template_secret_strategy",
                "`secret_strategy` 必须是 random/specific 之一。",
                invalid_fields=["secret_strategy"],
                allowed_values=sorted(SECRET_STRATEGIES),
            )
        if secret_strategy == "specific" and not has_cli_value(payload.get("secret")):
            _validation_error(
                "missing_account_template_secret",
                "`secret_strategy=specific` 时必须填写 `secret`。",
                missing_fields=["secret"],
            )
    else:
        if not has_cli_value(payload.get("secret")):
            _validation_error(
                "missing_account_template_secret",
                "`secret_type=%s` 时必须填写 `secret`。" % secret_type,
                missing_fields=["secret"],
            )
        if secret_strategy:
            _validation_error(
                "invalid_account_template_secret_strategy",
                "`secret_type=%s` 时不应填写 `secret_strategy`。" % secret_type,
                invalid_fields=["secret_strategy"],
            )
        if "password_rules" in payload:
            _validation_error(
                "invalid_account_template_password_rules",
                "`secret_type=%s` 时不应填写 `password_rules`。" % secret_type,
                invalid_fields=["password_rules"],
            )

    if secret_type == "password":
        _validate_password_rules(payload)
    elif "password_rules" in payload:
        _validation_error(
            "invalid_account_template_password_rules",
            "只有 `secret_type=password` 时才允许填写 `password_rules`。",
            invalid_fields=["password_rules"],
        )

    for field in ("privileged", "auto_push"):
        if field in payload and not isinstance(payload.get(field), bool):
            _validation_error(
                "invalid_account_template_boolean_field",
                "`%s` 必须是布尔值 true/false。" % field,
                invalid_fields=[field],
            )

    if "push_params" in payload and not isinstance(payload.get("push_params"), dict):
        _validation_error(
            "invalid_account_template_push_params",
            "`push_params` 必须是 JSON 对象。",
            invalid_fields=["push_params"],
        )

    _validate_platforms(payload)
    if _bool_arg(payload.get("auto_push")) and not payload.get("platforms"):
        _validation_error(
            "missing_account_template_platforms",
            "`auto_push=true` 时必须填写 `platforms`。",
            missing_fields=["platforms"],
        )


def _mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    masked = dict(payload)
    if "secret" in masked:
        masked["secret"] = mask_secret(masked.get("secret"))
    return masked


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "username": payload.get("username"),
        "secret_type": payload.get("secret_type"),
        "secret_strategy": payload.get("secret_strategy"),
        "privileged": payload.get("privileged"),
        "auto_push": payload.get("auto_push"),
        "platform_count": len(payload.get("platforms") or []),
        "su_from_sent": "su_from" in payload,
        "secret_sent": "secret" in payload,
        "password_rules_sent": "password_rules" in payload,
        "push_params_sent": "push_params" in payload,
        "comment_sent": "comment" in payload,
    }


def _list_su_from_templates(client, requested: str) -> list[dict[str, Any]]:
    records = client.list_paginated(
        CREATE_ACCOUNT_TEMPLATE_SU_FROM_PATH,
        params={"search": requested, "offset": 0, "limit": 10},
    )
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _resolve_su_from(client, requested: Any) -> tuple[Any, dict[str, Any]]:
    value = _text(requested)
    if not value:
        return requested, {}
    items = _list_su_from_templates(client, value)
    item, brief = _find_unique_reference(
        items,
        value,
        fields=("id", "pk", "name", "username"),
        reason_code="account_template_su_from_not_found",
        not_found_message="找不到可作为 su_from 的账号模板：%s。",
        ambiguous_message="su_from `%s` 匹配到多个账号模板。",
        candidate_key="candidate_account_templates",
        brief_func=_brief_account_template,
    )
    return _item_id(item), brief


def _resolve_platforms(payload: dict[str, Any], *, org_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    platforms = payload.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        return [], []
    discovery = create_discovery(org_id=org_id)
    platform_items = [_platform_to_dict(item) for item in discovery.list_platforms()]
    platform_items = [item for item in platform_items if item]
    resolved = []
    resolved_refs = []
    seen = set()
    for item in platforms:
        requested = item.get("pk") if isinstance(item, dict) else item
        platform, brief = _find_unique_reference(
            platform_items,
            requested,
            fields=("id", "pk", "name", "slug", "type.value"),
            reason_code="account_template_platform_not_found",
            not_found_message="找不到平台：%s。",
            ambiguous_message="平台 `%s` 匹配到多个结果。",
            candidate_key="candidate_platforms",
            brief_func=_brief_platform,
        )
        platform_id = _item_id(platform)
        if _text(platform_id) in seen:
            continue
        seen.add(_text(platform_id))
        resolved.append({"pk": platform_id})
        resolved_refs.append(brief)
    return resolved, resolved_refs


def _resolve_account_template_references(
    payload: dict[str, Any],
    *,
    client,
    org_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_payload = dict(payload)
    resolved_refs: dict[str, Any] = {}
    if has_cli_value(resolved_payload.get("su_from")):
        su_from_id, su_from_item = _resolve_su_from(client, resolved_payload.get("su_from"))
        resolved_payload["su_from"] = su_from_id
        resolved_refs["su_from"] = su_from_item
    if isinstance(resolved_payload.get("platforms"), list) and resolved_payload.get("platforms"):
        platforms, platform_items = _resolve_platforms(resolved_payload, org_id=org_id)
        resolved_payload["platforms"] = platforms
        resolved_refs["platforms"] = platform_items
    return resolved_payload, resolved_refs


def _create_account_template(args: argparse.Namespace):
    payload = _build_create_account_template_payload(args)
    _validate_create_account_template_payload(payload)

    if not args.confirm:
        org_context = _preview_org_context(args)
        return {
            "dry_run": True,
            "api_path": CREATE_ACCOUNT_TEMPLATE_PATH,
            "payload": _mask_payload(payload),
            "payload_summary": _payload_summary(payload),
            **org_context_output(org_context),
        }

    org_context = _resolve_account_template_org_context(args)
    target_org_id = org_id_from_context(org_context)
    if target_org_id == GLOBAL_ORG_ID:
        _raise_global_target_org_error(target_org_id)
    client = create_client(org_id=target_org_id)
    payload, resolved_references = _resolve_account_template_references(payload, client=client, org_id=target_org_id)
    created = client.post(CREATE_ACCOUNT_TEMPLATE_PATH, json_body=payload)
    return {
        "dry_run": False,
        "api_path": CREATE_ACCOUNT_TEMPLATE_PATH,
        "payload_summary": _payload_summary(payload),
        "resolved_references": resolved_references,
        "created_account_template": _brief_account_template(created) if isinstance(created, dict) else created,
        **org_context_output(org_context),
    }


def _add_bool_pair(parser: argparse.ArgumentParser, name: str, dest: str, help_text: str) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--%s" % name, dest=dest, action="store_true", default=None, help=help_text)
    group.add_argument("--no-%s" % name, dest=dest, action="store_false", default=None, help="禁用：%s" % help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 创建账号模板入口。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ACCOUNT_TEMPLATE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_template = subparsers.add_parser(
        "create-account-template",
        help="创建账号模板。",
        description="POST /api/v1/accounts/account-templates/；无 --confirm 只预览，追加 --confirm 才解析引用并创建。",
        epilog="Examples:\n  " + "\n  ".join(CREATE_ACCOUNT_TEMPLATE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    create_template.add_argument("--payload", help="JSON 对象 payload；复杂结构优先放这里，显式参数会覆盖同名字段。")
    create_template.add_argument("--name")
    create_template.add_argument("--username")
    create_template.add_argument("--secret-type", dest="secret_type", choices=sorted(SECRET_TYPES))
    create_template.add_argument("--secret-strategy", dest="secret_strategy", choices=sorted(SECRET_STRATEGIES))
    create_template.add_argument("--secret", help="密文；输出中会脱敏。")
    create_template.add_argument("--su-from", dest="su_from", help="切换至账号模板 ID 或名称；--confirm 时解析。")
    create_template.add_argument("--platform", dest="platform", action="append", help="自动推送平台 ID、名称或 slug；可重复。")
    create_template.add_argument("--platform-pk", dest="platform_pk", action="append", help="自动推送平台 pk；可重复。")
    create_template.add_argument("--comment")
    _add_bool_pair(create_template, "privileged", "privileged", "是否为特权账号。")
    _add_bool_pair(create_template, "auto-push", "auto_push", "是否自动推送；为 true 时需要 platforms。")
    create_template.add_argument("--org-id", dest="org_id", help="组织 ID；未传时使用 .env 中的 JMS_ORG_ID。")
    create_template.add_argument("--org-name", dest="org_name", help="组织名称；--confirm 时按名称解析组织。")
    create_template.add_argument("--confirm", action="store_true")
    create_template.set_defaults(func=_create_account_template)
    return parser


def main() -> int:
    def _run_cli():
        parser = build_parser()
        args = parser.parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
