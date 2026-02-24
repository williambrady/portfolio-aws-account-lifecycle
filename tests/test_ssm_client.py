"""Tests for SSM parameter operations and session management."""

from unittest.mock import MagicMock, patch

import pytest

from src.ssm_client import get_session, increment_unique_number, read_unique_number


class TestGetSession:
    """Test session creation with profiles, role assumption, and region handling."""

    @patch("src.ssm_client.boto3")
    def test_with_profile(self, mock_boto3):
        """Verify that a session is created using the specified AWS profile and region."""
        get_session(profile_name="my-profile", region_name="us-east-1")
        mock_boto3.Session.assert_called_once_with(profile_name="my-profile", region_name="us-east-1")

    @patch("src.ssm_client.boto3")
    def test_with_role_arn(self, mock_boto3):
        """Verify that a session is created by assuming the specified IAM role."""
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        get_session(role_arn="arn:aws:iam::role/TestRole", region_name="us-east-1")

        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::role/TestRole",
            RoleSessionName="account-lifecycle",
        )
        mock_boto3.Session.assert_called_once_with(
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
            aws_session_token="TOKEN",
            region_name="us-east-1",
        )

    @patch("src.ssm_client.boto3")
    def test_with_role_arn_custom_session_name(self, mock_boto3):
        """Verify that a custom session name is used when assuming a role."""
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        get_session(role_arn="arn:aws:iam::role/TestRole", session_name="custom")

        mock_boto3.client.assert_called_once_with("sts", region_name="us-east-1")
        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::role/TestRole",
            RoleSessionName="custom",
        )

    @patch("src.ssm_client.boto3")
    def test_profile_takes_precedence_over_role(self, mock_boto3):
        """Verify that profile-based auth takes precedence when both profile and role ARN are provided."""
        get_session(profile_name="my-profile", role_arn="arn:aws:iam::role/TestRole")
        mock_boto3.Session.assert_called_once_with(profile_name="my-profile", region_name="us-east-1")
        mock_boto3.client.assert_not_called()

    @patch("src.ssm_client.boto3")
    def test_default_session_uses_default_region(self, mock_boto3):
        """Verify that a default session uses us-east-1 when no region is specified."""
        get_session()
        mock_boto3.Session.assert_called_once_with(region_name="us-east-1")

    @patch("src.ssm_client.boto3")
    def test_explicit_region_overrides_default(self, mock_boto3):
        """Verify that an explicitly provided region overrides the default region."""
        get_session(region_name="eu-west-1")
        mock_boto3.Session.assert_called_once_with(region_name="eu-west-1")


class TestReadUniqueNumber:
    """Test reading the unique number SSM parameter with valid and invalid values."""

    def test_read_existing_parameter(self):
        """Verify that an existing SSM parameter value is read and returned as an integer."""
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "42"}}

        result = read_unique_number(mock_session, "/test/unique-number")

        assert result == 42
        mock_ssm.get_parameter.assert_called_once_with(Name="/test/unique-number")

    def test_parameter_not_found(self):
        """Verify that a missing SSM parameter causes a system exit."""
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error
        mock_ssm.get_parameter.side_effect = error()

        with pytest.raises(SystemExit):
            read_unique_number(mock_session, "/test/missing")

    def test_invalid_integer_value(self):
        """Verify that a non-integer SSM parameter value causes a system exit."""
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "not-a-number"}}

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error

        with pytest.raises(SystemExit):
            read_unique_number(mock_session, "/test/bad-value")


class TestIncrementUniqueNumber:
    """Test incrementing the unique number SSM parameter."""

    def test_increment_value(self):
        """Verify that the SSM parameter is incremented by one and written back."""
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm

        result = increment_unique_number(mock_session, "/test/unique-number", 42)

        assert result == 43
        mock_ssm.put_parameter.assert_called_once_with(
            Name="/test/unique-number",
            Value="43",
            Type="String",
            Overwrite=True,
        )
