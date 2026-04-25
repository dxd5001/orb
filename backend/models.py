"""
Data models for Orb - RAG Chatbot for Obsidian Vaults.

This module defines the core data structures used throughout the application:
- NoteDocument: Represents a single note from the vault
- Chunk: Represents a text chunk for vector storage
- Scope: Defines search scope filtering
- ChatRequest/Response: API request/response models
- Citation: Reference information for responses
- IngestResult/IndexResult: Processing result models
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field


@dataclass
class NoteDocument:
    """
    Represents a single note document from the vault.
    
    This is the output of the Ingestor layer and input to the Indexer layer.
    """
    file_path: str          # Vault root relative path (e.g., "daily/2024-01-01.md")
    title: str              # Frontmatter title, or filename if not present
    body: str               # Text content without frontmatter
    tags: List[str]         # Frontmatter tags
    frontmatter: Dict[str, Any]  # Complete frontmatter key-value pairs
    last_modified: datetime # File last modification timestamp


@dataclass
class Chunk:
    """
    Represents a text chunk for vector storage and retrieval.
    
    This is the basic unit stored in the vector store.
    """
    chunk_id: str           # Unique ID (e.g., "{file_path}::{chunk_index}")
    text: str               # Chunk text content
    source_path: str        # Original note file path
    title: str              # Original note title
    tags: List[str]         # Original note tags
    frontmatter: Dict[str, Any]  # Original note frontmatter
    last_modified: datetime # Original note modification time
    chunk_index: int        # Chunk index within the note


@dataclass
class IngestResult:
    """
    Result of the ingestion process.
    
    Contains statistics about the processed notes.
    """
    notes: List[NoteDocument]
    total_count: int
    skipped_count: int
    errors: List[Dict[str, str]]  # [{"path": ..., "reason": ...}]


@dataclass
class IndexResult:
    """
    Result of the indexing process.
    
    Contains statistics about the created chunks.
    """
    note_count: int
    chunk_count: int


class Scope(BaseModel):
    """
    Defines search scope filtering for retrieval.
    
    Used to limit search results to specific folders or tags.
    """
    folder: Optional[str] = Field(None, description="Folder path (e.g., 'daily/')")
    tags: Optional[List[str]] = Field(None, description="List of tags (e.g., ['journal', 'work'])")


class SearchMode(str, Enum):
    """
    Search mode enumeration for chat requests.
    
    Determines the retrieval strategy:
    - AUTO: Automatically determine diary vs general search
    - DIARY: Prioritize diary entries and date-based search
    - GENERAL: Prioritize general semantic search
    """
    AUTO = "auto"
    DIARY = "diary"
    GENERAL = "general"


class ChatTurn(BaseModel):
    """
    Represents a single turn in a conversation history.
    
    Used for maintaining conversation context.
    """
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """
    Request model for the /api/chat endpoint.
    
    Contains the user query and optional search scope/history.
    """
    query: str = Field(..., description="User question (required)")
    scope: Optional[Scope] = Field(None, description="Search scope (optional)")
    history: Optional[List[ChatTurn]] = Field(None, description="Conversation history (optional, max 5 turns)")
    search_mode: SearchMode = Field(SearchMode.AUTO, description="Search mode (default: auto)")


class Citation(BaseModel):
    """
    Reference information for chat responses.
    
    Provides source attribution for generated answers.
    """
    file_path: str = Field(..., description="Note file path relative to vault root")
    title: str = Field(..., description="Note title")
    snippet: str = Field(..., description="Relevant text snippet")
    source_path: str = Field(..., description="Source file path (for frontend compatibility)")


class AnswerBlock(BaseModel):
    """
    Structured answer block for frontend rendering.

    Separates answer sections such as summary, evidence, and notes.
    """
    type: str = Field(..., description="Block type (e.g., summary, evidence, note)")
    title: str = Field(..., description="Block title")
    content: str = Field(..., description="Main block content")
    items: List[str] = Field(default_factory=list, description="Optional bullet items")


class ChatResponse(BaseModel):
    """
    Response model for the /api/chat endpoint.
    
    Contains the generated answer and supporting citations.
    """
    answer: str = Field(..., description="Generated answer text")
    answer_blocks: List[AnswerBlock] = Field(default_factory=list, description="Structured answer blocks for UI rendering")
    citations: List[Citation] = Field(default_factory=list, description="Supporting citations")


class StatusResponse(BaseModel):
    """
    Response model for the /api/status endpoint.
    
    Contains indexing status and statistics.
    """
    index_status: str = Field(..., description="Index status (e.g., 'ready', 'empty', 'error')")
    total_notes: int = Field(..., description="Total number of indexed notes")
    total_chunks: int = Field(..., description="Total number of indexed chunks")
    last_indexed: Optional[datetime] = Field(None, description="Last indexing timestamp")
    vector_store_path: str = Field(..., description="Vector store storage path")


class IndexResponse(BaseModel):
    """
    Response model for the /api/index endpoint.
    
    Contains the result of the indexing process.
    """
    status: str = Field(..., description="Processing status (e.g., 'completed', 'error')")
    notes: Optional[int] = Field(None, description="Number of processed notes")
    chunks: Optional[int] = Field(None, description="Number of created chunks")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class ConfigGetResponse(BaseModel):
    """
    Response model for the GET /api/config endpoint.
    
    Contains current configuration (excluding sensitive data).
    """
    config: Dict[str, Any] = Field(..., description="Current configuration values")


class ConfigUpdateRequest(BaseModel):
    """
    Request model for the PUT /api/config endpoint.
    
    Contains configuration updates.
    """
    vault_path: Optional[str] = Field(None, description="Vault directory path")
    llm_provider: Optional[str] = Field(None, description="LLM provider (local or openai)")
    llm_model: Optional[str] = Field(None, description="LLM model name")
    llm_base_url: Optional[str] = Field(None, description="Local LLM endpoint URL")
    embedding_provider: Optional[str] = Field(None, description="Embedding provider (local or openai)")
    embedding_model: Optional[str] = Field(None, description="Embedding model name")
    vector_store_path: Optional[str] = Field(None, description="Vector store storage path")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    api_port: Optional[int] = Field(None, description="API server port")
    use_keyring: Optional[bool] = Field(None, description="Use OS keychain for API keys")


class ConfigUpdateResponse(BaseModel):
    """
    Response model for the PUT /api/config endpoint.
    
    Contains the result of configuration update.
    """
    success: bool = Field(..., description="Whether update was successful")
    message: str = Field(..., description="Result message")
    updated_fields: List[str] = Field(..., description="List of updated field names")
    errors: List[str] = Field(default_factory=list, description="List of error messages")


# Validation functions
def validate_chat_request(request: ChatRequest) -> List[str]:
    """
    Validate a chat request and return list of errors.
    
    Args:
        request: Chat request to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if not request.query.strip():
        errors.append("Query cannot be empty")
    
    if request.history and len(request.history) > 5:
        errors.append("History cannot exceed 5 turns")
    
    if request.scope and request.scope.tags and len(request.scope.tags) > 10:
        errors.append("Scope cannot contain more than 10 tags")
    
    return errors


def validate_scope(scope: Scope) -> List[str]:
    """
    Validate a scope object and return list of errors.
    
    Args:
        scope: Scope to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if scope.folder and not scope.folder.strip():
        errors.append("Folder path cannot be empty")
    
    if scope.tags:
        for tag in scope.tags:
            if not tag.strip():
                errors.append("Tag cannot be empty")
                break
    
    return errors


def create_chunk_id(file_path: str, chunk_index: int) -> str:
    """
    Create a unique chunk ID from file path and index.
    
    Args:
        file_path: Source file path
        chunk_index: Chunk index within the file
        
    Returns:
        Unique chunk ID
    """
    return f"{file_path}::{chunk_index}"


def extract_title_from_filename(file_path: str) -> str:
    """
    Extract title from file path (filename without extension).
    
    Args:
        file_path: File path
        
    Returns:
        Extracted title
    """
    import os
    filename = os.path.basename(file_path)
    title = os.path.splitext(filename)[0]
    return title
