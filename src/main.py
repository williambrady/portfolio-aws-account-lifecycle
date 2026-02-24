import argparse
import json
import sys

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
from src.ssm_client import get_session, increment_unique_number, read_unique_number


def create_account_command(args):
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
        unique_number = read_unique_number(automation_session, ssm_path)
        print(f"  Current unique number: {unique_number}", file=sys.stderr)

        print("Phase 2: Generating email...", file=sys.stderr)
        email = generate_email(config, unique_number, account_name)
        print(f"  Email: {email}", file=sys.stderr)

    ou_name = config.get("default_ou_name")
    ou_id = config.get("ou_id")

    if args.dry_run:
        print("\n--- DRY RUN ---", file=sys.stderr)
        print(f"  Account name: {account_name}", file=sys.stderr)
        print(f"  Email: {email}", file=sys.stderr)
        print(f"  OU: {ou_name or ou_id}", file=sys.stderr)
        print(f"  Tags: {tags}", file=sys.stderr)
        if unique_number is not None:
            print(f"  SSM unique number: {unique_number} -> {unique_number + 1} (not applied)", file=sys.stderr)
        else:
            print("  SSM: skipped (custom email provided)", file=sys.stderr)
        print("  No changes will be made.", file=sys.stderr)
        output = {
            "dry_run": True,
            "account_name": account_name,
            "email": email,
            "ou_name": ou_name,
            "ou_id": ou_id,
            "tags": tags,
        }
        if unique_number is not None:
            output["unique_number"] = unique_number
            output["next_unique_number"] = unique_number + 1
        print(json.dumps(output, indent=2))
        return

    print("Phase 3: Creating account in management account...", file=sys.stderr)
    mgmt_session = get_session(
        profile_name=config.get("mgmt_profile"),
        role_arn=config.get("management_role_arn"),
        region_name=region,
        session_name="lifecycle-create-account",
    )
    org_client = mgmt_session.client("organizations")

    status = create_account(org_client, account_name, email, tags)
    request_id = status["Id"]
    print(f"  Create request ID: {request_id}", file=sys.stderr)

    print("Phase 4: Polling account creation status...", file=sys.stderr)
    final_status = poll_account_creation(org_client, request_id, max_attempts, interval)
    account_id = final_status["AccountId"]
    print(f"  Account ID: {account_id}", file=sys.stderr)

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
    print(json.dumps(output, indent=2))
    print("\nAccount creation complete!", file=sys.stderr)


def main():
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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "create-account":
        create_account_command(args)


if __name__ == "__main__":
    main()
