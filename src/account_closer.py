import sys
import time
from datetime import datetime, timezone


def list_member_accounts(org_client):
    org_info = org_client.describe_organization()["Organization"]
    management_account_id = org_info["MasterAccountId"]

    accounts = []
    paginator = org_client.get_paginator("list_accounts")
    for page in paginator.paginate():
        for account in page["Accounts"]:
            if account["Id"] != management_account_id:
                accounts.append(account)

    return accounts


def find_account_by_email(org_client, email):
    paginator = org_client.get_paginator("list_accounts")
    for page in paginator.paginate():
        for account in page["Accounts"]:
            if account["Email"] == email:
                return account
    return None


def close_account(org_client, account_id):
    try:
        org_client.close_account(AccountId=account_id)
        return True
    except org_client.exceptions.AccountAlreadyClosedException:
        print(f"  Account {account_id} is already closed", file=sys.stderr)
        return True


def poll_account_closure(org_client, account_id, max_attempts=60, interval=5):
    for attempt in range(max_attempts):
        response = org_client.describe_account(AccountId=account_id)
        account = response["Account"]
        status = account["Status"]

        print(f"  Account {account_id} status: {status} (attempt {attempt + 1}/{max_attempts})", file=sys.stderr)

        if status != "ACTIVE":
            return status

        time.sleep(interval)

    print(f"  WARNING: Account {account_id} still ACTIVE after polling timeout", file=sys.stderr)
    return "ACTIVE"


def build_closure_output(account_id, account_name, email, status, closed_at=None):
    return {
        "account_id": account_id,
        "account_name": account_name,
        "email": email,
        "status": status,
        "closed_at": closed_at or datetime.now(timezone.utc).isoformat(),
    }
