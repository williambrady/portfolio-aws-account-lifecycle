"""Tests for configuration loading, merging, and validation."""

import os
import tempfile

import pytest
import yaml

from src.config import load_config, merge_cli_overrides, validate_config


def _write_config(data):
    """Write a config dictionary to a temporary YAML file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    return f.name


def _valid_config_with_roles():
    """Return a valid config dictionary using cross-account role ARNs for authentication."""
    return {
        "management_role_arn": "arn:aws:iam::role/MgmtRole",
        "automation_role_arn": "arn:aws:iam::role/AutoRole",
        "ssm_parameter_path": "/test/unique-number",
        "email": {"domain": "example.com", "prefix": "test"},
        "default_ou_name": "Non-Production",
        "tags": {"Environment": "test"},
    }


def _valid_config_with_profiles():
    """Return a valid config dictionary using named AWS profiles for authentication."""
    return {
        "mgmt_profile": "mgmt",
        "automation_profile": "portfolio",
        "ssm_parameter_path": "/test/unique-number",
        "email": {"domain": "example.com", "prefix": "test"},
        "default_ou_name": "Non-Production",
        "tags": {"Environment": "test"},
    }


class TestLoadConfig:
    """Tests for loading configuration from YAML files."""

    def test_load_valid_config(self):
        """Verify that a valid YAML config file is loaded and parsed correctly."""
        path = _write_config(_valid_config_with_roles())
        try:
            config = load_config(path)
            assert config["management_role_arn"] == "arn:aws:iam::role/MgmtRole"
            assert config["email"]["domain"] == "example.com"
        finally:
            os.unlink(path)

    def test_load_empty_config_returns_empty_dict(self):
        """Verify that an empty YAML file returns an empty dictionary."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        f.write("")
        f.close()
        try:
            config = load_config(f.name)
            assert config == {}
        finally:
            os.unlink(f.name)

    def test_load_config_file_not_found(self):
        """Verify that loading a nonexistent config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")


class TestMergeCliOverrides:
    """Tests for merging CLI argument overrides into the base configuration."""

    def test_override_management_role(self):
        """Verify that the management role ARN can be overridden via CLI arguments."""
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
        """Verify that management and automation AWS profiles can be overridden via CLI arguments."""
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
        """Verify that the OU name override replaces the default_ou_name in config."""
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
        """Verify that the OU ID can be set directly via CLI arguments."""
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
        """Verify that config values are preserved when all CLI overrides are None."""
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
    """Tests for configuration validation rules and required field checks."""

    def test_valid_config_with_roles(self):
        """Verify that a config using role ARNs passes validation successfully."""
        config = _valid_config_with_roles()
        result = validate_config(config)
        assert result == config

    def test_valid_config_with_profiles(self):
        """Verify that a config using named AWS profiles passes validation successfully."""
        config = _valid_config_with_profiles()
        result = validate_config(config)
        assert result == config

    def test_missing_mgmt_access(self):
        """Verify that validation exits when neither management role ARN nor profile is provided."""
        config = _valid_config_with_profiles()
        del config["mgmt_profile"]
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_automation_access(self):
        """Verify that validation exits when neither automation role ARN nor profile is provided."""
        config = _valid_config_with_profiles()
        del config["automation_profile"]
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_ssm_path(self):
        """Verify that validation exits when the SSM parameter path is empty."""
        config = _valid_config_with_roles()
        config["ssm_parameter_path"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_domain(self):
        """Verify that validation exits when the email domain is empty."""
        config = _valid_config_with_roles()
        config["email"]["domain"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_missing_email_prefix(self):
        """Verify that validation exits when the email prefix is empty."""
        config = _valid_config_with_roles()
        config["email"]["prefix"] = ""
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_email_override_skips_automation_and_email_validation(self):
        """Verify that email_override bypasses automation account and email setting validation."""
        config = {
            "mgmt_profile": "mgmt",
            "email_override": "custom@example.com",
        }
        result = validate_config(config)
        assert result["email_override"] == "custom@example.com"

    def test_email_override_still_requires_mgmt(self):
        """Verify that email_override still requires management account access to be configured."""
        config = {"email_override": "custom@example.com"}
        with pytest.raises(SystemExit):
            validate_config(config)
