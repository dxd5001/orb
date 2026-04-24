"""
Tests for data models.

This module tests the core data structures and validation functions.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from backend.models import (
    NoteDocument, Chunk, IngestResult, IndexResult, Scope,
    ChatTurn, ChatRequest, Citation, ChatResponse,
    StatusResponse, IndexResponse, ConfigGetResponse,
    ConfigUpdateRequest, ConfigUpdateResponse,
    validate_chat_request, validate_scope,
    create_chunk_id, extract_title_from_filename
)


class TestNoteDocument:
    """Test cases for NoteDocument."""
    
    def test_note_document_creation(self):
        """Test creating a NoteDocument."""
        doc = NoteDocument(
            file_path="test.md",
            title="Test Note",
            body="Test content",
            tags=["test"],
            frontmatter={"title": "Test Note", "tags": ["test"]},
            last_modified=datetime.now()
        )
        
        assert doc.file_path == "test.md"
        assert doc.title == "Test Note"
        assert doc.body == "Test content"
        assert doc.tags == ["test"]
        assert doc.frontmatter["title"] == "Test Note"
        assert isinstance(doc.last_modified, datetime)


class TestChunk:
    """Test cases for Chunk."""
    
    def test_chunk_creation(self):
        """Test creating a Chunk."""
        chunk = Chunk(
            chunk_id="test.md::0",
            text="Test chunk content",
            source_path="test.md",
            title="Test Note",
            tags=["test"],
            frontmatter={"title": "Test Note"},
            last_modified=datetime.now(),
            chunk_index=0
        )
        
        assert chunk.chunk_id == "test.md::0"
        assert chunk.text == "Test chunk content"
        assert chunk.source_path == "test.md"
        assert chunk.chunk_index == 0


class TestScope:
    """Test cases for Scope."""
    
    def test_scope_empty(self):
        """Test creating empty scope."""
        scope = Scope()
        assert scope.folder is None
        assert scope.tags is None
    
    def test_scope_with_folder(self):
        """Test creating scope with folder."""
        scope = Scope(folder="daily/")
        assert scope.folder == "daily/"
        assert scope.tags is None
    
    def test_scope_with_tags(self):
        """Test creating scope with tags."""
        scope = Scope(tags=["journal", "work"])
        assert scope.folder is None
        assert scope.tags == ["journal", "work"]
    
    def test_scope_full(self):
        """Test creating scope with both folder and tags."""
        scope = Scope(folder="daily/", tags=["journal"])
        assert scope.folder == "daily/"
        assert scope.tags == ["journal"]


class TestChatRequest:
    """Test cases for ChatRequest."""
    
    def test_chat_request_minimal(self):
        """Test creating minimal chat request."""
        request = ChatRequest(query="Hello")
        assert request.query == "Hello"
        assert request.scope is None
        assert request.history is None
    
    def test_chat_request_full(self):
        """Test creating full chat request."""
        history = [
            ChatTurn(role="user", content="Previous question"),
            ChatTurn(role="assistant", content="Previous answer")
        ]
        scope = Scope(folder="daily/")
        
        request = ChatRequest(
            query="New question",
            scope=scope,
            history=history
        )
        
        assert request.query == "New question"
        assert request.scope.folder == "daily/"
        assert len(request.history) == 2
    
    def test_chat_request_validation_empty_query(self):
        """Test validation with empty query."""
        request = ChatRequest(query="   ")
        errors = validate_chat_request(request)
        assert "Query cannot be empty" in errors
    
    def test_chat_request_validation_history_too_long(self):
        """Test validation with too many history turns."""
        history = [ChatTurn(role="user", content=f"Q{i}") for i in range(6)]
        request = ChatRequest(query="Question", history=history)
        errors = validate_chat_request(request)
        assert "History cannot exceed 5 turns" in errors
    
    def test_chat_request_validation_too_many_tags(self):
        """Test validation with too many scope tags."""
        scope = Scope(tags=[f"tag{i}" for i in range(11)])
        request = ChatRequest(query="Question", scope=scope)
        errors = validate_chat_request(request)
        assert "Scope cannot contain more than 10 tags" in errors


class TestChatResponse:
    """Test cases for ChatResponse."""
    
    def test_chat_response_minimal(self):
        """Test creating minimal chat response."""
        response = ChatResponse(answer="Test answer")
        assert response.answer == "Test answer"
        assert response.citations == []
    
    def test_chat_response_with_citations(self):
        """Test creating chat response with citations."""
        citations = [
            Citation(file_path="test.md", title="Test", snippet="Test snippet")
        ]
        response = ChatResponse(answer="Test answer", citations=citations)
        assert len(response.citations) == 1
        assert response.citations[0].file_path == "test.md"


class TestCitation:
    """Test cases for Citation."""
    
    def test_citation_creation(self):
        """Test creating a citation."""
        citation = Citation(
            file_path="daily/2024-01-01.md",
            title="2024-01-01",
            snippet="Important text here"
        )
        
        assert citation.file_path == "daily/2024-01-01.md"
        assert citation.title == "2024-01-01"
        assert citation.snippet == "Important text here"


class TestStatusResponse:
    """Test cases for StatusResponse."""
    
    def test_status_response_creation(self):
        """Test creating status response."""
        response = StatusResponse(
            index_status="ready",
            total_notes=100,
            total_chunks=500,
            last_indexed=datetime.now(),
            vector_store_path="/test/chroma"
        )
        
        assert response.index_status == "ready"
        assert response.total_notes == 100
        assert response.total_chunks == 500
        assert response.vector_store_path == "/test/chroma"


class TestIndexResponse:
    """Test cases for IndexResponse."""
    
    def test_index_response_success(self):
        """Test creating successful index response."""
        response = IndexResponse(
            status="completed",
            notes=50,
            chunks=200
        )
        
        assert response.status == "completed"
        assert response.notes == 50
        assert response.chunks == 200
        assert response.error is None
    
    def test_index_response_error(self):
        """Test creating error index response."""
        response = IndexResponse(
            status="error",
            error="Vault path not found"
        )
        
        assert response.status == "error"
        assert response.error == "Vault path not found"
        assert response.notes is None
        assert response.chunks is None


class TestConfigUpdateRequest:
    """Test cases for ConfigUpdateRequest."""
    
    def test_config_update_request_empty(self):
        """Test creating empty config update request."""
        request = ConfigUpdateRequest()
        assert request.vault_path is None
        assert request.llm_provider is None
    
    def test_config_update_request_partial(self):
        """Test creating partial config update request."""
        request = ConfigUpdateRequest(
            vault_path="/new/path",
            llm_provider="openai"
        )
        
        assert request.vault_path == "/new/path"
        assert request.llm_provider == "openai"
        assert request.llm_model is None


class TestConfigUpdateResponse:
    """Test cases for ConfigUpdateResponse."""
    
    def test_config_update_response_success(self):
        """Test creating successful config update response."""
        response = ConfigUpdateResponse(
            success=True,
            message="Configuration updated successfully",
            updated_fields=["vault_path", "llm_provider"]
        )
        
        assert response.success is True
        assert response.updated_fields == ["vault_path", "llm_provider"]
        assert len(response.errors) == 0
    
    def test_config_update_response_error(self):
        """Test creating error config update response."""
        response = ConfigUpdateResponse(
            success=False,
            message="Validation failed",
            updated_fields=[],
            errors=["Invalid vault path"]
        )
        
        assert response.success is False
        assert "Invalid vault path" in response.errors


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    def test_validate_scope_empty(self):
        """Test validating empty scope."""
        scope = Scope()
        errors = validate_scope(scope)
        assert len(errors) == 0
    
    def test_validate_scope_valid(self):
        """Test validating valid scope."""
        scope = Scope(folder="daily/", tags=["journal", "work"])
        errors = validate_scope(scope)
        assert len(errors) == 0
    
    def test_validate_scope_empty_folder(self):
        """Test validating scope with empty folder."""
        scope = Scope(folder="   ")
        errors = validate_scope(scope)
        assert "Folder path cannot be empty" in errors
    
    def test_validate_scope_empty_tag(self):
        """Test validating scope with empty tag."""
        scope = Scope(tags=["valid", "  "])
        errors = validate_scope(scope)
        assert "Tag cannot be empty" in errors
    
    def test_create_chunk_id(self):
        """Test chunk ID creation."""
        chunk_id = create_chunk_id("test.md", 0)
        assert chunk_id == "test.md::0"
        
        chunk_id = create_chunk_id("folder/note.md", 5)
        assert chunk_id == "folder/note.md::5"
    
    def test_extract_title_from_filename(self):
        """Test title extraction from filename."""
        title = extract_title_from_filename("test.md")
        assert title == "test"
        
        title = extract_title_from_filename("folder/2024-01-01.md")
        assert title == "2024-01-01"
        
        title = extract_title_from_filename("/path/to/note.md")
        assert title == "note"


class TestResultModels:
    """Test cases for result models."""
    
    def test_ingest_result_creation(self):
        """Test creating IngestResult."""
        notes = [
            NoteDocument(
                file_path="test.md",
                title="Test",
                body="Content",
                tags=[],
                frontmatter={},
                last_modified=datetime.now()
            )
        ]
        
        result = IngestResult(
            notes=notes,
            total_count=1,
            skipped_count=0,
            errors=[]
        )
        
        assert len(result.notes) == 1
        assert result.total_count == 1
        assert result.skipped_count == 0
        assert len(result.errors) == 0
    
    def test_index_result_creation(self):
        """Test creating IndexResult."""
        result = IndexResult(note_count=10, chunk_count=50)
        assert result.note_count == 10
        assert result.chunk_count == 50


if __name__ == '__main__':
    pytest.main([__file__])
