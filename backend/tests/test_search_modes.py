"""
Tests for Search Mode functionality.

This module tests the search mode selection feature (Auto/Diary/General)
and verifies that each mode behaves correctly with different query types.
"""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.retrieval.retriever import Retriever
from backend.models import Chunk, Scope, SearchMode


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


class TestSearchModes:
    """Test cases for Search Mode functionality."""
    
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
    
    def test_search_mode_enum_values(self):
        """Test SearchMode enum has correct values."""
        assert SearchMode.AUTO.value == "auto"
        assert SearchMode.DIARY.value == "diary"
        assert SearchMode.GENERAL.value == "general"
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_diary_mode_date_query(self, mock_chromadb):
        """Test DIARY mode with date query prioritizes filename search."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Mock filename search to return results
        mock_chunks = [
            Chunk(
                chunk_id="daily/2024-01-01::0",
                text="Diary entry for January 1st",
                source_path="daily/2024-01-01.md",
                title="2024-01-01",
                tags=["diary"],
                frontmatter={"date": "2024-01-01"},
                last_modified=datetime(2024, 1, 1),
                chunk_index=0
            )
        ]
        
        with patch.object(retriever, '_search_by_filename', return_value=mock_chunks):
            results = retriever.retrieve("2024-01-01", search_mode=SearchMode.DIARY)
            
            assert len(results) == 1
            assert results[0].source_path == "daily/2024-01-01.md"
            # Should not call semantic search when filename search succeeds
            mock_collection.query.assert_not_called()
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_diary_mode_semantic_fallback(self, mock_chromadb):
        """Test DIARY mode falls back to semantic search when filename search fails."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Mock filename search to return empty
        with patch.object(retriever, '_search_by_filename', return_value=[]):
            # Mock semantic search results
            mock_results = {
                'ids': [['chunk1']],
                'documents': [['Diary entry about my day']],
                'metadatas': [[{
                    'source_path': 'daily/2024-01-02.md',
                    'title': '2024-01-02',
                    'tags': '["diary"]',
                    'frontmatter': '{"date": "2024-01-02"}',
                    'last_modified': '2024-01-02T00:00:00',
                    'chunk_index': 0
                }]]
            }
            mock_collection.query.return_value = mock_results
            
            results = retriever.retrieve("what I ate today", search_mode=SearchMode.DIARY)
            
            assert len(results) == 1
            assert results[0].source_path == "daily/2024-01-02.md"
            
            # Verify semantic search was called without forcing a diary-only where filter
            mock_collection.query.assert_called_once()
            call_args = mock_collection.query.call_args
            where_filter = call_args.kwargs['where']
            assert where_filter is None
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_general_mode_semantic_search(self, mock_chromadb):
        """Test GENERAL mode performs semantic search without diary preference."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Mock semantic search results
        mock_results = {
            'ids': [['chunk1', 'chunk2']],
            'documents': [['Meeting notes', 'Project documentation']],
            'metadatas': [[
                {
                    'source_path': 'work/meetings.md',
                    'title': 'Meeting Notes',
                    'tags': '["work"]',
                    'frontmatter': '{"type": "meeting"}',
                    'last_modified': '2024-01-01T00:00:00',
                    'chunk_index': 0
                },
                {
                    'source_path': 'projects/project1.md',
                    'title': 'Project 1',
                    'tags': '["project"]',
                    'frontmatter': '{"type": "project"}',
                    'last_modified': '2024-01-02T00:00:00',
                    'chunk_index': 0
                }
            ]]
        }
        mock_collection.query.return_value = mock_results
        
        results = retriever.retrieve("project status", search_mode=SearchMode.GENERAL)
        
        assert len(results) == 2
        assert results[0].source_path == "work/meetings.md"
        assert results[1].source_path == "projects/project1.md"
        
        # Verify semantic search was called without diary folder preference
        mock_collection.query.assert_called_once()
        call_args = mock_collection.query.call_args
        where_filter = call_args.kwargs.get('where')
        # Should not have diary folder preference
        assert where_filter is None or 'source_path' not in where_filter
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_auto_mode_diary_detection(self, mock_chromadb):
        """Test AUTO mode detects diary-related queries and uses diary strategy."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Test diary-related queries
        diary_queries = [
            "what did I eat yesterday",
            "today's meeting notes",
            "my breakfast this morning",
            "how I slept last night",
            "journal entry about work"
        ]
        
        for query in diary_queries:
            with patch.object(retriever, '_retrieve_diary_mode') as mock_diary:
                mock_diary.return_value = []
                retriever.retrieve(query, search_mode=SearchMode.AUTO)
                mock_diary.assert_called_once()
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_auto_mode_date_detection(self, mock_chromadb):
        """Test AUTO mode detects date queries and uses diary strategy."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Test date queries
        date_queries = [
            "2024-01-01",
            "yesterday",
            "today",
            "tomorrow",
            "last week"
        ]
        
        for query in date_queries:
            with patch.object(retriever, '_retrieve_diary_mode') as mock_diary:
                mock_diary.return_value = []
                retriever.retrieve(query, search_mode=SearchMode.AUTO)
                mock_diary.assert_called_once()
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_auto_mode_general_detection(self, mock_chromadb):
        """Test AUTO mode detects general queries and uses general strategy."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Test general queries
        general_queries = [
            "project documentation",
            "technical specifications",
            "research findings",
            "book summary",
            "API reference"
        ]
        
        for query in general_queries:
            with patch.object(retriever, '_retrieve_general_mode') as mock_general:
                mock_general.return_value = []
                retriever.retrieve(query, search_mode=SearchMode.AUTO)
                mock_general.assert_called_once()
    
    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_diary_mode_with_scope(self, mock_chromadb):
        """Test DIARY mode respects user-specified scope."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        
        retriever = Retriever(self.mock_embedding, self.temp_dir)
        
        # Test with user-specified folder scope
        scope = Scope(folder="work/")
        
        with patch.object(retriever, '_search_by_filename', return_value=[]):
            mock_results = {
                'ids': [['chunk1']],
                'documents': [['Work diary entry']],
                'metadatas': [[{'source_path': 'work/diary.md'}]]
            }
            mock_collection.query.return_value = mock_results
            
            retriever.retrieve("work tasks", search_mode=SearchMode.DIARY, scope=scope)
            
            # Should use only the user's folder scope
            mock_collection.query.assert_called_once()
            call_args = mock_collection.query.call_args
            where_filter = call_args.kwargs['where']
            assert where_filter == {
                'source_path': {
                    '$contains': 'work/'
                }
            }

    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_general_mode_temporal_query_sorts_by_oldest(self, mock_chromadb):
        """Test GENERAL mode uses metadata-enhanced retrieval for temporal queries."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        retriever = Retriever(self.mock_embedding, self.temp_dir)

        mock_results = {
            'ids': [['chunk1', 'chunk2']],
            'documents': [['Oxios recent mention', 'Oxios first mention']],
            'metadatas': [[
                {
                    'source_path': 'notes/2025-12-30.md',
                    'title': '2025-12-30',
                    'tags': '["project"]',
                    'frontmatter': '{"date": "2025-12-30"}',
                    'last_modified': '2025-12-30T00:00:00',
                    'chunk_index': 0
                },
                {
                    'source_path': 'notes/2025-01-15.md',
                    'title': '2025-01-15',
                    'tags': '["project"]',
                    'frontmatter': '{"date": "2025-01-15"}',
                    'last_modified': '2025-01-15T00:00:00',
                    'chunk_index': 0
                }
            ]]
        }
        mock_collection.query.return_value = mock_results

        results = retriever.retrieve("oxiosという名前が初めて登場したのはいつ？", search_mode=SearchMode.GENERAL)

        assert len(results) == 2
        assert results[0].source_path == 'notes/2025-01-15.md'
        assert results[1].source_path == 'notes/2025-12-30.md'
        call_args = mock_collection.query.call_args
        assert call_args.kwargs['n_results'] == 50

    @patch('backend.retrieval.retriever.CHROMADB_AVAILABLE', True)
    @patch('backend.retrieval.retriever.chromadb')
    def test_diary_mode_temporal_query_prefers_diary_chunks(self, mock_chromadb):
        """Test DIARY mode temporal queries prefer diary chunks before sorting."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        retriever = Retriever(self.mock_embedding, self.temp_dir)

        mock_results = {
            'ids': [['chunk1', 'chunk2', 'chunk3']],
            'documents': [['recent diary', 'old work note', 'old diary']],
            'metadatas': [[
                {
                    'source_path': 'Diary/2025-07-01.md',
                    'title': '2025-07-01',
                    'tags': '["diary"]',
                    'frontmatter': '{"date": "2025-07-01"}',
                    'last_modified': '2025-07-01T00:00:00',
                    'chunk_index': 0
                },
                {
                    'source_path': 'work/2025-01-01.md',
                    'title': 'work',
                    'tags': '["work"]',
                    'frontmatter': '{"date": "2025-01-01"}',
                    'last_modified': '2025-01-01T00:00:00',
                    'chunk_index': 0
                },
                {
                    'source_path': 'Diary/2025-02-01.md',
                    'title': '2025-02-01',
                    'tags': '["diary"]',
                    'frontmatter': '{"date": "2025-02-01"}',
                    'last_modified': '2025-02-01T00:00:00',
                    'chunk_index': 0
                }
            ]]
        }
        mock_collection.query.return_value = mock_results

        with patch.object(retriever, '_search_by_filename', return_value=[]):
            results = retriever.retrieve("oxiosが初めて登場したのはいつ？", search_mode=SearchMode.DIARY)

        assert len(results) == 2
        assert results[0].source_path == 'Diary/2025-02-01.md'
        assert results[1].source_path == 'Diary/2025-07-01.md'
    
    def test_search_mode_parameter_passing(self):
        """Test that search_mode parameter is properly passed through the system."""
        # This test verifies the interface works correctly
        assert hasattr(self.retriever.retrieve, '__code__')
        params = self.retriever.retrieve.__code__.co_varnames
        assert 'search_mode' in params
    
    def test_example_based_search_mode_behavior(self):
        """
        Example-based test: Verify search modes behave as expected with realistic examples.
        
        Examples from requirements:
        - Diary query: "yesterday, ate" should prioritize diary entries
        - General query: "project documentation" should search across all notes
        - Auto mode should automatically choose appropriate strategy
        """
        examples = [
            {
                'query': 'yesterday, ate',
                'expected_mode': 'diary',
                'search_mode': SearchMode.DIARY,
                'description': 'Diary query with date expression'
            },
            {
                'query': 'project documentation',
                'expected_mode': 'general',
                'search_mode': SearchMode.GENERAL,
                'description': 'General query about documentation'
            },
            {
                'query': 'what I ate today',
                'expected_mode': 'diary',
                'search_mode': SearchMode.AUTO,
                'description': 'Auto mode should detect diary query'
            },
            {
                'query': 'API reference',
                'expected_mode': 'general',
                'search_mode': SearchMode.AUTO,
                'description': 'Auto mode should detect general query'
            }
        ]
        
        for example in examples:
            query = example['query']
            search_mode = example['search_mode']
            expected_behavior = example['expected_mode']
            description = example['description']
            
            # Test that the method accepts the parameters correctly
            try:
                # Mock the internal methods to avoid actual DB calls
                with patch.object(self.retriever, '_retrieve_diary_mode') as mock_diary:
                    with patch.object(self.retriever, '_retrieve_general_mode') as mock_general:
                        with patch.object(self.retriever, '_retrieve_auto_mode') as mock_auto:
                            mock_diary.return_value = []
                            mock_general.return_value = []
                            mock_auto.return_value = []
                            
                            self.retriever.retrieve(query, search_mode=search_mode)
                            
                            # Verify the correct mode was used
                            if search_mode == SearchMode.DIARY:
                                mock_diary.assert_called_once()
                            elif search_mode == SearchMode.GENERAL:
                                mock_general.assert_called_once()
                            elif search_mode == SearchMode.AUTO:
                                mock_auto.assert_called_once()
                                
            except Exception as e:
                pytest.fail(f"Example test failed for {description}: {e}")


if __name__ == '__main__':
    pytest.main([__file__])
