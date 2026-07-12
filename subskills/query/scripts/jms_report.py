#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from jumpserver_common.jms_bootstrap import ensure_requirements_installed

ensure_requirements_installed()

import argparse

from jms_reporting import (
    build_daily_usage_prepare,
    render_prepared_daily_usage_report,
    validate_report_contract,
)
from jumpserver_common.jms_runtime import (
    CLIHelpFormatter,
    print_json,
    reject_deprecated_pagination_cli_args,
    run_and_print,
)


DAILY_USAGE_EXAMPLES = [
    "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --date 20260310",
    "python3 subskills/query/scripts/jms_report.py daily-usage-prepare --period 上周 --org-name Default",
    "python3 subskills/query/scripts/jms_report.py daily-usage-render --prepared-path reports/prepared/JumpServer-2026-03-10.prepared.json --summary-file /tmp/jms-summary.json",
]


def _daily_usage_prepare(args: argparse.Namespace):
    return build_daily_usage_prepare(
        date_expr=args.date,
        period_expr=args.period,
        date_from_expr=args.date_from,
        date_to_expr=args.date_to,
        org_id=args.org_id,
        org_name=args.org_name,
        command_storage_id=args.command_storage_id,
    )


def _daily_usage_render(args: argparse.Namespace):
    return render_prepared_daily_usage_report(
        prepared_path=args.prepared_path,
        summary_file=args.summary_file,
        cleanup_intermediates=args.cleanup_intermediates,
    )


def _contract_check(_: argparse.Namespace):
    return validate_report_contract()


def _add_time_org_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", help="单天表达，例如 `20260310`、`2026-03-10`、`昨天`。")
    parser.add_argument("--period", help="周期表达，目前支持 `上周`、`本月`。")
    parser.add_argument("--date-from", help="显式开始时间，格式如 `2026-03-10 00:00:00`。")
    parser.add_argument("--date-to", help="显式结束时间，格式如 `2026-03-24 23:59:59`。")
    parser.add_argument("--org-id", help="组织 ID。")
    parser.add_argument("--org-name", help="组织名称。")
    parser.add_argument("--command-storage-id", help="显式指定单个 command storage。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JumpServer 正式报告生成入口。",
        epilog=(
            "时间参数规则:\n"
            "  1. `--date`、`--period`、`--date-from + --date-to` 三种写法只能选一种\n"
            "  2. 组织优先使用 `--org-name` 或 `--org-id`\n"
            "  3. 正式报告流程是 daily-usage-prepare -> Skill 总结 -> daily-usage-render"
        ),
        formatter_class=CLIHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily_usage_prepare = subparsers.add_parser(
        "daily-usage-prepare",
        help="取数并输出给 Skill 总结使用的 summary_input。",
        description="准备 JumpServer 使用报告数据；不生成最终 HTML。时间参数必须三选一：`--date`、`--period`、或 `--date-from + --date-to`。",
        epilog="Examples:\n  " + "\n  ".join(DAILY_USAGE_EXAMPLES[:2]),
        formatter_class=CLIHelpFormatter,
    )
    _add_time_org_arguments(daily_usage_prepare)
    daily_usage_prepare.set_defaults(func=_daily_usage_prepare)

    daily_usage_render = subparsers.add_parser(
        "daily-usage-render",
        help="使用 Skill 摘要 JSON 渲染最终 HTML 报告。",
        description="读取 daily-usage-prepare 工件和 Skill 摘要 JSON，生成最终 JumpServer 使用报告。",
        formatter_class=CLIHelpFormatter,
    )
    daily_usage_render.add_argument("--prepared-path", required=True, help="daily-usage-prepare 输出的 prepared_path。")
    daily_usage_render.add_argument("--summary-file", required=True, help="Skill 根据 summary_input 写出的摘要 JSON。")
    daily_usage_render.add_argument(
        "--cleanup-intermediates",
        action="store_true",
        help="成功渲染后清理受控的 prepared 文件和临时 jms-summary*.json；默认保留。",
    )
    daily_usage_render.set_defaults(func=_daily_usage_render)

    contract_check = subparsers.add_parser(
        "contract-check",
        help="校验报告模板契约。",
        description="验证模板与字段元数据的契约是否完整。",
        formatter_class=CLIHelpFormatter,
    )
    contract_check.set_defaults(func=_contract_check)
    return parser


def main() -> int:
    reject_deprecated_pagination_cli_args(
        sys.argv[1:],
        script_name="jms_report.py",
        deprecated_commands={"daily-usage-prepare"},
        usage_examples_by_command={"daily-usage-prepare": DAILY_USAGE_EXAMPLES[:2]},
    )
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "contract-check":
        result = args.func(args)
        print_json(result)
        return 0 if result.get("contract_passed") else 1
    return run_and_print(args.func, args)


if __name__ == "__main__":
    raise SystemExit(main())
