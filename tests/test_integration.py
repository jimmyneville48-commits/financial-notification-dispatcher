import sqlite3
import pytest
from unittest.mock import Mock
from notification_engine import NotificationEngine


class SqliteWalletRepository:
    def __init__(self, conn, table_name="messages"):
        self.conn = conn
        self.table_name = table_name

    def get_status(self, msg_id):
        cur = self.conn.execute(
            f"SELECT status FROM {self.table_name} WHERE msg_id = ?", (msg_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def save_status(self, msg_id, phone, status):
        self.conn.execute(
            f"INSERT INTO {self.table_name} (msg_id, phone, status) VALUES (?, ?, ?)",
            (msg_id, phone, status),
        )
        self.conn.commit()


@pytest.fixture
def sqlite_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE messages (msg_id TEXT, phone TEXT, status TEXT)"
    )
    yield conn
    conn.close()


def test_successful_dispatch_persists_sent_status(sqlite_conn):
    repo = SqliteWalletRepository(sqlite_conn, table_name="messages")
    primary = Mock()
    primary.send_sms.return_value = True

    engine = NotificationEngine(repo, primary)
    result = engine.dispatch("msg1", "+250780000000", "hello")

    assert result == "SENT_PRIMARY"

    row = sqlite_conn.execute(
        "SELECT status FROM messages WHERE msg_id = ?", ("msg1",)
    ).fetchone()
    assert row is not None
    assert row[0] == "SENT"


class TestMockLie:

    def test_unit_test_passes_with_wrong_table_name(self):
        mock_repo = Mock()
        mock_repo.get_status.return_value = None
        primary = Mock()
        primary.send_sms.return_value = True

        engine = NotificationEngine(mock_repo, primary)
        result = engine.dispatch("msg1", "+250780000000", "hello")

        assert result == "SENT_PRIMARY"
        mock_repo.save_status.assert_called_once_with(
            "msg1", "+250780000000", "SENT"
        )

    def test_integration_test_fails_with_wrong_table_name(self, sqlite_conn):
        broken_repo = SqliteWalletRepository(sqlite_conn, table_name="msg_logs")
        primary = Mock()
        primary.send_sms.return_value = True

        engine = NotificationEngine(broken_repo, primary)

        with pytest.raises(sqlite3.OperationalError):
            engine.dispatch("msg1", "+250780000000", "hello")
