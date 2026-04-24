"""
Abstract base class for embedding backends.

This module defines the interface that all embedding implementations must follow.
The design allows for both local models (sentence-transformers, Ollama) and
cloud APIs (OpenAI, etc.) to be used interchangeably.
"""

from abc import ABC, abstractmethod
from typing import List
import logging

logger = logging.getLogger(__name__)


class EmbeddingBackend(ABC):
    """
    Abstract base class for text embedding generation.
    
    This class defines the interface that all embedding backends must implement.
    It provides a common contract for converting text into vector embeddings
    for similarity search and retrieval.
    
    Design Principles:
    - Backend Agnostic: Can work with any embedding model/API
    - Batch Processing: Efficient handling of multiple texts
    - Error Resilient: Graceful handling of API failures
    - Extensible: Easy to add new embedding providers
    """
    
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (each vector is a list of floats)
            
        Raises:
            ValueError: If texts list is empty or contains invalid input
            ConnectionError: If unable to connect to the embedding service
            RuntimeError: If embedding generation fails
        """
        pass
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Dimension of the embedding vectors
        """
        # Default implementation - subclasses should override
        return 768  # Common dimension for many models
    
    def get_model_name(self) -> str:
        """
        Get the name of the embedding model.
        
        Returns:
            Name of the embedding model
        """
        # Default implementation - subclasses should override
        return self.__class__.__name__
    
    def validate_texts(self, texts: List[str]) -> None:
        """
        Validate input texts before embedding.
        
        Args:
            texts: List of texts to validate
            
        Raises:
            ValueError: If texts are invalid
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")
        
        if not isinstance(texts, list):
            raise ValueError("Texts must be provided as a list")
        
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise ValueError(f"Text at index {i} must be a string")
            
            if len(text.strip()) == 0:
                raise ValueError(f"Text at index {i} cannot be empty")
    
    def truncate_texts(self, texts: List[str], max_length: int = 8192) -> List[str]:
        """
        Truncate texts to maximum length if needed.
        
        Args:
            texts: List of texts to truncate
            max_length: Maximum character length per text
            
        Returns:
            List of truncated texts
        """
        truncated = []
        for text in texts:
            if len(text) > max_length:
                truncated_text = text[:max_length]
                logger.warning(f"Text truncated from {len(text)} to {max_length} characters")
                truncated.append(truncated_text)
            else:
                truncated.append(text)
        
        return truncated
    
    def log_embedding_request(self, num_texts: int) -> None:
        """
        Log embedding request information.
        
        Args:
            num_texts: Number of texts being embedded
        """
        logger.info(f"Generating embeddings for {num_texts} texts using {self.get_model_name()}")
    
    def log_embedding_response(self, num_embeddings: int, dimension: int) -> None:
        """
        Log embedding response information.
        
        Args:
            num_embeddings: Number of embeddings generated
            dimension: Dimension of each embedding
        """
        logger.info(f"Generated {num_embeddings} embeddings of dimension {dimension}")


class EmbeddingBackendFactory:
    """
    Factory class for creating appropriate embedding backend instances.
    
    This class provides a centralized way to create embedding backends
    based on configuration and provider type.
    """
    
    @staticmethod
    def create_backend(provider: str, model_name: str, **kwargs) -> EmbeddingBackend:
        """
        Create an embedding backend instance.
        
        Args:
            provider: Provider type ('local' or 'openai')
            model_name: Name of the embedding model
            **kwargs: Additional arguments for the backend
            
        Returns:
            Instance of the appropriate embedding backend
            
        Raises:
            ValueError: If provider is not supported
        """
        provider = provider.lower()
        
        if provider == 'local':
            from .local import LocalEmbeddingBackend
            return LocalEmbeddingBackend(model_name, **kwargs)
        elif provider == 'openai':
            from .openai_backend import OpenAIEmbeddingBackend
            api_key = kwargs.get('api_key')
            if not api_key:
                raise ValueError("API key is required for OpenAI embedding backend")
            return OpenAIEmbeddingBackend(api_key, model_name, **kwargs)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")
    
    @staticmethod
    def get_supported_providers() -> List[str]:
        """
        Get list of supported embedding providers.
        
        Returns:
            List of supported provider names
        """
        return ['local', 'openai']
