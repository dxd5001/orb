"""
Unit tests for Generator rule injection.

Tests cover:
- Prompt contains IMPROVEMENT RULES section when rules present
- Prompt does not contain section when no rules
- _trim_rules_to_fit respects token limit
- RuleRetriever exception does not break generation
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generation.generator import Generator
from models import ImprovementRule, Chunk, ChatTurn


def make_chunk(text="sample text", source="test.md", title="Test"):
    return Chunk(
        chunk_id="test::0",
        text=text,
        source_path=source,
        title=title,
        tags=[],
        frontmatter={},
        last_modified=datetime.now(),
        chunk_index=0,
    )


def make_rule(improvement_request: str) -> ImprovementRule:
    return ImprovementRule(
        id=1,
        query_text="q",
        answer_text="a",
        improvement_request=improvement_request,
        created_at=datetime.now(),
    )


def test_prompt_contains_improvement_rules_section():
    """When rules are provided, prompt should contain IMPROVEMENT RULES section."""
    llm = MagicMock()
    gen = Generator(llm)
    rules = [make_rule("具体的な日付を含めること"), make_rule("箇条書きで回答すること")]
    prompt = gen._build_prompt("test query", [make_chunk()], None, improvement_rules=rules)

    assert "IMPROVEMENT RULES" in prompt
    assert "具体的な日付を含めること" in prompt
    assert "箇条書きで回答すること" in prompt
    assert "- 具体的な日付を含めること" in prompt


def test_prompt_no_rules_section_when_empty():
    """When no rules, prompt should not contain IMPROVEMENT RULES section."""
    llm = MagicMock()
    gen = Generator(llm)
    prompt = gen._build_prompt("test query", [make_chunk()], None, improvement_rules=[])

    assert "IMPROVEMENT RULES" not in prompt


def test_improvement_rules_before_context():
    """IMPROVEMENT RULES section should appear before CONTEXT section."""
    llm = MagicMock()
    gen = Generator(llm)
    rules = [make_rule("rule1")]
    prompt = gen._build_prompt("test query", [make_chunk()], None, improvement_rules=rules)

    rules_pos = prompt.find("IMPROVEMENT RULES")
    context_pos = prompt.find("CONTEXT")
    assert rules_pos < context_pos


def test_estimate_tokens():
    gen = Generator(MagicMock())
    assert gen._estimate_tokens("ab") == 1
    assert gen._estimate_tokens("abcd") == 2
    assert gen._estimate_tokens("") == 0


def test_trim_rules_to_fit_respects_limit():
    """_trim_rules_to_fit should drop rules that exceed token limit."""
    gen = Generator(MagicMock())
    # Create a very long rule that will exceed a tiny limit
    long_rule = make_rule("x" * 10000)
    short_rule = make_rule("short")
    base_prompt = "base"

    # With a very small max_tokens, even the short rule might not fit
    result = gen._trim_rules_to_fit([long_rule, short_rule], base_prompt, max_tokens=10)
    # The long rule should be excluded
    for r in result:
        assert r.improvement_request != "x" * 10000


def test_rule_retriever_exception_does_not_break_generation():
    """If RuleRetriever raises, generate() should still return a response."""
    llm = MagicMock()
    llm.generate.return_value = '{"answer": "ok", "answer_blocks": [], "citations": []}'

    bad_retriever = MagicMock()
    bad_retriever.retrieve_rules.side_effect = RuntimeError("retriever failed")

    gen = Generator(llm, rule_retriever=bad_retriever)
    response = gen.generate("test query", [make_chunk()])
    assert response is not None
    assert response.answer is not None


def test_generate_without_rule_retriever():
    """Generator without rule_retriever should work normally."""
    llm = MagicMock()
    llm.generate.return_value = '{"answer": "ok", "answer_blocks": [], "citations": []}'

    gen = Generator(llm)  # no rule_retriever
    response = gen.generate("test query", [make_chunk()])
    assert response is not None
