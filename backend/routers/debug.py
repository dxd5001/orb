"""
Debug API router for Orb - RAG Chatbot for Obsidian Vaults.
Provides debugging endpoints for inspecting ChromaDB collections.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/debug", tags=["debug"])


class CollectionInfo(BaseModel):
    """Information about a ChromaDB collection."""

    name: str
    count: int


class DocumentInfo(BaseModel):
    """Information about a document in ChromaDB."""

    id: str
    source_path: str
    title: str
    last_modified: Optional[str]
    content_preview: str
    distance: Optional[float] = None


class CollectionInspectResponse(BaseModel):
    """Response for collection inspection."""

    collection_name: str
    total_documents: int
    documents: list[DocumentInfo]


class SearchResponse(BaseModel):
    """Response for search in collection."""

    collection_name: str
    query: str
    results: list[DocumentInfo]


@router.get("/collections", response_model=list[CollectionInfo])
async def list_collections(request: Request):
    """List all ChromaDB collections."""
    try:
        retriever = request.app.state.retriever
        client = retriever.client

        collections = client.list_collections()
        collection_infos = [
            CollectionInfo(name=collection.name, count=collection.count())
            for collection in collections
        ]

        return collection_infos
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise


@router.get(
    "/collections/{collection_name}/inspect", response_model=CollectionInspectResponse
)
async def inspect_collection(
    request: Request,
    collection_name: str,
    limit: int = 10,
    source_path: Optional[str] = None,
):
    """Inspect a ChromaDB collection."""
    try:
        retriever = request.app.state.retriever
        client = retriever.client

        collection = client.get_collection(name=collection_name)
        total_documents = collection.count()

        # Build where filter if source_path is provided
        where_filter = {"source_path": source_path} if source_path else None

        results = collection.get(
            include=["documents", "metadatas"], limit=limit, where=where_filter
        )

        documents = []
        for i, (doc, metadata) in enumerate(
            zip(results["documents"], results["metadatas"])
        ):
            documents.append(
                DocumentInfo(
                    id=f"doc_{i}",
                    source_path=metadata.get("source_path", "N/A"),
                    title=metadata.get("title", "N/A"),
                    last_modified=metadata.get("last_modified"),
                    content_preview=doc[:200],
                )
            )

        return CollectionInspectResponse(
            collection_name=collection_name,
            total_documents=total_documents,
            documents=documents,
        )
    except Exception as e:
        logger.error(f"Error inspecting collection {collection_name}: {e}")
        raise


@router.get("/collections/{collection_name}/search", response_model=SearchResponse)
async def search_collection(
    request: Request, collection_name: str, query: str, limit: int = 5
):
    """Search for documents in a collection."""
    try:
        retriever = request.app.state.retriever
        embedding_backend = request.app.state.embedding_backend
        client = retriever.client

        collection = client.get_collection(name=collection_name)

        # Generate embedding
        query_embedding = embedding_backend.embed([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )

        documents = []
        for i, (doc, metadata, distance) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            documents.append(
                DocumentInfo(
                    id=f"doc_{i}",
                    source_path=metadata.get("source_path", "N/A"),
                    title=metadata.get("title", "N/A"),
                    last_modified=metadata.get("last_modified"),
                    content_preview=doc[:300],
                    distance=distance,
                )
            )

        return SearchResponse(
            collection_name=collection_name, query=query, results=documents
        )
    except Exception as e:
        logger.error(f"Error searching collection {collection_name}: {e}")
        raise
