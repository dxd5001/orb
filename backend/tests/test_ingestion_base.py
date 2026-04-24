"""
Tests for BaseIngestor abstract class and related utilities.

This module tests the base functionality that all ingestors inherit from.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.ingestion.base import (
    BaseIngestor, IngestorFactory, sanitize_text, extract_metadata_from_path
)
from backend.models import NoteDocument, IngestResult


class MockIngestor(BaseIngestor):
    """Mock ingestor for testing the abstract base class."""
    
    def __init__(self, should_fail=False, fail_on_paths=None):
        """
        Initialize mock ingestor.
        
        Args:
            should_fail: Whether to simulate failures
            fail_on_paths: List of paths that should fail
        """
        self.should_fail = should_fail
        self.fail_on_paths = fail_on_paths or []
    
    def ingest(self, source_path: str) -> IngestResult:
        """Mock implementation of ingest method."""
        if self.should_fail:
            raise ValueError("Mock ingestor failure")
        
        # Create some mock notes
        notes = []
        errors = []
        
        # Simulate processing some files
        for i in range(3):
            file_path = f"test_file_{i}.md"
            
            if file_path in self.fail_on_paths:
                errors.append(self.create_error_entry(file_path, "Mock failure"))
                continue
            
            note = NoteDocument(
                file_path=file_path,
                title=f"Test Note {i}",
                body=f"Content of test note {i}",
                tags=["test"],
                frontmatter={"title": f"Test Note {i}"},
                last_modified=None
            )
            notes.append(note)
        
        return self.calculate_ingestion_stats(notes, errors)
    
    def validate_source_path(self, source_path: str) -> bool:
        """Mock validation that checks for 'invalid' in path."""
        return "invalid" not in source_path.lower()
    
    def get_supported_extensions(self) -> list:
        """Return mock supported extensions."""
        return [".md", ".txt"]
    
    def get_ingestor_name(self) -> str:
        """Return mock ingestor name."""
        return "MockIngestor"


class TestBaseIngestor:
    """Test cases for BaseIngestor abstract class."""
    
    def test_abstract_methods(self):
        """Test that BaseIngestor cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseIngestor()
    
    def test_concrete_implementation(self):
        """Test that concrete implementation works correctly."""
        ingestor = MockIngestor()
        
        # Test basic methods
        assert ingestor.validate_source_path("valid_path") is True
        assert ingestor.validate_source_path("invalid_path") is False
        assert ingestor.get_supported_extensions() == [".md", ".txt"]
        assert ingestor.get_ingestor_name() == "MockIngestor"
    
    def test_ingest_success(self):
        """Test successful ingestion."""
        ingestor = MockIngestor()
        result = ingestor.ingest("test_source")
        
        assert isinstance(result, IngestResult)
        assert len(result.notes) == 3
        assert result.total_count == 3
        assert result.skipped_count == 0
        assert len(result.errors) == 0
        
        # Check note content
        for i, note in enumerate(result.notes):
            assert isinstance(note, NoteDocument)
            assert note.file_path == f"test_file_{i}.md"
            assert note.title == f"Test Note {i}"
    
    def test_ingest_with_failures(self):
        """Test ingestion with some failures."""
        ingestor = MockIngestor(fail_on_paths=["test_file_1.md"])
        result = ingestor.ingest("test_source")
        
        assert len(result.notes) == 2  # One failed
        assert result.total_count == 2
        assert result.skipped_count == 1
        assert len(result.errors) == 1
        assert result.errors[0]["path"] == "test_file_1.md"
        assert result.errors[0]["reason"] == "Mock failure"
    
    def test_ingest_complete_failure(self):
        """Test ingestion that throws an exception."""
        ingestor = MockIngestor(should_fail=True)
        
        with pytest.raises(ValueError, match="Mock ingestor failure"):
            ingestor.ingest("test_source")
    
    def test_create_error_entry(self):
        """Test error entry creation."""
        ingestor = MockIngestor()
        error = ingestor.create_error_entry("test.md", "File not found")
        
        assert error["path"] == "test.md"
        assert error["reason"] == "File not found"
    
    def test_calculate_ingestion_stats(self):
        """Test ingestion statistics calculation."""
        ingestor = MockIngestor()
        
        notes = [
            NoteDocument("a.md", "A", "content", [], {}, None),
            NoteDocument("b.md", "B", "content", [], {}, None)
        ]
        errors = [
            ingestor.create_error_entry("c.md", "Error"),
            ingestor.create_error_entry("d.md", "Another error")
        ]
        
        result = ingestor.calculate_ingestion_stats(notes, errors)
        
        assert result.total_count == 2
        assert result.skipped_count == 2
        assert len(result.notes) == 2
        assert len(result.errors) == 2
    
    @patch('backend.ingestion.base.logger')
    def test_log_ingestion_start(self, mock_logger):
        """Test ingestion start logging."""
        ingestor = MockIngestor()
        ingestor.log_ingestion_start("test_path")
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Starting ingestion" in call_args
        assert "MockIngestor" in call_args
        assert "test_path" in call_args
    
    @patch('backend.ingestion.base.logger')
    def test_log_ingestion_complete(self, mock_logger):
        """Test ingestion completion logging."""
        ingestor = MockIngestor()
        result = IngestResult(
            notes=[],
            total_count=5,
            skipped_count=2,
            errors=[{"path": "test.md", "reason": "error"}]
        )
        
        ingestor.log_ingestion_complete(result)
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Ingestion completed" in call_args
        assert "5 notes processed" in call_args
        assert "2 skipped" in call_args
        assert "1 errors" in call_args
        
        # Should also log warnings for errors
        mock_logger.warning.assert_called_once()
    
    def test_default_validate_source_path(self):
        """Test default source path validation."""
        class MinimalIngestor(BaseIngestor):
            def ingest(self, source_path: str) -> IngestResult:
                return IngestResult([], 0, 0, [])
        
        ingestor = MinimalIngestor()
        
        assert ingestor.validate_source_path("valid_path") is True
        assert ingestor.validate_source_path("") is False
        assert ingestor.validate_source_path("   ") is False
        assert ingestor.validate_source_path(None) is False
    
    def test_default_get_supported_extensions(self):
        """Test default supported extensions method."""
        class MinimalIngestor(BaseIngestor):
            def ingest(self, source_path: str) -> IngestResult:
                return IngestResult([], 0, 0, [])
        
        ingestor = MinimalIngestor()
        assert ingestor.get_supported_extensions() == []
    
    def test_default_get_ingestor_name(self):
        """Test default ingestor name method."""
        class MinimalIngestor(BaseIngestor):
            def ingest(self, source_path: str) -> IngestResult:
                return IngestResult([], 0, 0, [])
        
        ingestor = MinimalIngestor()
        assert ingestor.get_ingestor_name() == "MinimalIngestor"


class TestIngestorFactory:
    """Test cases for IngestorFactory."""
    
    def test_register_ingestor(self):
        """Test registering an ingestor."""
        IngestorFactory.register_ingestor("mock", MockIngestor)
        
        assert "mock" in IngestorFactory.get_supported_types()
        assert MockIngestor in IngestorFactory._ingestors.values()
    
    def test_register_invalid_ingestor(self):
        """Test registering an invalid ingestor class."""
        class InvalidIngestor:
            pass
        
        with pytest.raises(ValueError, match="must inherit from BaseIngestor"):
            IngestorFactory.register_ingestor("invalid", InvalidIngestor)
    
    def test_create_ingestor(self):
        """Test creating an ingestor instance."""
        IngestorFactory.register_ingestor("mock", MockIngestor)
        
        ingestor = IngestorFactory.create_ingestor("mock")
        assert isinstance(ingestor, MockIngestor)
        
        # Test with constructor arguments
        ingestor = IngestorFactory.create_ingestor("mock", should_fail=True)
        assert isinstance(ingestor, MockIngestor)
        assert ingestor.should_fail is True
    
    def test_create_unsupported_ingestor(self):
        """Test creating an ingestor of unsupported type."""
        with pytest.raises(ValueError, match="Unsupported source type: unknown"):
            IngestorFactory.create_ingestor("unknown")
    
    def test_get_supported_types(self):
        """Test getting supported types list."""
        # Clear any existing registrations
        IngestorFactory._ingestors.clear()
        
        IngestorFactory.register_ingestor("mock", MockIngestor)
        IngestorFactory.register_ingestor("test", MockIngestor)
        
        types = IngestorFactory.get_supported_types()
        assert "mock" in types
        assert "test" in types
        assert len(types) == 2


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    def test_sanitize_text(self):
        """Test text sanitization."""
        # Normal text
        assert sanitize_text("Hello world") == "Hello world"
        
        # Text with null bytes
        assert sanitize_text("Hello\x00world") == "Helloworld"
        
        # Text with different line endings
        assert sanitize_text("Line 1\r\nLine 2\rLine 3") == "Line 1\nLine 2\nLine 3"
        
        # Text with leading/trailing whitespace
        assert sanitize_text("  Hello world  ") == "Hello world"
        
        # Empty and None text
        assert sanitize_text("") == ""
        assert sanitize_text(None) == ""
        assert sanitize_text("   ") == ""
    
    def test_extract_metadata_from_path(self):
        """Test metadata extraction from file path."""
        import tempfile
        import os
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name
        
        try:
            metadata = extract_metadata_from_path(temp_path)
            
            assert 'file_size' in metadata
            assert 'last_modified' in metadata
            assert 'created' in metadata
            assert metadata['file_size'] > 0
            assert metadata['last_modified'] is not None
            assert metadata['created'] is not None
        finally:
            os.unlink(temp_path)
    
    def test_extract_metadata_from_nonexistent_path(self):
        """Test metadata extraction from nonexistent file."""
        metadata = extract_metadata_from_path("/nonexistent/path")
        
        assert metadata['file_size'] == 0
        assert metadata['last_modified'] is not None
        assert metadata['created'] is not None


if __name__ == '__main__':
    pytest.main([__file__])
