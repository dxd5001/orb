"""
Generation layer for Obsidian RAG Chatbot.

This layer handles prompt construction, LLM generation, and response formatting
including citation extraction.
"""

from .generator import Generator

__all__ = ['Generator']
