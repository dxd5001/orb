"""
Generation layer for Orb - RAG Chatbot for Obsidian Vaults.

This layer handles prompt construction, LLM generation, and response formatting
including citation extraction.
"""

from .generator import Generator

__all__ = ['Generator']
