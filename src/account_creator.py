import sys
import time
from datetime import datetime, timezone

import boto3


def generate_email(config, org_number, account_name):
    email_config = config["email"]
    prefix = email_config["prefix"]
    domain = email_config["domain"]
    return f"{prefix}+rc-org-{org_number}-{account_name}@{domain}"


def create_account(org_client, account_name, email, tags):
    tag_list = [{"Key": k, "Value": v} for k, v in tags.items()]
    response = org_client.create_account(
        Email=email,
        AccountName=account_name,
        Tags=tag_list,
    )
    return response["CreateAccountStatus"]


def poll_account_creation(org_client, request_id, max_attempts=60, interval=5):
    for attempt in range(max_attempts):
        response = org_client.describe_create_account_status(CreateAccountRequestId=request_id)
        status = response["CreateAccountStatus"]

        state = status["State"]
        print(f"  Account creation status: {state} (attempt {attempt + 1}/{max_attempts})", file=sys.stderr)

        if state == "SUCCEEDED":
            return status
        elif state == "FAILED":
            reason = status.get("FailureReason", "Unknown")
            print(f"ERROR: Account creation failed: {reason}", file=sys.stderr)
            sys.exit(1)

        time.sleep(interval)

    print("ERROR: Account creation timed out", file=sys.stderr)
    sys.exit(1)


def find_ou_by_name(org_client, ou_name, parent_id=None):
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


def validate_account_access(account_id, role_name):
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    try:
        sts = boto3.client("sts")
        response = sts.assume_role(RoleArn=role_arn, RoleSessionName="lifecycle-validation")
        temp_session = boto3.Session(
            aws_access_key_id=response["Credentials"]["AccessKeyId"],
            aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
            aws_session_token=response["Credentials"]["SessionToken"],
        )
        identity = temp_session.client("sts").get_caller_identity()
        print(f"  Validated access to account {account_id}: {identity['Arn']}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  WARNING: Could not validate access to account {account_id}: {e}", file=sys.stderr)
        return False


def build_output(account_id, account_name, email, ou_id, ou_name, validated, created_at=None):
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
