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

from jms_inspect_core import CAPABILITY_BY_ID, run_capability  # noqa: E402
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIHelpFormatter,
    add_filter_arguments,
    merge_filter_args,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


INSPECT_EXAMPLES = [
    "python3 subskills/query/scripts/jms_inspect.py inspect --capability hot-assets-ranking --days 30 --top 10",
    "python3 subskills/query/scripts/jms_inspect.py inspect --capability system-settings-overview",
]


def _add_time_filter_arguments(parser: argparse.ArgumentParser, *, include_days: bool = True) -> None:
    parser.add_argument("--date-from", dest="date_from")
    parser.add_argument("--date-to", dest="date_to")
    if include_days:
        parser.add_argument("--days", type=int)


def _inspect(args: argparse.Namespace) -> dict[str, Any]:
    filters = merge_filter_args(
        args,
        explicit_fields=(
            "date_from",
            "date_to",
            "days",
            "search",
            "user",
            "user_id",
            "change_by",
            "asset",
            "asset_keywords",
            "status",
            "remote_addr",
            "direction",
            "keyword",
            "protocol",
            "top",
            "category",
            "id",
            "report_type",
        ),
        forbidden_fields=("limit", "offset"),
        usage_examples=INSPECT_EXAMPLES,
    )
    return run_capability(args.capability, filters)


def _capabilities(_: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "id": item.capability_id,
            "name": item.name,
            "category": item.category,
            "priority": item.priority,
            "entrypoint": item.entrypoint,
        }
        for item in sorted(CAPABILITY_BY_ID.values(), key=lambda item: item.capability_id)
        if item.entrypoint.startswith("jms_inspect.py inspect")
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JumpServer 治理巡检查询入口，属于 query 子 skill。", formatter_class=CLIHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="执行治理、排行、巡检 capability。", epilog="Examples:\n  " + "\n  ".join(INSPECT_EXAMPLES), formatter_class=CLIHelpFormatter)
    inspect.add_argument("--capability", required=True)
    _add_time_filter_arguments(inspect)
    inspect.add_argument("--search")
    inspect.add_argument("--user")
    inspect.add_argument("--user-id", dest="user_id")
    inspect.add_argument("--change-by", dest="change_by")
    inspect.add_argument("--asset")
    inspect.add_argument("--asset-keywords", dest="asset_keywords")
    inspect.add_argument("--status")
    inspect.add_argument("--remote-addr", dest="remote_addr")
    inspect.add_argument("--direction")
    inspect.add_argument("--keyword")
    inspect.add_argument("--protocol")
    inspect.add_argument("--top", type=int)
    inspect.add_argument("--category")
    inspect.add_argument("--id")
    inspect.add_argument("--report-type", dest="report_type")
    add_filter_arguments(inspect)
    inspect.set_defaults(func=_inspect)

    capabilities = subparsers.add_parser("capabilities", help="列出 inspect capability。", formatter_class=CLIHelpFormatter)
    capabilities.set_defaults(func=_capabilities)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_inspect.py",
            deprecated_commands={"inspect"},
            usage_examples_by_command={"inspect": INSPECT_EXAMPLES},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
