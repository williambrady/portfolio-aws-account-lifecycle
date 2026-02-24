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


def _valid_config_with_roles():
    return {
        "management_role_arn": "arn:aws:iam::role/MgmtRole",
        "automation_role_arn": "arn:aws:iam::role/AutoRole",
        "ssm_parameter_path": "/test/unique-number",
        "email": {"domain": "example.com", "prefix": "test"},
        "default_ou_name": "Non-Production",
        "tags": {"Environment": "test"},
    }


def _valid_config_with_profiles():
    return {
        "mgmt_profile": "mgmt",
        "automation_profile": "portfolio",
        "ssm_parameter_path": "/test/unique-number",
        "email": {"domain": "example.com", "prefix": "test"},
        "default_ou_name": "Non-Production",
        "tags": {"Environment": "test"},
    }


class TestLoadConfig:
    def test_load_valid_config(self):
        path = _write_config(_valid_config_with_roles())
        try:
            config = load_config(path)
            assert config["management_role_arn"] == "arn:aws:iam::role/MgmtRole"
            assert config["email"]["domain"] == "example.com"
        finally:
            os.unlink(path)

    def test_load_empty_config_returns_empty_dict(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        f.write("")
        f.close()
        try:
            config = load_config(f.name)
            assert config == {}
        finally:
            os.unlink(f.name)

    def test_load_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")


class TestMergeCliOverrides:
    def test_override_management_role(self):
        config = _valid_config_with_roles()
        overrides = {
            "management_role_arn": "arn:aws:iam::role/NewRole",
            "automation_role_arn": None,
            "mgmt_profile": None,
            "automation_profile": None,
            "ou_name": None,
            "ou_id": None,
            "email": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["management_role_arn"] == "arn:aws:iam::role/NewRole"

    def test_override_profiles(self):
        config = _valid_config_with_roles()
        overrides = {
            "management_role_arn": None,
            "automation_role_arn": None,
            "mgmt_profile": "new-mgmt",
            "automation_profile": "new-auto",
            "ou_name": None,
            "ou_id": None,
            "email": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["mgmt_profile"] == "new-mgmt"
        assert merged["automation_profile"] == "new-auto"

    def test_override_ou_name(self):
        config = _valid_config_with_roles()
        overrides = {
            "management_role_arn": None,
            "automation_role_arn": None,
            "mgmt_profile": None,
            "automation_profile": None,
            "ou_name": "Production",
            "ou_id": None,
            "email": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["default_ou_name"] == "Production"

    def test_override_ou_id(self):
        config = _valid_config_with_roles()
        overrides = {
            "management_role_arn": None,
            "automation_role_arn": None,
            "mgmt_profile": None,
            "automation_profile": None,
            "ou_name": None,
            "ou_id": "ou-abc123",
            "email": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["ou_id"] == "ou-abc123"

    def test_no_overrides(self):
        config = _valid_config_with_roles()
        overrides = {
            "management_role_arn": None,
            "automation_role_arn": None,
            "mgmt_profile": None,
            "automation_profile": None,
            "ou_name": None,
            "ou_id": None,
            "email": None,
        }
        merged = merge_cli_overrides(config, overrides)
        assert merged["management_role_arn"] == config["management_role_arn"]
        assert merged["default_ou_name"] == config["default_ou_name"]


class TestValidateConfig:
    def test_valid_config_with_roles(self):
        config = _valid_config_with_roles()
        result = validate_config(config)
        assert result == config

    def test_valid_config_with_profiles(self):
        config = _valid_config_with_profiles()
        result = validate_config(config)
        assert result == config

    def test_missing_mgmt_access(self):
        config = _valid_config_with_profiles()
        del config["mgmt_profile"]
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_automation_access(self):
        config = _valid_config_with_profiles()
        del config["automation_profile"]
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_ssm_path(self):
        config = _valid_config_with_roles()
        config["ssm_parameter_path"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_domain(self):
        config = _valid_config_with_roles()
        config["email"]["domain"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_prefix(self):
        config = _valid_config_with_roles()
        config["email"]["prefix"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_email_override_skips_automation_and_email_validation(self):
        config = {
            "mgmt_profile": "mgmt",
            "email_override": "custom@example.com",
        }
        result = validate_config(config)
        assert result["email_override"] == "custom@example.com"

    def test_email_override_still_requires_mgmt(self):
        config = {"email_override": "custom@example.com"}
        with pytest.raises(SystemExit):
            validate_config(config)
