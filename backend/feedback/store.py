"""
FeedbackStore: SQLite-based persistence for improvement rules and feedback logs.

This module provides the FeedbackStore class which manages:
- improvement_rules: Stores user-submitted improvement rules with embeddings
- feedback_logs: Records positive/negative feedback events
"""

import pickle
import sqlite3
from typing import List, Optional, Tuple

from models import ImprovementRule


class FeedbackStore:
    """
    SQLite-backed store for improvement rules and feedback logs.

    Improvement rules are saved with their embedding vectors (as BLOB via pickle)
    so that RuleRetriever can perform cosine similarity search at query time.
    """

    def __init__(self, db_path: str = "backend/feedback.db") -> None:
        """SQLiteデータベースを初期化し、テーブルを作成する"""
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Return a new SQLite connection with row_factory set."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not already exist (idempotent)."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_rules (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_text          TEXT    NOT NULL,
                    answer_text         TEXT    NOT NULL,
                    improvement_request TEXT    NOT NULL,
                    rule_embedding      BLOB    NOT NULL,
                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id    TEXT    NOT NULL,
                    query_text    TEXT    NOT NULL,
                    feedback_type TEXT    NOT NULL,
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_rule(
        self,
        query_text: str,
        answer_text: str,
        improvement_request: str,
        embedding: List[float],
    ) -> int:
        """
        改善ルールを保存し、生成されたIDを返す。

        Embedding は pickle.dumps() で BLOB としてシリアライズして保存する。
        """
        blob = pickle.dumps(embedding)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO improvement_rules
                    (query_text, answer_text, improvement_request, rule_embedding)
                VALUES (?, ?, ?, ?)
                """,
                (query_text, answer_text, improvement_request, blob),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def log_feedback(
        self,
        message_id: str,
        query_text: str,
        feedback_type: str,
    ) -> None:
        """フィードバックログを記録する。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback_logs (message_id, query_text, feedback_type)
                VALUES (?, ?, ?)
                """,
                (message_id, query_text, feedback_type),
            )
            conn.commit()

    def get_all_rules(self) -> List[ImprovementRule]:
        """全改善ルールを取得する（rule_embedding は含まない）。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, query_text, answer_text, improvement_request, created_at
                FROM improvement_rules
                ORDER BY id ASC
                """
            ).fetchall()

        return [
            ImprovementRule(
                id=row["id"],
                query_text=row["query_text"],
                answer_text=row["answer_text"],
                improvement_request=row["improvement_request"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_rule(self, rule_id: int) -> bool:
        """
        指定IDのルールを削除する。

        Returns:
            True  — 削除成功
            False — 該当IDが存在しなかった
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM improvement_rules WHERE id = ?",
                (rule_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_rules_with_embeddings(
        self,
    ) -> List[Tuple[ImprovementRule, List[float]]]:
        """
        コサイン類似度計算用にルールと Embedding を取得する。

        Returns:
            List of (ImprovementRule, embedding_vector) tuples.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, query_text, answer_text, improvement_request,
                       rule_embedding, created_at
                FROM improvement_rules
                ORDER BY id ASC
                """
            ).fetchall()

        result: List[Tuple[ImprovementRule, List[float]]] = []
        for row in rows:
            rule = ImprovementRule(
                id=row["id"],
                query_text=row["query_text"],
                answer_text=row["answer_text"],
                improvement_request=row["improvement_request"],
                created_at=row["created_at"],
            )
            embedding: List[float] = pickle.loads(row["rule_embedding"])  # noqa: S301
            result.append((rule, embedding))

        return result
