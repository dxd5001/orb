"""
Tests for embedding backends.

This module tests both local and cloud embedding implementations.
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.embedding.base import EmbeddingBackend, EmbeddingBackendFactory
from backend.embedding.local import LocalEmbeddingBackend, OllamaEmbeddingBackend
from backend.embedding.openai_backend import OpenAIEmbeddingBackend


class MockEmbeddingBackend(EmbeddingBackend):
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


class TestEmbeddingBackend:
    """Test cases for EmbeddingBackend abstract class."""
    
    def test_abstract_methods(self):
        """Test that EmbeddingBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            EmbeddingBackend()
    
    def test_concrete_implementation(self):
        """Test that concrete implementation works correctly."""
        backend = MockEmbeddingBackend()
        
        # Test basic methods
        assert backend.get_embedding_dimension() == 768
        assert backend.get_model_name() == "mock_model"
        
        # Test embedding
        embeddings = backend.embed(["test text"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768
    
    def test_validate_texts(self):
        """Test text validation."""
        backend = MockEmbeddingBackend()
        
        # Valid texts
        backend.validate_texts(["valid", "texts"])
        
        # Invalid cases
        with pytest.raises(ValueError, match="cannot be empty"):
            backend.validate_texts([])
        
        with pytest.raises(ValueError, match="must be provided as a list"):
            backend.validate_texts("not a list")
        
        with pytest.raises(ValueError, match="must be a string"):
            backend.validate_texts(["valid", 123])
        
        with pytest.raises(ValueError, match="cannot be empty"):
            backend.validate_texts(["valid", ""])
    
    def test_truncate_texts(self):
        """Test text truncation."""
        backend = MockEmbeddingBackend()
        
        # Texts under limit
        short_texts = ["short", "texts"]
        result = backend.truncate_texts(short_texts, max_length=10)
        assert result == short_texts
        
        # Texts over limit
        long_text = "a" * 100
        result = backend.truncate_texts([long_text], max_length=50)
        assert len(result[0]) == 50
        assert result[0] == "a" * 50
    
    @patch('backend.embedding.base.logger')
    def test_log_embedding_request(self, mock_logger):
        """Test embedding request logging."""
        backend = MockEmbeddingBackend()
        backend.log_embedding_request(5)
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Generating embeddings for 5 texts" in call_args
    
    @patch('backend.embedding.base.logger')
    def test_log_embedding_response(self, mock_logger):
        """Test embedding response logging."""
        backend = MockEmbeddingBackend()
        backend.log_embedding_response(5, 768)
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Generated 5 embeddings of dimension 768" in call_args


class TestEmbeddingBackendFactory:
    """Test cases for EmbeddingBackendFactory."""
    
    def test_create_local_backend(self):
        """Test creating local embedding backend."""
        with patch('backend.embedding.base.SENTENCE_TRANSFORMERS_AVAILABLE', True):
            backend = EmbeddingBackendFactory.create_backend('local', 'test-model')
            assert isinstance(backend, LocalEmbeddingBackend)
    
    def test_create_openai_backend(self):
        """Test creating OpenAI embedding backend."""
        backend = EmbeddingBackendFactory.create_backend(
            'openai', 
            'text-embedding-3-small',
            api_key='test-key'
        )
        assert isinstance(backend, OpenAIEmbeddingBackend)
    
    def test_create_openai_backend_no_api_key(self):
        """Test creating OpenAI backend without API key."""
        with pytest.raises(ValueError, match="API key is required"):
            EmbeddingBackendFactory.create_backend('openai', 'test-model')
    
    def test_create_unsupported_backend(self):
        """Test creating unsupported backend type."""
        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            EmbeddingBackendFactory.create_backend('unsupported', 'test-model')
    
    def test_get_supported_providers(self):
        """Test getting supported providers."""
        providers = EmbeddingBackendFactory.get_supported_providers()
        assert 'local' in providers
        assert 'openai' in providers


class TestLocalEmbeddingBackend:
    """Test cases for LocalEmbeddingBackend."""
    
    def test_init_without_sentence_transformers(self):
        """Test initialization without sentence-transformers."""
        with patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', False):
            with pytest.raises(ImportError, match="sentence-transformers library is not available"):
                LocalEmbeddingBackend()
    
    @patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', True)
    @patch('backend.embedding.local.SentenceTransformer')
    def test_init_with_sentence_transformers(self, mock_model_class):
        """Test initialization with sentence-transformers available."""
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model_class.return_value = mock_model
        
        backend = LocalEmbeddingBackend('test-model')
        assert backend.model_name == 'test-model'
        assert backend.device == 'cpu'
    
    @patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', True)
    @patch('backend.embedding.local.SentenceTransformer')
    def test_embed(self, mock_model_class):
        """Test embedding generation."""
        # Setup mock model
        mock_model = MagicMock()
        mock_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_model.encode.return_value = mock_embeddings
        mock_model.get_sentence_embedding_dimension.return_value = 3
        mock_model_class.return_value = mock_model
        
        backend = LocalEmbeddingBackend('test-model')
        result = backend.embed(["text1", "text2"])
        
        assert len(result) == 2
        assert result == mock_embeddings
        mock_model.encode.assert_called_once()
    
    @patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', True)
    @patch('backend.embedding.local.SentenceTransformer')
    def test_get_embedding_dimension(self, mock_model_class):
        """Test getting embedding dimension."""
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 512
        mock_model_class.return_value = mock_model
        
        backend = LocalEmbeddingBackend('test-model')
        dimension = backend.get_embedding_dimension()
        
        assert dimension == 512
    
    @patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', True)
    @patch('backend.embedding.local.SentenceTransformer')
    def test_get_supported_models(self, mock_model_class):
        """Test getting supported models."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        
        backend = LocalEmbeddingBackend()
        models = backend.get_supported_models()
        
        assert 'all-MiniLM-L6-v2' in models
        assert 'all-mpnet-base-v2' in models
        assert len(models) > 0
    
    @patch('backend.embedding.local.SENTENCE_TRANSFORMERS_AVAILABLE', True)
    @patch('backend.embedding.local.SentenceTransformer')
    def test_validate_model(self, mock_model_class):
        """Test model validation."""
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1, 0.2]]
        mock_model.get_sentence_embedding_dimension.return_value = 2
        mock_model_class.return_value = mock_model
        
        backend = LocalEmbeddingBackend('test-model')
        result = backend.validate_model()
        
        assert result is True
        mock_model.encode.assert_called_with(["test"], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)


class TestOllamaEmbeddingBackend:
    """Test cases for OllamaEmbeddingBackend."""
    
    def test_init_without_requests(self):
        """Test initialization without requests library."""
        with patch('backend.embedding.local.OPENAI_AVAILABLE', True):
            with patch.dict('sys.modules', {'requests': None}):
                with pytest.raises(ImportError, match="requests library is not available"):
                    OllamaEmbeddingBackend()
    
    @patch('backend.embedding.local.requests')
    def test_embed(self, mock_requests):
        """Test embedding generation with Ollama."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'embedding': [0.1, 0.2, 0.3]
        }
        mock_requests.post.return_value = mock_response
        
        backend = OllamaEmbeddingBackend('llama2', 'http://localhost:11434')
        result = backend.embed(["test text"])
        
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
        mock_requests.post.assert_called_once()
    
    @patch('backend.embedding.local.requests')
    def test_embed_api_error(self, mock_requests):
        """Test handling API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests.post.return_value = mock_response
        
        backend = OllamaEmbeddingBackend('llama2', 'http://localhost:11434')
        
        with pytest.raises(RuntimeError, match="Ollama API error"):
            backend.embed(["test text"])
    
    @patch('backend.embedding.local.requests')
    def test_validate_ollama_connection(self, mock_requests):
        """Test Ollama connection validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        
        backend = OllamaEmbeddingBackend('llama2', 'http://localhost:11434')
        result = backend.validate_ollama_connection()
        
        assert result is True
        mock_requests.get.assert_called_with('http://localhost:11434/api/tags', timeout=5)


class TestOpenAIEmbeddingBackend:
    """Test cases for OpenAIEmbeddingBackend."""
    
    def test_init_without_openai(self):
        """Test initialization without openai library."""
        with patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', False):
            with pytest.raises(ImportError, match="openai library is not available"):
                OpenAIEmbeddingBackend('test-key')
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_init_with_openai(self, mock_openai_class):
        """Test initialization with openai library available."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key', 'text-embedding-3-small')
        
        assert backend.api_key == 'test-key'
        assert backend.model_name == 'text-embedding-3-small'
        mock_openai_class.assert_called_once_with(api_key='test-key')
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_embed(self, mock_openai_class):
        """Test embedding generation with OpenAI."""
        # Setup mock client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.1, 0.2, 0.3]
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key', 'text-embedding-3-small')
        result = backend.embed(["test text"])
        
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once()
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_get_embedding_dimension(self, mock_openai_class):
        """Test getting embedding dimension."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key', 'text-embedding-3-large')
        dimension = backend.get_embedding_dimension()
        
        assert dimension == 3072
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_get_supported_models(self, mock_openai_class):
        """Test getting supported models."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key')
        models = backend.get_supported_models()
        
        assert 'text-embedding-ada-002' in models
        assert 'text-embedding-3-small' in models
        assert 'text-embedding-3-large' in models
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_validate_api_key(self, mock_openai_class):
        """Test API key validation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.1, 0.2]
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key')
        result = backend.validate_api_key()
        
        assert result is True
    
    @patch('backend.embedding.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.embedding.openai_backend.OpenAI')
    def test_estimate_cost(self, mock_openai_class):
        """Test cost estimation."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAIEmbeddingBackend('test-key', 'text-embedding-3-small')
        cost = backend.estimate_cost(100, 50)  # 100 texts, 50 tokens each
        
        # Expected: (100 * 50) / 1000 * 0.00002 = 0.0001
        assert cost == 0.0001


if __name__ == '__main__':
    pytest.main([__file__])
