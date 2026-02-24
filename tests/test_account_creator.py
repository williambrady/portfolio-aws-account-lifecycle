from unittest.mock import MagicMock, patch

import pytest

from src.account_creator import (
    build_output,
    create_account,
    find_ou_by_name,
    generate_email,
    move_account_to_ou,
    poll_account_creation,
    validate_account_access,
)


class TestGenerateEmail:
    def test_standard_email(self):
        config = {"email": {"prefix": "will", "domain": "crofton.cloud"}}
        result = generate_email(config, 5, "my-account")
        assert result == "will+rc-org-5-my-account@crofton.cloud"

    def test_different_prefix_and_domain(self):
        config = {"email": {"prefix": "admin", "domain": "example.com"}}
        result = generate_email(config, 100, "prod")
        assert result == "admin+rc-org-100-prod@example.com"


class TestCreateAccount:
    def test_create_account_calls_api(self):
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
    def test_succeeds_immediately(self):
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {"State": "SUCCEEDED", "AccountId": "123456789012"}
        }

        result = poll_account_creation(mock_client, "req-123", max_attempts=3, interval=0)
        assert result["AccountId"] == "123456789012"

    def test_succeeds_after_retries(self):
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
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {"State": "FAILED", "FailureReason": "EMAIL_ALREADY_EXISTS"}
        }

        with pytest.raises(SystemExit):
            poll_account_creation(mock_client, "req-123", max_attempts=3, interval=0)

    def test_fails_on_timeout(self):
        mock_client = MagicMock()
        mock_client.describe_create_account_status.return_value = {"CreateAccountStatus": {"State": "IN_PROGRESS"}}

        with pytest.raises(SystemExit):
            poll_account_creation(mock_client, "req-123", max_attempts=2, interval=0)


class TestFindOuByName:
    def test_find_top_level_ou(self):
        mock_client = MagicMock()
        mock_client.list_roots.return_value = {"Roots": [{"Id": "r-root"}]}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"OrganizationalUnits": [{"Id": "ou-123", "Name": "Non-Production"}]}]

        result = find_ou_by_name(mock_client, "Non-Production")
        assert result["Id"] == "ou-123"
        assert result["Name"] == "Non-Production"

    def test_ou_not_found(self):
        mock_client = MagicMock()
        mock_client.list_roots.return_value = {"Roots": [{"Id": "r-root"}]}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"OrganizationalUnits": []}]

        result = find_ou_by_name(mock_client, "Missing-OU")
        assert result is None


class TestMoveAccountToOu:
    def test_move_account(self):
        mock_client = MagicMock()
        mock_client.list_parents.return_value = {"Parents": [{"Id": "r-root"}]}

        move_account_to_ou(mock_client, "123456789012", "ou-dest")

        mock_client.move_account.assert_called_once_with(
            AccountId="123456789012",
            SourceParentId="r-root",
            DestinationParentId="ou-dest",
        )

    def test_already_in_target_ou(self):
        mock_client = MagicMock()
        mock_client.list_parents.return_value = {"Parents": [{"Id": "ou-dest"}]}

        move_account_to_ou(mock_client, "123456789012", "ou-dest")

        mock_client.move_account.assert_not_called()


class TestValidateAccountAccess:
    @patch("src.account_creator.boto3")
    def test_successful_validation(self, mock_boto3):
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }
        mock_session = MagicMock()
        mock_boto3.Session.return_value = mock_session
        mock_session.client.return_value.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::123456789012:assumed-role/OrganizationAccountAccessRole/validation"
        }

        result = validate_account_access("123456789012", "OrganizationAccountAccessRole")
        assert result is True

    @patch("src.account_creator.boto3")
    def test_failed_validation(self, mock_boto3):
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.side_effect = Exception("Access denied")

        result = validate_account_access("123456789012", "OrganizationAccountAccessRole")
        assert result is False


class TestBuildOutput:
    def test_build_output_structure(self):
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
        result = build_output("123", "test", "t@t.com", "ou-1", "OU", True)
        assert "created_at" in result
