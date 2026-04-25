"""
Retrieval layer for Orb - RAG Chatbot for Obsidian Vaults.

This layer handles similarity search and retrieval of relevant chunks
from the vector database based on user queries.
"""

from .retriever import Retriever

__all__ = ['Retriever']
