"""
Abstract base class for LLM backends.

This module defines the interface that all LLM implementations must follow.
The design allows for both local models (Ollama, LM Studio) and cloud APIs
(OpenAI, etc.) to be used interchangeably.
"""

from abc import ABC, abstractmethod
from typing import List
import logging

logger = logging.getLogger(__name__)


class LLMBackend(ABC):
    """
    Abstract base class for large language model backends.
    
    This class defines the interface that all LLM backends must implement.
    It provides a common contract for text generation using various LLM
    providers and models.
    
    Design Principles:
    - Backend Agnostic: Can work with any LLM provider/model
    - Prompt Engineering: Supports structured prompting
    - Error Resilient: Graceful handling of API failures
    - Extensible: Easy to add new LLM providers
    """
    
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Generate text response from the given prompt.
        
        Args:
            prompt: Input prompt for the LLM
            
        Returns:
            Generated text response
            
        Raises:
            ValueError: If prompt is empty or invalid
            ConnectionError: If unable to connect to the LLM service
            RuntimeError: If text generation fails
        """
        pass
    
    def get_model_name(self) -> str:
        """
        Get the name of the LLM model.
        
        Returns:
            Name of the LLM model
        """
        # Default implementation - subclasses should override
        return self.__class__.__name__
    
    def get_provider_name(self) -> str:
        """
        Get the name of the LLM provider.
        
        Returns:
            Name of the LLM provider
        """
        # Default implementation - subclasses should override
        return "unknown"
    
    def validate_prompt(self, prompt: str) -> None:
        """
        Validate input prompt before generation.
        
        Args:
            prompt: Prompt to validate
            
        Raises:
            ValueError: If prompt is invalid
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        if len(prompt) > 100000:  # Reasonable limit
            raise ValueError("Prompt is too long (max 100,000 characters)")
    
    def truncate_prompt(self, prompt: str, max_length: int = 95000) -> str:
        """
        Truncate prompt if it exceeds maximum length.
        
        Args:
            prompt: Prompt to truncate
            max_length: Maximum character length
            
        Returns:
            Truncated prompt
        """
        if len(prompt) <= max_length:
            return prompt
        
        # Try to truncate at a reasonable boundary
        truncated = prompt[:max_length]
        
        # Find the last sentence boundary
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclamation = truncated.rfind('!')
        
        last_boundary = max(last_period, last_question, last_exclamation)
        
        if last_boundary > max_length * 0.8:  # Only use boundary if it's not too far back
            return truncated[:last_boundary + 1]
        
        return truncated
    
    def log_generation_request(self, prompt_length: int) -> None:
        """
        Log generation request information.
        
        Args:
            prompt_length: Length of the prompt
        """
        logger.info(f"Generating text with {self.get_model_name()} (prompt length: {prompt_length})")
    
    def log_generation_response(self, response_length: int) -> None:
        """
        Log generation response information.
        
        Args:
            response_length: Length of the generated response
        """
        logger.info(f"Generated response (length: {response_length})")
    
    def test_connection(self) -> bool:
        """
        Test connection to the LLM service.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Use validate_connection instead of generating text
            if hasattr(self, 'validate_connection'):
                return self.validate_connection()
            else:
                # Fallback to simple API endpoint check
                return self._validate_api_connection()
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def _validate_api_connection(self) -> bool:
        """
        Default API connection validation.
        
        Returns:
            True if API is accessible, False otherwise
        """
        # Default implementation - subclasses should override
        return True


class LLMBackendFactory:
    """
    Factory class for creating appropriate LLM backend instances.
    
    This class provides a centralized way to create LLM backends
    based on configuration and provider type.
    """
    
    @staticmethod
    def create_backend(provider: str, model_name: str, **kwargs) -> LLMBackend:
        """
        Create an LLM backend instance.
        
        Args:
            provider: Provider type ('local' or 'openai')
            model_name: Name of the LLM model
            **kwargs: Additional arguments for the backend
            
        Returns:
            Instance of the appropriate LLM backend
            
        Raises:
            ValueError: If provider is not supported
        """
        provider = provider.lower()
        
        if provider == 'local':
            from .local import LocalLLMBackend
            base_url = kwargs.get('base_url')
            if not base_url:
                raise ValueError("base_url is required for local LLM backend")
            # Set explicit timeout for local LLM
            timeout = kwargs.get('timeout', 1800)  # Default to 30 minutes
            # Remove base_url from kwargs to avoid duplicate argument
            kwargs_without_base_url = {k: v for k, v in kwargs.items() if k != 'base_url'}
            return LocalLLMBackend(base_url, model_name, timeout=timeout, **kwargs_without_base_url)
        elif provider == 'openai':
            from .openai_backend import OpenAILLMBackend
            api_key = kwargs.get('api_key')
            if not api_key:
                raise ValueError("API key is required for OpenAI LLM backend")
            # Remove api_key from kwargs to avoid duplicate argument
            kwargs_without_api_key = {k: v for k, v in kwargs.items() if k != 'api_key'}
            return OpenAILLMBackend(api_key, model_name, **kwargs_without_api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    @staticmethod
    def get_supported_providers() -> List[str]:
        """
        Get list of supported LLM providers.
        
        Returns:
            List of supported provider names
        """
        return ['local', 'openai']
