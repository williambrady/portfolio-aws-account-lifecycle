import os
import tempfile

import pytest
import yaml

from src.config import load_config, merge_cli_overrides, validate_config


def _write_config(data):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    return f.name


def _valid_config():
    return {
        "management_role_arn": "arn:aws:iam::role/MgmtRole",
        "automation_role_arn": "arn:aws:iam::role/AutoRole",
        "ssm_parameter_path": "/test/org-number",
        "email": {"domain": "example.com", "prefix": "test"},
        "default_ou_name": "Non-Production",
        "tags": {"Environment": "test"},
    }


class TestLoadConfig:
    def test_load_valid_config(self):
        path = _write_config(_valid_config())
        try:
            config = load_config(path)
            assert config["management_role_arn"] == "arn:aws:iam::role/MgmtRole"
            assert config["email"]["domain"] == "example.com"
        finally:
            os.unlink(path)

    def test_load_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")


class TestMergeCliOverrides:
    def test_override_management_role(self):
        config = _valid_config()
        overrides = {
            "management_role_arn": "arn:aws:iam::role/NewRole",
            "ou_name": None,
            "ou_id": None,
            "automation_role_arn": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["management_role_arn"] == "arn:aws:iam::role/NewRole"

    def test_override_ou_name(self):
        config = _valid_config()
        overrides = {"management_role_arn": None, "automation_role_arn": None, "ou_name": "Production", "ou_id": None}
        merged = merge_cli_overrides(config, overrides)
        assert merged["default_ou_name"] == "Production"

    def test_override_ou_id(self):
        config = _valid_config()
        overrides = {"management_role_arn": None, "automation_role_arn": None, "ou_name": None, "ou_id": "ou-abc123"}
        merged = merge_cli_overrides(config, overrides)
        assert merged["ou_id"] == "ou-abc123"

    def test_no_overrides(self):
        config = _valid_config()
        overrides = {"management_role_arn": None, "automation_role_arn": None, "ou_name": None, "ou_id": None}
        merged = merge_cli_overrides(config, overrides)
        assert merged["management_role_arn"] == config["management_role_arn"]
        assert merged["default_ou_name"] == config["default_ou_name"]


class TestValidateConfig:
    def test_valid_config_passes(self):
        config = _valid_config()
        result = validate_config(config)
        assert result == config

    def test_missing_management_role(self):
        config = _valid_config()
        config["management_role_arn"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_automation_role(self):
        config = _valid_config()
        config["automation_role_arn"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_ssm_path(self):
        config = _valid_config()
        config["ssm_parameter_path"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_domain(self):
        config = _valid_config()
        config["email"]["domain"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_prefix(self):
        config = _valid_config()
        config["email"]["prefix"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)
