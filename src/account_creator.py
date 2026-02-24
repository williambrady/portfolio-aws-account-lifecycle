"""Account creation, OU placement, and validation for AWS Organizations."""

import re
import sys
import time
from datetime import datetime, timezone

import boto3


def sanitize_account_name(name):
    """Normalize an account name for use in email addresses."""
    sanitized = name.lower().strip()
    sanitized = re.sub(r"[^a-z0-9-]", "-", sanitized)
    sanitized = re.sub(r"-+", "-", sanitized)
    sanitized = sanitized.strip("-")
    return sanitized[:60]


def generate_email(config, unique_number, account_name):
    """Generate a unique email address for a new AWS account."""
    email_config = config["email"]
    prefix = email_config["prefix"]
    domain = email_config["domain"]
    safe_name = sanitize_account_name(account_name)
    return f"{prefix}+{unique_number}-{safe_name}@{domain}"


def create_account(org_client, account_name, email, tags):
    """Create a new AWS account in the organization."""
    tag_list = [{"Key": k, "Value": v} for k, v in tags.items()]
    response = org_client.create_account(
        Email=email,
        AccountName=account_name,
        Tags=tag_list,
    )
    return response["CreateAccountStatus"]


def poll_account_creation(org_client, request_id, max_attempts=60, interval=5):
    """Poll account creation status until it succeeds, fails, or times out."""
    for attempt in range(max_attempts):
        response = org_client.describe_create_account_status(CreateAccountRequestId=request_id)
        status = response["CreateAccountStatus"]

        state = status["State"]
        print(f"  Account creation status: {state} (attempt {attempt + 1}/{max_attempts})", file=sys.stderr)

        if state == "SUCCEEDED":
            return status
        if state == "FAILED":
            reason = status.get("FailureReason", "Unknown")
            print(f"ERROR: Account creation failed: {reason}", file=sys.stderr)
            sys.exit(1)

        time.sleep(interval)

    print("ERROR: Account creation timed out", file=sys.stderr)
    sys.exit(1)


def find_ou_by_name(org_client, ou_name, parent_id=None):
    """Recursively search for an OU by name, returning its dict or None."""
    if parent_id is None:
        roots = org_client.list_roots()["Roots"]
        parent_id = roots[0]["Id"]

    paginator = org_client.get_paginator("list_organizational_units_for_parent")
    for page in paginator.paginate(ParentId=parent_id):
        for ou in page["OrganizationalUnits"]:
            if ou["Name"] == ou_name:
                return ou
            child = find_ou_by_name(org_client, ou_name, parent_id=ou["Id"])
            if child:
                return child

    return None


def move_account_to_ou(org_client, account_id, destination_ou_id):
    """Move an account to a target OU, skipping if already there."""
    parents = org_client.list_parents(ChildId=account_id)["Parents"]
    source_id = parents[0]["Id"]

    if source_id == destination_ou_id:
        print(f"  Account {account_id} already in target OU", file=sys.stderr)
        return

    org_client.move_account(
        AccountId=account_id,
        SourceParentId=source_id,
        DestinationParentId=destination_ou_id,
    )
    print(f"  Moved account {account_id} to OU {destination_ou_id}", file=sys.stderr)


def validate_account_access(mgmt_session, account_id, role_name, max_attempts=6, initial_delay=5, max_delay=30):
    """Validate cross-account access to a new account with exponential backoff retries."""
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    delay = initial_delay

    for attempt in range(1, max_attempts + 1):
        try:
            sts = mgmt_session.client("sts")
            response = sts.assume_role(RoleArn=role_arn, RoleSessionName="lifecycle-validation")
            temp_session = boto3.Session(
                aws_access_key_id=response["Credentials"]["AccessKeyId"],
                aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
                aws_session_token=response["Credentials"]["SessionToken"],
                region_name=mgmt_session.region_name,
            )
            identity = temp_session.client("sts").get_caller_identity()
            print(f"  Validated access to account {account_id}: {identity['Arn']}", file=sys.stderr)
            return True
        except Exception as e:
            if attempt < max_attempts:
                print(
                    f"  Validation attempt {attempt}/{max_attempts} failed, retrying in {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                print(
                    f"  WARNING: Could not validate access to account {account_id} after {max_attempts} attempts: {e}",
                    file=sys.stderr,
                )
                return False

    return False


def build_output(account_id, account_name, email, ou_id, ou_name, validated, created_at=None):
    """Build a JSON-serializable output dict for account creation results."""
    return {
        "account_id": account_id,
        "account_name": account_name,
        "email": email,
        "ou_id": ou_id,
        "ou_name": ou_name,
        "validated": validated,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": "SUCCEEDED",
    }
