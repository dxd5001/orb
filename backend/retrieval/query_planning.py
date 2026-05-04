import re
from typing import List, Optional

try:
    from models import ParsedQuery, QueryIntent, RetrievalPlan, Scope, SearchMode
    from utils.date_normalizer import DateNormalizer
except ImportError:
    from backend.models import (
        ParsedQuery,
        QueryIntent,
        RetrievalPlan,
        Scope,
        SearchMode,
    )
    from backend.utils.date_normalizer import DateNormalizer


class QueryParser:
    """Parse explicit search commands from raw user input."""

    MODE_PATTERN = re.compile(r"(?<!\S)/(auto|diary|general)(?=\s|$)", re.IGNORECASE)
    TAG_PATTERN = re.compile(r"(?<!\S)#([^\s#@/]+)")
    FOLDER_PATTERN = re.compile(r"(?<!\S)@([^\s#@/]+)")

    def parse(
        self,
        raw_text: str,
        ui_search_mode: SearchMode = SearchMode.AUTO,
        ui_scope: Optional[Scope] = None,
    ) -> ParsedQuery:
        """Split inline commands from the natural-language query."""
        working_text = raw_text.strip()

        command_search_mode = self._extract_search_mode(working_text)
        command_tags = self._extract_tags(working_text)
        command_folder = self._extract_folder(working_text)

        query_text = self.MODE_PATTERN.sub(" ", working_text)
        query_text = self.TAG_PATTERN.sub(" ", query_text)
        query_text = self.FOLDER_PATTERN.sub(" ", query_text)
        query_text = re.sub(r"\s+", " ", query_text).strip()

        resolved_scope = self._merge_scope(
            ui_scope=ui_scope,
            command_scope=Scope(folder=command_folder, tags=command_tags or None),
        )

        return ParsedQuery(
            raw_query=raw_text,
            query_text=query_text or raw_text.strip(),
            search_mode=command_search_mode or ui_search_mode,
            scope=resolved_scope,
            command_search_mode=command_search_mode,
            command_scope=Scope(folder=command_folder, tags=command_tags or None)
            if command_folder or command_tags
            else None,
        )

    def _extract_search_mode(self, text: str) -> Optional[SearchMode]:
        match = self.MODE_PATTERN.search(text)
        if not match:
            return None
        return SearchMode(match.group(1).lower())

    def _extract_tags(self, text: str) -> List[str]:
        tags = [match.group(1) for match in self.TAG_PATTERN.finditer(text)]
        return list(dict.fromkeys(tags))

    def _extract_folder(self, text: str) -> Optional[str]:
        match = self.FOLDER_PATTERN.search(text)
        if not match:
            return None
        return match.group(1)

    def _merge_scope(
        self, ui_scope: Optional[Scope], command_scope: Optional[Scope]
    ) -> Optional[Scope]:
        if ui_scope is None and command_scope is None:
            return None

        folder = None
        tags: List[str] = []

        if ui_scope is not None:
            folder = ui_scope.folder
            tags.extend(ui_scope.tags or [])

        if command_scope is not None:
            if command_scope.folder:
                folder = command_scope.folder
            tags.extend(command_scope.tags or [])

        deduped_tags = list(dict.fromkeys(tags)) or None
        return Scope(folder=folder, tags=deduped_tags)


class QueryPlanner:
    """Build an executable retrieval plan from a parsed query."""

    DIARY_KEYWORDS = (
        "diary",
        "daily",
        "journal",
        "today",
        "yesterday",
        "tomorrow",
        "breakfast",
        "lunch",
        "dinner",
        "ate",
        "slept",
        "日記",
        "今日",
        "昨日",
        "明日",
        "食べた",
        "朝食",
        "昼食",
        "夕食",
    )

    def __init__(self, date_normalizer: Optional[DateNormalizer] = None):
        self.date_normalizer = date_normalizer or DateNormalizer()

    def build_plan(
        self,
        parsed_query: ParsedQuery,
        history: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> RetrievalPlan:
        """Build the final retrieval plan from parsed query data."""
        normalized_query = self.date_normalizer.normalize_query(
            parsed_query.query_text, history or []
        )
        is_temporal = self._is_temporal_query(parsed_query.query_text) or (
            normalized_query != parsed_query.query_text
        )
        is_fact_query = self._is_fact_query(parsed_query.query_text)
        is_context_query = self._is_context_query(parsed_query.query_text)
        is_diary_intent = self._is_diary_intent(
            parsed_query.query_text,
            normalized_query,
            parsed_query.scope,
            parsed_query.search_mode,
        )

        primary_intent = self._determine_primary_intent(
            search_mode=parsed_query.search_mode,
            is_diary_intent=is_diary_intent,
            is_temporal=is_temporal,
            is_fact_query=is_fact_query,
            is_context_query=is_context_query,
        )

        return RetrievalPlan(
            original_query=parsed_query.query_text,
            normalized_query=normalized_query,
            search_mode=parsed_query.search_mode,
            scope=parsed_query.scope,
            top_k=top_k,
            primary_intent=primary_intent,
            is_diary_intent=is_diary_intent,
            is_temporal=is_temporal,
            is_fact_query=is_fact_query,
            is_context_query=is_context_query,
        )

    def _determine_primary_intent(
        self,
        search_mode: SearchMode,
        is_diary_intent: bool,
        is_temporal: bool,
        is_fact_query: bool,
        is_context_query: bool,
    ) -> QueryIntent:
        if search_mode == SearchMode.DIARY or is_diary_intent:
            if is_temporal:
                return QueryIntent.TEMPORAL
            return QueryIntent.DIARY
        if search_mode == SearchMode.GENERAL:
            if is_fact_query:
                return QueryIntent.FACT
            if is_context_query:
                return QueryIntent.CONTEXT
            return QueryIntent.GENERAL
        if is_temporal:
            return QueryIntent.TEMPORAL
        if is_fact_query:
            return QueryIntent.FACT
        if is_context_query:
            return QueryIntent.CONTEXT
        return QueryIntent.UNKNOWN

    def _is_diary_intent(
        self,
        query: str,
        normalized_query: str,
        scope: Optional[Scope],
        search_mode: SearchMode,
    ) -> bool:
        if search_mode == SearchMode.DIARY:
            return True

        if scope and scope.folder and "diary" in scope.folder.lower():
            return True

        query_lower = query.lower()
        normalized_lower = normalized_query.lower()
        return any(keyword in query_lower for keyword in self.DIARY_KEYWORDS) or bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized_lower)
        )

    def _is_temporal_query(self, query: str) -> bool:
        query_lower = query.lower()
        temporal_keywords = [
            "いつ",
            "最後",
            "初めて",
            "最初",
            "直近",
            "yesterday",
            "today",
            "when",
            "last time",
            "first time",
        ]
        return any(keyword in query_lower for keyword in temporal_keywords)

    def _is_fact_query(self, query: str) -> bool:
        query_lower = query.lower()
        fact_keywords = [
            "いつ",
            "最後に",
            "初めて",
            "何を",
            "どこで",
            "誰と",
            "記録",
            "when",
            "what",
            "who",
        ]
        return any(keyword in query_lower for keyword in fact_keywords)

    def _is_context_query(self, query: str) -> bool:
        query_lower = query.lower()
        context_keywords = [
            "について",
            "教えて",
            "様子",
            "詳細",
            "説明",
            "話して",
            "まとめて",
            "要約",
            "about",
            "details",
            "summary",
        ]
        return any(keyword in query_lower for keyword in context_keywords)
