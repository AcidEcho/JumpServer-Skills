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

from jumpserver_common.jms_runtime import (
    CLIError,
    CLIHelpFormatter,
    add_filter_arguments,
    create_client,
    create_discovery,
    merge_filter_args,
    org_id_from_context,
    org_context_output,
    reject_deprecated_pagination_cli_args,
    resolve_command_org_context,
    run_and_print,
)


ASSET_PATH = "/api/v1/assets/assets/"
NODE_PATH = "/api/v1/assets/nodes/"
PLATFORM_PATH = "/api/v1/assets/platforms/"
ACCOUNT_PATH = "/api/v1/accounts/accounts/"
ACCOUNT_TEMPLATE_PATH = "/api/v1/accounts/account-templates/"
USER_PATH = "/api/v1/users/users/"
GROUP_PATH = "/api/v1/users/groups/"
ORG_PATH = "/api/v1/orgs/orgs/"
LABEL_PATH = "/api/v1/labels/labels/"
ZONE_PATH = "/api/v1/assets/zones/"

ASSET_KIND_PATHS = {
    "": ASSET_PATH,
    "generic": ASSET_PATH,
    "host": "/api/v1/assets/hosts/",
    "database": "/api/v1/assets/databases/",
    "device": "/api/v1/assets/devices/",
    "cloud": "/api/v1/assets/clouds/",
    "web": "/api/v1/assets/webs/",
    "website": "/api/v1/assets/webs/",
    "custom": "/api/v1/assets/customs/",
    "customs": "/api/v1/assets/customs/",
    "directory": "/api/v1/assets/directories/",
    "directories": "/api/v1/assets/directories/",
}

OBJECT_RESOURCE_PATHS = {
    "node": NODE_PATH,
    "platform": PLATFORM_PATH,
    "account": ACCOUNT_PATH,
    "account-template": ACCOUNT_TEMPLATE_PATH,
    "user": USER_PATH,
    "user-group": GROUP_PATH,
    "organization": ORG_PATH,
    "label": LABEL_PATH,
    "zone": ZONE_PATH,
}

LOCAL_MATCH_FIELDS = {
    "asset": ("id", "name", "address"),
    "node": ("id", "name", "value", "full_value"),
    "platform": ("id", "name"),
    "account": ("id", "name", "username"),
    "account-template": ("id", "name"),
    "user": ("id", "name", "username", "email"),
    "user-group": ("id", "name"),
    "organization": ("id", "name"),
    "label": ("id", "name"),
    "zone": ("id", "name"),
}

OBJECT_LIST_EXAMPLES = [
    "python3 subskills/query/scripts/jms_query.py object-list --resource organization --name Default",
    "python3 subskills/query/scripts/jms_query.py object-list --resource asset --kind host --search prod",
]
RESOLVE_EXAMPLES = [
    "python3 subskills/query/scripts/jms_query.py resolve --resource organization --name Default",
    "python3 subskills/query/scripts/jms_query.py resolve --resource user --name example.user",
]


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _value_from_path(item: dict[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _exact_first_filter(items: list[dict[str, Any]], expected: Any, *paths: str) -> list[dict[str, Any]]:
    wanted = _lower(expected)
    if not wanted:
        return items
    exact_matches = []
    partial_matches = []
    for item in items:
        values = [_value_from_path(item, path) for path in paths]
        text_values = [_lower(value) for value in values if value not in {None, ""}]
        if wanted in text_values:
            exact_matches.append(item)
        elif any(wanted in value for value in text_values):
            partial_matches.append(item)
    return exact_matches or partial_matches


def _asset_list_path(kind: str | None) -> str:
    kind_value = str(kind or "").strip().lower()
    if kind_value not in ASSET_KIND_PATHS:
        raise CLIError("Unsupported asset kind: %s" % kind)
    return ASSET_KIND_PATHS[kind_value]


def _object_list_path(resource: str, kind: str | None) -> str:
    if resource == "asset":
        return _asset_list_path(kind)
    if kind:
        raise CLIError("--kind is only supported when --resource asset.")
    return OBJECT_RESOURCE_PATHS[resource]


def _object_get_path(resource: str) -> str:
    if resource == "asset":
        return ASSET_PATH
    return OBJECT_RESOURCE_PATHS[resource]


def _without_pagination(filters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(filters)
    payload.pop("limit", None)
    payload.pop("offset", None)
    return payload


def _candidate_brief(resource: str, item: dict[str, Any]) -> dict[str, Any]:
    if resource == "asset":
        platform = item.get("platform")
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "address": item.get("address"),
            "platform": platform.get("name") if isinstance(platform, dict) else platform,
            "nodes_display": item.get("nodes_display"),
        }
    if resource == "node":
        return {
            "id": item.get("id"),
            "name": item.get("name") or item.get("value"),
            "full_value": item.get("full_value"),
            "org_name": item.get("org_name"),
        }
    return {"id": item.get("id"), "name": item.get("name")}


def _ambiguity_hint(resource: str, matched_fields: list[str]) -> str | None:
    if resource == "asset" and "address" in matched_fields:
        return "Address 可能对应多个资产，请改用 id、name 或 platform 继续确认。"
    if resource == "node" and "full_value" in matched_fields:
        return "full_value 应唯一命中；若仍多条，请改用 id。"
    if matched_fields:
        return "当前条件仍命中多个对象，请改用 id 或更精确字段继续缩小范围。"
    return None


def _apply_local_exact_filters(
    client,
    *,
    path: str,
    resource: str,
    filters: dict[str, Any],
    records: Any,
) -> tuple[Any, str, list[str]]:
    if not isinstance(records, list):
        return records, "server", []
    current = [item for item in records if isinstance(item, dict)]
    match_strategy = "server"
    matched_fields = []
    for field in LOCAL_MATCH_FIELDS.get(resource, ()):
        value = filters.get(field)
        if value in {None, ""}:
            continue
        matched_fields.append(field)
        narrowed = _exact_first_filter(current, value, field)
        if narrowed:
            if narrowed != current:
                match_strategy = "local_exact_first"
            current = narrowed
            continue
        broader_filters = _without_pagination(filters)
        broader_filters.pop(field, None)
        broader = client.list_paginated(path, params=broader_filters)
        broader_records = [item for item in broader if isinstance(item, dict)] if isinstance(broader, list) else []
        current = _exact_first_filter(broader_records, value, field)
        match_strategy = "local_exact_first_broad_fetch"
    return current, match_strategy, matched_fields


def _object_list(args: argparse.Namespace) -> dict[str, Any]:
    context = resolve_command_org_context(args)
    client = create_client(org_id=org_id_from_context(context))
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search"),
        forbidden_fields=("limit", "offset"),
        usage_examples=OBJECT_LIST_EXAMPLES,
    )
    path = _object_list_path(args.resource, args.kind)
    records = client.list_paginated(path, params=filters)
    records, match_strategy, matched_fields = _apply_local_exact_filters(
        client,
        path=path,
        resource=args.resource,
        filters=filters,
        records=records,
    )
    ambiguous = isinstance(records, list) and bool(matched_fields) and len(records) > 1
    return {
        "resource": args.resource,
        "kind": args.kind if args.resource == "asset" else None,
        "match_strategy": match_strategy,
        "summary": {
            "total": len(records) if isinstance(records, list) else None,
            "filters": filters,
            "matched_fields": matched_fields,
            "ambiguous": ambiguous,
            "ambiguity_hint": _ambiguity_hint(args.resource, matched_fields) if ambiguous else None,
            "candidates": [_candidate_brief(args.resource, item) for item in records[:10]] if ambiguous else [],
        },
        "records": records,
        **org_context_output(context),
    }


def _object_get(args: argparse.Namespace) -> dict[str, Any]:
    context = resolve_command_org_context(args)
    client = create_client(org_id=org_id_from_context(context))
    record = client.get("%s%s/" % (_object_get_path(args.resource), args.id))
    return {
        "resource": args.resource,
        "record": record,
        **org_context_output(context),
    }


def _resolve(args: argparse.Namespace) -> dict[str, Any]:
    context = resolve_command_org_context(args)
    org_id = org_id_from_context(context)
    client = create_client(org_id=org_id)
    discovery = create_discovery(org_id=org_id)
    filters = merge_filter_args(
        args,
        explicit_fields=("name", "search"),
        forbidden_fields=("limit", "offset"),
        usage_examples=RESOLVE_EXAMPLES,
    )
    if args.resource == "asset":
        items = discovery.list_assets()
        field_names = ("id", "name", "address")
    elif args.resource == "node":
        items = discovery.list_nodes()
        field_names = ("id", "name", "value", "full_value")
    elif args.resource == "user":
        items = discovery.list_users()
        field_names = ("id", "name", "username", "email")
    elif args.resource == "user-group":
        items = discovery.list_user_groups()
        field_names = ("id", "name")
    elif args.resource == "organization":
        items = client.list_paginated("/api/v1/orgs/orgs/")
        field_names = ("id", "name")
    elif args.resource == "account":
        items = client.list_paginated("/api/v1/accounts/accounts/")
        field_names = ("id", "name", "username")
    elif args.resource == "platform":
        items = [item.to_dict() for item in discovery.list_platforms()]
        field_names = ("id", "name", "slug", "category")
    elif args.resource == "permission":
        items = client.list_paginated("/api/v1/perms/asset-permissions/")
        field_names = ("id", "name")
    else:
        raise CLIError("Unsupported resolve resource: %s" % args.resource)

    if args.id:
        matches = [item for item in items if str(item.get("id")) == args.id]
    else:
        wanted = str(args.name or filters.get("name") or "").strip()
        matches = _exact_first_filter([item for item in items if isinstance(item, dict)], wanted, *field_names)
    return {"resource": args.resource, "matches": matches, **org_context_output(context)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 对象查询入口。",
        epilog=(
            "推荐路径:\n"
            "  1. 查清单用 object-list --resource <resource>\n"
            "  2. 查详情用 object-get --resource <resource> --id <id>\n"
            "  3. 高级补充筛选使用重复的 --filter key=value"
        ),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    object_resources = sorted({"asset", *OBJECT_RESOURCE_PATHS})

    object_list = subparsers.add_parser(
        "object-list",
        help="按资源类型列出对象。",
        description="列出资产、节点、平台、账号、用户、组织等对象。",
        epilog="Examples:\n  " + "\n  ".join(OBJECT_LIST_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    object_list.add_argument("--resource", required=True, choices=object_resources)
    object_list.add_argument("--kind", help="仅当 --resource asset 时可选，用于限定资产子类型。")
    object_list.add_argument("--name", help="按名称精确优先匹配。")
    object_list.add_argument("--search", help="服务端搜索关键字。")
    object_list.add_argument("--org-id", dest="org_id", help="组织 ID；只限定本次命令，不写 .env。")
    object_list.add_argument("--org-name", dest="org_name", help="组织名称；只限定本次命令，不写 .env。")
    add_filter_arguments(object_list)
    object_list.set_defaults(func=_object_list)

    object_get = subparsers.add_parser(
        "object-get",
        help="按 ID 读取单个对象详情。",
        description="按资源类型和 ID 读取单个对象详情。",
        formatter_class=CLIHelpFormatter,
    )
    object_get.add_argument("--resource", required=True, choices=object_resources)
    object_get.add_argument("--id", required=True)
    object_get.add_argument("--org-id", dest="org_id", help="组织 ID；只限定本次命令，不写 .env。")
    object_get.add_argument("--org-name", dest="org_name", help="组织名称；只限定本次命令，不写 .env。")
    object_get.set_defaults(func=_object_get)

    resolve = subparsers.add_parser(
        "resolve",
        help="解析对象名称、用户名或 ID。",
        description="按对象类型解析名称、用户名、地址、邮箱或 ID，返回候选匹配。",
        epilog="Examples:\n  " + "\n  ".join(RESOLVE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    resolve.add_argument(
        "--resource",
        required=True,
        choices=["asset", "node", "user", "user-group", "organization", "account", "platform", "permission"],
    )
    resolve.add_argument("--id")
    resolve.add_argument("--name")
    resolve.add_argument("--search")
    resolve.add_argument("--org-id", dest="org_id", help="组织 ID；只限定本次命令，不写 .env。")
    resolve.add_argument("--org-name", dest="org_name", help="组织名称；只限定本次命令，不写 .env。")
    add_filter_arguments(resolve)
    resolve.set_defaults(func=_resolve)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_query.py",
            deprecated_commands={"object-list", "resolve"},
            usage_examples_by_command={"object-list": OBJECT_LIST_EXAMPLES, "resolve": RESOLVE_EXAMPLES},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
