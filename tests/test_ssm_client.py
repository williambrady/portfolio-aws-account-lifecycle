from unittest.mock import MagicMock, patch

import pytest

from src.ssm_client import get_session, increment_unique_number, read_unique_number


class TestGetSession:
    @patch("src.ssm_client.boto3")
    def test_with_profile(self, mock_boto3):
        get_session(profile_name="my-profile", region_name="us-east-1")
        mock_boto3.Session.assert_called_once_with(profile_name="my-profile", region_name="us-east-1")

    @patch("src.ssm_client.boto3")
    def test_with_role_arn(self, mock_boto3):
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
        get_session(profile_name="my-profile", role_arn="arn:aws:iam::role/TestRole")
        mock_boto3.Session.assert_called_once_with(profile_name="my-profile", region_name="us-east-1")
        mock_boto3.client.assert_not_called()

    @patch("src.ssm_client.boto3")
    def test_default_session_uses_default_region(self, mock_boto3):
        get_session()
        mock_boto3.Session.assert_called_once_with(region_name="us-east-1")

    @patch("src.ssm_client.boto3")
    def test_explicit_region_overrides_default(self, mock_boto3):
        get_session(region_name="eu-west-1")
        mock_boto3.Session.assert_called_once_with(region_name="eu-west-1")


class TestReadUniqueNumber:
    def test_read_existing_parameter(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "42"}}

        result = read_unique_number(mock_session, "/test/unique-number")

        assert result == 42
        mock_ssm.get_parameter.assert_called_once_with(Name="/test/unique-number")

    def test_parameter_not_found(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error
        mock_ssm.get_parameter.side_effect = error()

        with pytest.raises(SystemExit):
            read_unique_number(mock_session, "/test/missing")

    def test_invalid_integer_value(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "not-a-number"}}

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error

        with pytest.raises(SystemExit):
            read_unique_number(mock_session, "/test/bad-value")


class TestIncrementUniqueNumber:
    def test_increment_value(self):
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
