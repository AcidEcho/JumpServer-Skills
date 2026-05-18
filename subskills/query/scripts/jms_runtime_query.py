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

from jms_runtime_queries import (  # noqa: E402
    _normalize_ticket_filters,
    run_capability,
)
from jumpserver_common.jms_runtime import (  # noqa: E402
    CLIHelpFormatter,
    add_filter_arguments,
    ensure_selected_org_context,
    merge_filter_args,
    org_id_from_context,
    reject_deprecated_pagination_cli_args,
    resolve_platform_reference,
    run_and_print,
)


REPORTS_EXAMPLES = [
    "python3 subskills/query/scripts/jms_runtime_query.py reports --report-type account-statistic --days 30",
]


def _add_time_filter_arguments(parser: argparse.ArgumentParser, *, include_days: bool = True) -> None:
    parser.add_argument("--date-from", dest="date_from")
    parser.add_argument("--date-to", dest="date_to")
    if include_days:
        parser.add_argument("--days", type=int)


def _settings_category(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, default={"category": args.category}, explicit_fields=("category", "id"))
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("setting-category-query", filters)


def _license_detail(_: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    return run_capability("license-detail-query", {"_org_id": org_id_from_context(context)})


def _tickets(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = _normalize_ticket_filters(
        merge_filter_args(args, explicit_fields=("search", "applicant_username_name", "state", "type"), forbidden_fields=("limit", "offset"))
    )
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("ticket-list-query", filters)


def _command_storages(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, explicit_fields=("name", "search"), forbidden_fields=("limit", "offset"))
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("command-storage-query", filters)


def _replay_storages(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, explicit_fields=("name", "search"), forbidden_fields=("limit", "offset"))
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("replay-storage-query", filters)


def _terminals(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, explicit_fields=("name", "search"), forbidden_fields=("limit", "offset"))
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("terminal-component-query", filters)


def _reports(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(
        args,
        default={"report_type": args.report_type},
        explicit_fields=(
            "report_type",
            "days",
            "date_from",
            "date_to",
            "top",
            "daily_success_and_failure_metrics",
            "total_long_time_no_login_accounts",
            "total_new_found_accounts",
            "total_groups_changed_accounts",
            "total_sudoers_changed_accounts",
            "total_authorized_keys_changed_accounts",
            "total_account_deleted_accounts",
            "total_password_expired_accounts",
            "total_long_time_password_accounts",
            "total_weak_password_accounts",
            "total_leaked_password_accounts",
            "total_repeated_password_accounts",
        ),
        forbidden_fields=("limit", "offset"),
        usage_examples=REPORTS_EXAMPLES,
    )
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("report-query", filters)


def _account_automations(args: argparse.Namespace) -> dict[str, Any]:
    context = ensure_selected_org_context()
    filters = merge_filter_args(args, explicit_fields=("days", "date_from", "date_to", "top", "search"), forbidden_fields=("limit", "offset"))
    filters["_org_id"] = org_id_from_context(context)
    return run_capability("account-automation-overview", filters)


def _resolve_platform(args: argparse.Namespace) -> dict[str, Any]:
    ensure_selected_org_context()
    return resolve_platform_reference(args.value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JumpServer 运行时只读查询入口，属于 query 子 skill。", formatter_class=CLIHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    settings = subparsers.add_parser("settings-category", help="按分类读取系统设置。", formatter_class=CLIHelpFormatter)
    settings.add_argument("--category", required=True)
    settings.add_argument("--id")
    add_filter_arguments(settings)
    settings.set_defaults(func=_settings_category)

    license_detail = subparsers.add_parser("license-detail", help="查看许可证详情。", formatter_class=CLIHelpFormatter)
    license_detail.set_defaults(func=_license_detail)

    tickets = subparsers.add_parser("tickets", help="查看工单列表。", formatter_class=CLIHelpFormatter)
    tickets.add_argument("--search")
    tickets.add_argument("--applicant", dest="applicant_username_name")
    tickets.add_argument("--state")
    tickets.add_argument("--type")
    add_filter_arguments(tickets)
    tickets.set_defaults(func=_tickets)

    for name, func in (("command-storages", _command_storages), ("replay-storages", _replay_storages), ("terminals", _terminals)):
        sub = subparsers.add_parser(name, help="查看 %s 列表。" % name, formatter_class=CLIHelpFormatter)
        sub.add_argument("--name")
        sub.add_argument("--search")
        add_filter_arguments(sub)
        sub.set_defaults(func=func)

    reports = subparsers.add_parser("reports", help="读取系统报表与 dashboard。", epilog="Examples:\n  " + "\n  ".join(REPORTS_EXAMPLES), formatter_class=CLIHelpFormatter)
    reports.add_argument("--report-type", required=True, choices=["account-statistic", "account-automation", "asset-statistic", "asset-activity", "users", "user-change-password", "pam-dashboard", "change-secret-dashboard"])
    _add_time_filter_arguments(reports)
    reports.add_argument("--top", type=int)
    for name in (
        "daily_success_and_failure_metrics",
        "total_long_time_no_login_accounts",
        "total_new_found_accounts",
        "total_groups_changed_accounts",
        "total_sudoers_changed_accounts",
        "total_authorized_keys_changed_accounts",
        "total_account_deleted_accounts",
        "total_password_expired_accounts",
        "total_long_time_password_accounts",
        "total_weak_password_accounts",
        "total_leaked_password_accounts",
        "total_repeated_password_accounts",
    ):
        reports.add_argument("--" + name.replace("_", "-"), dest=name, action="store_const", const=1, default=None)
    add_filter_arguments(reports)
    reports.set_defaults(func=_reports)

    automations = subparsers.add_parser("account-automations", help="查看账号自动化与风险概览。", formatter_class=CLIHelpFormatter)
    _add_time_filter_arguments(automations)
    automations.add_argument("--search")
    automations.add_argument("--top", type=int)
    add_filter_arguments(automations)
    automations.set_defaults(func=_account_automations)

    platform = subparsers.add_parser("resolve-platform", help="解析平台名称或分类。", formatter_class=CLIHelpFormatter)
    platform.add_argument("--value", required=True)
    platform.set_defaults(func=_resolve_platform)
    return parser


def main() -> int:
    def _run_cli():
        reject_deprecated_pagination_cli_args(
            sys.argv[1:],
            script_name="jms_runtime_query.py",
            deprecated_commands={"tickets", "command-storages", "replay-storages", "terminals", "reports", "account-automations"},
            usage_examples_by_command={"reports": REPORTS_EXAMPLES},
        )
        args = build_parser().parse_args(sys.argv[1:])
        return args.func(args)

    return run_and_print(_run_cli)


if __name__ == "__main__":
    raise SystemExit(main())
