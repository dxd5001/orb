"""
Indexing layer for Orb - RAG Chatbot for Obsidian Vaults.

This layer handles chunking, embedding generation, and vector storage
of ingested documents for retrieval and search.
"""

from .indexer import Indexer

__all__ = ['Indexer']
