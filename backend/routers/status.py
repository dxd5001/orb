"""
Status API router for Orb - RAG Chatbot for Obsidian Vaults.

This module provides the /api/status endpoint for checking system status.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request

from models import StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    """
    Get system status and statistics.
    """
    try:
        retriever = request.app.state.retriever
        config_manager = request.app.state.config_manager

        # Get collection statistics
        collection_stats = retriever.get_collection_stats()
        total_chunks = collection_stats.get('total_chunks', 0)

        # Check if collection is empty
        is_empty = retriever.is_collection_empty()
        index_status = "ready" if not is_empty else "not_indexed"

        last_indexed = datetime.now() if not is_empty else None
        vector_store_path = config_manager.get_config('VECTOR_STORE_PATH')

        return StatusResponse(
            index_status=index_status,
            total_notes=total_chunks,
            total_chunks=total_chunks,
            last_indexed=last_indexed,
            vector_store_path=vector_store_path
        )

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
