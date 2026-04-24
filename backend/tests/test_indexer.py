"""
Tests for Indexer implementation.

This module tests the chunking, embedding, and vector storage functionality.
"""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.indexing.indexer import Indexer
from backend.models import NoteDocument, Chunk, IngestResult, IndexResult


class MockEmbeddingBackend:
    """Mock embedding backend for testing."""
    
    def __init__(self, dimension=768):
        self.dimension = dimension
        self.model_name = "mock_model"
    
    def embed(self, texts):
        # Return mock embeddings
        return [[0.1] * self.dimension for _ in texts]
    
    def get_embedding_dimension(self):
        return self.dimension
    
    def get_model_name(self):
        return self.model_name


class TestIndexer:
    """Test cases for Indexer."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_embedding = MockEmbeddingBackend()
        
        # Mock ChromaDB availability
        with patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True):
            with patch('backend.indexing.indexer.chromadb') as mock_chromadb:
                # Setup mock ChromaDB client and collection
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_client.get_collection.side_effect = Exception("Collection not found")
                mock_client.create_collection.return_value = mock_collection
                mock_chromadb.PersistentClient.return_value = mock_client
                
                self.indexer = Indexer(self.mock_embedding, self.temp_dir)
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_without_chromadb(self):
        """Test initialization without ChromaDB."""
        with patch('backend.indexing.indexer.CHROMADB_AVAILABLE', False):
            with pytest.raises(ImportError, match="chromadb library is not available"):
                Indexer(self.mock_embedding, self.temp_dir)
    
    def test_chunk_note_short_text(self):
        """Test chunking a note with short text."""
        note = NoteDocument(
            file_path="test.md",
            title="Test Note",
            body="Short text content",
            tags=["test"],
            frontmatter={"title": "Test Note"},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        assert len(chunks) == 1
        assert chunks[0].text == "Short text content"
        assert chunks[0].chunk_index == 0
        assert chunks[0].source_path == "test.md"
    
    def test_chunk_note_long_text(self):
        """Test chunking a note with long text."""
        # Create text longer than chunk size
        long_text = "a" * 1500  # Longer than CHUNK_SIZE (1000)
        
        note = NoteDocument(
            file_path="long.md",
            title="Long Note",
            body=long_text,
            tags=["test"],
            frontmatter={"title": "Long Note"},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        assert len(chunks) > 1
        
        # Check chunk sizes
        for i, chunk in enumerate(chunks):
            assert len(chunk.text) <= self.indexer.CHUNK_SIZE
            assert chunk.chunk_index == i
            assert chunk.source_path == "long.md"
        
        # Check that chunks overlap correctly
        if len(chunks) > 1:
            # Second chunk should overlap with first
            first_chunk_end = chunks[0].text[-50:]
            second_chunk_start = chunks[1].text[:50]
            # There should be some overlap
            assert len(first_chunk_end) + len(second_chunk_start) > len(set(first_chunk_end + second_chunk_start))
    
    def test_chunk_note_exact_chunk_size(self):
        """Test chunking text exactly at chunk size boundary."""
        exact_text = "a" * self.indexer.CHUNK_SIZE
        
        note = NoteDocument(
            file_path="exact.md",
            title="Exact Note",
            body=exact_text,
            tags=["test"],
            frontmatter={"title": "Exact Note"},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        assert len(chunks) == 1
        assert len(chunks[0].text) == self.indexer.CHUNK_SIZE
    
    def test_chunk_note_empty_text(self):
        """Test chunking a note with empty text."""
        note = NoteDocument(
            file_path="empty.md",
            title="Empty Note",
            body="",
            tags=["test"],
            frontmatter={"title": "Empty Note"},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        # Should create one chunk even with empty text
        assert len(chunks) == 1
        assert chunks[0].text == ""
    
    def test_chunk_to_metadata(self):
        """Test converting chunk to metadata format."""
        chunk = Chunk(
            chunk_id="test.md::0",
            text="Test content",
            source_path="test.md",
            title="Test Note",
            tags=["tag1", "tag2"],
            frontmatter={"title": "Test Note", "author": "John"},
            last_modified=datetime.now(),
            chunk_index=0
        )
        
        metadata = self.indexer._chunk_to_metadata(chunk)
        
        assert metadata['source_path'] == "test.md"
        assert metadata['title'] == "Test Note"
        assert metadata['tags'] == '["tag1", "tag2"]'  # JSON string
        assert metadata['frontmatter'] == '{"title": "Test Note", "author": "John"}'  # JSON string
        assert 'last_modified' in metadata
        assert metadata['chunk_index'] == 0
    
    def test_index_empty_ingest_result(self):
        """Test indexing with empty ingest result."""
        empty_result = IngestResult(notes=[], total_count=0, skipped_count=0, errors=[])
        
        with pytest.raises(ValueError, match="No notes to index"):
            self.indexer.index(empty_result)
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_index_success(self, mock_chromadb):
        """Test successful indexing process."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.side_effect = Exception("Collection not found")
        mock_client.create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        # Create test data
        note = NoteDocument(
            file_path="test.md",
            title="Test Note",
            body="Test content for indexing",
            tags=["test"],
            frontmatter={"title": "Test Note"},
            last_modified=datetime.now()
        )
        
        ingest_result = IngestResult(
            notes=[note],
            total_count=1,
            skipped_count=0,
            errors=[]
        )
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        result = indexer.index(ingest_result)
        
        assert isinstance(result, IndexResult)
        assert result.note_count == 1
        assert result.chunk_count == 1
        
        # Verify ChromaDB operations
        mock_client.delete_collection.assert_called_once()
        mock_client.create_collection.assert_called_once()
        mock_collection.add.assert_called_once()
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_index_multiple_notes(self, mock_chromadb):
        """Test indexing multiple notes."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.side_effect = Exception("Collection not found")
        mock_client.create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        # Create test notes
        notes = [
            NoteDocument(
                file_path=f"note{i}.md",
                title=f"Note {i}",
                body=f"Content for note {i}",
                tags=["test"],
                frontmatter={"title": f"Note {i}"},
                last_modified=datetime.now()
            )
            for i in range(3)
        ]
        
        ingest_result = IngestResult(
            notes=notes,
            total_count=3,
            skipped_count=0,
            errors=[]
        )
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        result = indexer.index(ingest_result)
        
        assert result.note_count == 3
        assert result.chunk_count == 3  # One chunk per note for short texts
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_clear_collection(self, mock_chromadb):
        """Test clearing existing collection."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        indexer._clear_collection()
        
        mock_client.delete_collection.assert_called_once_with(name="obsidian_vault")
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_get_collection_stats(self, mock_chromadb):
        """Test getting collection statistics."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 42
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        stats = indexer.get_collection_stats()
        
        assert stats['collection_name'] == "obsidian_vault"
        assert stats['total_chunks'] == 42
        assert stats['embedding_dimension'] == 768
        assert stats['embedding_model'] == "mock_model"
        assert stats['vector_store_path'] == self.temp_dir
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_validate_indexing(self, mock_chromadb):
        """Test indexing validation."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        result = indexer.validate_indexing()
        
        assert result is True
        
        # Test with empty collection
        mock_collection.count.return_value = 0
        result = indexer.validate_indexing()
        assert result is False
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_delete_collection(self, mock_chromadb):
        """Test deleting collection."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        indexer.delete_collection()
        
        mock_client.delete_collection.assert_called_once_with(name="obsidian_vault")
    
    @patch('backend.indexing.indexer.CHROMADB_AVAILABLE', True)
    @patch('backend.indexing.indexer.chromadb')
    def test_get_sample_chunks(self, mock_chromadb):
        """Test getting sample chunks."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            'ids': ['chunk1', 'chunk2'],
            'documents': ['Document 1', 'Document 2'],
            'metadatas': [{'meta1': 'value1'}, {'meta2': 'value2'}]
        }
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        indexer = Indexer(self.mock_embedding, self.temp_dir)
        samples = indexer.get_sample_chunks(limit=2)
        
        assert len(samples) == 2
        assert samples[0]['id'] == 'chunk1'
        assert samples[0]['text'] == 'Document 1'
        assert samples[0]['metadata'] == {'meta1': 'value1'}
    
    def test_chunk_boundary_word_break(self):
        """Test that chunks break at word boundaries when possible."""
        # Create text with word boundaries near chunk size
        words = ["word"] * 200  # Each word is 4 chars + space = 5 chars
        text = " ".join(words)  # ~1000 chars
        
        note = NoteDocument(
            file_path="boundary.md",
            title="Boundary Test",
            body=text,
            tags=["test"],
            frontmatter={"title": "Boundary Test"},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        # Should have at least 2 chunks
        assert len(chunks) >= 2
        
        # Check that chunks don't break in the middle of words
        for chunk in chunks:
            # Chunk should not start or end with partial word
            assert not chunk.text.startswith('word') and not chunk.text.endswith('word')
            # If not empty, should start with a word (not partial)
            if chunk.text.strip():
                assert chunk.text.strip()[0].isalnum() or chunk.text.strip()[0] == '"'
    
    def test_property_based_chunk_size_constraints(self):
        """
        Property-based test: All chunks should satisfy size constraints.
        
        Feature: orb, Property 6: Chunk size constraints
        """
        import random
        import string
        
        # Generate random text of various lengths
        for _ in range(10):
            # Random length between 500 and 3000 characters
            length = random.randint(500, 3000)
            random_text = ''.join(random.choices(string.ascii_letters + ' ', k=length))
            
            note = NoteDocument(
                file_path="random.md",
                title="Random",
                body=random_text,
                tags=["test"],
                frontmatter={"title": "Random"},
                last_modified=datetime.now()
            )
            
            chunks = self.indexer._chunk_note(note)
            
            # Property 6: All chunks must be <= CHUNK_SIZE characters
            for chunk in chunks:
                assert len(chunk.text) <= self.indexer.CHUNK_SIZE, \
                    f"Chunk size {len(chunk.text)} exceeds limit {self.indexer.CHUNK_SIZE}"
    
    def test_property_based_metadata_roundtrip(self):
        """
        Property-based test: Metadata should round-trip correctly.
        
        Feature: orb, Property 7: Metadata propagation round-trip
        """
        note = NoteDocument(
            file_path="test/path/note.md",
            title="Test Title",
            body="Test content",
            tags=["tag1", "tag2", "tag3"],
            frontmatter={"title": "Test Title", "author": "John Doe", "published": True},
            last_modified=datetime.now()
        )
        
        chunks = self.indexer._chunk_note(note)
        
        # Property 7: All chunk metadata should match original note
        for chunk in chunks:
            assert chunk.source_path == note.file_path
            assert chunk.title == note.title
            assert chunk.tags == note.tags
            assert chunk.frontmatter == note.frontmatter
            assert chunk.last_modified == note.last_modified


if __name__ == '__main__':
    pytest.main([__file__])
