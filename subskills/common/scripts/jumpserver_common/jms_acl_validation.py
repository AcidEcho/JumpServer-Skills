from __future__ import annotations

import ipaddress
import re
from typing import Any

from .jms_runtime import CLIError, build_cli_guidance_payload, has_cli_value


RULE_FIELDS = frozenset({"ip_group", "time_period"})
WEEKDAY_IDS = frozenset({0, 1, 2, 3, 4, 5, 6})
TIME_PERIOD_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d~(?:[01]\d|2[0-3]):[0-5]\d$")

TEXT_MATCHES = frozenset({"exact", "not", "endswith", "in", "startswith", "regex"})
BOOL_MATCHES = frozenset({"exact", "not"})
M2M_MATCHES = frozenset({"m2m", "m2m_all"})

USER_ATTR_TEXT_FIELDS = frozenset({"name", "username", "email", "comment"})
USER_ATTR_BOOL_FIELDS = frozenset({"is_active", "is_first_login"})
USER_ATTR_ROLE_M2M_FIELDS = frozenset({"org_roles", "system_roles"})
USER_ATTR_EXTENDED_M2M_FIELDS = frozenset({"org_roles", "system_roles", "groups", "labels"})
USER_ATTR_CONNECT_METHOD_M2M_FIELDS = frozenset({"system_roles", "groups", "labels"})

ASSET_ATTR_TEXT_FIELDS = frozenset({"name", "address", "comment"})
ASSET_ATTR_M2M_FIELDS = frozenset({"nodes", "platform", "labels"})
ASSET_ATTR_EXACT_FIELDS = frozenset({"category", "type", "protocols"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _raise_validation_error(
    reason_code: str,
    message: str,
    *,
    examples: list[str],
    action_hint: str,
    **details: Any,
) -> None:
    raise CLIError(
        "ACL 参数不合法。",
        payload=build_cli_guidance_payload(
            reason_code,
            user_message=message,
            action_hint=action_hint,
            suggested_commands=examples,
            **details,
        ),
    )


def validate_acl_accounts(
    accounts: Any,
    *,
    reason_code: str,
    examples: list[str],
    resource_label: str,
) -> None:
    if not isinstance(accounts, list):
        _raise_validation_error(
            reason_code,
            "`accounts` 必须是列表；只允许 [\"@ALL\"] 或 [\"@SPEC\", \"account\"]。",
            examples=examples,
            action_hint="请按 API.md 中 %s 的 accounts 规则修正后重试。" % resource_label,
            accounts=accounts,
        )
    normalized = [_text(item) for item in accounts if has_cli_value(item)]
    if len(normalized) != len(accounts) or not normalized:
        _raise_validation_error(
            reason_code,
            "`accounts` 不能为空，且不能包含空值。",
            examples=examples,
            action_hint="请使用 [\"@ALL\"]，或使用 [\"@SPEC\", \"账号名\"]。",
            accounts=accounts,
        )
    unknown_markers = [item for item in normalized if item.startswith("@") and item not in {"@ALL", "@SPEC"}]
    if unknown_markers:
        _raise_validation_error(
            reason_code,
            "`accounts` 包含不支持的账号标记：%s。" % ", ".join(unknown_markers),
            examples=examples,
            action_hint="%s 只支持 @ALL 或 @SPEC 账号模式。" % resource_label,
            accounts=normalized,
            invalid_markers=unknown_markers,
        )
    if "@ALL" in normalized:
        if normalized != ["@ALL"]:
            _raise_validation_error(
                reason_code,
                "`@ALL` 不能与其他账号值混用。",
                examples=examples,
                action_hint="所有账号请只传 [\"@ALL\"]；指定账号请改用 [\"@SPEC\", \"账号名\"]。",
                accounts=normalized,
            )
        return
    if normalized[0] != "@SPEC":
        _raise_validation_error(
            reason_code,
            "指定账号时，`accounts` 必须以 `@SPEC` 开头。",
            examples=examples,
            action_hint="请改成 [\"@SPEC\", \"账号名\"]。",
            accounts=normalized,
        )
    account_names = normalized[1:]
    if not account_names or any(item.startswith("@") for item in account_names) or any(item.startswith("!") for item in account_names):
        _raise_validation_error(
            reason_code,
            "`@SPEC` 后必须跟一个或多个普通账号名。",
            examples=examples,
            action_hint="请在 @SPEC 后补充账号名；不要传虚拟账号、排除账号或其他 @ 标记。",
            accounts=normalized,
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


def validate_acl_rules(
    rules: Any,
    *,
    reason_prefix: str,
    examples: list[str],
    resource_label: str,
) -> None:
    if not isinstance(rules, dict):
        _raise_validation_error(
            "invalid_%s_rules" % reason_prefix,
            "`rules` 必须是对象，只允许字段 ip_group/time_period。",
            examples=examples,
            action_hint="请按 API.md 中 %s 的 rules 结构修正后重试。" % resource_label,
            rules=rules,
            allowed_fields=sorted(RULE_FIELDS),
        )
    unknown_fields = sorted(set(rules) - RULE_FIELDS)
    if unknown_fields:
        _raise_validation_error(
            "invalid_%s_rules" % reason_prefix,
            "`rules` 只允许字段：ip_group, time_period。",
            examples=examples,
            action_hint="移除 rules 中不支持的字段后重试。",
            invalid_fields=["rules.%s" % item for item in unknown_fields],
            allowed_fields=sorted(RULE_FIELDS),
        )
    if "ip_group" in rules:
        ip_group = rules.get("ip_group")
        if not isinstance(ip_group, list) or not ip_group:
            _raise_validation_error(
                "invalid_%s_ip_group" % reason_prefix,
                "`rules.ip_group` 必须是非空列表。",
                examples=examples,
                action_hint="请传入 *、单 IP、CIDR 或 IP 范围。",
                ip_group=ip_group,
            )
        invalid_items = [item for item in ip_group if not _valid_ip_group_item(item)]
        if invalid_items:
            _raise_validation_error(
                "invalid_%s_ip_group" % reason_prefix,
                "`rules.ip_group` 只允许 *、单 IP、CIDR 或同版本 IP 范围。",
                examples=examples,
                action_hint="请修正非法 IP 条件后重试。",
                invalid_ip_group_items=invalid_items,
            )
    if "time_period" in rules:
        periods = rules.get("time_period")
        if not isinstance(periods, list) or not periods:
            _raise_validation_error(
                "invalid_%s_time_period" % reason_prefix,
                "`rules.time_period` 必须是非空列表。",
                examples=examples,
                action_hint="请传入 {id,value}，例如 {\"id\":1,\"value\":\"08:00~18:00\"}。",
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
            _raise_validation_error(
                "invalid_%s_time_period" % reason_prefix,
                "`rules.time_period` 需要 {id,value}，id 只能是 0-6 且不能重复，value 格式为 HH:MM~HH:MM。",
                examples=examples,
                action_hint="请修正非法时间段后重试。",
                invalid_time_periods=invalid_periods,
            )


def _attr_value_is_scalar(value: Any) -> bool:
    return has_cli_value(value) and not isinstance(value, (list, dict))


def _attr_value_is_nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(has_cli_value(item) for item in value)


def validate_selector_attrs(
    selector: Any,
    *,
    attr_scope: str,
    reason_prefix: str,
    examples: list[str],
    resource_label: str,
    text_fields: frozenset[str],
    bool_fields: frozenset[str] = frozenset(),
    m2m_fields: frozenset[str] = frozenset(),
    exact_fields: frozenset[str] = frozenset(),
) -> None:
    if not isinstance(selector, dict) or _text(selector.get("type")) != "attrs":
        return
    attrs = selector.get("attrs")
    reason_code = "invalid_%s_%s_attrs" % (reason_prefix, attr_scope)
    if not isinstance(attrs, list) or not attrs:
        _raise_validation_error(
            reason_code,
            "`%s.attrs` 必须是非空数组。" % attr_scope,
            examples=examples,
            action_hint="请按 API.md 中 %s 的 %s.attrs 字段矩阵修正后重试。" % (resource_label, attr_scope),
            attr_scope=attr_scope,
            attrs=attrs,
        )
    allowed_fields = text_fields | bool_fields | m2m_fields | exact_fields
    for index, attr in enumerate(attrs):
        if not isinstance(attr, dict):
            _raise_validation_error(
                reason_code,
                "`%s.attrs[%s]` 必须是对象。" % (attr_scope, index),
                examples=examples,
                action_hint="请将 attrs 中每一项改成包含 name/match/value 的对象。",
                attr_index=index,
                attr=attr,
            )
        field = _text(attr.get("name"))
        match = _text(attr.get("match"))
        if not field or not match or "value" not in attr:
            _raise_validation_error(
                reason_code,
                "`%s.attrs[%s]` 必须包含 name、match、value。" % (attr_scope, index),
                examples=examples,
                action_hint="请补齐属性筛选条件后重试。",
                attr_index=index,
                attr=attr,
            )
        value = attr.get("value")
        if field in text_fields:
            allowed_matches = TEXT_MATCHES
            valid_value = _attr_value_is_nonempty_list(value) if match == "in" else _attr_value_is_scalar(value)
        elif field in bool_fields:
            allowed_matches = BOOL_MATCHES
            valid_value = isinstance(value, bool)
        elif field in m2m_fields:
            allowed_matches = M2M_MATCHES
            valid_value = _attr_value_is_nonempty_list(value)
        elif field in exact_fields:
            allowed_matches = BOOL_MATCHES
            valid_value = _attr_value_is_scalar(value)
        else:
            _raise_validation_error(
                reason_code,
                "`%s.attrs.name` 不支持：%s。" % (attr_scope, field),
                examples=examples,
                action_hint="请使用 API.md 中 %s 支持的 %s.attrs.name。" % (resource_label, attr_scope),
                attr=field,
                allowed_fields=sorted(allowed_fields),
            )
        if match not in allowed_matches:
            _raise_validation_error(
                reason_code,
                "`%s.attrs` 字段 `%s` 不支持 match=%s。" % (attr_scope, field, match),
                examples=examples,
                action_hint="请按字段类型选择受支持的 match。",
                attr=field,
                match=match,
                allowed_matches=sorted(allowed_matches),
            )
        if not valid_value:
            _raise_validation_error(
                reason_code,
                "`%s.attrs` 字段 `%s` 的 value 类型不正确。" % (attr_scope, field),
                examples=examples,
                action_hint="文本字段使用标量或 in 数组；布尔字段使用 true/false；多对多字段使用非空数组。",
                attr=field,
                match=match,
                value=value,
            )
