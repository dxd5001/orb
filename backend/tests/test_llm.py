"""
Tests for LLM backends.

This module tests both local and cloud LLM implementations.
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.llm.base import LLMBackend, LLMBackendFactory
from backend.llm.local import LocalLLMBackend, OllamaLLMBackend
from backend.llm.openai_backend import OpenAILLMBackend


class MockLLMBackend(LLMBackend):
    """Mock LLM backend for testing."""
    
    def __init__(self, model_name="mock_model", provider="mock"):
        self.model_name = model_name
        self.provider_name = provider
    
    def generate(self, prompt):
        return f"Mock response to: {prompt[:20]}..."
    
    def get_model_name(self):
        return self.model_name
    
    def get_provider_name(self):
        return self.provider_name


class TestLLMBackend:
    """Test cases for LLMBackend abstract class."""
    
    def test_abstract_methods(self):
        """Test that LLMBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMBackend()
    
    def test_concrete_implementation(self):
        """Test that concrete implementation works correctly."""
        backend = MockLLMBackend()
        
        # Test basic methods
        assert backend.get_model_name() == "mock_model"
        assert backend.get_provider_name() == "mock"
        
        # Test generation
        response = backend.generate("test prompt")
        assert "Mock response" in response
    
    def test_validate_prompt(self):
        """Test prompt validation."""
        backend = MockLLMBackend()
        
        # Valid prompts
        backend.validate_prompt("valid prompt")
        backend.validate_prompt("  valid prompt with spaces  ")
        
        # Invalid prompts
        with pytest.raises(ValueError, match="cannot be empty"):
            backend.validate_prompt("")
        
        with pytest.raises(ValueError, match="cannot be empty"):
            backend.validate_prompt("   ")
        
        with pytest.raises(ValueError, match="too long"):
            backend.validate_prompt("a" * 100001)
    
    def test_truncate_prompt(self):
        """Test prompt truncation."""
        backend = MockLLMBackend()
        
        # Short prompt - no truncation
        short = "short prompt"
        result = backend.truncate_prompt(short, max_length=100)
        assert result == short
        
        # Long prompt - truncation
        long = "a" * 100
        result = backend.truncate_prompt(long, max_length=50)
        assert len(result) <= 50
        
        # Long prompt with sentence boundary
        long_with_sentences = "This is sentence one. This is sentence two. This is sentence three."
        result = backend.truncate_prompt(long_with_sentences, max_length=40)
        assert result.endswith(".")
    
    @patch('backend.llm.base.logger')
    def test_log_generation_request(self, mock_logger):
        """Test generation request logging."""
        backend = MockLLMBackend()
        backend.log_generation_request(100)
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Generating text" in call_args
        assert "prompt length: 100" in call_args
    
    @patch('backend.llm.base.logger')
    def test_log_generation_response(self, mock_logger):
        """Test generation response logging."""
        backend = MockLLMBackend()
        backend.log_generation_response(50)
        
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Generated response" in call_args
        assert "length: 50" in call_args
    
    def test_test_connection(self):
        """Test connection testing."""
        backend = MockLLMBackend()
        result = backend.test_connection()
        assert result is True


class TestLLMBackendFactory:
    """Test cases for LLMBackendFactory."""
    
    def test_create_local_backend(self):
        """Test creating local LLM backend."""
        backend = LLMBackendFactory.create_backend(
            'local',
            'test-model',
            base_url='http://localhost:11434'
        )
        assert isinstance(backend, LocalLLMBackend)
    
    def test_create_openai_backend(self):
        """Test creating OpenAI LLM backend."""
        backend = LLMBackendFactory.create_backend(
            'openai',
            'gpt-4o-mini',
            api_key='test-key'
        )
        assert isinstance(backend, OpenAILLMBackend)
    
    def test_create_local_backend_no_base_url(self):
        """Test creating local backend without base URL."""
        with pytest.raises(ValueError, match="base_url is required"):
            LLMBackendFactory.create_backend('local', 'test-model')
    
    def test_create_openai_backend_no_api_key(self):
        """Test creating OpenAI backend without API key."""
        with pytest.raises(ValueError, match="API key is required"):
            LLMBackendFactory.create_backend('openai', 'test-model')
    
    def test_create_unsupported_backend(self):
        """Test creating unsupported backend type."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMBackendFactory.create_backend('unsupported', 'test-model')
    
    def test_get_supported_providers(self):
        """Test getting supported providers."""
        providers = LLMBackendFactory.get_supported_providers()
        assert 'local' in providers
        assert 'openai' in providers


class TestLocalLLMBackend:
    """Test cases for LocalLLMBackend."""
    
    def test_init_without_requests(self):
        """Test initialization without requests library."""
        with patch('backend.llm.local.REQUESTS_AVAILABLE', False):
            with pytest.raises(ImportError, match="requests library is not available"):
                LocalLLMBackend('http://localhost:11434', 'test-model')
    
    def test_init_invalid_base_url(self):
        """Test initialization with invalid base URL."""
        with pytest.raises(ValueError, match="must start with http:// or https://"):
            LocalLLMBackend('invalid-url', 'test-model')
    
    @patch('backend.llm.local.requests')
    def test_generate_success(self, mock_requests):
        """Test successful text generation."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'Generated response'
                }
            }]
        }
        mock_requests.post.return_value = mock_response
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        result = backend.generate('Test prompt')
        
        assert result == 'Generated response'
        mock_requests.post.assert_called_once()
    
    @patch('backend.llm.local.requests')
    def test_generate_api_error(self, mock_requests):
        """Test handling API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {'error': {'message': 'Internal error'}}
        mock_requests.post.return_value = mock_response
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        
        with pytest.raises(RuntimeError, match="Local LLM API error: 500 - Internal error"):
            backend.generate('Test prompt')
    
    @patch('backend.llm.local.requests')
    def test_generate_timeout(self, mock_requests):
        """Test handling timeout errors."""
        mock_requests.post.side_effect = mock_requests.exceptions.Timeout()
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        
        with pytest.raises(RuntimeError, match="request timed out"):
            backend.generate('Test prompt')
    
    @patch('backend.llm.local.requests')
    def test_generate_connection_error(self, mock_requests):
        """Test handling connection errors."""
        mock_requests.post.side_effect = mock_requests.exceptions.ConnectionError()
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        
        with pytest.raises(RuntimeError, match="Failed to connect"):
            backend.generate('Test prompt')
    
    @patch('backend.llm.local.requests')
    def test_get_available_models(self, mock_requests):
        """Test getting available models."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'id': 'model1'},
                {'id': 'model2'}
            ]
        }
        mock_requests.get.return_value = mock_response
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        models = backend.get_available_models()
        
        assert models == ['model1', 'model2']
        mock_requests.get.assert_called_with('http://localhost:11434/v1/models', timeout=10)
    
    @patch('backend.llm.local.requests')
    def test_validate_connection(self, mock_requests):
        """Test connection validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        result = backend.validate_connection()
        
        assert result is True
        mock_requests.get.assert_called_with('http://localhost:11434/v1/models', timeout=5)
    
    def test_get_model_info(self):
        """Test getting model information."""
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        info = backend.get_model_info()
        
        assert info['model_name'] == 'test-model'
        assert info['provider'] == 'local'
        assert info['base_url'] == 'http://localhost:11434'
        assert info['api_format'] == 'openai-compatible'
    
    def test_estimate_tokens(self):
        """Test token estimation."""
        backend = LocalLLMBackend('http://localhost:11434', 'test-model')
        tokens = backend.estimate_tokens('This is a test text.')
        
        # Rough approximation: ~4 characters per token
        expected = len('This is a test text.') // 4
        assert tokens == expected
    
    def test_get_context_length(self):
        """Test getting context length."""
        backend = LocalLLMBackend('http://localhost:11434', 'llama2')
        context = backend.get_context_length()
        
        assert context == 4096  # Default for llama2


class TestOllamaLLMBackend:
    """Test cases for OllamaLLMBackend."""
    
    def test_init_default_port(self):
        """Test initialization with default port."""
        backend = OllamaLLMBackend('http://localhost', 'llama2')
        assert backend.base_url == 'http://localhost:11434'
    
    @patch('backend.llm.local.requests')
    def test_generate_ollama_api(self, mock_requests):
        """Test generation using Ollama API format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'response': 'Ollama response'
        }
        mock_requests.post.return_value = mock_response
        
        backend = OllamaLLMBackend('http://localhost:11434', 'llama2')
        result = backend.generate('Test prompt')
        
        assert result == 'Ollama response'
        mock_requests.post.assert_called_with(
            'http://localhost:11434/api/generate',
            json=pytest.approx({
                'model': 'llama2',
                'prompt': 'Test prompt',
                'stream': False,
                'options': {'temperature': 0.7, 'num_predict': 2000}
            }, allow_extra_keys=True),
            timeout=60
        )
    
    @patch('backend.llm.local.requests')
    def test_get_available_models_ollama(self, mock_requests):
        """Test getting Ollama models."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [
                {'name': 'llama2'},
                {'name': 'mistral'}
            ]
        }
        mock_requests.get.return_value = mock_response
        
        backend = OllamaLLMBackend('http://localhost:11434', 'llama2')
        models = backend.get_available_models()
        
        assert models == ['llama2', 'mistral']
        mock_requests.get.assert_called_with('http://localhost:11434/api/tags', timeout=10)
    
    @patch('backend.llm.local.requests')
    def test_pull_model(self, mock_requests):
        """Test pulling a model."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response
        
        backend = OllamaLLMBackend('http://localhost:11434', 'llama2')
        result = backend.pull_model('mistral')
        
        assert result is True
        mock_requests.post.assert_called_with(
            'http://localhost:11434/api/pull',
            json={'name': 'mistral'},
            timeout=300
        )


class TestOpenAILLMBackend:
    """Test cases for OpenAILLMBackend."""
    
    def test_init_without_openai(self):
        """Test initialization without openai library."""
        with patch('backend.llm.openai_backend.OPENAI_AVAILABLE', False):
            with pytest.raises(ImportError, match="openai library is not available"):
                OpenAILLMBackend('test-key')
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_init_with_openai(self, mock_openai_class):
        """Test initialization with openai library available."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key', 'gpt-4o-mini')
        
        assert backend.api_key == 'test-key'
        assert backend.model_name == 'gpt-4o-mini'
        mock_openai_class.assert_called_once_with(api_key='test-key', timeout=60)
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_generate_success(self, mock_openai_class):
        """Test successful text generation."""
        # Setup mock client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = 'OpenAI response'
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key', 'gpt-4o-mini')
        result = backend.generate('Test prompt')
        
        assert result == 'OpenAI response'
        mock_client.chat.completions.create.assert_called_once()
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_generate_rate_limit_error(self, mock_openai_class):
        """Test handling rate limit errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.RateLimitError("Rate limit exceeded")
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key', 'gpt-4o-mini')
        
        with pytest.raises(RuntimeError, match="OpenAI API rate limit exceeded"):
            backend.generate('Test prompt')
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_get_supported_models(self, mock_openai_class):
        """Test getting supported models."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key')
        models = backend.get_supported_models()
        
        assert 'gpt-4o-mini' in models
        assert 'gpt-4' in models
        assert 'gpt-4o' in models
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_validate_api_key(self, mock_openai_class):
        """Test API key validation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key')
        result = backend.validate_api_key()
        
        assert result is True
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_estimate_tokens_with_tiktoken(self, mock_openai_class):
        """Test token estimation with tiktoken."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock tiktoken
        with patch('backend.llm.openai_backend.tiktoken') as mock_tiktoken:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
            mock_tiktoken.encoding_for_model.return_value = mock_encoding
            
            backend = OpenAILLMBackend('test-key', 'gpt-4o-mini')
            tokens = backend.estimate_tokens('Test text')
            
            assert tokens == 5
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_get_context_length(self, mock_openai_class):
        """Test getting context length."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key', 'gpt-4')
        context = backend.get_context_length()
        
        assert context == 8192
    
    @patch('backend.llm.openai_backend.OPENAI_AVAILABLE', True)
    @patch('backend.llm.openai_backend.OpenAI')
    def test_estimate_cost(self, mock_openai_class):
        """Test cost estimation."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        backend = OpenAILLMBackend('test-key', 'gpt-4o-mini')
        cost = backend.estimate_cost(100, 50)  # 100 prompt tokens, 50 completion tokens
        
        # Expected: (100/1000) * 0.00015 + (50/1000) * 0.0006 = 0.000015 + 0.00003 = 0.000045
        assert cost == 0.000045


if __name__ == '__main__':
    pytest.main([__file__])
