"""
Unit tests for FeedbackStore.

Tests cover:
- Table auto-creation
- Rule save / retrieve / delete
- Feedback log recording
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feedback.store import FeedbackStore
from models import ImprovementRule


@pytest.fixture
def store(tmp_path):
    """Create a FeedbackStore backed by a temporary SQLite file."""
    db_path = str(tmp_path / "test_feedback.db")
    return FeedbackStore(db_path=db_path)


def test_tables_created_on_init(store):
    """Tables should exist after initialization."""
    import sqlite3
    conn = sqlite3.connect(store.db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "improvement_rules" in tables
    assert "feedback_logs" in tables


def test_save_and_get_all_rules(store):
    """Saved rules should be retrievable via get_all_rules."""
    embedding = [0.1, 0.2, 0.3]
    rule_id = store.save_rule("query1", "answer1", "improve this", embedding)
    assert isinstance(rule_id, int)

    rules = store.get_all_rules()
    assert len(rules) == 1
    assert rules[0].query_text == "query1"
    assert rules[0].improvement_request == "improve this"


def test_get_rules_with_embeddings(store):
    """get_rules_with_embeddings should return rules with their vectors."""
    embedding = [0.5, 0.6, 0.7]
    store.save_rule("q", "a", "fix it", embedding)

    results = store.get_rules_with_embeddings()
    assert len(results) == 1
    rule, vec = results[0]
    assert rule.improvement_request == "fix it"
    assert vec == pytest.approx(embedding)


def test_delete_existing_rule(store):
    """delete_rule should return True and remove the rule."""
    store.save_rule("q", "a", "improve", [0.1])
    rules = store.get_all_rules()
    rule_id = rules[0].id

    deleted = store.delete_rule(rule_id)
    assert deleted is True
    assert store.get_all_rules() == []


def test_delete_nonexistent_rule(store):
    """delete_rule should return False for a non-existent ID."""
    assert store.delete_rule(9999) is False


def test_log_feedback(store):
    """log_feedback should insert a row into feedback_logs."""
    store.log_feedback("msg1", "some query", "positive")

    import sqlite3
    conn = sqlite3.connect(store.db_path)
    rows = conn.execute("SELECT * FROM feedback_logs").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][1] == "msg1"
    assert rows[0][3] == "positive"


def test_multiple_rules_order(store):
    """Rules should be returned in insertion order."""
    for i in range(3):
        store.save_rule(f"q{i}", f"a{i}", f"rule{i}", [float(i)])

    rules = store.get_all_rules()
    assert [r.improvement_request for r in rules] == ["rule0", "rule1", "rule2"]
