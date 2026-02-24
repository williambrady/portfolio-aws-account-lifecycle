"""CLI entrypoint for AWS Account Lifecycle Management."""

import argparse
import json
import sys

from src.account_closer import (
    build_closure_output,
    close_account,
    find_account_by_email,
    list_member_accounts,
    poll_account_closure,
)
from src.account_creator import (
    build_output,
    create_account,
    find_ou_by_name,
    generate_email,
    move_account_to_ou,
    poll_account_creation,
    validate_account_access,
)
from src.config import load_config, merge_cli_overrides, validate_config
from src.ssm_client import get_caller_identity, get_session, increment_unique_number, read_unique_number


def create_account_command(args):
    """Execute the create-account workflow."""
    config = load_config(args.config)
    cli_overrides = {
        "management_role_arn": args.management_role_arn,
        "automation_role_arn": args.automation_role_arn,
        "mgmt_profile": args.mgmt_profile,
        "automation_profile": args.automation_profile,
        "ou_name": args.ou_name,
        "ou_id": args.ou_id,
        "email": args.email,
    }
    config = merge_cli_overrides(config, cli_overrides)
    config = validate_config(config)

    account_name = args.account_name
    polling_config = config.get("polling", {})
    max_attempts = polling_config.get("max_attempts", 60)
    interval = polling_config.get("interval_seconds", 5)
    tags = config.get("tags", {})
    validation_role = config.get("validation_role_name", "OrganizationAccountAccessRole")
    region = config.get("region")
    email_override = config.get("email_override")

    # Resolve management account identity
    print("Phase 0: Resolving account identities...", file=sys.stderr)
    mgmt_session = get_session(
        profile_name=config.get("mgmt_profile"),
        role_arn=config.get("management_role_arn"),
        region_name=region,
        session_name="lifecycle-create-account",
    )
    mgmt_identity = get_caller_identity(mgmt_session)
    print(f"  Management account: {mgmt_identity['account_id']} ({mgmt_identity['arn']})", file=sys.stderr)

    automation_identity = None
    unique_number = None
    if email_override:
        print("Phase 1: Using provided email (skipping SSM)...", file=sys.stderr)
        email = email_override
        print(f"  Email: {email}", file=sys.stderr)
    else:
        ssm_path = config["ssm_parameter_path"]
        print("Phase 1: Reading SSM unique number from automation account...", file=sys.stderr)
        automation_session = get_session(
            profile_name=config.get("automation_profile"),
            role_arn=config.get("automation_role_arn"),
            region_name=region,
            session_name="lifecycle-ssm-read",
        )
        automation_identity = get_caller_identity(automation_session)
        print(
            f"  Automation account: {automation_identity['account_id']} ({automation_identity['arn']})", file=sys.stderr
        )
        unique_number = read_unique_number(automation_session, ssm_path)
        print(f"  Current unique number: {unique_number}", file=sys.stderr)

        print("Phase 2: Generating email...", file=sys.stderr)
        email = generate_email(config, unique_number, account_name)
        print(f"  Email: {email}", file=sys.stderr)

    ou_name = config.get("default_ou_name")
    ou_id = config.get("ou_id")

    skip_ou = email_override and not ou_name and not ou_id

    if args.dry_run:
        print("\n--- DRY RUN ---", file=sys.stderr)
        print(f"  Account name: {account_name}", file=sys.stderr)
        print(f"  Email: {email}", file=sys.stderr)
        if skip_ou:
            print("  OU: skipped (custom email, no OU specified)", file=sys.stderr)
        else:
            print(f"  OU: {ou_name or ou_id}", file=sys.stderr)
        print(f"  Tags: {tags}", file=sys.stderr)
        if unique_number is not None:
            print(f"  SSM unique number: {unique_number} -> {unique_number + 1} (not applied)", file=sys.stderr)
        else:
            print("  SSM: skipped (custom email provided)", file=sys.stderr)
        print("  No changes will be made.", file=sys.stderr)
        output = {
            "dry_run": True,
            "management_account": mgmt_identity,
            "account_name": account_name,
            "email": email,
            "ou_name": ou_name,
            "ou_id": ou_id,
            "tags": tags,
        }
        if automation_identity:
            output["automation_account"] = automation_identity
        if unique_number is not None:
            output["unique_number"] = unique_number
            output["next_unique_number"] = unique_number + 1
        print(json.dumps(output, indent=2))
        return

    print("Phase 3: Creating account in management account...", file=sys.stderr)
    org_client = mgmt_session.client("organizations")

    status = create_account(org_client, account_name, email, tags)
    request_id = status["Id"]
    print(f"  Create request ID: {request_id}", file=sys.stderr)

    print("Phase 4: Polling account creation status...", file=sys.stderr)
    final_status = poll_account_creation(org_client, request_id, max_attempts, interval)
    account_id = final_status["AccountId"]
    print(f"  Account ID: {account_id}", file=sys.stderr)

    target_ou_id = None
    target_ou_name = None

    if skip_ou:
        print("Phase 5: Skipping OU placement (custom email, no OU specified)...", file=sys.stderr)
    else:
        print("Phase 5: Moving account to OU...", file=sys.stderr)
        if ou_id:
            target_ou_id = ou_id
            target_ou_name = ou_id
        else:
            ou = find_ou_by_name(org_client, ou_name)
            if not ou:
                print(f"ERROR: OU not found: {ou_name}", file=sys.stderr)
                sys.exit(1)
            target_ou_id = ou["Id"]
            target_ou_name = ou["Name"]

        move_account_to_ou(org_client, account_id, target_ou_id)
        print(f"  Account moved to OU: {target_ou_name} ({target_ou_id})", file=sys.stderr)

    print("Phase 6: Validating account access...", file=sys.stderr)
    validated = validate_account_access(mgmt_session, account_id, validation_role)

    if unique_number is not None:
        ssm_path = config["ssm_parameter_path"]
        print("Phase 7: Incrementing SSM unique number...", file=sys.stderr)
        automation_session = get_session(
            profile_name=config.get("automation_profile"),
            role_arn=config.get("automation_role_arn"),
            region_name=region,
            session_name="lifecycle-ssm-increment",
        )
        increment_unique_number(automation_session, ssm_path, unique_number)
    else:
        print("Phase 7: Skipping SSM increment (custom email provided)", file=sys.stderr)

    output = build_output(account_id, account_name, email, target_ou_id, target_ou_name, validated)
    output["management_account"] = mgmt_identity
    if automation_identity:
        output["automation_account"] = automation_identity
    print(json.dumps(output, indent=2))
    print("\nAccount creation complete!", file=sys.stderr)


def _get_mgmt_org_client(args):
    """Build an Organizations client from management account credentials."""
    config = load_config(args.config)
    cli_overrides = {
        "management_role_arn": args.management_role_arn,
        "mgmt_profile": args.mgmt_profile,
    }
    for key, value in cli_overrides.items():
        if value:
            config[key] = value

    has_mgmt_access = config.get("mgmt_profile") or config.get("management_role_arn")
    if not has_mgmt_access:
        print("ERROR: Must provide either mgmt_profile or management_role_arn", file=sys.stderr)
        sys.exit(1)

    region = config.get("region")
    mgmt_session = get_session(
        profile_name=config.get("mgmt_profile"),
        role_arn=config.get("management_role_arn"),
        region_name=region,
        session_name="lifecycle-close-account",
    )
    mgmt_identity = get_caller_identity(mgmt_session)
    print(f"  Management account: {mgmt_identity['account_id']} ({mgmt_identity['arn']})", file=sys.stderr)
    return mgmt_session.client("organizations"), config, mgmt_identity


def close_account_command(args):
    """Execute the close-account workflow."""
    print("Phase 1: Getting management account session...", file=sys.stderr)
    org_client, config, mgmt_identity = _get_mgmt_org_client(args)

    polling_config = config.get("polling", {})
    max_attempts = polling_config.get("max_attempts", 60)
    interval = polling_config.get("interval_seconds", 5)

    if args.all:
        _close_all_accounts(org_client, args, max_attempts, interval, mgmt_identity)
    else:
        _close_single_account(org_client, args, max_attempts, interval, mgmt_identity)


def _close_single_account(org_client, args, max_attempts, interval, mgmt_identity):
    """Close a single account identified by account ID or email."""
    if args.email:
        print(f"Phase 2: Looking up account by email: {args.email}", file=sys.stderr)
        account = find_account_by_email(org_client, args.email)
        if not account:
            print(f"ERROR: No account found with email: {args.email}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Phase 2: Looking up account: {args.account_id}", file=sys.stderr)
        try:
            response = org_client.describe_account(AccountId=args.account_id)
            account = response["Account"]
        except Exception as e:
            print(f"ERROR: Could not describe account {args.account_id}: {e}", file=sys.stderr)
            sys.exit(1)

    account_id = account["Id"]
    account_name = account.get("Name", "")
    email = account.get("Email", "")
    status = account.get("Status", "UNKNOWN")

    print(f"  Account: {account_name} ({account_id})", file=sys.stderr)
    print(f"  Email: {email}", file=sys.stderr)
    print(f"  Status: {status}", file=sys.stderr)

    if status != "ACTIVE":
        print(f"  Account is already {status}, skipping closure", file=sys.stderr)
        output = build_closure_output(account_id, account_name, email, status)
        output["management_account"] = mgmt_identity
        print(json.dumps(output, indent=2))
        return

    if args.dry_run:
        print("\n--- DRY RUN ---", file=sys.stderr)
        print(f"  Would close account: {account_name} ({account_id})", file=sys.stderr)
        print("  No changes will be made.", file=sys.stderr)
        output = {
            "dry_run": True,
            "management_account": mgmt_identity,
            "account_id": account_id,
            "account_name": account_name,
            "email": email,
        }
        print(json.dumps(output, indent=2))
        return

    print(f"Phase 3: Closing account {account_id}...", file=sys.stderr)
    try:
        close_account(org_client, account_id)
    except Exception as e:
        print(f"ERROR: Failed to close account {account_id}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_wait:
        print("  --no-wait specified, skipping polling", file=sys.stderr)
        final_status = "CLOSE_REQUESTED"
    else:
        print("Phase 4: Polling account closure status...", file=sys.stderr)
        final_status = poll_account_closure(org_client, account_id, max_attempts, interval)

    output = build_closure_output(account_id, account_name, email, final_status)
    output["management_account"] = mgmt_identity
    print(json.dumps(output, indent=2))
    print("\nAccount closure complete!", file=sys.stderr)


def _close_all_accounts(org_client, args, max_attempts, interval, mgmt_identity):
    """Close all active member accounts with interactive confirmation."""
    print("Phase 2: Listing all member accounts...", file=sys.stderr)
    all_accounts = list_member_accounts(org_client)
    active_accounts = [a for a in all_accounts if a.get("Status") == "ACTIVE"]
    skipped_accounts = [a for a in all_accounts if a.get("Status") != "ACTIVE"]

    print(f"  Total member accounts: {len(all_accounts)}", file=sys.stderr)
    print(f"  Active (to close): {len(active_accounts)}", file=sys.stderr)
    print(f"  Already closed/suspended: {len(skipped_accounts)}", file=sys.stderr)

    if not active_accounts:
        print("  No active member accounts to close.", file=sys.stderr)
        output = {
            "management_account": mgmt_identity,
            "closed": [],
            "failed": [],
            "skipped": [
                {"account_id": a["Id"], "account_name": a.get("Name", ""), "status": a.get("Status")}
                for a in skipped_accounts
            ],
            "total": len(all_accounts),
            "closed_count": 0,
            "failed_count": 0,
            "skipped_count": len(skipped_accounts),
        }
        print(json.dumps(output, indent=2))
        return

    print("\n  Accounts to close:", file=sys.stderr)
    for account in active_accounts:
        print(f"    - {account.get('Name', '')} ({account['Id']}) [{account.get('Email', '')}]", file=sys.stderr)

    if args.dry_run:
        print("\n--- DRY RUN ---", file=sys.stderr)
        print("  No changes will be made.", file=sys.stderr)
        output = {
            "dry_run": True,
            "management_account": mgmt_identity,
            "accounts_to_close": [
                {"account_id": a["Id"], "account_name": a.get("Name", ""), "email": a.get("Email", "")}
                for a in active_accounts
            ],
            "count": len(active_accounts),
        }
        print(json.dumps(output, indent=2))
        return

    print(f"\n  WARNING: This will close {len(active_accounts)} account(s).", file=sys.stderr)
    print('  Type "yes" to confirm: ', end="", file=sys.stderr, flush=True)
    confirmation = input()
    if confirmation != "yes":
        print("  Aborted.", file=sys.stderr)
        sys.exit(1)

    closed = []
    failed = []
    skipped = [
        {"account_id": a["Id"], "account_name": a.get("Name", ""), "status": a.get("Status")} for a in skipped_accounts
    ]

    for i, account in enumerate(active_accounts, 1):
        account_id = account["Id"]
        account_name = account.get("Name", "")
        print(f"\n  [{i}/{len(active_accounts)}] Closing {account_name} ({account_id})...", file=sys.stderr)

        try:
            close_account(org_client, account_id)
            if args.no_wait:
                final_status = "CLOSE_REQUESTED"
            else:
                final_status = poll_account_closure(org_client, account_id, max_attempts, interval)
            closed.append({"account_id": account_id, "account_name": account_name, "status": final_status})
        except Exception as e:
            print(f"  ERROR closing {account_id}: {e}", file=sys.stderr)
            failed.append({"account_id": account_id, "account_name": account_name, "error": str(e)})

    output = {
        "management_account": mgmt_identity,
        "closed": closed,
        "failed": failed,
        "skipped": skipped,
        "total": len(all_accounts),
        "closed_count": len(closed),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
    }
    print(json.dumps(output, indent=2))

    if failed:
        print(f"\nWARNING: {len(failed)} account(s) failed to close.", file=sys.stderr)
    else:
        print(f"\nAll {len(closed)} account(s) closed successfully!", file=sys.stderr)


def main():
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        description="AWS Account Lifecycle Management",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    create_parser = subparsers.add_parser("create-account", help="Create a new AWS account")
    create_parser.add_argument("account_name", help="Name for the new account")
    create_parser.add_argument("--config", default="config.yaml", help="Path to config file")
    create_parser.add_argument("--email", help="Use a specific email address (skips SSM unique number)")
    create_parser.add_argument("--mgmt-profile", help="AWS profile for management account")
    create_parser.add_argument("--automation-profile", help="AWS profile for automation account")
    create_parser.add_argument("--management-role-arn", help="Role ARN for management account (alternative to profile)")
    create_parser.add_argument("--automation-role-arn", help="Role ARN for automation account (alternative to profile)")
    create_parser.add_argument("--ou-name", help="Override target OU name")
    create_parser.add_argument("--ou-id", help="Target OU ID (bypasses name lookup)")
    create_parser.add_argument("--dry-run", action="store_true", help="Show plan without making changes")

    close_parser = subparsers.add_parser("close-account", help="Close an AWS member account")
    close_target = close_parser.add_mutually_exclusive_group(required=True)
    close_target.add_argument("--account-id", help="Account ID to close")
    close_target.add_argument("--email", help="Close account matching this email address")
    close_target.add_argument("--all", action="store_true", help="Close ALL member accounts")
    close_parser.add_argument("--config", default="config.yaml", help="Path to config file")
    close_parser.add_argument("--mgmt-profile", help="AWS profile for management account")
    close_parser.add_argument("--management-role-arn", help="Role ARN for management account (alternative to profile)")
    close_parser.add_argument("--dry-run", action="store_true", help="Show what would be closed without closing")
    close_parser.add_argument("--no-wait", action="store_true", help="Return after close_account without polling")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "create-account":
        create_account_command(args)
    elif args.command == "close-account":
        close_account_command(args)


if __name__ == "__main__":
    main()
