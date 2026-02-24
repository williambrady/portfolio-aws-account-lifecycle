import sys

import yaml

REQUIRED_FIELDS = [
    "management_role_arn",
    "automation_role_arn",
    "ssm_parameter_path",
]


def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def merge_cli_overrides(config, cli_args):
    overrides = {}
    if cli_args.get("management_role_arn"):
        overrides["management_role_arn"] = cli_args["management_role_arn"]
    if cli_args.get("automation_role_arn"):
        overrides["automation_role_arn"] = cli_args["automation_role_arn"]
    if cli_args.get("ou_name"):
        overrides["default_ou_name"] = cli_args["ou_name"]
    if cli_args.get("ou_id"):
        overrides["ou_id"] = cli_args["ou_id"]

    merged = {**config, **overrides}
    return merged


def validate_config(config):
    missing = [f for f in REQUIRED_FIELDS if not config.get(f)]
    if missing:
        print(f"ERROR: Missing required config fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    email_config = config.get("email", {})
    if not email_config.get("domain"):
        print("ERROR: Missing required config field: email.domain", file=sys.stderr)
        sys.exit(1)
    if not email_config.get("prefix"):
        print("ERROR: Missing required config field: email.prefix", file=sys.stderr)
        sys.exit(1)

    return config
