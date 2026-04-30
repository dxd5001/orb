"""
Tests for Generator implementation.

This module tests the prompt construction, response generation, and citation extraction.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from generation.generator import Generator
from models import Chunk, ChatTurn, ChatResponse, Citation
from llm.base import LLMBackend


class MockLLMBackend(LLMBackend):
    """Mock LLM backend for testing."""

    def __init__(self, response_text="Mock response"):
        self.response_text = response_text
        self.model_name = "mock_model"

    def generate(self, prompt):
        return self.response_text

    def get_model_name(self):
        return self.model_name


class TestGenerator:
    """Test cases for Generator."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_llm = MockLLMBackend()
        self.generator = Generator(self.mock_llm)

        # Create test chunks
        self.test_chunks = [
            Chunk(
                chunk_id="test1.md::0",
                text="This is the first chunk about artificial intelligence and machine learning.",
                source_path="test1.md",
                title="AI Notes",
                tags=["ai", "ml"],
                frontmatter={"title": "AI Notes"},
                last_modified=datetime.now(),
                chunk_index=0,
            ),
            Chunk(
                chunk_id="test2.md::0",
                text="This is the second chunk about natural language processing and transformers.",
                source_path="test2.md",
                title="NLP Notes",
                tags=["nlp", "transformers"],
                frontmatter={"title": "NLP Notes"},
                last_modified=datetime.now(),
                chunk_index=0,
            ),
        ]

    def test_init(self):
        """Test generator initialization."""
        assert self.generator.llm_backend == self.mock_llm
        assert self.generator.MAX_HISTORY_TURNS == 5
        assert len(self.generator.SYSTEM_PROMPT) > 0

    def test_generate_empty_query(self):
        """Test generation with empty query."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            self.generator.generate("", self.test_chunks)

        with pytest.raises(ValueError, match="Query cannot be empty"):
            self.generator.generate("   ", self.test_chunks)

    def test_generate_no_chunks(self):
        """Test generation with no relevant chunks."""
        response = self.generator.generate("What is AI?", [])

        assert isinstance(response, ChatResponse)
        assert "Vault related information" in response.answer
        assert len(response.citations) == 0

    def test_generate_with_chunks(self):
        """Test generation with chunks."""
        # Mock LLM response with citations
        mock_response = "Based on the context, artificial intelligence [1] is a field that includes machine learning [1] and natural language processing [2]."
        self.mock_llm.response_text = mock_response

        response = self.generator.generate("What is AI?", self.test_chunks)

        assert isinstance(response, ChatResponse)
        assert len(response.answer) > 0
        assert len(response.citations) >= 1

    def test_build_prompt_basic(self):
        """Test basic prompt building."""
        prompt = self.generator._build_prompt("What is AI?", self.test_chunks, [])

        assert "What is AI?" in prompt
        assert "artificial intelligence" in prompt
        assert "natural language processing" in prompt

    def test_chunk_id_citation_mapping(self):
        """Test chunk ID to citation number mapping."""
        # Mock LLM response with chunk IDs
        mock_response = """{
            "answer": "Based on the context, artificial intelligence [chunk_test1.md::0] is a field that includes machine learning [chunk_test1.md::0] and natural language processing [chunk_test2.md::0].",
            "answer_blocks": [
                {
                    "type": "summary",
                    "title": "AI Overview",
                    "content": "Artificial intelligence [chunk_test1.md::0] encompasses machine learning [chunk_test1.md::0] and NLP [chunk_test2.md::0].",
                    "items": ["Machine learning [chunk_test1.md::0]", "NLP [chunk_test2.md::0]"]
                }
            ]
        }"""
        self.mock_llm.response_text = mock_response

        response = self.generator.generate("What is AI?", self.test_chunks)

        # Verify response structure
        assert isinstance(response, ChatResponse)
        assert len(response.answer) > 0
        assert len(response.citations) >= 1

        # Verify chunk IDs are converted to citation numbers
        assert "[chunk_test1.md::0]" not in response.answer
        assert "[chunk_test2.md::0]" not in response.answer

        # Should contain citation numbers like [1], [2]
        assert "[1]" in response.answer or "[2]" in response.answer

        # Verify answer blocks also have correct citations
        if response.answer_blocks:
            for block in response.answer_blocks:
                assert "[chunk_test1.md::0]" not in (block.content or "")
                assert "[chunk_test2.md::0]" not in (block.content or "")
                if block.items:
                    for item in block.items:
                        assert "[chunk_test1.md::0]" not in item
                        assert "[chunk_test2.md::0]" not in item

    def test_chunk_id_extraction_patterns(self):
        """Test various chunk ID extraction patterns."""
        # Test chunk ID pattern matching
        citations = self.generator._extract_structured_citations(
            "This uses [chunk_test1.md::0] and [chunk_test2.md::0] for reference.",
            self.test_chunks,
        )

        assert len(citations) >= 2

        # Test fallback to numeric pattern
        citations = self.generator._extract_structured_citations(
            "This uses [1] and [2] for reference.", self.test_chunks
        )

        assert len(citations) >= 1

    def test_build_prompt_with_history(self):
        """Test prompt building with conversation history."""
        history = [
            ChatTurn(role="user", content="Hello"),
            ChatTurn(role="assistant", content="Hi there!"),
            ChatTurn(role="user", content="How are you?"),
            ChatTurn(role="assistant", content="I'm doing well!"),
            ChatTurn(role="user", content="Great!"),
            ChatTurn(role="assistant", content="Yes, great!"),
            ChatTurn(role="user", content="Latest question"),  # This should be excluded
        ]

        prompt = self.generator._build_prompt("What is AI?", self.test_chunks, history)

        assert "CONVERSATION HISTORY" in prompt
        assert "User: Hello" in prompt
        assert "Assistant: Hi there!" in prompt
        # Should only include last 5 turns
        assert "Latest question" not in prompt

    def test_prepare_chunk_text(self):
        """Test chunk text preparation."""
        short_text = "Short text"
        result = self.generator._prepare_chunk_text(short_text)
        assert result == short_text

        long_text = "a" * 2500  # Longer than max_chunk_length
        result = self.generator._prepare_chunk_text(long_text)
        assert len(result) <= 2003  # 2000 + "..."
        assert result.endswith("...")

    def test_extract_structured_citations_numeric(self):
        """Test extracting numeric citations."""
        response = "According to chunk [1], AI is important. Also mentioned in [2]."
        citations = self.generator._extract_structured_citations(
            response, self.test_chunks
        )

        assert len(citations) == 2
        assert citations[0].file_path == "test1.md"
        assert citations[1].file_path == "test2.md"

    def test_extract_structured_citations_filename(self):
        """Test extracting filename citations."""
        response = "Based on [test1.md], AI is important. Also mentioned in [test2.md]."
        citations = self.generator._extract_structured_citations(
            response, self.test_chunks
        )

        assert len(citations) == 2
        assert citations[0].file_path == "test1.md"
        assert citations[1].file_path == "test2.md"

    def test_extract_structured_citations_source_format(self):
        """Test extracting source format citations."""
        response = "Based on [Source: test1.md], AI is important."
        citations = self.generator._extract_structured_citations(
            response, self.test_chunks
        )

        assert len(citations) == 1
        assert citations[0].file_path == "test1.md"

    def test_extract_structured_citations_no_match(self):
        """Test when no citations match."""
        response = "This is a response with no citations."
        citations = self.generator._extract_structured_citations(
            response, self.test_chunks
        )

        assert len(citations) == 0

    def test_infer_citations_from_content(self):
        """Test inferring citations from content."""
        response = "Artificial intelligence and machine learning are important fields."
        citations = self.generator._infer_citations_from_content(
            response, self.test_chunks
        )

        # Should find citation from first chunk
        assert len(citations) >= 1
        assert any(c.file_path == "test1.md" for c in citations)

    def test_clean_response_text(self):
        """Test cleaning response text."""
        dirty_response = (
            "This is [1] a response [Source: test.md] with citations [note.md]."
        )
        clean_response = self.generator._clean_response_text(dirty_response)

        assert "[1]" not in clean_response
        assert "[Source: test.md]" not in clean_response
        assert "[note.md]" not in clean_response
        assert "This is a response with citations." in clean_response

    def test_create_citation_from_chunk(self):
        """Test creating citation from chunk."""
        chunk = self.test_chunks[0]
        citation = self.generator._create_citation_from_chunk(chunk)

        assert isinstance(citation, Citation)
        assert citation.file_path == "test1.md"
        assert citation.title == "AI Notes"
        assert "artificial intelligence" in citation.snippet.lower()

    def test_format_citations(self):
        """Test formatting citations."""
        citations = [
            Citation(file_path="test1.md", title="Test 1", snippet="Short snippet"),
            Citation(
                file_path="test2.md", title="Test 2", snippet="a" * 400
            ),  # Too long
        ]

        formatted = self.generator._format_citations(citations, self.test_chunks)

        assert len(formatted) == 2
        assert formatted[0].snippet == "Short snippet"
        assert len(formatted[1].snippet) <= 303  # 300 + "..."

    def test_get_system_prompt(self):
        """Test getting system prompt."""
        prompt = self.generator.get_system_prompt()
        assert prompt == self.generator.SYSTEM_PROMPT
        assert len(prompt) > 0

    def test_update_system_prompt(self):
        """Test updating system prompt."""
        new_prompt = "New system prompt"
        self.generator.update_system_prompt(new_prompt)

        assert self.generator.SYSTEM_PROMPT == new_prompt
        assert self.generator.get_system_prompt() == new_prompt

    def test_test_generation_success(self):
        """Test test generation functionality."""
        result = self.generator.test_generation("What is AI?", self.test_chunks)

        assert result["query"] == "What is AI?"
        assert result["num_chunks"] == 2
        assert result["success"] is True
        assert "prompt_length" in result
        assert "response_length" in result
        assert "answer" in result
        assert "citations" in result

    def test_test_generation_error(self):
        """Test test generation with error."""
        # Make LLM raise an exception
        self.mock_llm.response_text = None
        self.mock_llm.generate = MagicMock(side_effect=Exception("Test error"))

        result = self.generator.test_generation("What is AI?", self.test_chunks)

        assert result["query"] == "What is AI?"
        assert result["success"] is False
        assert "error" in result
        assert result["error"] == "Test error"

    def test_property_based_citation_completeness(self):
        """
        Property-based test: Citation generation completeness.

        Feature: orb, Property 10: Citation generation completeness
        """
        # Test various citation formats
        citation_responses = [
            "According to [1], AI is important.",
            "Based on [test1.md], machine learning is a subset.",
            "From [Source: test2.md], we can see that NLP is important.",
            "The research shows [1] and [2] are related.",
            "Multiple sources [test1.md], [test2.md], and [1] agree.",
        ]

        for response in citation_responses:
            citations = self.generator._extract_structured_citations(
                response, self.test_chunks
            )

            # Property 10: All citations should have valid file_path and title
            for citation in citations:
                assert citation.file_path, "Citation must have file_path"
                assert citation.title, "Citation must have title"
                assert citation.snippet, "Citation must have snippet"

                # File path should correspond to actual chunks
                assert any(
                    c.file_path == citation.file_path for c in self.test_chunks
                ), f"Citation file_path {citation.file_path} not found in chunks"

    def test_property_based_history_limit(self):
        """
        Property-based test: Conversation history limit.

        Feature: orb, Property 11: Conversation history limit
        """
        # Create history with more than MAX_HISTORY_TURNS
        long_history = []
        for i in range(10):
            long_history.append(ChatTurn(role="user", content=f"User question {i}"))
            long_history.append(
                ChatTurn(role="assistant", content=f"Assistant answer {i}")
            )

        prompt = self.generator._build_prompt(
            "Current question", self.test_chunks, long_history
        )

        # Count history turns in prompt
        user_count = prompt.count("User:")
        assistant_count = prompt.count("Assistant:")

        # Should include at most MAX_HISTORY_TURNS user turns
        assert user_count <= self.generator.MAX_HISTORY_TURNS + 1, (
            f"Too many user turns in prompt: {user_count}"
        )

        # Property 11: Should not exceed maximum history turns
        total_history_turns = (
            user_count + assistant_count - 2
        )  # Exclude current question
        assert total_history_turns <= self.generator.MAX_HISTORY_TURNS * 2, (
            f"Too many history turns: {total_history_turns}"
        )


if __name__ == "__main__":
    pytest.main([__file__])
