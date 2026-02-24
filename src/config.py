"""Configuration loading, merging, and validation."""

import sys

import yaml

REQUIRED_FIELDS = [
    "ssm_parameter_path",
]


def load_config(config_path="config.yaml"):
    """Load configuration from a YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_cli_overrides(config, cli_args):
    """Merge CLI argument overrides into the loaded configuration."""
    overrides = {}
    if cli_args.get("management_role_arn"):
        overrides["management_role_arn"] = cli_args["management_role_arn"]
    if cli_args.get("automation_role_arn"):
        overrides["automation_role_arn"] = cli_args["automation_role_arn"]
    if cli_args.get("mgmt_profile"):
        overrides["mgmt_profile"] = cli_args["mgmt_profile"]
    if cli_args.get("automation_profile"):
        overrides["automation_profile"] = cli_args["automation_profile"]
    if cli_args.get("ou_name"):
        overrides["default_ou_name"] = cli_args["ou_name"]
    if cli_args.get("ou_id"):
        overrides["ou_id"] = cli_args["ou_id"]
    if cli_args.get("email"):
        overrides["email_override"] = cli_args["email"]

    merged = {**config, **overrides}
    return merged


def validate_config(config):
    """Validate required configuration fields, exiting on errors."""
    has_mgmt_access = config.get("mgmt_profile") or config.get("management_role_arn")
    if not has_mgmt_access:
        print("ERROR: Must provide either mgmt_profile or management_role_arn", file=sys.stderr)
        sys.exit(1)

    if config.get("email_override"):
        return config

    missing = [f for f in REQUIRED_FIELDS if not config.get(f)]
    if missing:
        print(f"ERROR: Missing required config fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    has_automation_access = config.get("automation_profile") or config.get("automation_role_arn")
    if not has_automation_access:
        print("ERROR: Must provide either automation_profile or automation_role_arn", file=sys.stderr)
        sys.exit(1)

    email_config = config.get("email", {})
    if not email_config.get("domain"):
        print("ERROR: Missing required config field: email.domain", file=sys.stderr)
        sys.exit(1)
    if not email_config.get("prefix"):
        print("ERROR: Missing required config field: email.prefix", file=sys.stderr)
        sys.exit(1)

    return config
