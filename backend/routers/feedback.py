"""
Feedback API router for Orb - RAG Chatbot for Obsidian Vaults.

Provides endpoints for:
- POST /feedback        — Submit feedback and save improvement rules
- GET  /feedback/rules  — List all saved improvement rules
- DELETE /feedback/rules/{rule_id} — Delete a specific rule
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request

from models import FeedbackRequest, FeedbackRuleResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_feedback_store(request: Request):
    return request.app.state.feedback_store


def _get_embedding_backend(request: Request):
    return request.app.state.embedding_backend


@router.post("/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest):
    """
    フィードバックを受け取り、必要に応じて改善ルールを保存する。

    - positive: フィードバックログのみ記録
    - negative + improvement_request あり: ルールを保存してログ記録
    - negative + improvement_request なし: フィードバックログのみ記録
    """
    store = _get_feedback_store(request)
    embedding_backend = _get_embedding_backend(request)

    try:
        # Save improvement rule if negative feedback with request
        if (
            body.feedback_type == "negative"
            and body.improvement_request
            and body.improvement_request.strip()
        ):
            # Generate embedding for the rule
            rule_text = f"{body.query} {body.improvement_request}"
            embedding = embedding_backend.embed([rule_text])[0]
            store.save_rule(
                query_text=body.query,
                answer_text=body.answer,
                improvement_request=body.improvement_request.strip(),
                embedding=embedding,
            )
            logger.info(f"Saved improvement rule for query: '{body.query[:50]}'")

        # Always log the feedback
        store.log_feedback(
            message_id=body.message_id,
            query_text=body.query,
            feedback_type=body.feedback_type,
        )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Failed to process feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/rules", response_model=List[FeedbackRuleResponse])
async def list_rules(request: Request):
    """保存済みの改善ルール一覧を返す。"""
    store = _get_feedback_store(request)
    try:
        rules = store.get_all_rules()
        return [
            FeedbackRuleResponse(
                id=rule.id,
                query_text=rule.query_text,
                improvement_request=rule.improvement_request,
                created_at=rule.created_at,
            )
            for rule in rules
        ]
    except Exception as e:
        logger.error(f"Failed to list rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/feedback/rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request):
    """指定IDの改善ルールを削除する。存在しない場合は404を返す。"""
    store = _get_feedback_store(request)
    try:
        deleted = store.delete_rule(rule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
