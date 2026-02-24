# portfolio-aws-account-lifecycle

AWS Account Lifecycle Management — creates new member accounts in an AWS Organization, places them in the correct OU, and validates access.

## Features

- Creates AWS accounts via Organizations API
- Generates unique email addresses using SSM-tracked unique numbers
- Places accounts in the correct Organizational Unit
- Validates access via assumeRole into new accounts
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
make dry-run ACCOUNT_NAME=my-new-account AWS_PROFILE=mgmt

# Create a new account
make create-account ACCOUNT_NAME=my-new-account AWS_PROFILE=mgmt
```

## Configuration

Edit `config.yaml` to set:

- **management_role_arn** — IAM role in the management account for Organizations API
- **automation_role_arn** — IAM role in the automation account for SSM access
- **ssm_parameter_path** — SSM parameter storing the current unique number
- **email** — Domain and prefix for generated email addresses
- **default_ou_name** — Target OU for new accounts
- **tags** — Default tags applied to new accounts

## Email Pattern

```
{prefix}+rc-org-{unique_number}-{account_name}@{domain}
```

Example: `will+rc-org-5-my-new-account@crofton.cloud`

## CLI Options

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

## Project Structure

```
├── src/
│   ├── main.py              # CLI entrypoint
│   ├── config.py            # Config loading and validation
│   ├── ssm_client.py        # SSM parameter operations
│   └── account_creator.py   # Account creation logic
├── tests/
│   ├── test_config.py
│   ├── test_ssm_client.py
│   └── test_account_creator.py
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
