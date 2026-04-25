"""
Ingestion layer for Orb - RAG Chatbot for Obsidian Vaults.

This layer is responsible for reading data from various sources and converting
them into NoteDocument objects for downstream processing.
"""

from .base import BaseIngestor

__all__ = ['BaseIngestor']
