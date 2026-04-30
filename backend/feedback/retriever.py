"""
RuleRetriever: Cosine similarity-based retrieval of improvement rules.

Retrieves the most relevant improvement rules from FeedbackStore
based on query embedding similarity.
"""

import logging
from typing import List

from models import ImprovementRule
from embedding.base import EmbeddingBackend
from feedback.store import FeedbackStore

logger = logging.getLogger(__name__)


class RuleRetriever:
    """
    Retrieves improvement rules relevant to a given query using cosine similarity.

    Uses the same EmbeddingBackend as the main retriever to ensure
    embedding space consistency.
    """

    def __init__(self, store: FeedbackStore, embedding_backend: EmbeddingBackend) -> None:
        self.store = store
        self.embedding_backend = embedding_backend

    def retrieve_rules(self, query: str, top_k: int = 3) -> List[ImprovementRule]:
        """
        クエリに関連する改善ルールをコサイン類似度で取得する。

        Args:
            query: ユーザーのクエリテキスト
            top_k: 返却する最大件数

        Returns:
            類似度降順の改善ルールリスト（最大 top_k 件）
            - top_k <= 0 の場合は空リスト
            - ストアが空の場合は空リスト
            - 失敗時は空リスト（例外を伝播させない）
        """
        if top_k <= 0:
            return []

        try:
            rules_with_embeddings = self.store.get_rules_with_embeddings()
            if not rules_with_embeddings:
                return []

            # Generate query embedding
            query_embedding = self.embedding_backend.embed([query])[0]

            # Compute cosine similarities
            scored: List[tuple] = []
            for rule, rule_embedding in rules_with_embeddings:
                similarity = self._cosine_similarity(query_embedding, rule_embedding)
                scored.append((similarity, rule))

            # Sort by similarity descending and return top_k
            scored.sort(key=lambda x: x[0], reverse=True)
            return [rule for _, rule in scored[:top_k]]

        except Exception as e:
            logger.warning(f"RuleRetriever.retrieve_rules failed, returning empty list: {e}")
            return []

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """コサイン類似度を計算する（numpy を使用）。"""
        try:
            import numpy as np
            va = np.array(a, dtype=float)
            vb = np.array(b, dtype=float)
            norm_a = np.linalg.norm(va)
            norm_b = np.linalg.norm(vb)
            if norm_a == 0.0 or norm_b == 0.0:
                return 0.0
            return float(np.dot(va, vb) / (norm_a * norm_b))
        except Exception:
            return 0.0
