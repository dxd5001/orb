"""
Index API router for Orb - RAG Chatbot for Obsidian Vaults.
"""

import logging
from fastapi import APIRouter, HTTPException, Request

from models import IndexResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/index", response_model=IndexResponse)
async def index_vault(request: Request) -> IndexResponse:
    try:
        ingestor = request.app.state.ingestor
        indexer = request.app.state.indexer
        config_manager = request.app.state.config_manager

        logger.info("Starting vault indexing...")
        vault_path = config_manager.get_config('VAULT_PATH')

        ingest_result = ingestor.ingest(vault_path)
        if ingest_result.errors:
            logger.warning(f"Ingestion completed with {len(ingest_result.errors)} errors")

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
