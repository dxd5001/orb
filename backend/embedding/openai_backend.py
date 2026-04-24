"""
OpenAI embedding backend implementation.

This module provides embedding generation using OpenAI's embedding API.
"""

import logging
from typing import List
import time

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None
    OpenAI = None

from .base import EmbeddingBackend

logger = logging.getLogger(__name__)


class OpenAIEmbeddingBackend(EmbeddingBackend):
    """
    OpenAI embedding backend using OpenAI's embedding API.
    
    This backend provides embedding generation using OpenAI's hosted models
    such as text-embedding-ada-002, text-embedding-3-small, etc.
    """
    
    # Known embedding models and their dimensions
    MODEL_DIMENSIONS = {
        'text-embedding-ada-002': 1536,
        'text-embedding-3-small': 1536,
        'text-embedding-3-large': 3072,
    }
    
    def __init__(self, api_key: str, model_name: str = 'text-embedding-3-small', base_url: str = None):
        """
        Initialize OpenAI embedding backend.
        
        Args:
            api_key: OpenAI API key
            model_name: Name of the OpenAI embedding model
            base_url: Custom base URL (for compatible APIs)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai library is not available. "
                "Install it with: pip install openai"
            )
        
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        
        # Initialize OpenAI client
        client_kwargs = {'api_key': api_key}
        if base_url:
            client_kwargs['base_url'] = base_url
        
        self.client = OpenAI(**client_kwargs)
        
        # Set dimension based on model
        self._dimension = self.MODEL_DIMENSIONS.get(model_name, 1536)  # Default to 1536
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using OpenAI API.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        self.validate_texts(texts)
        self.log_embedding_request(len(texts))
        
        try:
            # Truncate texts if they're too long (OpenAI has input limits)
            truncated_texts = self.truncate_texts(texts, max_length=8192)
            
            # Process in batches to avoid rate limits
            batch_size = 100  # OpenAI allows up to 2048 inputs per request
            all_embeddings = []
            
            for i in range(0, len(truncated_texts), batch_size):
                batch_texts = truncated_texts[i:i + batch_size]
                
                try:
                    response = self.client.embeddings.create(
                        model=self.model_name,
                        input=batch_texts
                    )
                    
                    batch_embeddings = [data.embedding for data in response.data]
                    all_embeddings.extend(batch_embeddings)
                    
                    # Add small delay to avoid rate limiting
                    if i + batch_size < len(truncated_texts):
                        time.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"Failed to process batch {i//batch_size}: {e}")
                    raise
            
            self.log_embedding_response(len(all_embeddings), self.get_embedding_dimension())
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings with OpenAI: {e}")
            raise RuntimeError(f"OpenAI embedding generation failed: {e}")
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Dimension of the embedding vectors
        """
        return self._dimension
    
    def get_model_name(self) -> str:
        """
        Get the name of the embedding model.
        
        Returns:
            Name of the embedding model
        """
        return self.model_name
    
    def get_supported_models(self) -> List[str]:
        """
        Get list of supported OpenAI embedding models.
        
        Returns:
            List of supported model names
        """
        return list(self.MODEL_DIMENSIONS.keys())
    
    def validate_api_key(self) -> bool:
        """
        Validate that the API key is working.
        
        Returns:
            True if API key is valid, False otherwise
        """
        try:
            # Try to generate an embedding for a simple test text
            test_embedding = self.embed(["test"])
            return len(test_embedding) == 1 and len(test_embedding[0]) > 0
        except Exception as e:
            logger.error(f"API key validation failed: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """
        Get information about the embedding model.
        
        Returns:
            Dictionary with model information
        """
        info = {
            'model_name': self.model_name,
            'provider': 'openai',
            'dimension': self.get_embedding_dimension(),
            'base_url': self.base_url or 'https://api.openai.com/v1'
        }
        
        return info
    
    def estimate_cost(self, num_texts: int, avg_text_length: int = 100) -> float:
        """
        Estimate cost for embedding the given texts.
        
        Args:
            num_texts: Number of texts to embed
            avg_text_length: Average length of texts in tokens
            
        Returns:
            Estimated cost in USD
        """
        # Pricing per 1K tokens (approximate, check OpenAI for current pricing)
        pricing_per_1k = {
            'text-embedding-ada-002': 0.0001,
            'text-embedding-3-small': 0.00002,
            'text-embedding-3-large': 0.00013,
        }
        
        price_per_1k = pricing_per_1k.get(self.model_name, 0.0001)
        total_tokens = num_texts * avg_text_length
        cost = (total_tokens / 1000) * price_per_1k
        
        return cost
