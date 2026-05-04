"""
Retriever implementation for similarity search and chunk retrieval.

This module handles the retrieval of relevant chunks from the vector database
based on user queries, with support for scope filtering.
"""

import logging
import json
from typing import List, Optional, Dict, Any, TYPE_CHECKING

try:
    import chromadb
    from chromadb.config import Settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

if TYPE_CHECKING:
    from llm.base import LLMBackend

from models import Chunk, Scope, SearchMode
from embedding.base import EmbeddingBackend

logger = logging.getLogger(__name__)


class Retriever:
    """
    Retriever for finding relevant chunks based on similarity search.

    This class handles:
    1. Query embedding generation
    2. Similarity search in ChromaDB
    3. Scope-based filtering (folder and tag filters)
    4. Result conversion to Chunk objects
    """

    # ChromaDB collection name (must match Indexer)
    COLLECTION_NAME = "obsidian_vault"
    PROPOSITION_COLLECTION_NAME = "obsidian_vault_propositions"

    def __init__(
        self,
        embedding_backend: EmbeddingBackend,
        vector_store_path: str,
        llm_backend: Optional["LLMBackend"] = None,
    ):
        """
        Initialize the retriever.

        Args:
            embedding_backend: Backend for generating embeddings
            vector_store_path: Path for ChromaDB storage
            llm_backend: Optional LLM backend for HyDE query expansion
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb library is not available. "
                "Install it with: pip install chromadb"
            )

        self.embedding_backend = embedding_backend
        self.vector_store_path = vector_store_path
        self.llm_backend = llm_backend
        self._client = None
        self._collection = None
        self._proposition_collection = None

    @property
    def client(self):
        """Lazy loading of ChromaDB client."""
        if self._client is None:
            logger.info(
                f"Initializing ChromaDB client with path: {self.vector_store_path}"
            )
            self._client = chromadb.PersistentClient(path=self.vector_store_path)
        return self._client

    @property
    def collection(self):
        """Lazy loading of ChromaDB collection."""
        if self._collection is None:
            self._collection = self._get_collection()
        return self._collection

    @property
    def proposition_collection(self):
        """Lazy loading of proposition collection."""
        if self._proposition_collection is None:
            self._proposition_collection = self._get_proposition_collection()
        return self._proposition_collection

    def _get_proposition_collection(self):
        """Get the proposition collection."""
        try:
            collection = self.client.get_collection(
                name=self.PROPOSITION_COLLECTION_NAME
            )
            logger.info(
                f"Using proposition collection: {self.PROPOSITION_COLLECTION_NAME}"
            )
            return collection
        except Exception as e:
            logger.warning(
                f"Failed to get proposition collection {self.PROPOSITION_COLLECTION_NAME}: {e}"
            )
            return None

    def _get_collection(self):
        """Get the ChromaDB collection."""
        try:
            collection = self.client.get_collection(name=self.COLLECTION_NAME)
            logger.info(f"Using collection: {self.COLLECTION_NAME}")
            return collection
        except Exception as e:
            logger.error(f"Failed to get collection {self.COLLECTION_NAME}: {e}")
            # Try to list all collections to debug
            try:
                collections = self.client.list_collections()
                logger.info(f"Available collections: {[c.name for c in collections]}")
                # If collection doesn't exist, return None to indicate not indexed
                if not any(c.name == self.COLLECTION_NAME for c in collections):
                    logger.info(f"Collection {self.COLLECTION_NAME} not found")
                    return None
            except:
                pass
            # Return None instead of raising exception
            return None

    def retrieve(
        self,
        query: str,
        scope: Optional[Scope] = None,
        top_k: int = 5,
        search_mode: SearchMode = SearchMode.AUTO,
        plan: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        Retrieve relevant chunks based on query similarity and search mode.

        Args:
            query: User query string
            scope: Optional search scope (folder and/or tag filters)
            top_k: Number of top results to return
            search_mode: Search mode (AUTO, DIARY, or GENERAL)

        Returns:
            List of relevant chunks

        Raises:
            ValueError: If query is empty
            RuntimeError: If retrieval fails
        """
        try:
            if not query or not query.strip():
                raise ValueError("Query cannot be empty")

            logger.info(
                f"RETRIEVER CALLED with query: '{query}', search_mode: {search_mode}"
            )

            # Query type detection for proposition vs regular search
            is_fact_query = self._is_fact_query(query)
            is_context_query = self._is_context_query(query)
            is_temporal_query = self._is_temporal_query(query)

            logger.info(
                f"Query analysis: is_fact_query={is_fact_query}, is_context_query={is_context_query}, is_temporal_query={is_temporal_query}"
            )

            # Route to appropriate search strategy based on query type
            # Prioritize temporal queries over fact queries
            if is_temporal_query and search_mode == SearchMode.AUTO:
                logger.info("Using TEMPORAL query mode - temporal query detected")
                normalized_query = self._normalize_date_query(query)
                return self._retrieve_temporal_query(
                    query, normalized_query, scope, top_k, prefer_diary=True
                )
            elif is_fact_query and self.proposition_collection is not None:
                logger.info("Using PROPOSITION mode - fact-based query detected")
                return self._retrieve_propositions(query, scope, top_k)
            elif is_context_query and search_mode == SearchMode.AUTO:
                logger.info("Using CONTEXT mode - context-based query detected")
                return self._retrieve_general_mode(query, scope, top_k)
            elif (
                search_mode == SearchMode.AUTO
                and not is_fact_query
                and not is_context_query
            ):
                logger.info(
                    "Using HYBRID mode - ambiguous query, combining both strategies"
                )
                return self._retrieve_hybrid(query, scope, top_k)
            else:
                # Fall back to existing search modes
                # Disable HyDE query expansion for stability - use original query directly
                hyde_query = query
                logger.info(
                    f"HyDE disabled for stability, using original query: '{query}'"
                )

                # Normalize date expressions in query
                normalized_query = self._normalize_date_query(hyde_query)
                logger.info(f"Normalized query: '{normalized_query}'")

                # Route to appropriate search mode
                if search_mode == SearchMode.DIARY:
                    logger.info(
                        "Using DIARY mode - prioritizing diary entries and date-based search"
                    )
                    return self._retrieve_diary_mode(
                        query, normalized_query, scope, top_k
                    )
                elif search_mode == SearchMode.GENERAL:
                    logger.info("Using GENERAL mode - prioritizing semantic similarity")
                    return self._retrieve_general_mode(normalized_query, scope, top_k)
                else:  # SearchMode.AUTO
                    logger.info(
                        "Using AUTO mode - automatically determining search strategy"
                    )
                    return self._retrieve_auto_mode(
                        query, normalized_query, scope, top_k
                    )

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            raise RuntimeError(f"Retrieval failed: {e}")

    def _expand_query_with_llm(self, query: str) -> str:
        """
        Query Expansion: use LLM to expand the query with related concrete terms.

        Asks the LLM to list specific words that would appear in a diary entry
        related to the query (e.g. "アルコール" → "ビール 日本酒 ワイン 飲んだ").
        Returns the original query + expanded keywords for embedding and keyword scan.

        Falls back to the original query if LLM is unavailable or fails.
        """
        if self.llm_backend is None:
            return query

        try:
            prompt = f"""以下の質問に関連する具体的な単語や表現を、日記に実際に書かれそうな言葉で5〜10個列挙してください。
単語のみをスペース区切りで出力してください。説明や文章は不要です。

質問: {query}

関連単語:"""
            result = self.llm_backend.generate(prompt)
            result = result.strip().strip('"').strip("'").strip()
            if result and len(result) > 2:
                logger.info(f"HyDE keyword expansion: '{query}' -> '{result[:100]}'")
                # Return original query + expanded keywords for embedding
                return f"{query} {result}"
        except Exception as e:
            logger.warning(f"HyDE generation failed, using original query: {e}")

        return query

    def _normalize_date_query(self, query: str) -> str:
        """
        Normalize date queries to match Obsidian diary format.

        Args:
            query: Original query string

        Returns:
            Query with normalized dates
        """
        import re
        from datetime import date

        original_query = query
        current_year = date.today().year

        logger.info(f"Starting date normalization in Retriever for query: '{query}'")

        # Handle patterns like "4/20", "2/2" -> "2026-04-20", "2026-02-02"
        # Remove word boundaries to work with Japanese text
        month_day_pattern = r"(\d{1,2})/(\d{1,2})"

        def replace_month_day(match):
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            return f"{current_year}-{month}-{day}"

        # Handle relative dates
        relative_date_patterns = [
            {
                "label": "一昨日",
                "offset": -2,
                "terms": [
                    "一昨日",
                    "一昨日の",
                    "昨々日",
                    "昨々日の",
                    "おととい",
                    "おとといの",
                ],
            },
            {
                "label": "昨日",
                "offset": -1,
                "terms": ["昨日", "昨日の", "きのう", "きのうの", "yesterday"],
            },
            {
                "label": "今日",
                "offset": 0,
                "terms": ["今日", "今日の", "きょう", "きょうの", "today"],
            },
            {
                "label": "明日",
                "offset": 1,
                "terms": ["明日", "明日の", "あした", "あしたの", "tomorrow"],
            },
        ]

        for relative_date_pattern in relative_date_patterns:
            matched_terms = [
                term
                for term in relative_date_pattern["terms"]
                if term.lower() in query.lower()
            ]
            if not matched_terms:
                continue

            target_date = date.fromordinal(
                date.today().toordinal() + relative_date_pattern["offset"]
            )
            replacement = target_date.strftime("%Y-%m-%d")
            pattern = "|".join(
                re.escape(term)
                for term in sorted(
                    relative_date_pattern["terms"], key=len, reverse=True
                )
            )
            query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
            logger.info(
                f"Normalized '{relative_date_pattern['label']}' to: {replacement}"
            )
            break

        # Replace month/day patterns with full date format
        matches = re.findall(month_day_pattern, query)
        logger.info(f"DEBUG: month_day_pattern = '{month_day_pattern}'")
        logger.info(f"DEBUG: query = '{query}'")
        logger.info(f"DEBUG: re.findall result = {matches}")
        logger.info(f"DEBUG: re.search result = {re.search(month_day_pattern, query)}")

        if matches:
            logger.info(f"Found month/day patterns: {matches}")
            query = re.sub(month_day_pattern, replace_month_day, query)
            logger.info(f"Normalized month/day patterns, result: '{query}'")

        if original_query != query:
            logger.info(
                f"Date normalization successful in Retriever: '{original_query}' -> '{query}'"
            )
        else:
            logger.info(
                f"No date normalization needed in Retriever for query: '{query}'"
            )

        return query

    def _is_date_query(self, query: str) -> bool:
        """
        Check if query looks like a date.

        Args:
            query: Query string

        Returns:
            True if query looks like a date
        """
        import re

        date_patterns = [
            r"\d{4}[-/]\d{2}[-/]\d{2}",
            r"\d{1,2}/\d{1,2}",
            r"一昨日|昨々日|おととい|昨日|きのう|今日|きょう|明日|あした",
            r"yesterday|today|tomorrow",
        ]
        return any(
            re.search(pattern, query, re.IGNORECASE) for pattern in date_patterns
        )

    def _extract_date_token(self, query: str) -> str:
        """
        Extract canonical date token from query for filename matching.

        Args:
            query: Query string that may contain a normalized date

        Returns:
            Extracted date token or original query if not found
        """
        import re

        iso_match = re.search(r"\d{4}-\d{2}-\d{2}", query)
        if iso_match:
            return iso_match.group(0)

        slash_match = re.search(r"\d{4}/\d{2}/\d{2}", query)
        if slash_match:
            return slash_match.group(0)

        return query

    def _search_by_filename(self, query: str, top_k: int) -> List[Chunk]:
        """
        Search chunks by filename matching.

        Args:
            query: Date query string
            top_k: Number of results to return

        Returns:
            List of matching chunks
        """
        try:
            # Get all chunks in the collection
            all_results = self.collection.get(include=["documents", "metadatas"])

            chunks = []
            query_lower = query.lower()

            for i, doc_id in enumerate(all_results["ids"]):
                metadata = (
                    all_results["metadatas"][i]
                    if i < len(all_results["metadatas"])
                    else {}
                )
                source_path = metadata.get("source_path", "")

                # Check if source path contains the date
                if query_lower in source_path.lower():
                    # Parse metadata safely
                    tags = []
                    frontmatter = {}
                    try:
                        tags = (
                            json.loads(metadata.get("tags", "[]"))
                            if metadata.get("tags")
                            else []
                        )
                        frontmatter = (
                            json.loads(metadata.get("frontmatter", "{}"))
                            if metadata.get("frontmatter")
                            else {}
                        )
                    except (json.JSONDecodeError, TypeError):
                        # Fallback to empty values if parsing fails
                        tags = []
                        frontmatter = {}

                    chunk = Chunk(
                        chunk_id=doc_id,
                        text=all_results["documents"][i]
                        if i < len(all_results["documents"])
                        else "",
                        source_path=source_path,
                        title=metadata.get("title", ""),
                        tags=tags,
                        frontmatter=frontmatter,
                        last_modified=metadata.get("last_modified"),
                        chunk_index=metadata.get("chunk_index", 0),
                    )
                    chunks.append(chunk)

                    if len(chunks) >= top_k:
                        break

            logger.info(f"Filename-based search found {len(chunks)} matching chunks")
            return chunks

        except Exception as e:
            logger.error(f"Filename-based search failed: {e}")
            return []

    def _build_scope_filter(self, scope: Optional[Scope]) -> Optional[Dict[str, Any]]:
        """
        Build ChromaDB filter conditions from scope.
        Only tag filters are applied at ChromaDB level.
        Folder filtering is done post-retrieval in Python (ChromaDB $contains
        does not reliably support substring matching on string fields).
        """
        if not scope:
            return None

        conditions = []

        # Tag scope filter only (folder is handled post-retrieval)
        if scope.tags:
            tag_conditions = []
            for tag in scope.tags:
                tag_condition = {"tags": {"$contains": f'"{tag}"'}}
                tag_conditions.append(tag_condition)

            if len(tag_conditions) == 1:
                conditions.append(tag_conditions[0])
            else:
                conditions.append({"$and": tag_conditions})

        if len(conditions) == 0:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}

    def _apply_folder_filter(self, chunks: List[Chunk], folder: str) -> List[Chunk]:
        """Filter chunks by folder prefix in Python."""
        # Normalize: ensure folder ends with /
        prefix = folder if folder.endswith("/") else folder + "/"
        filtered = [
            c
            for c in chunks
            if c.source_path.startswith(prefix) or c.source_path.startswith(folder)
        ]
        logger.info(
            f"Folder filter '{folder}': {len(chunks)} -> {len(filtered)} chunks"
        )
        return filtered

    def _is_diary_source_path(self, source_path: str) -> bool:
        return source_path.startswith("Diary/") or source_path.startswith("daily/")

    def _prioritize_diary_chunks(self, chunks: List[Chunk], top_k: int) -> List[Chunk]:
        diary_chunks = [
            chunk for chunk in chunks if self._is_diary_source_path(chunk.source_path)
        ]
        if diary_chunks:
            return diary_chunks[:top_k]
        return chunks[:top_k]

    def _is_temporal_query(self, query: str) -> bool:
        temporal_terms = [
            # 最初・最後系
            "初めて",
            "最初",
            "最後",
            "いつ",
            "登場",
            "現れ",
            "出現",
            # 最近系（「最近の〇〇は？」のようなクエリをカバー）
            "最近",
            "近頃",
            "最新",
            "直近",
            "lately",
            "recently",
            "recent",
            # 英語の最初・最後系
            "first",
            "earliest",
            "last",
            "latest",
            "when",
            "appeared",
            "appearance",
        ]
        lowered_query = query.lower()
        return any(term in query or term in lowered_query for term in temporal_terms)

    def _extract_main_keyword(self, query: str) -> str:
        import re

        keyword = query.strip()
        replacement_patterns = [
            # 具体的な複合パターンを先に処理
            r"が初めて登場したのはいつ[？?]?",
            r"が最初に登場したのはいつ[？?]?",
            r"が最後に登場したのはいつ[？?]?",
            r"が登場する日記",
            r"が登場した日記",
            r"が出てきた日記",
            r"はいつ登場した[？?]?",
            r"はいつ出現した[？?]?",
            # 「最後に〜を〜のはいつ」→「〜」だけ残す（最後に・を以降を除去）
            r"最後に",
            r"最初に",
            r"初めて",
            r"を.+のはいつ[？?]?",
            r"を飲んだのは",
            r"を食べたのは",
            r"を.+たのは",
            r"に.+のは",
            # 単語除去
            r"という名前",
            r"っていう名前",
            r"という言葉",
            r"とは",
            r"について",
            r"最初",
            r"最後",
            r"登場",
            r"出現",
            r"いつ",
            r"when did",
            r"when was",
            r"first appeared",
            r"first appearance",
            r"last appeared",
            r"latest appearance",
        ]

        for pattern in replacement_patterns:
            keyword = re.sub(pattern, " ", keyword, flags=re.IGNORECASE)

        keyword = re.sub(r"[「」『』\"'“”‘’?？。、,.!！:：()（）]", " ", keyword)
        keyword = re.sub(r"\s+", " ", keyword).strip()

        if not keyword:
            return query.strip()

        return keyword

    def _get_chunk_date(self, chunk: Chunk):
        from datetime import datetime

        frontmatter_date = chunk.frontmatter.get("date") if chunk.frontmatter else None
        if isinstance(frontmatter_date, str):
            try:
                return datetime.fromisoformat(frontmatter_date.replace("Z", "+00:00"))
            except ValueError:
                pass

        return chunk.last_modified or datetime.max

    def _sort_chunks_by_date(
        self, chunks: List[Chunk], ascending: bool = True
    ) -> List[Chunk]:
        return sorted(chunks, key=self._get_chunk_date, reverse=not ascending)

    def _retrieve_temporal_query(
        self,
        query: str,
        normalized_query: str,
        scope: Optional[Scope],
        top_k: int,
        prefer_diary: bool = False,
    ) -> List[Chunk]:
        keyword = self._extract_main_keyword(query)
        temporal_query = keyword if keyword and keyword != query else normalized_query
        ascending = any(
            term in query.lower() for term in ["初めて", "最初", "earliest", "first"]
        )

        logger.info(
            f"Temporal query detected: query='{query}', keyword='{keyword}', ascending={ascending}, prefer_diary={prefer_diary}"
        )

        # Log proposition collection state
        logger.info(
            f"Temporal query: proposition_collection is None: {self.proposition_collection is None}, "
            f"proposition_collection == collection: {self.proposition_collection == self.collection if self.proposition_collection is not None else 'N/A'}"
        )

        query_embedding = self.embedding_backend.embed([temporal_query])[0]
        where_filter = self._build_scope_filter(scope)

        chunks = []

        # Search proposition collection first if available
        if (
            self.proposition_collection is not None
            and self.proposition_collection != self.collection
        ):
            logger.info("Temporal query: Searching proposition collection first")
            try:
                prop_results = self.proposition_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(max(top_k * 10, top_k), 100),
                    where=where_filter,
                )
                prop_chunks = self._results_to_chunks(prop_results, is_proposition=True)
                logger.info(
                    f"Temporal query: Retrieved {len(prop_chunks)} proposition chunks"
                )
                # Log the source paths of retrieved proposition chunks
                for chunk in prop_chunks[:10]:  # Log first 10 chunks
                    logger.info(
                        f"Temporal query: Proposition chunk - source_path={chunk.source_path}, chunk_id={chunk.chunk_id}, is_proposition={chunk.is_proposition}"
                    )
                # Sort proposition chunks by date and take top_k
                prop_chunks_sorted = self._sort_chunks_by_date(
                    prop_chunks, ascending=ascending
                )
                chunks.extend(prop_chunks_sorted[:top_k])
                logger.info(
                    f"Temporal query: Selected {len(chunks)} proposition chunks (top {top_k})"
                )
            except Exception as err:
                logger.warning(f"Temporal query proposition search failed: {err}")

        # If we don't have enough chunks from propositions, search regular collection
        if len(chunks) < top_k:
            logger.info(
                "Temporal query: Searching regular collection for remaining chunks"
            )
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(max(top_k * 10, top_k), 100),
                where=where_filter,
            )
            regular_chunks = self._results_to_chunks(results)
            # Filter out chunks that are already in proposition chunks (by source_path)
            existing_sources = {c.source_path for c in chunks}
            regular_chunks_filtered = [
                c for c in regular_chunks if c.source_path not in existing_sources
            ]
            # Sort regular chunks by date
            regular_chunks_sorted = self._sort_chunks_by_date(
                regular_chunks_filtered, ascending=ascending
            )
            # Add remaining chunks
            remaining = top_k - len(chunks)
            chunks.extend(regular_chunks_sorted[:remaining])
            logger.info(
                f"Temporal query: Added {len(chunks) - (top_k - remaining)} regular chunks"
            )

        # Build scan keywords from HyDE-expanded query
        scan_keywords = set()
        if keyword and len(keyword) >= 2 and keyword != normalized_query:
            scan_keywords.add(keyword)
        # Extract individual words from the HyDE-expanded normalized_query
        if normalized_query != query:
            import re

            # Split on spaces and common Japanese punctuation
            words = re.split(r"[\s　、。,，!！?？「」『』（）()・\n]", normalized_query)
            for w in words:
                w = w.strip()
                if len(w) >= 2:
                    scan_keywords.add(w)

        if scan_keywords:
            try:
                all_results = self.collection.get(
                    include=["documents", "metadatas"],
                    where=where_filter if where_filter else None,
                )
                keyword_chunks = []
                existing_ids = {c.chunk_id for c in chunks}
                for i, doc in enumerate(all_results.get("documents", [])):
                    if not doc:
                        continue
                    if any(kw in doc for kw in scan_keywords):
                        meta = all_results["metadatas"][i]
                        chunk = self._results_to_chunks(
                            {
                                "ids": [[all_results["ids"][i]]],
                                "documents": [[doc]],
                                "metadatas": [[meta]],
                            }
                        )
                        if chunk and chunk[0].chunk_id not in existing_ids:
                            keyword_chunks.extend(chunk)
                            existing_ids.add(chunk[0].chunk_id)
                chunks.extend(keyword_chunks)
                logger.info(
                    f"Keyword scan for {scan_keywords} added {len(keyword_chunks)} chunks, total: {len(chunks)}"
                )
                # Log the source paths of keyword scan chunks
                for chunk in keyword_chunks[:10]:  # Log first 10 chunks
                    logger.info(
                        f"Keyword scan chunk - source_path={chunk.source_path}, chunk_id={chunk.chunk_id}, is_proposition={chunk.is_proposition}"
                    )
            except Exception as e:
                logger.warning(f"Keyword scan failed: {e}")
        if prefer_diary and not (scope and scope.folder):
            diary_chunks = [
                chunk
                for chunk in chunks
                if self._is_diary_source_path(chunk.source_path)
            ]
            if diary_chunks:
                chunks = diary_chunks

        sorted_chunks = self._sort_chunks_by_date(chunks, ascending=ascending)
        logger.info(
            f"Temporal query retrieval returned {len(sorted_chunks[:top_k])} chunks"
        )
        return sorted_chunks[:top_k]

    def _results_to_chunks(
        self, results: Dict[str, Any], is_proposition: bool = False
    ) -> List[Chunk]:
        """
        Convert ChromaDB results to Chunk objects.

        Args:
            results: ChromaDB query results
            is_proposition: Whether these chunks are from proposition collection

        Returns:
            List of Chunk objects
        """
        chunks = []

        if not results or not results["ids"] or not results["ids"][0]:
            return chunks

        # ChromaDB returns lists of lists, we want the first (and only) query result
        ids = results["ids"][0]
        documents = (
            results["documents"][0] if results["documents"] else [None] * len(ids)
        )
        metadatas = (
            results["metadatas"][0] if results["metadatas"] else [None] * len(ids)
        )

        for i, chunk_id in enumerate(ids):
            try:
                text = documents[i] if i < len(documents) else ""
                metadata = metadatas[i] if i < len(metadatas) else {}

                # Parse metadata
                source_path = metadata.get("source_path", "")
                title = metadata.get("title", "")
                tags = self._parse_tags(metadata.get("tags", "[]"))
                frontmatter = self._parse_json(metadata.get("frontmatter", "{}"))
                last_modified = self._parse_datetime(metadata.get("last_modified"))
                chunk_index = metadata.get("chunk_index", 0)

                chunk = Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    source_path=source_path,
                    title=title,
                    tags=tags,
                    frontmatter=frontmatter,
                    last_modified=last_modified,
                    chunk_index=chunk_index,
                    is_proposition=is_proposition,
                )

                chunks.append(chunk)

            except Exception as e:
                logger.warning(f"Failed to convert result {i} to chunk: {e}")
                continue

        return chunks

    def _parse_tags(self, tags_str: str) -> List[str]:
        """
        Parse tags from JSON string.

        Args:
            tags_str: JSON string representation of tags list

        Returns:
            List of tags
        """
        try:
            tags = json.loads(tags_str)
            if isinstance(tags, list):
                return [str(tag) for tag in tags]
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def _parse_json(self, json_str: str) -> Dict[str, Any]:
        """
        Parse JSON string to dictionary.

        Args:
            json_str: JSON string

        Returns:
            Parsed dictionary
        """
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _parse_datetime(self, datetime_str: str) -> Optional[Any]:
        """
        Parse ISO datetime string.

        Args:
            datetime_str: ISO format datetime string

        Returns:
            Parsed datetime or None
        """
        if not datetime_str:
            return None

        try:
            from datetime import datetime

            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            # Check if collections exist
            if self.collection is None or self.proposition_collection is None:
                logger.warning("One or both collections are None")
                return {
                    "collection_name": self.COLLECTION_NAME,
                    "total_chunks": 0,
                    "regular_chunks": 0,
                    "proposition_chunks": 0,
                    "embedding_dimension": self.embedding_backend.get_embedding_dimension(),
                    "embedding_model": self.embedding_backend.get_model_name(),
                    "vector_store_path": self.vector_store_path,
                }

            # Get counts from both collections
            regular_count = self.collection.count()
            proposition_count = self.proposition_collection.count()
            total_count = regular_count + proposition_count

            logger.info(
                f"Collection stats - Regular: {regular_count}, Propositions: {proposition_count}, Total: {total_count}"
            )

            return {
                "collection_name": self.COLLECTION_NAME,
                "total_chunks": total_count,
                "regular_chunks": regular_count,
                "proposition_chunks": proposition_count,
                "embedding_dimension": self.embedding_backend.get_embedding_dimension(),
                "embedding_model": self.embedding_backend.get_model_name(),
                "vector_store_path": self.vector_store_path,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}

    def is_collection_empty(self) -> bool:
        """
        Check if the collection is empty.

        Returns:
            True if collection is empty, False otherwise
        """
        try:
            # Check if collections exist
            if self.collection is None or self.proposition_collection is None:
                logger.warning("One or both collections are None, treating as empty")
                return True

            # Check both regular and proposition collections
            regular_count = self.collection.count()
            proposition_count = self.proposition_collection.count()
            total_count = regular_count + proposition_count

            logger.info(
                f"Collection counts - Regular: {regular_count}, Propositions: {proposition_count}, Total: {total_count}"
            )

            return total_count == 0
        except Exception as e:
            logger.error(f"Failed to check collection emptiness: {e}")
            return True

    def validate_scope(self, scope: Scope) -> List[str]:
        """
        Validate scope parameters.

        Args:
            scope: Scope to validate

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

    def test_query(self, query: str, scope: Optional[Scope] = None) -> Dict[str, Any]:
        """
        Test a query and return detailed results for debugging.

        Args:
            query: Test query string
            scope: Optional search scope

        Returns:
            Dictionary with test results
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_backend.embed([query])[0]

            # Build filter
            where_filter = self._build_scope_filter(scope)

            # Perform search
            results = self.collection.query(
                query_embeddings=[query_embedding], n_results=5, where=where_filter
            )

            # Get collection stats
            stats = self.get_collection_stats()

            return {
                "query": query,
                "scope": scope.dict() if scope else None,
                "filter": where_filter,
                "num_results": len(results["ids"][0])
                if results["ids"] and results["ids"][0]
                else 0,
                "collection_stats": stats,
                "sample_results": self._results_to_chunks(results)[
                    :3
                ],  # First 3 results
            }

        except Exception as e:
            return {
                "query": query,
                "scope": scope.dict() if scope else None,
                "error": str(e),
            }

    def _retrieve_diary_mode(
        self, query: str, normalized_query: str, scope: Optional[Scope], top_k: int
    ) -> List[Chunk]:
        """
        Retrieve chunks in diary mode - prioritize date-based search and diary entries.

        Args:
            query: Original query string
            normalized_query: Normalized query string
            scope: Optional search scope
            top_k: Number of results to return

        Returns:
            List of relevant chunks
        """
        logger.info(
            "Using DIARY mode - prioritizing diary entries and date-based search"
        )

        # First try date-based search if query contains date expressions
        is_date_query = self._is_date_query(normalized_query)
        if is_date_query:
            date_token = self._extract_date_token(normalized_query)
            logger.info(
                f"DIARY mode: Date query detected, extracted date token: '{date_token}'"
            )
            logger.info("DIARY mode: Trying filename-based search first")
            filename_chunks = self._search_by_filename(date_token, top_k)
            if filename_chunks:
                logger.info(
                    f"DIARY mode: Using {len(filename_chunks)} filename-matched chunks"
                )
                return filename_chunks
            else:
                logger.info(
                    "DIARY mode: No filename matches found, falling back to semantic search"
                )

        if self._is_temporal_query(query):
            logger.info(
                "DIARY mode: Temporal query detected, using metadata-enhanced retrieval"
            )
            return self._retrieve_temporal_query(
                query, normalized_query, scope, top_k, prefer_diary=True
            )

        # If no date query or no filename matches, do semantic search with diary preference
        logger.info("DIARY mode: Performing semantic search")
        query_embedding = self.embedding_backend.embed([normalized_query])[0]
        where_filter = self._build_scope_filter(scope)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(max(top_k * 5, top_k), 100),
            where=where_filter,
        )

        logger.info(
            f"DIARY mode: Search found {len(results.get('ids', [[]])[0])} documents before diary prioritization"
        )
        chunks = self._results_to_chunks(results)
        if scope and scope.folder:
            prioritized_chunks = chunks[:top_k]
        else:
            prioritized_chunks = self._prioritize_diary_chunks(chunks, top_k)
        logger.info(
            f"DIARY mode: Retrieved {len(prioritized_chunks)} chunks after diary prioritization"
        )
        return prioritized_chunks

    def _retrieve_general_mode(
        self, normalized_query: str, scope: Optional[Scope], top_k: int
    ) -> List[Chunk]:
        """
        Retrieve chunks in general mode - prioritize semantic search across all notes.

        Args:
            normalized_query: Normalized query string
            scope: Optional search scope
            top_k: Number of results to return

        Returns:
            List of relevant chunks
        """
        logger.info(
            "Using GENERAL mode - prioritizing semantic search across all notes"
        )

        if self._is_temporal_query(normalized_query):
            logger.info(
                "GENERAL mode: Temporal query detected, using metadata-enhanced retrieval"
            )
            return self._retrieve_temporal_query(
                normalized_query, normalized_query, scope, top_k
            )

        # Perform semantic search without diary preference
        query_embedding = self.embedding_backend.embed([normalized_query])[0]
        where_filter = self._build_scope_filter(scope)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 5, 100),
            where=where_filter,
        )

        logger.info(
            f"GENERAL mode: Search found {len(results.get('ids', [[]])[0])} documents"
        )
        chunks = self._results_to_chunks(results)
        logger.info(f"GENERAL mode: Retrieved {len(chunks)} chunks")
        return chunks

    def _retrieve_auto_mode(
        self,
        original_query: str,
        normalized_query: str,
        scope: Optional[Scope],
        top_k: int,
    ) -> List[Chunk]:
        """
        Retrieve chunks in auto mode - automatically determine best search strategy.

        Args:
            original_query: Original query string
            normalized_query: Normalized query string
            scope: Optional search scope
            top_k: Number of results to return

        Returns:
            List of relevant chunks
        """
        logger.info("Using AUTO mode - automatically determining search strategy")

        # Check if this looks like a diary-related query
        diary_keywords = [
            "diary",
            "diaries",
            "daily",
            "journal",
            "journals",
            "ate",
            "slept",
            "woke",
            "woke up",
            "went to bed",
            "breakfast",
            "lunch",
            "dinner",
            "meal",
            "food",
            "day",
            "today",
            "yesterday",
            "tomorrow",
            "last week",
            "last month",
            "this week",
            "this month",
            "last year",
            "this year",
            "日記",
            "昨日",
            "今日",
            "明日",
            "一昨日",
            "食べた",
            "朝食",
            "昼食",
            "夕食",
        ]

        query_lower = original_query.lower()
        is_diary_related = any(keyword in query_lower for keyword in diary_keywords)
        is_date_query = self._is_date_query(normalized_query)
        is_temporal = self._is_temporal_query(original_query)

        logger.info(
            f"AUTO mode: is_diary_related={is_diary_related}, is_date_query={is_date_query}, is_temporal={is_temporal}"
        )

        # Temporal queries (最後に、初めて、いつ etc.) → diary mode with temporal retrieval
        if is_temporal:
            logger.info(
                "AUTO mode: Detected temporal query, using diary strategy with temporal retrieval"
            )
            return self._retrieve_diary_mode(
                original_query, normalized_query, scope, top_k
            )

        # If it looks diary-related or has date expressions, use diary mode
        if is_diary_related or is_date_query:
            logger.info("AUTO mode: Detected diary-related query, using diary strategy")
            return self._retrieve_diary_mode(
                original_query, normalized_query, scope, top_k
            )
        else:
            logger.info("AUTO mode: Using general search strategy")
            return self._retrieve_general_mode(normalized_query, scope, top_k)

    def _is_fact_query(self, query: str) -> bool:
        """
        Determine if query is asking for a specific fact (when/what/who).

        Args:
            query: User query string

        Returns:
            True if this is a fact-based query suitable for proposition search
        """
        fact_patterns = [
            r"いつ.*した[？\?]",
            r"最後に.*した[？\?]",
            r"初めて.*した[？\?]",
            r"何を.*した[？\?]",
            r"どこで.*した[？\?]",
            r"誰と.*した[？\?]",
            r".*したのはいつ[？\?]",
            r".*したのを覚えて[？\?]",
            r".*した記録[？\?]",
        ]

        import re

        query_lower = query.lower()

        for pattern in fact_patterns:
            if re.search(pattern, query_lower):
                return True

        # Check for fact-seeking keywords
        fact_keywords = [
            "いつ",
            "最後に",
            "初めて",
            "何を",
            "どこで",
            "誰と",
            "したか",
            "したの",
            "記録",
            "覚えて",
            "思い出して",
        ]

        return any(keyword in query_lower for keyword in fact_keywords)

    def _is_context_query(self, query: str) -> bool:
        """
        Determine if query is asking for context or detailed information.

        Args:
            query: User query string

        Returns:
            True if this is a context-based query suitable for regular chunk search
        """
        context_patterns = [
            r".*について教えて",
            r".*の様子は",
            r".*の詳細は",
            r".*を説明して",
            r".*について話して",
            r".*のことを思い出して",
        ]

        import re

        query_lower = query.lower()

        for pattern in context_patterns:
            if re.search(pattern, query_lower):
                return True

        # Check for context-seeking keywords
        context_keywords = [
            "について",
            "教えて",
            "様子",
            "詳細",
            "説明",
            "話して",
            "思い出して",
            "まとめて",
            "要約して",
        ]

        return any(keyword in query_lower for keyword in context_keywords)

    def _retrieve_propositions(
        self, query: str, scope: Optional[Scope] = None, top_k: int = 5
    ) -> List[Chunk]:
        """
        Retrieve from proposition collection for fact-based queries.

        Args:
            query: User query string
            scope: Optional search scope filter
            top_k: Number of results to return

        Returns:
            List of proposition chunks
        """
        if self.proposition_collection is None:
            logger.warning(
                "Proposition collection not available, falling back to regular search"
            )
            return self._retrieve_general_mode(query, scope, top_k)

        logger.info(f"Retrieving propositions for query: {query}")

        try:
            # Generate query embedding
            query_embedding = self.embedding_backend.embed([query])[0]

            # Build where filter for scope
            where_filter = self._build_where_filter(scope) if scope else None

            # Search in proposition collection
            results = self.proposition_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            # Convert results to chunks
            chunks = self._results_to_chunks(results)

            # For propositions, we need to retrieve the original note content
            # This is handled by the Generator which will use original_note_path
            logger.info(f"Retrieved {len(chunks)} proposition chunks")

            return chunks

        except Exception as e:
            logger.error(f"Proposition retrieval failed: {e}")
            # Fallback to regular search
            return self._retrieve_general_mode(query, scope, top_k)

    def _retrieve_hybrid(
        self, query: str, scope: Optional[Scope] = None, top_k: int = 5
    ) -> List[Chunk]:
        """
        Hybrid retrieval combining propositions and regular chunks.

        Args:
            query: User query string
            scope: Optional search scope filter
            top_k: Number of results to return

        Returns:
            List of merged chunks from both collections
        """
        logger.info(f"Hybrid retrieval for query: {query}")

        # Retrieve from both collections
        proposition_chunks = []
        regular_chunks = []

        try:
            # Get proposition chunks (half of results)
            if self.proposition_collection is not None:
                proposition_chunks = self._retrieve_propositions(
                    query, scope, top_k // 2
                )
        except Exception as e:
            logger.warning(f"Proposition search failed: {e}")

        try:
            # Get regular chunks (remaining results)
            regular_chunks = self._retrieve_general_mode(
                query, scope, top_k - len(proposition_chunks)
            )
        except Exception as e:
            logger.warning(f"Regular search failed: {e}")

        # Merge and deduplicate results
        all_chunks = proposition_chunks + regular_chunks
        merged_chunks = self._merge_and_rank_chunks(all_chunks, query)

        # Limit to top_k results
        merged_chunks = merged_chunks[:top_k]

        logger.info(
            f"Hybrid retrieval: {len(proposition_chunks)} propositions + {len(regular_chunks)} regular = {len(merged_chunks)} total"
        )

        return merged_chunks

    def _merge_and_rank_chunks(self, chunks: List[Chunk], query: str) -> List[Chunk]:
        """
        Merge and rank chunks from different collections.

        Args:
            chunks: List of chunks from both collections
            query: Original query for relevance scoring

        Returns:
            Ranked list of chunks
        """
        if not chunks:
            return chunks

        # Group chunks by original note path
        note_groups = {}
        for chunk in chunks:
            note_path = chunk.source_path
            if note_path not in note_groups:
                note_groups[note_path] = []
            note_groups[note_path].append(chunk)

        # Rank groups: prioritize notes with both proposition and regular chunks
        ranked_chunks = []
        for note_path, note_chunks in note_groups.items():
            has_proposition = any(chunk.is_proposition for chunk in note_chunks)
            has_regular = any(not chunk.is_proposition for chunk in note_chunks)

            # Prioritize notes that have both types
            if has_proposition and has_regular:
                # Add proposition chunks first, then regular chunks
                proposition_chunks = [c for c in note_chunks if c.is_proposition]
                regular_chunks = [c for c in note_chunks if not c.is_proposition]
                ranked_chunks.extend(proposition_chunks + regular_chunks)
            elif has_proposition:
                ranked_chunks.extend(note_chunks)
            else:
                ranked_chunks.extend(note_chunks)

        return ranked_chunks
