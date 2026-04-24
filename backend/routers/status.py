"""
Status API router for Obsidian RAG Chatbot.

This module provides the /api/status endpoint for checking system status.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends

from models import StatusResponse
from routers.dependencies import get_components

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(components: dict = Depends(get_components)) -> StatusResponse:
    """
    Get system status and statistics.
    
    Args:
        components: Application components (retriever, indexer, config_manager)
        
    Returns:
        Status response with system information
        
    Raises:
        HTTPException: If status check fails
    """
    try:
        retriever = components['retriever']
        indexer = components['indexer']
        config_manager = components['config_manager']
        embedding_backend = components['embedding_backend']
        llm_backend = components['llm_backend']
        
        logger.info("Getting system status...")
        
        # Get collection statistics
        collection_stats = retriever.get_collection_stats()
        total_notes = collection_stats.get('total_chunks', 0)
        total_chunks = collection_stats.get('total_chunks', 0)
        
        # Check if collection is empty
        is_empty = retriever.is_collection_empty()
        index_status = "ready" if not is_empty else "not_indexed"
        
        # Get last indexed time (placeholder - would need to be stored somewhere)
        last_indexed = datetime.now() if not is_empty else None
        
        # Get vector store path
        vector_store_path = config_manager.get_config('VECTOR_STORE_PATH')
        
        # Test component connections
        embedding_status = "ready"
        llm_status = "ready"
        
        try:
            embedding_backend.test_connection()
        except Exception:
            embedding_status = "error"
        
        try:
            llm_backend.test_connection()
        except Exception:
            llm_status = "error"
        
        return StatusResponse(
            index_status=index_status,
            total_notes=total_notes,
            total_chunks=total_chunks,
            last_indexed=last_indexed,
            vector_store_path=vector_store_path
        )
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
