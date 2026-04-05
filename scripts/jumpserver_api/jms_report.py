#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jumpserver_api.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

import argparse

from jumpserver_api.jms_reporting import build_daily_usage_report, validate_report_contract
from jumpserver_api.jms_runtime import CLIHelpFormatter, print_json, run_and_print


DAILY_USAGE_EXAMPLES = [
    "python3 scripts/jumpserver_api/jms_report.py daily-usage --date 20260310",
    "python3 scripts/jumpserver_api/jms_report.py daily-usage --period 上周 --org-name Default",
    "python3 scripts/jumpserver_api/jms_report.py daily-usage --date-from '2026-03-10 00:00:00' --date-to '2026-03-24 23:59:59' --org-id 00000000-0000-0000-0000-000000000000",
]


def _daily_usage(args: argparse.Namespace):
    return build_daily_usage_report(
        output_path=args.output,
        date_expr=args.date,
        period_expr=args.period,
        date_from_expr=args.date_from,
        date_to_expr=args.date_to,
        org_id=args.org_id,
        org_name=args.org_name,
        command_storage_id=args.command_storage_id,
    )


def _contract_check(_: argparse.Namespace):
    return validate_report_contract()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 正式报告生成入口。",
        epilog=(
            "时间参数规则:\n"
            "  1. `--date`、`--period`、`--date-from + --date-to` 三种写法只能选一种\n"
            "  2. 组织优先使用 `--org-name` 或 `--org-id`\n"
            "  3. 报告会固定写入 reports/JumpServer-YYYY-MM-DD.html"
        ),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily_usage = subparsers.add_parser(
        "daily-usage",
        help="生成某天或某时间段的使用报告。",
        description="生成 JumpServer 日使用报告；时间参数必须三选一：`--date`、`--period`、或 `--date-from + --date-to`。",
        epilog="Examples:\n  " + "\n  ".join(DAILY_USAGE_EXAMPLES),
        formatter_class=CLIHelpFormatter,
    )
    daily_usage.add_argument("--output", help="deprecated compatibility flag; actual reports are always written to reports/JumpServer-YYYY-MM-DD.html")
    daily_usage.add_argument("--date", help="单天表达，例如 `20260310`、`2026-03-10`、`昨天`。")
    daily_usage.add_argument("--period", help="周期表达，目前支持 `上周`、`本月`。")
    daily_usage.add_argument("--date-from", help="显式开始时间，格式如 `2026-03-10 00:00:00`。")
    daily_usage.add_argument("--date-to", help="显式结束时间，格式如 `2026-03-24 23:59:59`。")
    daily_usage.add_argument("--org-id", help="组织 ID。")
    daily_usage.add_argument("--org-name", help="组织名称。")
    daily_usage.add_argument("--command-storage-id", help="显式指定单个 command storage。")
    daily_usage.set_defaults(func=_daily_usage)

    contract_check = subparsers.add_parser(
        "contract-check",
        help="校验报告模板契约。",
        description="验证模板与字段元数据的契约是否完整。",
        formatter_class=CLIHelpFormatter,
    )
    contract_check.set_defaults(func=_contract_check)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "contract-check":
        result = args.func(args)
        print_json(result)
        return 0 if result.get("contract_passed") else 1
    return run_and_print(args.func, args)


if __name__ == "__main__":
    raise SystemExit(main())
