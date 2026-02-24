"""Tests for account creation, OU placement, and validation."""

from unittest.mock import MagicMock, patch

import pytest

from src.account_creator import (
    build_output,
    create_account,
    find_ou_by_name,
    generate_email,
    move_account_to_ou,
    poll_account_creation,
    sanitize_account_name,
    validate_account_access,
)


class TestSanitizeAccountName:
    """Test account name sanitization logic."""

    def test_lowercase(self):
        """Verify that uppercase characters are converted to lowercase."""
        assert sanitize_account_name("My-Account") == "my-account"

    def test_spaces_replaced(self):
        """Verify that spaces are replaced with hyphens."""
        assert sanitize_account_name("my account") == "my-account"

    def test_special_chars_replaced(self):
        """Verify that special characters are replaced with hyphens."""
        assert sanitize_account_name("my_account!@#") == "my-account"

    def test_consecutive_hyphens_collapsed(self):
        """Verify that consecutive hyphens are collapsed into a single hyphen."""
        assert sanitize_account_name("my---account") == "my-account"

    def test_leading_trailing_hyphens_stripped(self):
        """Verify that leading and trailing hyphens are stripped."""
        assert sanitize_account_name("-my-account-") == "my-account"

    def test_truncated_to_60_chars(self):
        """Verify that names longer than 60 characters are truncated."""
        long_name = "a" * 100
        assert len(sanitize_account_name(long_name)) == 60

    def test_already_clean(self):
        """Verify that an already-clean name passes through unchanged."""
        assert sanitize_account_name("my-account") == "my-account"


class TestGenerateEmail:
    """Test email address generation from config, org number, and account name."""

    def test_standard_email(self):
        """Verify that a standard email is generated with the correct format."""
        config = {"email": {"prefix": "will", "domain": "crofton.cloud"}}
        result = generate_email(config, 5, "my-account")
        assert result == "will+5-my-account@crofton.cloud"

    def test_different_prefix_and_domain(self):
        """Verify that custom prefix and domain values are used correctly."""
        config = {"email": {"prefix": "admin", "domain": "example.com"}}
        result = generate_email(config, 100, "prod")
        assert result == "admin+100-prod@example.com"

    def test_sanitizes_account_name(self):
        """Verify that the account name is sanitized before embedding in the email."""
        config = {"email": {"prefix": "will", "domain": "crofton.cloud"}}
        result = generate_email(config, 5, "My Account!")
        assert result == "will+5-my-account@crofton.cloud"


class TestCreateAccount:
    """Test AWS Organizations create_account API calls."""

    def test_create_account_calls_api(self):
        """Verify that create_account invokes the API with correct parameters and returns the status."""
        mock_client = MagicMock()
        mock_client.create_account.return_value = {"CreateAccountStatus": {"Id": "req-123", "State": "IN_PROGRESS"}}

        result = create_account(mock_client, "test-account", "test@example.com", {"Env": "dev"})

        mock_client.create_account.assert_called_once_with(
            Email="test@example.com",
            AccountName="test-account",
            Tags=[{"Key": "Env", "Value": "dev"}],
        )
        assert result["Id"] == "req-123"


class TestPollAccountCreation:
    """Test polling logic for account creation status."""

    def test_succeeds_immediately(self):
        """Verify that polling returns immediately when the status is SUCCEEDED."""
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {"State": "SUCCEEDED", "AccountId": "123456789012"}
        }

        result = poll_account_creation(mock_client, "req-123", max_attempts=3, interval=0)
        assert result["AccountId"] == "123456789012"

    def test_succeeds_after_retries(self):
        """Verify that polling succeeds after multiple IN_PROGRESS responses."""
        mock_client = MagicMock()
        mock_client.describe_create_account_status.side_effect = [
            {"CreateAccountStatus": {"State": "IN_PROGRESS"}},
            {"CreateAccountStatus": {"State": "IN_PROGRESS"}},
            {"CreateAccountStatus": {"State": "SUCCEEDED", "AccountId": "123456789012"}},
        ]

        result = poll_account_creation(mock_client, "req-123", max_attempts=5, interval=0)
        assert result["AccountId"] == "123456789012"
        assert mock_client.describe_create_account_status.call_count == 3

    def test_fails_on_failure_state(self):
        """Verify that polling exits with an error when the status is FAILED."""
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {"State": "FAILED", "FailureReason": "EMAIL_ALREADY_EXISTS"}
        }

        with pytest.raises(SystemExit):
            poll_account_creation(mock_client, "req-123", max_attempts=3, interval=0)

    def test_fails_on_timeout(self):
        """Verify that polling exits with an error when max attempts are exhausted."""
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {"CreateAccountStatus": {"State": "IN_PROGRESS"}}

        with pytest.raises(SystemExit):
            poll_account_creation(mock_client, "req-123", max_attempts=2, interval=0)


class TestFindOuByName:
    """Test OU lookup by name within the organization hierarchy."""

    def test_find_top_level_ou(self):
        """Verify that a top-level OU is found by its name."""
        mock_client = MagicMock()
        mock_client.list_roots.return_value = {"Roots": [{"Id": "r-root"}]}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"OrganizationalUnits": [{"Id": "ou-123", "Name": "Non-Production"}]}]

        result = find_ou_by_name(mock_client, "Non-Production")
        assert result["Id"] == "ou-123"
        assert result["Name"] == "Non-Production"

    def test_ou_not_found(self):
        """Verify that None is returned when the OU name does not exist."""
        mock_client = MagicMock()
        mock_client.list_roots.return_value = {"Roots": [{"Id": "r-root"}]}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"OrganizationalUnits": []}]

        result = find_ou_by_name(mock_client, "Missing-OU")
        assert result is None


class TestMoveAccountToOu:
    """Test moving an account from its current parent to a target OU."""

    def test_move_account(self):
        """Verify that move_account calls the API with correct source and destination."""
        mock_client = MagicMock()
        mock_client.list_parents.return_value = {"Parents": [{"Id": "r-root"}]}

        move_account_to_ou(mock_client, "123456789012", "ou-dest")

        mock_client.move_account.assert_called_once_with(
            AccountId="123456789012",
            SourceParentId="r-root",
            DestinationParentId="ou-dest",
        )

    def test_already_in_target_ou(self):
        """Verify that no move is performed when the account is already in the target OU."""
        mock_client = MagicMock()
        mock_client.list_parents.return_value = {"Parents": [{"Id": "ou-dest"}]}

        move_account_to_ou(mock_client, "123456789012", "ou-dest")

        mock_client.move_account.assert_not_called()


class TestValidateAccountAccess:
    """Test cross-account role assumption validation with retry logic."""

    @patch("src.account_creator.boto3")
    def test_successful_validation_first_attempt(self, mock_boto3):
        """Verify that validation succeeds on the first assume-role attempt."""
        mock_mgmt_session = MagicMock()
        mock_mgmt_sts = MagicMock()
        mock_mgmt_session.client.return_value = mock_mgmt_sts
        mock_mgmt_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }
        mock_new_session = MagicMock()
        mock_boto3.Session.return_value = mock_new_session
        mock_new_session.client.return_value.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::123456789012:assumed-role/OrganizationAccountAccessRole/validation"
        }

        result = validate_account_access(mock_mgmt_session, "123456789012", "OrganizationAccountAccessRole")
        assert result is True
        assert mock_mgmt_sts.assume_role.call_count == 1

    @patch("src.account_creator.time.sleep")
    @patch("src.account_creator.boto3")
    def test_successful_validation_after_retries(self, mock_boto3, mock_sleep):
        """Verify that validation succeeds after transient assume-role failures."""
        mock_mgmt_session = MagicMock()
        mock_mgmt_sts = MagicMock()
        mock_mgmt_session.client.return_value = mock_mgmt_sts
        mock_mgmt_sts.assume_role.side_effect = [
            Exception("Access denied"),
            Exception("Access denied"),
            {
                "Credentials": {
                    "AccessKeyId": "AKID",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            },
        ]
        mock_new_session = MagicMock()
        mock_boto3.Session.return_value = mock_new_session
        mock_new_session.client.return_value.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::123456789012:assumed-role/OrganizationAccountAccessRole/validation"
        }

        result = validate_account_access(mock_mgmt_session, "123456789012", "OrganizationAccountAccessRole")
        assert result is True
        assert mock_mgmt_sts.assume_role.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.account_creator.time.sleep")
    def test_failed_validation_exhausts_retries(self, mock_sleep):
        """Verify that validation returns False after all retry attempts are exhausted."""
        mock_mgmt_session = MagicMock()
        mock_mgmt_sts = MagicMock()
        mock_mgmt_session.client.return_value = mock_mgmt_sts
        mock_mgmt_sts.assume_role.side_effect = Exception("Access denied")

        result = validate_account_access(
            mock_mgmt_session, "123456789012", "OrganizationAccountAccessRole", max_attempts=3, initial_delay=1
        )
        assert result is False
        assert mock_mgmt_sts.assume_role.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.account_creator.time.sleep")
    def test_exponential_backoff(self, mock_sleep):
        """Verify that retry delays follow an exponential backoff pattern."""
        mock_mgmt_session = MagicMock()
        mock_mgmt_sts = MagicMock()
        mock_mgmt_session.client.return_value = mock_mgmt_sts
        mock_mgmt_sts.assume_role.side_effect = Exception("Access denied")

        validate_account_access(
            mock_mgmt_session,
            "123456789012",
            "OrganizationAccountAccessRole",
            max_attempts=4,
            initial_delay=5,
            max_delay=30,
        )
        mock_sleep.assert_any_call(5)
        mock_sleep.assert_any_call(10)
        mock_sleep.assert_any_call(20)


class TestBuildOutput:
    """Test JSON output structure construction."""

    def test_build_output_structure(self):
        """Verify that build_output returns all expected fields with correct values."""
        result = build_output(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            ou_id="ou-123",
            ou_name="Non-Production",
            validated=True,
            created_at="2024-01-01T00:00:00+00:00",
        )

        assert result["account_id"] == "123456789012"
        assert result["account_name"] == "test-account"
        assert result["email"] == "test@example.com"
        assert result["ou_id"] == "ou-123"
        assert result["ou_name"] == "Non-Production"
        assert result["validated"] is True
        assert result["status"] == "SUCCEEDED"
        assert result["created_at"] == "2024-01-01T00:00:00+00:00"

    def test_build_output_auto_timestamp(self):
        """Verify that build_output generates a created_at timestamp when none is provided."""
        result = build_output("123", "test", "t@t.com", "ou-1", "OU", True)
        assert "created_at" in result
