"""
Local LLM backend implementation.

This module provides LLM generation using local models such as
Ollama, LM Studio, or other OpenAI-compatible local API servers.
"""

import logging
from typing import List
import time

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

from .base import LLMBackend

logger = logging.getLogger(__name__)


class LocalLLMBackend(LLMBackend):
    """
    Local LLM backend using OpenAI-compatible API servers.
    
    This backend provides text generation using local models running on
    services like Ollama, LM Studio, or other OpenAI-compatible servers.
    """
    
    def __init__(self, base_url: str, model_name: str, timeout: int = 1800, **kwargs):
        """
        Initialize local LLM backend.
        
        Args:
            base_url: Base URL for the local LLM API
            model_name: Name of the model to use
            timeout: Request timeout in seconds (default: 30 minutes)
            **kwargs: Additional parameters
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError(
                "requests library is not available. "
                "Install it with: pip install requests"
            )
        
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = timeout
        
        # Validate base URL format
        if not self.base_url.startswith(('http://', 'https://')):
            raise ValueError("base_url must start with http:// or https://")
    
    def generate(self, prompt: str) -> str:
        """
        Generate text response using local LLM API.
        
        Args:
            prompt: Input prompt for the LLM
            
        Returns:
            Generated text response
        """
        self.validate_prompt(prompt)
        self.log_generation_request(len(prompt))
        
        try:
            # Truncate prompt if needed
            truncated_prompt = self.truncate_prompt(prompt)
            
            # Prepare request payload
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": truncated_prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": False
            }
            
            # Make API request
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Local LLM API error: {response.status_code}"
                try:
                    error_detail = response.json().get('error', {}).get('message', '')
                    if error_detail:
                        error_msg += f" - {error_detail}"
                except:
                    pass
                raise RuntimeError(error_msg)
            
            # Parse response
            data = response.json()
            
            if 'choices' not in data or not data['choices']:
                raise RuntimeError("Invalid response from local LLM API")
            
            choice = data['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                raise RuntimeError("Invalid response format from local LLM API")
            
            generated_text = choice['message']['content']
            
            self.log_generation_response(len(generated_text))
            
            return generated_text
            
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Local LLM API request timed out after {self.timeout} seconds")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Failed to connect to local LLM API at {self.base_url}")
        except Exception as e:
            logger.error(f"Failed to generate text with local LLM: {e}")
            raise RuntimeError(f"Local LLM generation failed: {e}")
    
    def get_model_name(self) -> str:
        """
        Get the name of the LLM model.
        
        Returns:
            Name of the LLM model
        """
        return self.model_name
    
    def get_provider_name(self) -> str:
        """
        Get the name of the LLM provider.
        
        Returns:
            Name of the LLM provider
        """
        return "local"
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available models from the local API server.
        
        Returns:
            List of available model names
        """
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model['id'] for model in data.get('data', [])]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
        
        return []
    
    def validate_connection(self) -> bool:
        """
        Validate connection to the local LLM API server.
        
        Returns:
            True if connection is valid, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to validate local LLM connection: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """
        Get information about the current model configuration.
        
        Returns:
            Dictionary with model information
        """
        info = {
            'model_name': self.model_name,
            'provider': 'local',
            'base_url': self.base_url,
            'timeout': self.timeout,
            'api_format': 'openai-compatible'
        }
        
        return info
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation).
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
    
    def get_context_length(self) -> int:
        """
        Get estimated context length for the model.
        
        Returns:
            Estimated context window size
        """
        # Common context lengths for popular models
        model_contexts = {
            'llama2': 4096,
            'llama3': 8192,
            'mistral': 8192,
            'mixtral': 32768,
            'qwen': 8192,
        }
        
        model_lower = self.model_name.lower()
        for model_name, context in model_contexts.items():
            if model_name in model_lower:
                return context
        
        # Default fallback
        return 4096


class OllamaLLMBackend(LocalLLMBackend):
    """
    Specialized backend for Ollama API.
    
    This backend uses Ollama's native API format instead of the OpenAI-compatible
    endpoint for better integration with Ollama-specific features.
    """
    
    def __init__(self, base_url: str = 'http://localhost:11434', model_name: str = 'llama2', timeout: int = 60):
        """
        Initialize Ollama LLM backend.
        
        Args:
            base_url: Base URL of the Ollama server
            model_name: Name of the Ollama model
            timeout: Request timeout in seconds
        """
        # Use Ollama's default port if not specified
        if not base_url.endswith(':11434'):
            base_url = base_url.rstrip('/') + ':11434'
        
        super().__init__(base_url, model_name, timeout)
    
    def generate(self, prompt: str) -> str:
        """
        Generate text using Ollama's native API.
        
        Args:
            prompt: Input prompt for the LLM
            
        Returns:
            Generated text response
        """
        self.validate_prompt(prompt)
        self.log_generation_request(len(prompt))
        
        try:
            # Truncate prompt if needed
            truncated_prompt = self.truncate_prompt(prompt)
            
            # Prepare Ollama-specific request
            payload = {
                "model": self.model_name,
                "prompt": truncated_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 2000
                }
            }
            
            # Make API request to Ollama
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Ollama API error: {response.status_code}"
                try:
                    error_detail = response.json().get('error', '')
                    if error_detail:
                        error_msg += f" - {error_detail}"
                except:
                    pass
                raise RuntimeError(error_msg)
            
            # Parse Ollama response
            data = response.json()
            
            if 'response' not in data:
                raise RuntimeError("Invalid response from Ollama API")
            
            generated_text = data['response']
            
            self.log_generation_response(len(generated_text))
            
            return generated_text
            
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Ollama API request timed out after {self.timeout} seconds")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Failed to connect to Ollama at {self.base_url}")
        except Exception as e:
            logger.error(f"Failed to generate text with Ollama: {e}")
            raise RuntimeError(f"Ollama generation failed: {e}")
    
    def get_provider_name(self) -> str:
        """
        Get the name of the LLM provider.
        
        Returns:
            Name of the LLM provider
        """
        return "ollama"
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available Ollama models.
        
        Returns:
            List of available model names
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            logger.error(f"Failed to get Ollama models: {e}")
        
        return []
    
    def validate_connection(self) -> bool:
        """
        Validate connection to Ollama server.
        
        Returns:
            True if connection is valid, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to validate Ollama connection: {e}")
            return False
    
    def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama registry.
        
        Args:
            model_name: Name of the model to pull
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                timeout=300  # 5 minutes for model pull
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull Ollama model {model_name}: {e}")
            return False
