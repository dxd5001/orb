"""
Local embedding backend implementation.

This module provides embedding generation using local models such as
sentence-transformers or Ollama embeddings.
"""

import logging
from typing import List
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

from .base import EmbeddingBackend

logger = logging.getLogger(__name__)


class LocalEmbeddingBackend(EmbeddingBackend):
    """
    Local embedding backend using sentence-transformers.
    
    This backend provides embedding generation using models running locally
    on the machine. It supports sentence-transformers models and provides
    fast, private embedding generation without external API calls.
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', device: str = 'cpu'):
        """
        Initialize local embedding backend.
        
        Args:
            model_name: Name of the sentence-transformers model
            device: Device to run inference on ('cpu' or 'cuda')
        """
        self.model_name = model_name
        self.device = device
        self._model = None
        self._dimension = None
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers library is not available. "
                "Install it with: pip install sentence-transformers"
            )
    
    @property
    def model(self) -> SentenceTransformer:
        """
        Lazy loading of the sentence-transformers model.
        
        Returns:
            Loaded sentence-transformers model
        """
        if self._model is None:
            logger.info(f"Loading sentence-transformers model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dimension = self._model.get_sentence_embedding_dimension()
            logger.info(f"Model loaded successfully. Embedding dimension: {self._dimension}")
        
        return self._model
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        self.validate_texts(texts)
        self.log_embedding_request(len(texts))
        
        try:
            # Truncate texts if they're too long for the model
            truncated_texts = self.truncate_texts(texts)
            
            # Generate embeddings
            embeddings = self.model.encode(
                truncated_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            
            # Convert to list of lists
            embedding_list = embeddings.tolist()
            
            self.log_embedding_response(len(embedding_list), self.get_embedding_dimension())
            
            return embedding_list
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Dimension of the embedding vectors
        """
        if self._dimension is None:
            # Load model to get dimension
            _ = self.model
        
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
        Get list of supported sentence-transformers models.
        
        Returns:
            List of supported model names
        """
        # Common models that work well for general purposes
        return [
            'all-MiniLM-L6-v2',      # Fast, good quality (384 dim)
            'all-mpnet-base-v2',      # Higher quality (768 dim)
            'multi-qa-mpnet-base-dot-v1',  # Good for QA (768 dim)
            'paraphrase-multilingual-MiniLM-L12-v2',  # Multilingual (384 dim)
        ]
    
    def validate_model(self) -> bool:
        """
        Validate that the model can be loaded and used.
        
        Returns:
            True if model is valid and working, False otherwise
        """
        try:
            # Try to load the model
            _ = self.model
            
            # Try to embed a test text
            test_embedding = self.embed(["test"])
            
            # Check that we got a valid embedding
            return (len(test_embedding) == 1 and 
                   len(test_embedding[0]) == self.get_embedding_dimension())
        except Exception as e:
            logger.error(f"Model validation failed: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """
        Get information about the loaded model.
        
        Returns:
            Dictionary with model information
        """
        info = {
            'model_name': self.model_name,
            'device': self.device,
            'provider': 'local',
            'dimension': self.get_embedding_dimension(),
            'library': 'sentence-transformers'
        }
        
        return info


class OllamaEmbeddingBackend(EmbeddingBackend):
    """
    Local embedding backend using Ollama API.
    
    This backend provides embedding generation using Ollama running locally.
    It communicates with Ollama via its HTTP API.
    """
    
    def __init__(self, model_name: str = 'llama2', base_url: str = 'http://localhost:11434'):
        """
        Initialize Ollama embedding backend.
        
        Args:
            model_name: Name of the Ollama model
            base_url: Base URL of the Ollama API
        """
        self.model_name = model_name
        self.base_url = base_url.rstrip('/')
        self._dimension = None  # Will be determined from first response
        
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError(
                "requests library is not available. "
                "Install it with: pip install requests"
            )
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using Ollama.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        self.validate_texts(texts)
        self.log_embedding_request(len(texts))
        
        embeddings = []
        
        for text in texts:
            try:
                response = self.requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model_name,
                        "prompt": text
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama API error: {response.status_code} - {response.text}")
                
                data = response.json()
                
                if 'embedding' not in data:
                    raise RuntimeError("No embedding in Ollama response")
                
                embedding = data['embedding']
                embeddings.append(embedding)
                
                # Set dimension from first response
                if self._dimension is None:
                    self._dimension = len(embedding)
                
            except Exception as e:
                logger.error(f"Failed to generate embedding with Ollama: {e}")
                raise
        
        self.log_embedding_response(len(embeddings), self.get_embedding_dimension())
        
        return embeddings
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Dimension of the embedding vectors
        """
        if self._dimension is None:
            # Default dimension for common models
            return 4096  # Common for many Llama models
        return self._dimension
    
    def get_model_name(self) -> str:
        """
        Get the name of the embedding model.
        
        Returns:
            Name of the embedding model
        """
        return self.model_name
    
    def validate_ollama_connection(self) -> bool:
        """
        Validate that Ollama is running and accessible.
        
        Returns:
            True if Ollama is accessible, False otherwise
        """
        try:
            response = self.requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available models from Ollama.
        
        Returns:
            List of available model names
        """
        try:
            response = self.requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            logger.error(f"Failed to get Ollama models: {e}")
        
        return []
