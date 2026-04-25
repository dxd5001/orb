"""
Chat API router for Orb - RAG Chatbot for Obsidian Vaults.

This module provides the /api/chat endpoint for handling chat requests
with RAG functionality.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from models import ChatRequest, ChatResponse
from routers.dependencies import get_components
from utils.date_normalizer import DateNormalizer

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    components: dict = Depends(get_components)
) -> ChatResponse:
    """
    Process a chat request with RAG functionality.
    
    Args:
        request: Chat request with query, scope, and history
        components: Application components (retriever, generator)
        
    Returns:
        Chat response with answer and citations
        
    Raises:
        HTTPException: If processing fails
    """
    try:
        retriever = components['retriever']
        generator = components['generator']
        
        import time
        request_id = int(time.time() * 1000)  # Simple unique ID
        logger.info(f"[{request_id}] Processing chat request: '{request.query[:50]}...'")
        logger.info(f"[{request_id}] Request history length: {len(request.history) if request.history else 0}")
        
        # Validate request
        errors = _validate_chat_request(request)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        
        # Normalize temporal expressions for diary-specific queries
        normalizer = DateNormalizer()
        context_history = [turn.content for turn in (request.history or [])]
        normalized_query = normalizer.normalize_query(request.query, context_history)
        
        if normalized_query != request.query:
            logger.info(f"[{request_id}] Normalized query: '{request.query}' -> '{normalized_query}'")
        
        # Retrieve relevant chunks
        chunks = retriever.retrieve(
            query=normalized_query,
            scope=request.scope,
            top_k=5,
            search_mode=request.search_mode
        )
        
        logger.info(f"Retrieved {len(chunks)} chunks")
        
        # Generate response using original query for better LLM understanding
        response = generator.generate(
            query=request.query,
            chunks=chunks,
            history=request.history
        )
        
        logger.info(f"Generated response with {len(response.citations)} citations")
        
        logger.info(f"[{request_id}] Chat request completed successfully")
        return response
        
    except HTTPException:
        logger.error(f"[{request_id}] Chat request failed with HTTP exception")
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Chat request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _validate_chat_request(request: ChatRequest) -> list[str]:
    """
    Validate chat request.
    
    Args:
        request: Chat request to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    # Validate query
    if not request.query or not request.query.strip():
        errors.append("Query cannot be empty")
    
    # Validate scope
    if request.scope:
        scope_errors = _validate_scope(request.scope)
        errors.extend(scope_errors)
    
    # No history validation needed for local private use
    # History length is managed by frontend (currently last 10 messages)
    if request.history:
        logger.debug(f"Processing request with {len(request.history)} history messages")
    
    return errors


def _validate_scope(scope) -> list[str]:
    """
    Validate scope object.
    
    Args:
        scope: Scope object to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if scope.folder and not scope.folder.strip():
        errors.append("Folder path cannot be empty")
    
    if scope.tags:
        for tag in scope.tags:
            if not tag or not tag.strip():
                errors.append("Tag cannot be empty")
                break
    
    return errors
