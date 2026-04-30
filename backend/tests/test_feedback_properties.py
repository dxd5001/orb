"""
Property-based tests for the feedback-driven improvement feature.

Feature: feedback-driven-improvement

Uses hypothesis to verify correctness properties across random inputs.
Each property runs at least 100 examples.
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feedback.store import FeedbackStore
from feedback.retriever import RuleRetriever
from generation.generator import Generator
from models import ImprovementRule, Chunk


# ── Strategies ────────────────────────────────────────────────────────────────

nonempty_text = st.text(min_size=1, max_size=200)
embedding_strategy = st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False), min_size=3, max_size=8)

improvement_rule_strategy = st.builds(
    ImprovementRule,
    id=st.none(),
    query_text=nonempty_text,
    answer_text=nonempty_text,
    improvement_request=nonempty_text,
    created_at=st.just(datetime.now()),
)


def make_store(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("db")
    return FeedbackStore(db_path=str(tmp / "test.db"))


# ── Property 1: 改善ルール保存ラウンドトリップ ────────────────────────────────

@given(
    query_text=nonempty_text,
    answer_text=nonempty_text,
    improvement_request=nonempty_text,
    embedding=embedding_strategy,
)
@settings(max_examples=100)
def test_property_1_save_roundtrip(tmp_path_factory, query_text, answer_text, improvement_request, embedding):
    """
    Feature: feedback-driven-improvement, Property 1: 改善ルール保存ラウンドトリップ

    For any valid text triple and embedding vector, saving then retrieving
    via get_rules_with_embeddings returns a rule with matching fields.
    """
    store = make_store(tmp_path_factory)
    store.save_rule(query_text, answer_text, improvement_request, embedding)

    results = store.get_rules_with_embeddings()
    assert len(results) == 1
    rule, vec = results[0]
    assert rule.query_text == query_text
    assert rule.answer_text == answer_text
    assert rule.improvement_request == improvement_request
    assert len(vec) == len(embedding)
    for a, b in zip(vec, embedding):
        assert abs(a - b) < 1e-6


# ── Property 2: FeedbackStore 初期化の冪等性 ─────────────────────────────────

@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=100)
def test_property_2_init_idempotent(tmp_path_factory, n):
    """
    Feature: feedback-driven-improvement, Property 2: FeedbackStore 初期化の冪等性

    Initializing FeedbackStore multiple times on the same path should not
    raise errors and tables should always exist.
    """
    import sqlite3
    tmp = tmp_path_factory.mktemp("db2")
    db_path = str(tmp / "test.db")

    for _ in range(n):
        store = FeedbackStore(db_path=db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "improvement_rules" in tables
    assert "feedback_logs" in tables


# ── Property 3: ルール取得の順序と件数制約 ────────────────────────────────────

@given(
    n_rules=st.integers(min_value=1, max_value=10),
    top_k=st.integers(min_value=1, max_value=15),
)
@settings(max_examples=100)
def test_property_3_retrieval_order_and_count(tmp_path_factory, n_rules, top_k):
    """
    Feature: feedback-driven-improvement, Property 3: ルール取得の順序と件数制約

    retrieve_rules returns at most top_k results, and results are ordered
    by cosine similarity descending.
    """
    store = make_store(tmp_path_factory)
    import random
    random.seed(42)

    for i in range(n_rules):
        emb = [float(i), 0.0, 0.0]
        store.save_rule(f"q{i}", f"a{i}", f"rule{i}", emb)

    mock_backend = MagicMock()
    mock_backend.embed.return_value = [[1.0, 0.0, 0.0]]
    retriever = RuleRetriever(store, mock_backend)

    results = retriever.retrieve_rules("query", top_k=top_k)

    # Count constraint
    assert len(results) <= top_k
    assert len(results) <= n_rules

    # Order constraint: compute similarities and verify descending order
    if len(results) >= 2:
        rules_with_emb = {r.improvement_request: emb for r, emb in store.get_rules_with_embeddings()}
        query_vec = [1.0, 0.0, 0.0]

        def cosine(a, b):
            import math
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x ** 2 for x in a))
            nb = math.sqrt(sum(x ** 2 for x in b))
            return dot / (na * nb) if na > 0 and nb > 0 else 0.0

        sims = [cosine(query_vec, rules_with_emb[r.improvement_request]) for r in results]
        for i in range(len(sims) - 1):
            assert sims[i] >= sims[i + 1] - 1e-9


# ── Property 4: プロンプトへのルール注入フォーマット ──────────────────────────

@given(rules=st.lists(improvement_rule_strategy, min_size=1, max_size=5))
@settings(max_examples=100)
def test_property_4_prompt_injection_format(rules):
    """
    Feature: feedback-driven-improvement, Property 4: プロンプトへのルール注入フォーマット

    When improvement_rules are provided, the prompt contains an
    IMPROVEMENT RULES section and each rule starts with '- '.
    """
    gen = Generator(MagicMock())
    chunk = Chunk(
        chunk_id="c::0", text="text", source_path="f.md", title="T",
        tags=[], frontmatter={}, last_modified=datetime.now(), chunk_index=0,
    )
    prompt = gen._build_prompt("query", [chunk], None, improvement_rules=rules)

    assert "IMPROVEMENT RULES" in prompt
    for rule in rules:
        assert f"- {rule.improvement_request}" in prompt


# ── Property 5: トークン上限の遵守 ───────────────────────────────────────────

@given(
    rules=st.lists(improvement_rule_strategy, min_size=0, max_size=10),
    base_prompt=st.text(min_size=0, max_size=500),
)
@settings(max_examples=100)
def test_property_5_token_limit(rules, base_prompt):
    """
    Feature: feedback-driven-improvement, Property 5: トークン上限の遵守

    After _trim_rules_to_fit, the estimated token count of the combined
    prompt does not exceed max_tokens=4096.
    """
    gen = Generator(MagicMock())
    max_tokens = 4096
    trimmed = gen._trim_rules_to_fit(rules, base_prompt, max_tokens=max_tokens)

    rules_text = "\n".join(f"- {r.improvement_request}" for r in trimmed)
    combined = base_prompt + rules_text
    estimated = gen._estimate_tokens(combined)
    assert estimated <= max_tokens


# ── Property 6: ルール削除ラウンドトリップ ────────────────────────────────────

@given(
    query_text=nonempty_text,
    improvement_request=nonempty_text,
)
@settings(max_examples=100)
def test_property_6_delete_roundtrip(tmp_path_factory, query_text, improvement_request):
    """
    Feature: feedback-driven-improvement, Property 6: ルール削除ラウンドトリップ

    After saving and deleting a rule, it no longer appears in get_all_rules,
    and a second delete returns False.
    """
    store = make_store(tmp_path_factory)
    rule_id = store.save_rule(query_text, "answer", improvement_request, [0.1, 0.2])

    # First delete: should succeed
    assert store.delete_rule(rule_id) is True

    # Rule should no longer exist
    remaining_ids = [r.id for r in store.get_all_rules()]
    assert rule_id not in remaining_ids

    # Second delete: should return False
    assert store.delete_rule(rule_id) is False
