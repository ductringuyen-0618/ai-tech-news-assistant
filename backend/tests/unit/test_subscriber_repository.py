"""
Unit Tests for Subscriber Repository
====================================

Tests for digest email-capture data access operations.
"""

from src.repositories.subscriber_repository import SubscriberRepository


class TestSubscriberRepository:
    """Test cases for SubscriberRepository."""

    def test_subscribe_new_email(self, temp_db_path):
        repository = SubscriberRepository(db_path=temp_db_path)

        result = repository.subscribe("reader@example.com")

        assert result["id"] is not None
        assert result["email"] == "reader@example.com"
        assert result["is_active"] is True

    def test_subscribe_duplicate_email_is_idempotent(self, temp_db_path):
        repository = SubscriberRepository(db_path=temp_db_path)

        first = repository.subscribe("reader@example.com")
        second = repository.subscribe("reader@example.com")

        assert first["id"] == second["id"]
        assert repository.count_active() == 1

    def test_resubscribe_reactivates_inactive_row(self, temp_db_path):
        repository = SubscriberRepository(db_path=temp_db_path)
        created = repository.subscribe("reader@example.com")

        import sqlite3

        with sqlite3.connect(temp_db_path) as conn:
            conn.execute(
                "UPDATE subscribers SET is_active = 0 WHERE id = ?",
                (created["id"],),
            )
            conn.commit()

        assert repository.count_active() == 0

        result = repository.subscribe("reader@example.com")

        assert result["id"] == created["id"]
        assert result["is_active"] is True
        assert repository.count_active() == 1

    def test_get_by_email_not_found(self, temp_db_path):
        repository = SubscriberRepository(db_path=temp_db_path)

        assert repository.get_by_email("nobody@example.com") is None

    def test_count_active_multiple_subscribers(self, temp_db_path):
        repository = SubscriberRepository(db_path=temp_db_path)

        repository.subscribe("a@example.com")
        repository.subscribe("b@example.com")

        assert repository.count_active() == 2
