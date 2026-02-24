# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Account Lifecycle Management tool that creates new member accounts in an AWS Organization, places them in the correct OU, and validates access. Uses a separate automation account's SSM parameter to track org numbers for email generation.

## Common Commands

### Using the Makefile
```bash
make help                                              # Show available targets
make build                                             # Build Docker image
make create-account ACCOUNT_NAME=my-account AWS_PROFILE=mgmt  # Create account
make dry-run ACCOUNT_NAME=my-account AWS_PROFILE=mgmt  # Show plan without changes
make shell AWS_PROFILE=mgmt                            # Open interactive shell
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
Assume role → Automation Account → Read SSM org number
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
Increment SSM org number in automation account
        │
        ▼
Output JSON to stdout
```

### Key Components

- `src/main.py` — CLI entrypoint with argparse subcommands
- `src/config.py` — Config loading, merging, validation
- `src/ssm_client.py` — SSM parameter read/increment via cross-account role assumption
- `src/account_creator.py` — Account creation, OU placement, validation
- `config.yaml` — Configuration file with role ARNs, email settings, tags
- `Dockerfile` — Python 3.11-slim with AWS CLI, non-root user
- `entrypoint.sh` — Credential validation and Python module execution

### Design Decisions

- Stderr for progress messages, stdout for JSON output (enables piping)
- SSM increment is last — only after account creation + OU move succeed
- Validation failure is a warning — new accounts may have brief assumeRole delays
- Subcommand pattern (`create-account`) — extensible for future commands
- `--dry-run` shows plan without making changes beyond SSM read
- Recursive OU search by name, with `--ou-id` escape hatch

## Important Notes

- Never commit directly to main — always use feature branches
- Docker container runs as non-root `lifecycle` user
- AWS credentials are mounted read-only from host
