from unittest.mock import MagicMock, patch

from src.account_closer import (
    build_closure_output,
    close_account,
    find_account_by_email,
    list_member_accounts,
    poll_account_closure,
)


class TestListMemberAccounts:
    def test_excludes_management_account(self):
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {
            "Organization": {"MasterAccountId": "111111111111"}
        }
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
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {
            "Organization": {"MasterAccountId": "111111111111"}
        }
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "111111111111", "Name": "management", "Email": "mgmt@example.com"}]}
        ]

        result = list_member_accounts(mock_client)
        assert result == []

    def test_multiple_pages(self):
        mock_client = MagicMock()
        mock_client.describe_organization.return_value = {
            "Organization": {"MasterAccountId": "111111111111"}
        }
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "222222222222", "Name": "member-1"}]},
            {"Accounts": [{"Id": "333333333333", "Name": "member-2"}]},
        ]

        result = list_member_accounts(mock_client)
        assert len(result) == 2


class TestFindAccountByEmail:
    def test_finds_matching_account(self):
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
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "222222222222", "Email": "other@example.com"}]}
        ]

        result = find_account_by_email(mock_client, "missing@example.com")
        assert result is None


class TestCloseAccount:
    def test_close_account_success(self):
        mock_client = MagicMock()
        mock_client.close_account.return_value = {}

        result = close_account(mock_client, "222222222222")

        assert result is True
        mock_client.close_account.assert_called_once_with(AccountId="222222222222")

    def test_close_already_closed_account(self):
        mock_client = MagicMock()
        mock_client.exceptions.AccountAlreadyClosedException = type("AccountAlreadyClosedException", (Exception,), {})
        mock_client.close_account.side_effect = mock_client.exceptions.AccountAlreadyClosedException()

        result = close_account(mock_client, "222222222222")
        assert result is True


class TestPollAccountClosure:
    def test_returns_immediately_when_suspended(self):
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {
            "Account": {"Id": "222222222222", "Status": "SUSPENDED"}
        }

        result = poll_account_closure(mock_client, "222222222222", max_attempts=3, interval=0)
        assert result == "SUSPENDED"
        assert mock_client.describe_account.call_count == 1

    def test_returns_pending_closure(self):
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {
            "Account": {"Id": "222222222222", "Status": "PENDING_CLOSURE"}
        }

        result = poll_account_closure(mock_client, "222222222222", max_attempts=3, interval=0)
        assert result == "PENDING_CLOSURE"

    @patch("src.account_closer.time.sleep")
    def test_polls_until_not_active(self, mock_sleep):
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
    def test_returns_active_on_timeout(self, mock_sleep):
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {
            "Account": {"Id": "222222222222", "Status": "ACTIVE"}
        }

        result = poll_account_closure(mock_client, "222222222222", max_attempts=2, interval=5)
        assert result == "ACTIVE"
        assert mock_client.describe_account.call_count == 2


class TestBuildClosureOutput:
    def test_build_output_structure(self):
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
        result = build_closure_output("222", "test", "t@t.com", "SUSPENDED")
        assert "closed_at" in result
