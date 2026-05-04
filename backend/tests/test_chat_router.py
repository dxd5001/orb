"""
Unit tests for the chat API router.

Tests cover:
- POST /api/chat happy path with retrieval + generation wiring
- POST /api/chat validation failure for empty query
"""

import os
import sys
from datetime import datetime
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from embedding.base import EmbeddingBackend
from generation.generator import Generator
from llm.base import LLMBackend
from models import AnswerBlock, ChatResponse, Citation, Chunk, SearchMode
from retrieval.retriever import Retriever
from routers.chat import router


class MockEmbeddingBackend(EmbeddingBackend):
    """Mock embedding backend for integration tests."""

    def __init__(self, dimension=768):
        self.dimension = dimension
        self.model_name = "mock_model"

    def embed(self, texts):
        return [[0.1] * self.dimension for _ in texts]

    def get_embedding_dimension(self):
        return self.dimension

    def get_model_name(self):
        return self.model_name


class MockLLMBackend(LLMBackend):
    """Mock LLM backend for chat router semi-integration tests."""

    def __init__(self, response_text="Mock response"):
        self.response_text = response_text
        self.model_name = "mock_model"
        self.last_prompt = None

    def generate(self, prompt):
        self.last_prompt = prompt
        return self.response_text

    def get_model_name(self):
        return self.model_name


@pytest.fixture
def app():
    """Create a minimal FastAPI app with chat router and mocked state."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    test_app.state.retriever = MagicMock()
    test_app.state.generator = MagicMock()
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_chat_endpoint_wires_retrieval_and_generation(client, app):
    """POST /api/chat should pass planned retrieval output into generator."""
    retrieved_chunks = [
        MagicMock(chunk_id="prop.md::0"),
        MagicMock(chunk_id="context.md::0"),
    ]
    app.state.retriever.retrieve.return_value = retrieved_chunks
    app.state.generator.generate.return_value = ChatResponse(
        answer="AI includes machine learning [1].",
        answer_blocks=[
            AnswerBlock(
                type="summary",
                title="回答",
                content="AI includes machine learning [1].",
                items=[],
            ),
            AnswerBlock(
                type="evidence",
                title="根拠",
                content="主要な根拠です。",
                items=["AI includes machine learning. [prop.md::0]"],
            ),
            AnswerBlock(
                type="context",
                title="補足文脈",
                content="背景情報です。",
                items=["Longer narrative context. [context.md::0]"],
            ),
        ],
        citations=[
            Citation(
                file_path="notes/ai.md",
                title="AI",
                snippet="AI includes machine learning.",
                source_path="prop.md::0",
            )
        ],
    )

    response = client.post(
        "/api/chat",
        json={
            "query": "AIとは?",
            "search_mode": SearchMode.AUTO.value,
            "history": [{"role": "user", "content": "前提を教えて"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "AI includes machine learning [1]."
    assert any(block["type"] == "evidence" for block in data["answer_blocks"])
    assert any(block["type"] == "context" for block in data["answer_blocks"])
    app.state.retriever.retrieve.assert_called_once()
    app.state.generator.generate.assert_called_once()
    generate_call = app.state.generator.generate.call_args
    assert generate_call.kwargs["query"] == "AIとは?"
    assert generate_call.kwargs["chunks"] == retrieved_chunks
    assert generate_call.kwargs["history"][0].content == "前提を教えて"


def test_chat_endpoint_returns_expected_response_shape(client, app):
    """POST /api/chat should return answer, structured blocks, and citations with required fields."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="AI includes machine learning [1].",
        answer_blocks=[
            AnswerBlock(
                type="summary",
                title="回答",
                content="AI includes machine learning [1].",
                items=[],
            ),
            AnswerBlock(
                type="evidence",
                title="根拠",
                content="主要な根拠です。",
                items=["AI includes machine learning. [prop.md::0]"],
            ),
            AnswerBlock(
                type="context",
                title="補足文脈",
                content="背景情報です。",
                items=["Longer narrative context. [context.md::0]"],
            ),
        ],
        citations=[
            Citation(
                file_path="notes/ai.md",
                title="AI",
                snippet="AI includes machine learning.",
                source_path="prop.md::0",
            )
        ],
    )

    response = client.post(
        "/api/chat",
        json={"query": "AIとは?", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"answer", "answer_blocks", "citations"}
    assert isinstance(data["answer"], str)
    assert isinstance(data["answer_blocks"], list)
    assert isinstance(data["citations"], list)

    block = data["answer_blocks"][0]
    assert set(block.keys()) == {"type", "title", "content", "items"}
    assert isinstance(block["type"], str)
    assert isinstance(block["title"], str)
    assert isinstance(block["content"], str)
    assert isinstance(block["items"], list)
    assert {item["type"] for item in data["answer_blocks"]} == {
        "summary",
        "evidence",
        "context",
    }

    citation = data["citations"][0]
    assert set(citation.keys()) == {"file_path", "title", "snippet", "source_path"}
    assert citation["file_path"] == "notes/ai.md"
    assert citation["title"] == "AI"
    assert citation["source_path"] == "prop.md::0"


def test_chat_endpoint_preserves_role_aware_block_content(client, app):
    """POST /api/chat should preserve evidence/context block content aligned with chunk roles."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="AI includes machine learning [1].",
        answer_blocks=[
            AnswerBlock(
                type="summary",
                title="回答",
                content="AI includes machine learning [1].",
                items=[],
            ),
            AnswerBlock(
                type="evidence",
                title="根拠",
                content="主要な主張を直接支える根拠です。",
                items=["AI includes machine learning. [prop.md::0]"],
            ),
            AnswerBlock(
                type="context",
                title="補足文脈",
                content="背景説明や詳細理解のための補足コンテキストです。",
                items=[
                    "This note explains historical background for AI systems. [context.md::0]"
                ],
            ),
        ],
        citations=[
            Citation(
                file_path="notes/ai.md",
                title="AI",
                snippet="AI includes machine learning.",
                source_path="prop.md::0",
            )
        ],
    )

    response = client.post(
        "/api/chat",
        json={"query": "AIとは?", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 200
    data = response.json()
    blocks_by_type = {block["type"]: block for block in data["answer_blocks"]}
    assert "prop.md::0" in blocks_by_type["evidence"]["items"][0]
    assert "AI includes machine learning" in blocks_by_type["evidence"]["items"][0]
    assert "context.md::0" in blocks_by_type["context"]["items"][0]
    assert (
        "historical background for AI systems" in blocks_by_type["context"]["items"][0]
    )


def test_chat_endpoint_with_real_generator_produces_role_aware_response(client, app):
    """POST /api/chat should work with a real Generator and produce evidence/context blocks."""
    app.state.retriever.retrieve.return_value = [
        Chunk(
            chunk_id="prop.md::0",
            text="AI includes machine learning.",
            source_path="notes/ai.md",
            title="AI",
            tags=["ai"],
            frontmatter={},
            last_modified=datetime.now(),
            chunk_index=0,
            is_proposition=True,
        ),
        Chunk(
            chunk_id="context.md::0",
            text="This note explains historical background for AI systems.",
            source_path="notes/history.md",
            title="History",
            tags=["ai"],
            frontmatter={},
            last_modified=datetime.now(),
            chunk_index=0,
        ),
    ]
    mock_llm = MockLLMBackend(
        response_text="""{
            "answer": "AI includes machine learning [chunk_prop.md::0].",
            "answer_blocks": [
                {
                    "type": "summary",
                    "title": "回答",
                    "content": "AI includes machine learning [chunk_prop.md::0].",
                    "items": []
                }
            ]
        }"""
    )
    app.state.generator = Generator(mock_llm)

    response = client.post(
        "/api/chat",
        json={"query": "AIとは?", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 200
    data = response.json()
    assert any(block["type"] == "evidence" for block in data["answer_blocks"])
    assert any(block["type"] == "context" for block in data["answer_blocks"])
    blocks_by_type = {block["type"]: block for block in data["answer_blocks"]}
    assert "[1]" in data["answer"]
    assert any("prop.md::0" in item for item in blocks_by_type["evidence"]["items"])
    assert any("context.md::0" in item for item in blocks_by_type["context"]["items"])
    assert data["citations"][0]["source_path"] == "prop.md::0"


def test_chat_endpoint_with_real_generator_includes_history_in_prompt(client, app):
    """POST /api/chat should pass conversation history into the real Generator prompt."""
    app.state.retriever.retrieve.return_value = [
        Chunk(
            chunk_id="prop.md::0",
            text="AI includes machine learning.",
            source_path="notes/ai.md",
            title="AI",
            tags=["ai"],
            frontmatter={},
            last_modified=datetime.now(),
            chunk_index=0,
            is_proposition=True,
        )
    ]
    mock_llm = MockLLMBackend(
        response_text="""{
            "answer": "AI includes machine learning [chunk_prop.md::0].",
            "answer_blocks": [
                {
                    "type": "summary",
                    "title": "回答",
                    "content": "AI includes machine learning [chunk_prop.md::0].",
                    "items": []
                }
            ]
        }"""
    )
    app.state.generator = Generator(mock_llm)

    response = client.post(
        "/api/chat",
        json={
            "query": "AIとは?",
            "search_mode": SearchMode.AUTO.value,
            "history": [
                {"role": "user", "content": "前提を教えて"},
                {"role": "assistant", "content": "AIの基本から説明します。"},
            ],
        },
    )

    assert response.status_code == 200
    assert mock_llm.last_prompt is not None
    assert "--- CONVERSATION HISTORY ---" in mock_llm.last_prompt
    assert "User: 前提を教えて" in mock_llm.last_prompt
    assert "Assistant: AIの基本から説明します。" in mock_llm.last_prompt
    assert "--- CURRENT QUESTION ---" in mock_llm.last_prompt
    assert "User: AIとは?" in mock_llm.last_prompt


def test_chat_endpoint_with_real_retriever_and_generator_integration(client, app):
    """POST /api/chat should work with real Retriever and Generator using in-memory Chroma."""
    temp_dir = tempfile.mkdtemp()
    mock_embedding = MockEmbeddingBackend()
    mock_llm = MockLLMBackend(
        response_text="""{
            "answer": "AI includes machine learning [chunk_prop.md::0].",
            "answer_blocks": [
                {
                    "type": "summary",
                    "title": "回答",
                    "content": "AI includes machine learning [chunk_prop.md::0].",
                    "items": []
                }
            ]
        }"""
    )

    try:
        with patch("retrieval.retriever.CHROMADB_AVAILABLE", True):
            with patch("retrieval.retriever.chromadb") as mock_chromadb:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_collection.count.return_value = 2
                mock_client.get_collection.return_value = mock_collection
                mock_chromadb.PersistentClient.return_value = mock_client

                retriever = Retriever(mock_embedding, temp_dir)
                app.state.retriever = retriever
                app.state.generator = Generator(mock_llm)

                mock_results = {
                    "ids": [["prop.md::0", "context.md::0"]],
                    "documents": [
                        [
                            "AI includes machine learning.",
                            "This note explains historical background for AI systems.",
                        ]
                    ],
                    "metadatas": [
                        [
                            {
                                "source_path": "notes/ai.md",
                                "title": "AI",
                                "chunk_index": 0,
                                "is_proposition": True,
                            },
                            {
                                "source_path": "notes/history.md",
                                "title": "History",
                                "chunk_index": 0,
                                "is_proposition": False,
                            },
                        ]
                    ],
                    "distances": [[0.1, 0.2]],
                }
                mock_collection.query.return_value = mock_results

                response = client.post(
                    "/api/chat",
                    json={"query": "AIとは?", "search_mode": SearchMode.AUTO.value},
                )

                assert response.status_code == 200
                data = response.json()
                assert any(
                    block["type"] == "evidence" for block in data["answer_blocks"]
                )
                assert any(
                    block["type"] == "context" for block in data["answer_blocks"]
                )
                assert len(data["citations"]) >= 1
                assert mock_collection.query.called
    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


def test_chat_endpoint_rejects_empty_query(client):
    """POST /api/chat with empty query should return 400."""
    response = client.post(
        "/api/chat",
        json={"query": "   ", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data["detail"]
    assert "Query cannot be empty" in data["detail"]["errors"]


def test_chat_endpoint_passes_diary_temporal_plan_to_retriever(client, app):
    """POST /api/chat should build a diary-temporal plan for diary queries."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="No answer.",
        answer_blocks=[
            AnswerBlock(type="summary", title="回答", content="No answer.", items=[])
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={"query": "/diary 昨日何を食べた?", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 200
    retrieve_call = app.state.retriever.retrieve.call_args
    plan = retrieve_call.kwargs["plan"]
    assert plan.search_mode == SearchMode.DIARY
    assert plan.is_diary_intent is True
    assert plan.is_temporal is True
    assert plan.top_k == 5


def test_chat_endpoint_passes_general_context_plan_to_retriever(client, app):
    """POST /api/chat should build a general-context plan for general explanation queries."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="API design answer.",
        answer_blocks=[
            AnswerBlock(
                type="summary", title="回答", content="API design answer.", items=[]
            )
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={
            "query": "/general API設計について教えて",
            "search_mode": SearchMode.AUTO.value,
        },
    )

    assert response.status_code == 200
    retrieve_call = app.state.retriever.retrieve.call_args
    plan = retrieve_call.kwargs["plan"]
    assert plan.search_mode == SearchMode.GENERAL
    assert plan.is_context_query is True
    assert plan.is_fact_query is False
    assert plan.original_query == "API設計について教えて"


def test_chat_endpoint_passes_auto_fact_plan_to_retriever(client, app):
    """POST /api/chat should build an auto fact plan for fact-oriented queries."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="Oxios answer.",
        answer_blocks=[
            AnswerBlock(type="summary", title="回答", content="Oxios answer.", items=[])
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={"query": "oxiosはいつ登場した?", "search_mode": SearchMode.AUTO.value},
    )

    assert response.status_code == 200
    retrieve_call = app.state.retriever.retrieve.call_args
    plan = retrieve_call.kwargs["plan"]
    assert plan.search_mode == SearchMode.AUTO
    assert plan.is_fact_query is True
    assert plan.is_context_query is False
    assert plan.original_query == "oxiosはいつ登場した?"


def test_chat_endpoint_applies_inline_mode_and_tag_scope(client, app):
    """POST /api/chat should apply inline mode command and tag scope to the retrieval plan."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="Diary answer.",
        answer_blocks=[
            AnswerBlock(type="summary", title="回答", content="Diary answer.", items=[])
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={
            "query": "/diary 最後にビールを飲んだのはいつ? #飲み会",
            "search_mode": SearchMode.AUTO.value,
        },
    )

    assert response.status_code == 200
    plan = app.state.retriever.retrieve.call_args.kwargs["plan"]
    assert plan.search_mode == SearchMode.DIARY
    assert plan.scope is not None
    assert plan.scope.tags == ["飲み会"]
    assert plan.original_query == "最後にビールを飲んだのはいつ?"


def test_chat_endpoint_merges_ui_scope_with_inline_command_scope(client, app):
    """POST /api/chat should let inline folder override UI folder and merge tags."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="Scoped answer.",
        answer_blocks=[
            AnswerBlock(
                type="summary", title="回答", content="Scoped answer.", items=[]
            )
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={
            "query": "/general project update #backend @projects",
            "search_mode": SearchMode.AUTO.value,
            "scope": {"folder": "old", "tags": ["work"]},
        },
    )

    assert response.status_code == 200
    plan = app.state.retriever.retrieve.call_args.kwargs["plan"]
    assert plan.search_mode == SearchMode.GENERAL
    assert plan.scope is not None
    assert plan.scope.folder == "projects"
    assert plan.scope.tags == ["work", "backend"]
    assert plan.original_query == "project update"


def test_chat_endpoint_uses_history_for_date_normalization(client, app):
    """POST /api/chat should use history dates when building a temporal retrieval plan."""
    app.state.retriever.retrieve.return_value = []
    app.state.generator.generate.return_value = ChatResponse(
        answer="Temporal answer.",
        answer_blocks=[
            AnswerBlock(
                type="summary", title="回答", content="Temporal answer.", items=[]
            )
        ],
        citations=[],
    )

    response = client.post(
        "/api/chat",
        json={
            "query": "翌日何をした?",
            "search_mode": SearchMode.AUTO.value,
            "history": [
                {"role": "user", "content": "2024-03-01の出来事を教えて"},
                {"role": "assistant", "content": "2024-03-01は会議がありました。"},
            ],
        },
    )

    assert response.status_code == 200
    plan = app.state.retriever.retrieve.call_args.kwargs["plan"]
    assert plan.original_query == "翌日何をした?"
    assert plan.normalized_query == "2024-03-02何をした?"
    assert plan.is_temporal is True
