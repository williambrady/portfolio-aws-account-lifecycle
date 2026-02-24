# Implementation Plan: portfolio-aws-account-lifecycle

## Context

This is a template project being converted into an AWS account lifecycle management tool. It creates new member accounts in an AWS Organization, places them in the correct OU, and validates access. It uses a separate automation account's SSM parameter to track org numbers for email generation. The project follows Docker-based patterns established by sibling projects (`portfolio-aws-org-baseline`, `portfolio-aws-account-baseline`).

---

## Files to Create

### Python Source (`src/`)
1. **`src/__init__.py`** — empty package marker
2. **`src/config.py`** — Load `config.yaml`, merge CLI overrides, validate required fields
3. **`src/ssm_client.py`** — Assume role into automation account, read/increment SSM org number
4. **`src/account_creator.py`** — Core logic: create account, poll status, find OU, move account, validate access via assumeRole, generate email, build JSON output
5. **`src/main.py`** — CLI entrypoint with argparse subcommand `create-account`. Orchestrates: SSM read → email gen → create account → move to OU → validate → SSM increment → JSON output

### Tests (`tests/`)
6. **`tests/__init__.py`** — empty
7. **`tests/test_config.py`** — config loading, merging, validation
8. **`tests/test_ssm_client.py`** — mock boto3 SSM read/increment
9. **`tests/test_account_creator.py`** — mock boto3 account creation, email generation, output building

### Infrastructure
10. **`config.yaml`** — Example config with placeholders for management/automation role ARNs, SSM path, OU name, email settings, tags
11. **`requirements.txt`** — `boto3>=1.34.0`, `botocore>=1.34.0`, `pyyaml>=6.0`
12. **`Dockerfile`** — `python:3.11-slim`, AWS CLI v2, non-root `lifecycle` user, copies src/ and config
13. **`entrypoint.sh`** — Validate AWS creds via `sts get-caller-identity`, then `exec python3 -m src.main "$@"`
14. **`.flake8`** — `max-line-length = 120`

## Files to Modify

15. **`Makefile`** — Replace Terraform targets with: `build`, `create-account` (requires `ACCOUNT_NAME`), `dry-run`, `shell`, `clean`
16. **`.pre-commit-config.yaml`** — Remove all Terraform hooks (`antonbabenko/pre-commit-terraform`), keep Python hooks
17. **`.github/workflows/lint.yml`** — Remove Terraform/TFLint/terraform-docs setup steps
18. **`CLAUDE.md`** — Project-specific commands and architecture
19. **`README.md`** — Real project documentation
20. **`PLAN.md`** — Overwrite with this plan

## Files to Delete

21. **`terraform/main.tf`**, **`outputs.tf`**, **`providers.tf`**, **`variables.tf`**, **`versions.tf`** — Not a Terraform project
22. **`.terraform-docs.yml`**, **`.tflint.hcl`** — Terraform-specific config
23. **`cloudformation/.gitkeep`**, **`scripts/.gitkeep`** — Unused directories

---

## Key Design Decisions

- **Stderr for progress, stdout for JSON** — allows piping output
- **SSM increment is last** — only after account creation + OU move succeed
- **Validation failure = warning** — new accounts may have brief assumeRole delays
- **Subcommand pattern** (`create-account`) — extensible for future `close-account`, `list-accounts`
- **`--dry-run`** — shows plan (email, OU, tags) without making changes beyond SSM read
- **Recursive OU search** by name, with `--ou-id` escape hatch for direct lookup

## Workflow

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
Assume OrganizationAccountAccessRole in new account → sts.get_caller_identity
        │
        ▼
Increment SSM org number in automation account
        │
        ▼
Output JSON: {account_id, name, email, timestamps, status, ou_id, ou_name}
```

## Implementation Order

1. Config & deps: `config.yaml`, `requirements.txt`, `.flake8`
2. Python core: `src/config.py` → `src/ssm_client.py` → `src/account_creator.py` → `src/main.py`
3. Docker: `Dockerfile`, `entrypoint.sh`
4. Makefile: replace with Docker targets
5. Tests: all `tests/` files
6. Cleanup: delete Terraform files, `.terraform-docs.yml`, `.tflint.hcl`, empty dirs
7. Update configs: `.pre-commit-config.yaml`, `.github/workflows/lint.yml`
8. Documentation: `CLAUDE.md`, `README.md`, `PLAN.md`

## Verification

1. `make build` — Docker image builds successfully
2. `make dry-run ACCOUNT_NAME=test-account AWS_PROFILE=mgmt` — shows plan JSON without creating anything
3. `pytest tests/ -v` — all unit tests pass
4. `pre-commit run --all-files` — all hooks pass (black, flake8, isort)
