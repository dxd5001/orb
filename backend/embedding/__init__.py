"""
Embedding layer for Orb - RAG Chatbot for Obsidian Vaults.

This layer provides abstract interfaces and implementations for text embedding
generation using both local models and cloud APIs.
"""

from .base import EmbeddingBackend
from .local import LocalEmbeddingBackend
from .openai_backend import OpenAIEmbeddingBackend

__all__ = ['EmbeddingBackend', 'LocalEmbeddingBackend', 'OpenAIEmbeddingBackend']
