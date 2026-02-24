"""Tests for account closure operations."""

from unittest.mock import MagicMock, patch

from src.account_closer import (
    build_closure_output,
    close_account,
    find_account_by_email,
    list_member_accounts,
    poll_account_closure,
)


class TestListMemberAccounts:
    """Test listing member accounts from an AWS Organization."""

    def test_excludes_management_account(self):
        """Verify that the management account is excluded from the returned member list."""
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {"Organization": {"ManagementAccountId": "111111111111"}}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "111111111111", "Name": "management", "Email": "mgmt@example.com", "Status": "ACTIVE"},
                    {"Id": "222222222222", "Name": "member-1", "Email": "m1@example.com", "Status": "ACTIVE"},
                    {"Id": "333333333333", "Name": "member-2", "Email": "m2@example.com", "Status": "ACTIVE"},
                ]
            }
        ]

        result = list_member_accounts(mock_client)

        assert len(result) == 2
        assert all(a["Id"] != "111111111111" for a in result)

    def test_empty_org_returns_empty_list(self):
        """Verify that an organization with only the management account returns an empty list."""
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {"Organization": {"ManagementAccountId": "111111111111"}}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "111111111111", "Name": "management", "Email": "mgmt@example.com"}]}
        ]

        result = list_member_accounts(mock_client)
        assert not result

    def test_multiple_pages(self):
        """Verify that accounts from multiple paginated responses are aggregated correctly."""
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {"Organization": {"ManagementAccountId": "111111111111"}}
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "222222222222", "Name": "member-1"}]},
            {"Accounts": [{"Id": "333333333333", "Name": "member-2"}]},
        ]

        result = list_member_accounts(mock_client)
        assert len(result) == 2


class TestFindAccountByEmail:
    """Test finding an AWS account by its email address."""

    def test_finds_matching_account(self):
        """Verify that the correct account is returned when a matching email exists."""
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "222222222222", "Email": "other@example.com"},
                    {"Id": "333333333333", "Email": "target@example.com"},
                ]
            }
        ]

        result = find_account_by_email(mock_client, "target@example.com")
        assert result["Id"] == "333333333333"

    def test_returns_none_when_not_found(self):
        """Verify that None is returned when no account matches the given email."""
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Accounts": [{"Id": "222222222222", "Email": "other@example.com"}]}]

        result = find_account_by_email(mock_client, "missing@example.com")
        assert result is None


class TestCloseAccount:
    """Test the account closure API call and error handling."""

    def test_close_account_success(self):
        """Verify that a successful close_account call returns True."""
        mock_client = MagicMock()
        mock_client.close_account.return_value = {}

        result = close_account(mock_client, "222222222222")

        assert result is True
        mock_client.close_account.assert_called_once_with(AccountId="222222222222")

    def test_close_already_closed_account(self):
        """Verify that closing an already-closed account returns True without raising an error."""
        mock_client = MagicMock()
        mock_client.exceptions.AccountAlreadyClosedException = type("AccountAlreadyClosedException", (Exception,), {})
        mock_client.close_account.side_effect = mock_client.exceptions.AccountAlreadyClosedException()

        result = close_account(mock_client, "222222222222")
        assert result is True


class TestPollAccountClosure:
    """Test polling logic for account closure status transitions."""

    def test_returns_immediately_when_suspended(self):
        """Verify that polling returns immediately when the account is already SUSPENDED."""
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {"Account": {"Id": "222222222222", "Status": "SUSPENDED"}}

        result = poll_account_closure(mock_client, "222222222222", max_attempts=3, interval=0)
        assert result == "SUSPENDED"
        assert mock_client.describe_account.call_count == 1

    def test_returns_pending_closure(self):
        """Verify that PENDING_CLOSURE status is returned as a terminal polling state."""
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {"Account": {"Id": "222222222222", "Status": "PENDING_CLOSURE"}}

        result = poll_account_closure(mock_client, "222222222222", max_attempts=3, interval=0)
        assert result == "PENDING_CLOSURE"

    @patch("src.account_closer.time.sleep")
    def test_polls_until_not_active(self, mock_sleep):
        """Verify that polling retries while ACTIVE and stops when status changes to SUSPENDED."""
        mock_client = MagicMock()
        mock_client.describe_account.side_effect = [
            {"Account": {"Id": "222222222222", "Status": "ACTIVE"}},
            {"Account": {"Id": "222222222222", "Status": "ACTIVE"}},
            {"Account": {"Id": "222222222222", "Status": "SUSPENDED"}},
        ]

        result = poll_account_closure(mock_client, "222222222222", max_attempts=5, interval=5)
        assert result == "SUSPENDED"
        assert mock_client.describe_account.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.account_closer.time.sleep")
    def test_returns_active_on_timeout(self, _mock_sleep):
        """Verify that ACTIVE status is returned when max polling attempts are exhausted."""
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {"Account": {"Id": "222222222222", "Status": "ACTIVE"}}

        result = poll_account_closure(mock_client, "222222222222", max_attempts=2, interval=5)
        assert result == "ACTIVE"
        assert mock_client.describe_account.call_count == 2


class TestBuildClosureOutput:
    """Test construction of the closure output dictionary."""

    def test_build_output_structure(self):
        """Verify that all provided fields are correctly included in the output dictionary."""
        result = build_closure_output(
            account_id="222222222222",
            account_name="test-account",
            email="test@example.com",
            status="SUSPENDED",
            closed_at="2026-02-24T12:00:00+00:00",
        )

        assert result["account_id"] == "222222222222"
        assert result["account_name"] == "test-account"
        assert result["email"] == "test@example.com"
        assert result["status"] == "SUSPENDED"
        assert result["closed_at"] == "2026-02-24T12:00:00+00:00"

    def test_auto_timestamp(self):
        """Verify that a closed_at timestamp is auto-generated when not explicitly provided."""
        result = build_closure_output("222", "test", "t@t.com", "SUSPENDED")
        assert "closed_at" in result
