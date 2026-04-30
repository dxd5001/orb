"""
Unit tests for the feedback API router.

Tests cover:
- POST /api/feedback (positive, negative with/without improvement_request)
- GET /api/feedback/rules
- DELETE /api/feedback/rules/{rule_id}
"""

import os
import sys
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.feedback import router
from feedback.store import FeedbackStore


@pytest.fixture
def app(tmp_path):
    """Create a minimal FastAPI app with feedback router and mocked state."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    db_path = str(tmp_path / "test.db")
    store = FeedbackStore(db_path=db_path)

    mock_embedding = MagicMock()
    mock_embedding.embed.return_value = [[0.1, 0.2, 0.3]]

    test_app.state.feedback_store = store
    test_app.state.embedding_backend = mock_embedding

    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_positive_feedback(client):
    """POST /api/feedback with positive type should return 200."""
    resp = client.post("/api/feedback", json={
        "message_id": "msg1",
        "query": "test query",
        "answer": "test answer",
        "feedback_type": "positive",
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_negative_feedback_with_improvement(client, app):
    """POST /api/feedback with negative + improvement_request should save a rule."""
    resp = client.post("/api/feedback", json={
        "message_id": "msg2",
        "query": "test query",
        "answer": "test answer",
        "feedback_type": "negative",
        "improvement_request": "Please be more specific",
    })
    assert resp.status_code == 200

    rules = app.state.feedback_store.get_all_rules()
    assert len(rules) == 1
    assert rules[0].improvement_request == "Please be more specific"


def test_negative_feedback_without_improvement(client, app):
    """POST /api/feedback with negative but no improvement_request should not save a rule."""
    resp = client.post("/api/feedback", json={
        "message_id": "msg3",
        "query": "test query",
        "answer": "test answer",
        "feedback_type": "negative",
    })
    assert resp.status_code == 200
    assert app.state.feedback_store.get_all_rules() == []


def test_invalid_feedback_type(client):
    """POST /api/feedback with invalid feedback_type should return 422."""
    resp = client.post("/api/feedback", json={
        "message_id": "msg4",
        "query": "q",
        "answer": "a",
        "feedback_type": "invalid",
    })
    assert resp.status_code == 422


def test_missing_required_fields(client):
    """POST /api/feedback without required fields should return 422."""
    resp = client.post("/api/feedback", json={"message_id": "msg5"})
    assert resp.status_code == 422


def test_get_rules_empty(client):
    """GET /api/feedback/rules should return empty list initially."""
    resp = client.get("/api/feedback/rules")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_rules_after_save(client, app):
    """GET /api/feedback/rules should return saved rules."""
    app.state.feedback_store.save_rule("q", "a", "rule1", [0.1, 0.2])
    resp = client.get("/api/feedback/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["improvement_request"] == "rule1"


def test_delete_existing_rule(client, app):
    """DELETE /api/feedback/rules/{id} should return 200 and remove the rule."""
    rule_id = app.state.feedback_store.save_rule("q", "a", "rule", [0.1])
    resp = client.delete(f"/api/feedback/rules/{rule_id}")
    assert resp.status_code == 200
    assert app.state.feedback_store.get_all_rules() == []


def test_delete_nonexistent_rule(client):
    """DELETE /api/feedback/rules/{id} for non-existent ID should return 404."""
    resp = client.delete("/api/feedback/rules/9999")
    assert resp.status_code == 404
