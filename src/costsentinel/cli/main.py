"""CostSentinel CLI - command-line interface for cost governance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from costsentinel.core.config import generate_default_config, load_config
from costsentinel.core.state import CostState
from costsentinel.policies.attribution import AttributionStore
from costsentinel.reporting.reporter import CostReporter


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="costsentinel",
        description="CostSentinel - AI cost governance middleware",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize CostSentinel config")
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing config"
    )

    # report command
    report_parser = subparsers.add_parser("report", help="Generate cost reports")
    report_parser.add_argument(
        "--today", action="store_true", help="Show today's report"
    )
    report_parser.add_argument(
        "--monthly", action="store_true", help="Show monthly report"
    )
    report_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # budget command
    budget_parser = subparsers.add_parser("budget", help="Budget management")
    budget_sub = budget_parser.add_subparsers(dest="budget_action")
    budget_sub.add_parser("status", help="Show budget status")
    reset_parser = budget_sub.add_parser("reset", help="Reset budget counters")
    reset_parser.add_argument("--scope", required=True, help="Scope to reset")
    reset_parser.add_argument("--id", required=True, help="Scope ID to reset")

    # validate command
    subparsers.add_parser("validate", help="Validate configuration file")

    # status command
    subparsers.add_parser("status", help="Show CostSentinel status")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "init":
            return cmd_init(args)
        elif args.command == "report":
            return cmd_report(args)
        elif args.command == "budget":
            return cmd_budget(args)
        elif args.command == "validate":
            return cmd_validate(args)
        elif args.command == "status":
            return cmd_status(args)
        else:
            parser.print_help()
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize CostSentinel configuration."""
    config_path = Path("costsentinel.yaml")

    if config_path.exists() and not args.force:
        print(f"Config file already exists: {config_path}")
        print("Use --force to overwrite.")
        return 1

    config_path.write_text(generate_default_config())
    print(f"Created {config_path}")
    print("Edit the file to configure your project's cost policies.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate and display cost reports."""
    config = load_config()
    reporter = CostReporter(config)

    if args.monthly:
        report = reporter.daily_report()  # Uses current period
        print(reporter.format_report(report, format=args.format))
    else:
        # Default to today's report
        report = reporter.daily_report()
        print(reporter.format_report(report, format=args.format))

    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    """Budget management commands."""
    config = load_config()
    state = CostState(config.state_file)

    if args.budget_action == "status":
        print("Budget Status")
        print("=" * 50)

        for policy in config.policies:
            scope = policy.scope
            totals = state.get_all_totals(scope)

            print(f"\n  [{scope.upper()}]")
            print(f"  Daily limit:   ${policy.limit_daily or 'unlimited'}")
            print(f"  Monthly limit: ${policy.limit_monthly or 'unlimited'}")
            print(f"  On exceed:     {policy.on_exceed}")

            if totals:
                for scope_id, amounts in totals.items():
                    daily = amounts.get("daily", 0.0)
                    monthly = amounts.get("monthly", 0.0)
                    print(f"    {scope_id}: daily=${daily:.4f}, monthly=${monthly:.4f}")
            else:
                print("    No usage recorded.")

        print()
        return 0

    elif args.budget_action == "reset":
        state.reset(args.scope, args.id)
        print(f"Reset budget for {args.scope}/{args.id}")
        return 0

    else:
        print("Use 'costsentinel budget status' or 'costsentinel budget reset'")
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate the configuration file."""
    try:
        config = load_config()
        print("✓ Configuration is valid")
        print(f"  Project: {config.project_name}")
        print(f"  Models:  {len(config.pricing)} configured")
        print(f"  Policies: {len(config.policies)} defined")
        return 0
    except FileNotFoundError as e:
        print(f"✗ {e}")
        return 1
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show CostSentinel status."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("CostSentinel is not initialized.")
        print("Run 'costsentinel init' to create a configuration file.")
        return 1

    state = CostState(config.state_file)
    attribution = AttributionStore(config.attribution_file)

    print("CostSentinel Status")
    print("=" * 50)
    print(f"  Project:      {config.project_name}")
    print(f"  Config:       costsentinel.yaml")
    print(f"  State file:   {config.state_file}")
    print(f"  Models:       {len(config.pricing)} configured")
    print(f"  Policies:     {len(config.policies)} defined")

    # Show global totals
    global_totals = state.get_all_totals("global")
    if global_totals:
        default = global_totals.get("default", {})
        print(f"\n  Today's spend: ${default.get('daily', 0.0):.4f}")
        print(f"  Month's spend: ${default.get('monthly', 0.0):.4f}")
    else:
        print("\n  No usage recorded yet.")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
