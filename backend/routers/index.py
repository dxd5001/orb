"""
Index API router for Orb - RAG Chatbot for Obsidian Vaults.

This module provides the /api/index endpoint for indexing vault content.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends

from models import IndexResponse
from routers.dependencies import get_components

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/index", response_model=IndexResponse)
async def index_vault(components: dict = Depends(get_components)) -> IndexResponse:
    """
    Index the vault content.
    
    Args:
        components: Application components (ingestor, indexer)
        
    Returns:
        Index response with statistics
        
    Raises:
        HTTPException: If indexing fails
    """
    try:
        ingestor = components['ingestor']
        indexer = components['indexer']
        config_manager = components['config_manager']
        
        logger.info("Starting vault indexing...")
        
        # Get vault path from configuration
        vault_path = config_manager.get_config('VAULT_PATH')
        
        # Ingest vault content
        ingest_result = ingestor.ingest(vault_path)
        
        if ingest_result.errors:
            logger.warning(f"Ingestion completed with {len(ingest_result.errors)} errors")
        
        # Index ingested content
        index_result = indexer.index(ingest_result)
        
        logger.info(f"Indexing completed: {index_result.note_count} notes, {index_result.chunk_count} chunks")
        
        return IndexResponse(
            status="completed",
            notes=index_result.note_count,
            chunks=index_result.chunk_count
        )
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
