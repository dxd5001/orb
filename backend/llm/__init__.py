"""
LLM layer for Obsidian RAG Chatbot.

This layer provides abstract interfaces and implementations for large language
model backends including local models and cloud APIs.
"""

from .base import LLMBackend
from .local import LocalLLMBackend
from .openai_backend import OpenAILLMBackend

__all__ = ['LLMBackend', 'LocalLLMBackend', 'OpenAILLMBackend']
