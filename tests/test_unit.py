import pytest
from unittest.mock import Mock
from notification_engine import NotificationEngine


@pytest.fixture
def mock_repo():
    return Mock()


@pytest.fixture
def mock_primary():
    return Mock()


@pytest.fixture
def mock_backup():
    return Mock()


@pytest.fixture
def engine(mock_repo, mock_primary, mock_backup):
    return NotificationEngine(mock_repo, mock_primary, mock_backup)


class TestValidationBoundary:

    def test_valid_e164_number_is_accepted(self, engine, mock_repo, mock_primary):
        mock_repo.get_status.return_value = None
        mock_primary.send_sms.return_value = True

        result = engine.dispatch("msg1", "+250780000000", "hello")

        assert result == "SENT_PRIMARY"

    @pytest.mark.parametrize("bad_phone", ["0780000000", "+00012"])
    def test_invalid_number_raises_without_touching_repo(self, engine, mock_repo, bad_phone):
        with pytest.raises(ValueError, match="Invalid E.164 phone number format"):
            engine.dispatch("msg1", bad_phone, "hello")

        mock_repo.get_status.assert_not_called()
        mock_repo.save_status.assert_not_called()


class TestIdempotency:

    def test_already_sent_short_circuits(self, engine, mock_repo, mock_primary, mock_backup):
        mock_repo.get_status.return_value = "SENT"

        result = engine.dispatch("msg1", "+250780000000", "hello")

        assert result == "ALREADY_SENT"
        mock_primary.send_sms.assert_not_called()
        mock_backup.send_sms.assert_not_called()


class TestRetryLogic:

    def test_primary_fails_once_then_succeeds(self, engine, mock_repo, mock_primary):
        mock_repo.get_status.return_value = None
        mock_primary.send_sms.side_effect = [Exception("timeout"), True]

        result = engine.dispatch("msg1", "+250780000000", "hello")

        assert result == "SENT_PRIMARY"
        assert mock_primary.send_sms.call_count == 2
        mock_repo.save_status.assert_called_once_with("msg1", "+250780000000", "SENT")


class TestFailover:

    def test_primary_fails_twice_backup_succeeds(self, engine, mock_repo, mock_primary, mock_backup):
        mock_repo.get_status.return_value = None
        mock_primary.send_sms.side_effect = Exception("down")
        mock_backup.send_sms.return_value = True

        result = engine.dispatch("msg1", "+250780000000", "hello")

        assert result == "SENT_BACKUP"
        assert mock_primary.send_sms.call_count == 2
        mock_repo.save_status.assert_called_once_with("msg1", "+250780000000", "SENT_BACKUP")


class TestCompleteFailure:

    def test_both_gateways_fail(self, engine, mock_repo, mock_primary, mock_backup):
        mock_repo.get_status.return_value = None
        mock_primary.send_sms.side_effect = Exception("down")
        mock_backup.send_sms.side_effect = Exception("down")

        with pytest.raises(RuntimeError, match="All gateways failed to deliver message"):
            engine.dispatch("msg1", "+250780000000", "hello")

        mock_repo.save_status.assert_called_once_with("msg1", "+250780000000", "FAILED")
