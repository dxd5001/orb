"""
Tests for Retriever implementation.

This module tests the similarity search and scope filtering functionality.
"""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.retrieval.retriever import Retriever
from backend.models import Chunk, Scope


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


class TestRetriever:
    """Test cases for Retriever."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_embedding = MockEmbeddingBackend()
        
        # Mock ChromaDB availability
        with patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True):
            with patch('backend.retrieval.retriever.chromadb') as mock_chromadb:
                # Setup mock ChromaDB client and collection
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_collection.count.return_value = 10
                mock_client.get_collection.return_value = mock_collection
                mock_chromadb.PersistentClient.return_value = mock_client
                
                self.retriever = Retriever(self.mock_embedding, self.temp_dir)
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_without_chromadb(self):
        """Test initialization without ChromaDB."""
        with patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', False):
            with pytest.raises(ImportError, match="chromadb library is not available"):
                Retriever(self.mock_embedding, self.temp_dir)
    
    def test_get_collection_success(self):
        """Test successful collection retrieval."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        
        with patch('backend.retrieval.retriever.chromadb') as mock_chromadb:
            mock_chromadb.PersistentClient.return_value = mock_client
            
            retriever = Retriever(self.mock_embedding, self.temp_dir)
            collection = retriever._get_collection()
            
            assert collection == mock_collection
    
    def test_get_collection_not_found(self):
        """Test collection not found error."""
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Collection not found")
        
        with patch('backend.retrieval.retriever.chromadb') as mock_chromadb:
            mock_chromadb.PersistentClient.return_value = mock_client
            
            retriever = Retriever(self.mock_embedding, self.temp_dir)
            
            with pytest.raises(RuntimeError, match="Collection obsidian_vault not found"):
                retriever._get_collection()
    
    def test_retrieve_empty_query(self):
        """Test retrieval with empty query."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            self.retriever.retrieve("")
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            self.retriever.retrieve("   ")
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_retrieve_success(self, mock_chromadb):
        """Test successful retrieval."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        
        # Mock query results
        mock_results = {
            'ids': [['chunk1', 'chunk2']],
            'documents': [['Document 1 content', 'Document 2 content']],
            'metadatas': [[
                {
                    'source_path': 'test1.md',
                    'title': 'Test 1',
                    'tags': '["tag1", "tag2"]',
                    'frontmatter': '{"title": "Test 1"}',
                    'last_modified': '2024-01-01T00:00:00',
                    'chunk_index': 0
                },
                {
                    'source_path': 'test2.md',
                    'title': 'Test 2',
                    'tags': '["tag3"]',
                    'frontmatter': '{"title": "Test 2"}',
                    'last_modified': '2024-01-02T00:00:00',
                    'chunk_index': 0
                }
            ]]
        }
        
        mock_collection.query.return_value = mock_results
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        results = retriever.retrieve("test query")
        
        assert len(results) == 2
        
        # Check first result
        chunk1 = results[0]
        assert chunk1.chunk_id == 'chunk1'
        assert chunk1.text == 'Document 1 content'
        assert chunk1.source_path == 'test1.md'
        assert chunk1.title == 'Test 1'
        assert chunk1.tags == ['tag1', 'tag2']
        assert chunk1.frontmatter == {'title': 'Test 1'}
        assert chunk1.chunk_index == 0
        
        # Check second result
        chunk2 = results[1]
        assert chunk2.chunk_id == 'chunk2'
        assert chunk2.source_path == 'test2.md'
        assert chunk2.tags == ['tag3']
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_retrieve_with_scope(self, mock_chromadb):
        """Test retrieval with scope filtering."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            'ids': [['chunk1']],
            'documents': [['Document 1']],
            'metadatas': [[{'source_path': 'folder/test.md'}]]
        }
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        scope = Scope(folder="daily/", tags=["journal"])
        
        results = retriever.retrieve("test query", scope=scope)
        
        assert len(results) == 1
        
        # Verify that query was called with filter
        mock_collection.query.assert_called_once()
        call_args = mock_collection.query.call_args
        assert 'where' in call_args.kwargs
        where_filter = call_args.kwargs['where']
        assert '$and' in where_filter  # Should combine folder and tag filters
    
    def test_build_scope_filter_none(self):
        """Test building filter with no scope."""
        filter_result = self.retriever._build_scope_filter(None)
        assert filter_result is None
    
    def test_build_scope_filter_folder_only(self):
        """Test building filter with folder scope only."""
        scope = Scope(folder="daily/")
        filter_result = self.retriever._build_scope_filter(scope)
        
        assert 'source_path' in filter_result
        assert '$contains' in filter_result['source_path']
        assert filter_result['source_path']['$contains'] == "daily/"
    
    def test_build_scope_filter_tags_only(self):
        """Test building filter with tags scope only."""
        scope = Scope(tags=["journal", "work"])
        filter_result = self.retriever._build_scope_filter(scope)
        
        assert 'tags' in filter_result
        assert '$contains' in filter_result['tags']
        assert '"journal"' in filter_result['tags']['$contains']
    
    def test_build_scope_filter_both(self):
        """Test building filter with both folder and tags."""
        scope = Scope(folder="daily/", tags=["journal"])
        filter_result = self.retriever._build_scope_filter(scope)
        
        assert '$and' in filter_result
        assert len(filter_result['$and']) == 2
    
    def test_build_scope_filter_multiple_tags(self):
        """Test building filter with multiple tags."""
        scope = Scope(tags=["tag1", "tag2", "tag3"])
        filter_result = self.retriever._build_scope_filter(scope)
        
        assert '$and' in filter_result
        assert len(filter_result['$and']) == 3
        for condition in filter_result['$and']:
            assert 'tags' in condition
            assert '$contains' in condition['tags']
    
    def test_results_to_chunks_empty(self):
        """Test converting empty results to chunks."""
        empty_results = {'ids': [[]], 'documents': [[]], 'metadatas': [[]]}
        chunks = self.retriever._results_to_chunks(empty_results)
        assert len(chunks) == 0
    
    def test_results_to_chunks_malformed(self):
        """Test converting malformed results to chunks."""
        malformed_results = {
            'ids': [['chunk1']],
            'documents': [['Document 1']],
            'metadatas': [[]]  # Missing metadata
        }
        
        chunks = self.retriever._results_to_chunks(malformed_results)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == 'chunk1'
        assert chunks[0].text == 'Document 1'
        assert chunks[0].source_path == ''  # Default empty value
    
    def test_parse_tags(self):
        """Test tag parsing from JSON strings."""
        # Valid JSON array
        tags = self.retriever._parse_tags('["tag1", "tag2", "tag3"]')
        assert tags == ['tag1', 'tag2', 'tag3']
        
        # Empty array
        tags = self.retriever._parse_tags('[]')
        assert tags == []
        
        # Invalid JSON
        tags = self.retriever._parse_tags('invalid')
        assert tags == []
        
        # Non-array JSON
        tags = self.retriever._parse_tags('"single_tag"')
        assert tags == []
    
    def test_parse_json(self):
        """Test JSON parsing."""
        # Valid JSON object
        obj = self.retriever._parse_json('{"key": "value", "number": 42}')
        assert obj == {'key': 'value', 'number': 42}
        
        # Empty object
        obj = self.retriever._parse_json('{}')
        assert obj == {}
        
        # Invalid JSON
        obj = self.retriever._parse_json('invalid')
        assert obj == {}
        
        # Non-object JSON
        obj = self.retriever._parse_json('"string"')
        assert obj == {}
    
    def test_parse_datetime(self):
        """Test datetime parsing."""
        # Valid ISO datetime
        dt = self.retriever._parse_datetime('2024-01-01T12:00:00')
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        
        # With timezone
        dt = self.retriever._parse_datetime('2024-01-01T12:00:00Z')
        assert dt is not None
        
        # Empty string
        dt = self.retriever._parse_datetime('')
        assert dt is None
        
        # Invalid datetime
        dt = self.retriever._parse_datetime('invalid')
        assert dt is None
    
    def test_get_collection_stats(self):
        """Test getting collection statistics."""
        stats = self.retriever.get_collection_stats()
        
        assert stats['collection_name'] == 'obsidian_vault'
        assert stats['total_chunks'] == 10
        assert stats['embedding_dimension'] == 768
        assert stats['embedding_model'] == 'mock_model'
        assert stats['vector_store_path'] == self.temp_dir
    
    def test_is_collection_empty(self):
        """Test checking if collection is empty."""
        # Mock collection with count > 0
        self.retriever.collection.count.return_value = 5
        assert self.retriever.is_collection_empty() is False
        
        # Mock collection with count = 0
        self.retriever.collection.count.return_value = 0
        assert self.retriever.is_collection_empty() is True
    
    def test_validate_scope_valid(self):
        """Test scope validation with valid scope."""
        scope = Scope(folder="daily/", tags=["journal", "work"])
        errors = self.retriever.validate_scope(scope)
        assert len(errors) == 0
    
    def test_validate_scope_invalid(self):
        """Test scope validation with invalid scope."""
        scope = Scope(folder="", tags=["", "valid"])
        errors = self.retriever.validate_scope(scope)
        assert len(errors) == 2
        assert "Folder path cannot be empty" in errors
        assert "Tag cannot be empty" in errors
    
    def test_test_query_success(self,):
        """Test test query functionality."""
        # Setup mock results
        self.retriever.collection.query.return_value = {
            'ids': [['chunk1']],
            'documents': [['Test document']],
            'metadatas': [[{'source_path': 'test.md'}]]
        }
        
        result = self.retriever.test_query("test query", Scope(folder="daily/"))
        
        assert result['query'] == "test query"
        assert result['scope'] == {'folder': 'daily/', 'tags': None}
        assert 'filter' in result
        assert result['num_results'] == 1
        assert 'collection_stats' in result
        assert len(result['sample_results']) == 1
    
    def test_test_query_error(self):
        """Test test query with error."""
        self.retriever.collection.query.side_effect = Exception("Test error")
        
        result = self.retriever.test_query("test query")
        
        assert result['query'] == "test query"
        assert result['scope'] is None
        assert 'error' in result
        assert result['error'] == "Test error"
    
    def test_property_based_retrieval_count_constraint(self):
        """
        Property-based test: Retrieval should return at most top_k results.
        
        Feature: orb, Property 9: Retrieval result count constraint
        """
        import random
        
        # Test with various top_k values
        for top_k in [1, 3, 5, 10, 20]:
            # Mock results with more items than requested
            mock_results = {
                'ids': [[f'chunk{i}' for i in range(top_k * 2)]],
                'documents': [[f'Document {i}' for i in range(top_k * 2)]],
                'metadatas': [[{'source_path': f'test{i}.md'} for i in range(top_k * 2)]]
            }
            
            self.retriever.collection.query.return_value = mock_results
            
            results = self.retriever.retrieve("test query", top_k=top_k)
            
            # Property 9: Should return at most top_k results
            assert len(results) <= top_k, \
                f"Retrieved {len(results)} results but requested at most {top_k}"
    
    def test_property_based_scope_filter_accuracy(self):
        """
        Property-based test: Scope filtering should be accurate.
        
        Feature: orb, Property 12: Scope filter accuracy
        """
        test_scopes = [
            Scope(folder="daily/"),
            Scope(tags=["journal"]),
            Scope(folder="work/", tags=["important"]),
            Scope(tags=["tag1", "tag2", "tag3"])
        ]
        
        for scope in test_scopes:
            filter_result = self.retriever._build_scope_filter(scope)
            
            if scope.folder and scope.tags:
                # Both folder and tags - should use $and
                assert '$and' in filter_result
                conditions = filter_result['$and']
                assert len(conditions) == 2
                
                # Check folder condition
                folder_cond = next(c for c in conditions if 'source_path' in c)
                assert scope.folder in folder_cond['source_path']['$contains']
                
                # Check tag conditions
                tag_conds = [c for c in conditions if 'tags' in c]
                assert len(tag_conds) == len(scope.tags)
                
            elif scope.folder:
                # Only folder
                assert 'source_path' in filter_result
                assert scope.folder in filter_result['source_path']['$contains']
                
            elif scope.tags:
                # Only tags
                if len(scope.tags) == 1:
                    assert 'tags' in filter_result
                else:
                    assert '$and' in filter_result
                    tag_conds = filter_result['$and']
                    assert len(tag_conds) == len(scope.tags)


if __name__ == '__main__':
    pytest.main([__file__])
