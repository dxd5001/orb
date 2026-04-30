"""
Unit tests for RuleRetriever.

Tests cover:
- Cosine similarity search
- top_k=0 returns empty list
- Empty store returns empty list
- Exception safety
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feedback.store import FeedbackStore
from feedback.retriever import RuleRetriever


@pytest.fixture
def store(tmp_path):
    return FeedbackStore(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def mock_embedding_backend():
    backend = MagicMock()
    # Default: return a unit vector
    backend.embed.return_value = [[1.0, 0.0, 0.0]]
    return backend


def test_empty_store_returns_empty(store, mock_embedding_backend):
    retriever = RuleRetriever(store, mock_embedding_backend)
    assert retriever.retrieve_rules("any query") == []


def test_top_k_zero_returns_empty(store, mock_embedding_backend):
    store.save_rule("q", "a", "rule", [1.0, 0.0, 0.0])
    retriever = RuleRetriever(store, mock_embedding_backend)
    assert retriever.retrieve_rules("query", top_k=0) == []


def test_top_k_negative_returns_empty(store, mock_embedding_backend):
    store.save_rule("q", "a", "rule", [1.0, 0.0, 0.0])
    retriever = RuleRetriever(store, mock_embedding_backend)
    assert retriever.retrieve_rules("query", top_k=-1) == []


def test_retrieves_most_similar_rule(store, mock_embedding_backend):
    """Rule with highest cosine similarity should be returned first."""
    # Rule A: parallel to query vector → similarity 1.0
    store.save_rule("q1", "a1", "rule_A", [1.0, 0.0, 0.0])
    # Rule B: orthogonal → similarity 0.0
    store.save_rule("q2", "a2", "rule_B", [0.0, 1.0, 0.0])

    mock_embedding_backend.embed.return_value = [[1.0, 0.0, 0.0]]
    retriever = RuleRetriever(store, mock_embedding_backend)
    results = retriever.retrieve_rules("query", top_k=2)

    assert len(results) == 2
    assert results[0].improvement_request == "rule_A"
    assert results[1].improvement_request == "rule_B"


def test_top_k_limits_results(store, mock_embedding_backend):
    for i in range(5):
        store.save_rule(f"q{i}", f"a{i}", f"rule{i}", [1.0, 0.0, 0.0])

    mock_embedding_backend.embed.return_value = [[1.0, 0.0, 0.0]]
    retriever = RuleRetriever(store, mock_embedding_backend)
    results = retriever.retrieve_rules("query", top_k=3)
    assert len(results) == 3


def test_exception_returns_empty_list(store):
    """If embedding backend raises, retrieve_rules should return []."""
    bad_backend = MagicMock()
    bad_backend.embed.side_effect = RuntimeError("embedding failed")
    retriever = RuleRetriever(store, bad_backend)
    store.save_rule("q", "a", "rule", [1.0])
    result = retriever.retrieve_rules("query")
    assert result == []
