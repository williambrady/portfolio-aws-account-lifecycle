# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Account Lifecycle Management tool that creates new member accounts in an AWS Organization, places them in the correct OU, validates access, and closes accounts when no longer needed. Uses a separate automation account's SSM parameter to track unique numbers for email generation.

## Common Commands

### Using the Makefile
```bash
make help                                              # Show available targets
make build                                             # Build Docker image
make create-account ACCOUNT_NAME=my-account MGMT_PROFILE=mgmt AUTOMATION_PROFILE=automation  # Create account
make dry-run ACCOUNT_NAME=my-account MGMT_PROFILE=mgmt AUTOMATION_PROFILE=automation  # Show plan without changes
make close-account ACCOUNT_ID=123456789012 MGMT_PROFILE=mgmt  # Dry-run close (default)
make close-account ACCOUNT_ID=123456789012 MGMT_PROFILE=mgmt APPROVE=true  # Actually close
make close-all-accounts MGMT_PROFILE=mgmt              # Dry-run close all (default)
make close-all-accounts MGMT_PROFILE=mgmt APPROVE=true # Actually close all
make shell MGMT_PROFILE=mgmt                           # Open interactive shell
make clean                                             # Remove Docker image
```

### Running Tests
```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

### Code Quality
```bash
pre-commit install              # Install hooks (first time)
pre-commit run --all-files      # Run all checks
ruff check src/ tests/          # Lint
ruff format src/ tests/         # Format code
```

## Architecture

```
CLI args + config.yaml
        │
        ▼
Assume role → Automation Account → Read SSM unique number
        │
        ▼
Generate email: will+rc-org-<number>-<name>@crofton.cloud
        │
        ▼
Assume role → Management Account → organizations.create_account()
        │
        ▼
Poll create_account_status (up to 5 min)
        │
        ▼
Find OU by name/ID → move_account to OU
        │
        ▼
Assume OrganizationAccountAccessRole in new account → validate
        │
        ▼
Increment SSM unique number in automation account
        │
        ▼
Output JSON to stdout
```

### Account Closure Flow

```
CLI args + config.yaml
        │
        ▼
Assume role → Management Account → organizations
        │
        ├─ --account-id → describe_account()
        ├─ --email → list_accounts() + match email
        └─ --all → list_accounts() + exclude management account
        │
        ▼
Validate account is ACTIVE (skip if already closed/suspended)
        │
        ▼
[dry-run exits here]
        │
        ▼
organizations.close_account()
        │
        ▼
Poll describe_account() until status != ACTIVE (unless --no-wait)
        │
        ▼
Output JSON to stdout
```

### Key Components

- `src/main.py` — CLI entrypoint with argparse subcommands
- `src/config.py` — Config loading, merging, validation
- `src/ssm_client.py` — SSM parameter read/increment via cross-account role assumption
- `src/account_creator.py` — Account creation, OU placement, validation
- `src/account_closer.py` — Account closure, email lookup, bulk close
- `config.yaml` — Configuration file with role ARNs, email settings, tags
- `Dockerfile` — Python 3.11-slim with AWS CLI, non-root user
- `entrypoint.sh` — Credential validation and Python module execution

### Design Decisions

- Stderr for progress messages, stdout for JSON output (enables piping)
- SSM increment is last — only after account creation + OU move succeed
- Validation failure is a warning — new accounts may have brief assumeRole delays
- Subcommand pattern (`create-account`, `close-account`) — extensible for future commands
- `--dry-run` shows plan without making changes beyond SSM read
- Close targets are dry-run by default via Makefile (`APPROVE=true` required to execute)
- `--all` requires interactive "yes" confirmation as a second safety layer
- `AccountAlreadyClosedException` handled idempotently
- Recursive OU search by name, with `--ou-id` escape hatch

## Important Notes

- Never commit directly to main — always use feature branches
- Docker container runs as non-root `lifecycle` user
- AWS credentials are mounted read-only from host
