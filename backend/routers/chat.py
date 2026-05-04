"""
Chat API router for Orb - RAG Chatbot for Obsidian Vaults.
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Request

try:
    from models import ChatRequest, ChatResponse
    from retrieval.query_planning import QueryParser, QueryPlanner
except ImportError:
    from backend.models import ChatRequest, ChatResponse
    from backend.retrieval.query_planning import QueryParser, QueryPlanner

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    try:
        retriever = request.app.state.retriever
        generator = request.app.state.generator

        request_id = int(time.time() * 1000)
        logger.info(f"[{request_id}] Processing chat request: '{body.query[:50]}...'")

        errors = _validate_chat_request(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})

        context_history = [turn.content for turn in (body.history or [])]
        parser = QueryParser()
        planner = QueryPlanner()
        parsed_query = parser.parse(
            raw_text=body.query,
            ui_search_mode=body.search_mode,
            ui_scope=body.scope,
        )
        plan = planner.build_plan(
            parsed_query=parsed_query,
            history=context_history,
            top_k=5,
        )

        if plan.normalized_query != parsed_query.query_text:
            logger.info(
                f"[{request_id}] Normalized query: '{parsed_query.query_text}' -> '{plan.normalized_query}'"
            )

        chunks = retriever.retrieve(plan.normalized_query, plan=plan)

        logger.info(f"Retrieved {len(chunks)} chunks")

        response = generator.generate(
            query=body.query, chunks=chunks, history=body.history
        )

        logger.info(f"[{request_id}] Chat request completed successfully")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
