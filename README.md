# portfolio-aws-account-lifecycle

AWS Account Lifecycle Management — creates new member accounts in an AWS Organization, places them in the correct OU, validates access, and closes accounts when no longer needed.

## Features

- Creates AWS accounts via Organizations API
- Generates unique email addresses using SSM-tracked unique numbers
- Places accounts in the correct Organizational Unit
- Validates access via assumeRole into new accounts
- Closes accounts by ID, email, or all member accounts at once
- JSON output for pipeline integration
- Dry-run mode to preview changes

## Prerequisites

- Docker
- AWS CLI configured with appropriate profiles
- IAM roles in management and automation accounts

## Quick Start

```bash
# Build the Docker image
make build

# Preview what will happen (no changes made)
make dry-run ACCOUNT_NAME=my-new-account

# Create a new account
make create-account ACCOUNT_NAME=my-new-account
```

## Configuration

Edit `config.yaml` to set:

- **mgmt_profile** / **management_role_arn** — AWS profile or IAM role for the management account
- **automation_profile** / **automation_role_arn** — AWS profile or IAM role for the automation account
- **ssm_parameter_path** — SSM parameter storing the current unique number
- **email** — Domain and prefix for generated email addresses
- **default_ou_name** — Target OU for new accounts
- **tags** — Default tags applied to new accounts

## Email Pattern

```
{prefix}+{unique_number}-{account_name}@{domain}
```

Example: `will+5-my-new-account@crofton.cloud`

## Closing Accounts

Close targets are **dry-run by default**. You must pass `APPROVE=true` to actually close accounts.

```bash
# Preview what would be closed (default, safe)
make close-account ACCOUNT_ID=123456789012 MGMT_PROFILE=mgmt

# Actually close the account
make close-account ACCOUNT_ID=123456789012 MGMT_PROFILE=mgmt APPROVE=true

# Preview closing ALL member accounts
make close-all-accounts MGMT_PROFILE=mgmt

# Actually close ALL member accounts (also requires interactive confirmation)
make close-all-accounts MGMT_PROFILE=mgmt APPROVE=true

# Close by email (CLI, no dry-run default)
python -m src.main close-account --email "will+50-testing@crofton.cloud" --mgmt-profile mgmt
```

## AWS Constraints

### Account Creation

- New accounts are created via `organizations:CreateAccount` and take 1-5 minutes to complete
- Each account requires a unique email address
- The `OrganizationAccountAccessRole` is automatically created in new accounts

### Account Closure

- Closure is **asynchronous** — `close_account()` returns immediately, then the account transitions: `ACTIVE` → `PENDING_CLOSURE` → `SUSPENDED`
- After 90 days in `SUSPENDED` state, the account is permanently deleted
- Closure is **reversible** within 90 days via AWS Support
- **Rate limit**: Max 10% of member accounts can be closed in a rolling 30-day window (minimum 10, maximum 1000)
- Cannot close the **management account**
- Organization must be in **All Features** mode
- There is no built-in "find by email" API — `list_accounts()` must be paginated and matched client-side

## CLI Options

### create-account

```bash
# Override target OU
... create-account my-account --ou-name Production

# Use OU ID directly (bypasses name lookup)
... create-account my-account --ou-id ou-abc123def

# Override role ARNs
... create-account my-account --management-role-arn arn:aws:iam::role/CustomRole

# Use a different config file
... create-account my-account --config /path/to/config.yaml
```

### close-account

```bash
# Close by account ID
... close-account --account-id 123456789012

# Close by email
... close-account --email "will+50-testing@crofton.cloud"

# Close all member accounts (interactive confirmation required)
... close-account --all

# Skip polling for closure status
... close-account --account-id 123456789012 --no-wait

# Preview without closing
... close-account --account-id 123456789012 --dry-run
```

## Project Structure

```
├── src/
│   ├── main.py              # CLI entrypoint
│   ├── config.py            # Config loading and validation
│   ├── ssm_client.py        # SSM parameter operations
│   ├── account_creator.py   # Account creation logic
│   └── account_closer.py    # Account closure logic
├── tests/
│   ├── test_config.py
│   ├── test_ssm_client.py
│   ├── test_account_creator.py
│   └── test_account_closer.py
├── config.yaml              # Configuration
├── Dockerfile               # Container definition
├── entrypoint.sh            # Container entrypoint
├── Makefile                 # Build and run targets
└── requirements.txt         # Python dependencies
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest

# Run tests
pytest tests/ -v

# Run linting
pre-commit run --all-files
```

## Branching Strategy

- `main` — Production
- `develop` — Integration
- `feature/*` — Feature branches (PR to develop)

## License

See [LICENSE](LICENSE) for details.
