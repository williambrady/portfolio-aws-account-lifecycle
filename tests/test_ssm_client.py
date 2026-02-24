from unittest.mock import MagicMock, patch

import pytest

from src.ssm_client import assume_role, increment_org_number, read_org_number


class TestAssumeRole:
    @patch("src.ssm_client.boto3")
    def test_assume_role_returns_session(self, mock_boto3):
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        assume_role("arn:aws:iam::role/TestRole")

        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::role/TestRole",
            RoleSessionName="account-lifecycle",
        )
        mock_boto3.Session.assert_called_once_with(
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
            aws_session_token="TOKEN",
        )

    @patch("src.ssm_client.boto3")
    def test_assume_role_custom_session_name(self, mock_boto3):
        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        assume_role("arn:aws:iam::role/TestRole", "custom-session")

        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::role/TestRole",
            RoleSessionName="custom-session",
        )


class TestReadOrgNumber:
    def test_read_existing_parameter(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "42"}}

        result = read_org_number(mock_session, "/test/org-number")

        assert result == 42
        mock_ssm.get_parameter.assert_called_once_with(Name="/test/org-number")

    def test_parameter_not_found(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error
        mock_ssm.get_parameter.side_effect = error()

        with pytest.raises(SystemExit):
            read_org_number(mock_session, "/test/missing")

    def test_invalid_integer_value(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "not-a-number"}}

        error = type("ParameterNotFound", (Exception,), {})
        mock_ssm.exceptions.ParameterNotFound = error

        with pytest.raises(SystemExit):
            read_org_number(mock_session, "/test/bad-value")


class TestIncrementOrgNumber:
    def test_increment_value(self):
        mock_session = MagicMock()
        mock_ssm = MagicMock()
        mock_session.client.return_value = mock_ssm

        result = increment_org_number(mock_session, "/test/org-number", 42)

        assert result == 43
        mock_ssm.put_parameter.assert_called_once_with(
            Name="/test/org-number",
            Value="43",
            Type="String",
            Overwrite=True,
        )
