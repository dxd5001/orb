"""
Retriever implementation for similarity search and chunk retrieval.

This module handles the retrieval of relevant chunks from the vector database
based on user queries, with support for scope filtering.
"""

import logging
import json
from typing import List, Optional, Dict, Any

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

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
    
    def __init__(self, embedding_backend: EmbeddingBackend, vector_store_path: str):
        """
        Initialize the retriever.
        
        Args:
            embedding_backend: Backend for generating embeddings
            vector_store_path: Path for ChromaDB storage
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb library is not available. "
                "Install it with: pip install chromadb"
            )
        
        self.embedding_backend = embedding_backend
        self.vector_store_path = vector_store_path
        self._client = None
        self._collection = None
    
    @property
    def client(self):
        """Lazy loading of ChromaDB client."""
        if self._client is None:
            logger.info(f"Initializing ChromaDB client with path: {self.vector_store_path}")
            self._client = chromadb.PersistentClient(path=self.vector_store_path)
        return self._client
    
    @property
    def collection(self):
        """Lazy loading of ChromaDB collection."""
        if self._collection is None:
            self._collection = self._get_collection()
        return self._collection
    
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
            raise RuntimeError(f"Collection {self.COLLECTION_NAME} not found. Please run indexing first.")
    
    def retrieve(self, query: str, scope: Optional[Scope] = None, top_k: int = 5, search_mode: SearchMode = SearchMode.AUTO) -> List[Chunk]:
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
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        logger.info(f"RETRIEVER CALLED with query: '{query}', search_mode: {search_mode}")
        
        # Normalize date queries to match Obsidian diary format
        normalized_query = self._normalize_date_query(query)
        
        logger.info(f"AFTER NORMALIZATION: original='{query}', normalized='{normalized_query}'")
        
        if query != normalized_query:
            logger.info(f"Date normalization in Retriever: '{query}' -> '{normalized_query}'")
        
        logger.info(f"Retrieving chunks for query: '{query[:50]}...' (normalized: '{normalized_query[:50]}...') with scope: {scope}, search_mode: {search_mode}")
        
        try:
            # Handle different search modes
            if search_mode == SearchMode.DIARY:
                return self._retrieve_diary_mode(query, normalized_query, scope, top_k)
            elif search_mode == SearchMode.GENERAL:
                return self._retrieve_general_mode(normalized_query, scope, top_k)
            else:  # AUTO mode
                return self._retrieve_auto_mode(query, normalized_query, scope, top_k)
            
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            raise RuntimeError(f"Retrieval failed: {e}")
    
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
        month_day_pattern = r'(\d{1,2})/(\d{1,2})'
        
        def replace_month_day(match):
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            return f"{current_year}-{month}-{day}"
        
        # Handle relative dates
        relative_date_patterns = [
            {
                "label": "一昨日",
                "offset": -2,
                "terms": ["一昨日", "一昨日の", "昨々日", "昨々日の", "おととい", "おとといの"]
            },
            {
                "label": "昨日",
                "offset": -1,
                "terms": ["昨日", "昨日の", "きのう", "きのうの", "yesterday"]
            },
            {
                "label": "今日",
                "offset": 0,
                "terms": ["今日", "今日の", "きょう", "きょうの", "today"]
            },
            {
                "label": "明日",
                "offset": 1,
                "terms": ["明日", "明日の", "あした", "あしたの", "tomorrow"]
            }
        ]

        for relative_date_pattern in relative_date_patterns:
            matched_terms = [term for term in relative_date_pattern["terms"] if term.lower() in query.lower()]
            if not matched_terms:
                continue

            target_date = date.fromordinal(date.today().toordinal() + relative_date_pattern["offset"])
            replacement = target_date.strftime('%Y-%m-%d')
            pattern = '|'.join(re.escape(term) for term in sorted(relative_date_pattern["terms"], key=len, reverse=True))
            query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
            logger.info(f"Normalized '{relative_date_pattern['label']}' to: {replacement}")
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
            logger.info(f"Date normalization successful in Retriever: '{original_query}' -> '{query}'")
        else:
            logger.info(f"No date normalization needed in Retriever for query: '{query}'")
        
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
            r'\d{4}[-/]\d{2}[-/]\d{2}',
            r'\d{1,2}/\d{1,2}',
            r'一昨日|昨々日|おととい|昨日|きのう|今日|きょう|明日|あした',
            r'yesterday|today|tomorrow'
        ]
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in date_patterns)

    def _extract_date_token(self, query: str) -> str:
        """
        Extract canonical date token from query for filename matching.

        Args:
            query: Query string that may contain a normalized date

        Returns:
            Extracted date token or original query if not found
        """
        import re

        iso_match = re.search(r'\d{4}-\d{2}-\d{2}', query)
        if iso_match:
            return iso_match.group(0)

        slash_match = re.search(r'\d{4}/\d{2}/\d{2}', query)
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
            all_results = self.collection.get(include=['documents', 'metadatas'])
            
            chunks = []
            query_lower = query.lower()
            
            for i, doc_id in enumerate(all_results['ids']):
                metadata = all_results['metadatas'][i] if i < len(all_results['metadatas']) else {}
                source_path = metadata.get('source_path', '')
                
                # Check if source path contains the date
                if query_lower in source_path.lower():
                    # Parse metadata safely
                    tags = []
                    frontmatter = {}
                    try:
                        tags = json.loads(metadata.get('tags', '[]')) if metadata.get('tags') else []
                        frontmatter = json.loads(metadata.get('frontmatter', '{}')) if metadata.get('frontmatter') else {}
                    except (json.JSONDecodeError, TypeError):
                        # Fallback to empty values if parsing fails
                        tags = []
                        frontmatter = {}
                    
                    chunk = Chunk(
                        chunk_id=doc_id,
                        text=all_results['documents'][i] if i < len(all_results['documents']) else "",
                        source_path=source_path,
                        title=metadata.get('title', ''),
                        tags=tags,
                        frontmatter=frontmatter,
                        last_modified=metadata.get('last_modified'),
                        chunk_index=metadata.get('chunk_index', 0)
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
        
        Args:
            scope: Search scope with folder and/or tag filters
            
        Returns:
            ChromaDB where filter dictionary or None
        """
        if not scope:
            return None
        
        conditions = []
        
        # Folder scope filter
        if scope.folder:
            folder_condition = {
                "source_path": {
                    "$contains": scope.folder
                }
            }
            conditions.append(folder_condition)
        
        # Tag scope filter
        if scope.tags:
            # For tag filtering, we need to check if the serialized tags contain all required tags
            tag_conditions = []
            for tag in scope.tags:
                tag_condition = {
                    "tags": {
                        "$contains": f'"{tag}"'  # Tag should be in JSON serialized format
                    }
                }
                tag_conditions.append(tag_condition)
            
            if len(tag_conditions) == 1:
                conditions.append(tag_conditions[0])
            else:
                # Multiple tags - use $and operator
                conditions.append({"$and": tag_conditions})
        
        # Combine conditions with $and if multiple
        if len(conditions) == 0:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}
    
    def _is_diary_source_path(self, source_path: str) -> bool:
        return source_path.startswith("Diary/") or source_path.startswith("daily/")
    
    def _prioritize_diary_chunks(self, chunks: List[Chunk], top_k: int) -> List[Chunk]:
        diary_chunks = [chunk for chunk in chunks if self._is_diary_source_path(chunk.source_path)]
        if diary_chunks:
            return diary_chunks[:top_k]
        return chunks[:top_k]

    def _is_temporal_query(self, query: str) -> bool:
        temporal_terms = [
            "初めて", "最初", "最後", "いつ", "登場", "現れ", "出現",
            "first", "earliest", "last", "latest", "when", "appeared", "appearance"
        ]
        lowered_query = query.lower()
        return any(term in query or term in lowered_query for term in temporal_terms)

    def _extract_main_keyword(self, query: str) -> str:
        import re

        keyword = query.strip()
        replacement_patterns = [
            r"という名前",
            r"っていう名前",
            r"という言葉",
            r"とは",
            r"について",
            r"が初めて登場したのはいつ[？?]?",
            r"が最初に登場したのはいつ[？?]?",
            r"が最後に登場したのはいつ[？?]?",
            r"が登場する日記",
            r"が登場した日記",
            r"が出てきた日記",
            r"はいつ登場した[？?]?",
            r"はいつ出現した[？?]?",
            r"初めて",
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

    def _sort_chunks_by_date(self, chunks: List[Chunk], ascending: bool = True) -> List[Chunk]:
        return sorted(chunks, key=self._get_chunk_date, reverse=not ascending)

    def _retrieve_temporal_query(
        self,
        query: str,
        normalized_query: str,
        scope: Optional[Scope],
        top_k: int,
        prefer_diary: bool = False
    ) -> List[Chunk]:
        keyword = self._extract_main_keyword(query)
        temporal_query = keyword if keyword and keyword != query else normalized_query
        ascending = any(term in query.lower() for term in ["初めて", "最初", "earliest", "first"])

        logger.info(
            f"Temporal query detected: query='{query}', keyword='{keyword}', ascending={ascending}, prefer_diary={prefer_diary}"
        )

        query_embedding = self.embedding_backend.embed([temporal_query])[0]
        where_filter = self._build_scope_filter(scope)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(max(top_k * 10, top_k), 100),
            where=where_filter
        )

        chunks = self._results_to_chunks(results)
        if prefer_diary and not (scope and scope.folder):
            diary_chunks = [chunk for chunk in chunks if self._is_diary_source_path(chunk.source_path)]
            if diary_chunks:
                chunks = diary_chunks

        sorted_chunks = self._sort_chunks_by_date(chunks, ascending=ascending)
        logger.info(f"Temporal query retrieval returned {len(sorted_chunks[:top_k])} chunks")
        return sorted_chunks[:top_k]
    
    def _results_to_chunks(self, results: Dict[str, Any]) -> List[Chunk]:
        """
        Convert ChromaDB results to Chunk objects.
        
        Args:
            results: ChromaDB query results
            
        Returns:
            List of Chunk objects
        """
        chunks = []
        
        if not results or not results['ids'] or not results['ids'][0]:
            return chunks
        
        # ChromaDB returns lists of lists, we want the first (and only) query result
        ids = results['ids'][0]
        documents = results['documents'][0] if results['documents'] else [None] * len(ids)
        metadatas = results['metadatas'][0] if results['metadatas'] else [None] * len(ids)
        
        for i, chunk_id in enumerate(ids):
            try:
                text = documents[i] if i < len(documents) else ""
                metadata = metadatas[i] if i < len(metadatas) else {}
                
                # Parse metadata
                source_path = metadata.get('source_path', '')
                title = metadata.get('title', '')
                tags = self._parse_tags(metadata.get('tags', '[]'))
                frontmatter = self._parse_json(metadata.get('frontmatter', '{}'))
                last_modified = self._parse_datetime(metadata.get('last_modified'))
                chunk_index = metadata.get('chunk_index', 0)
                
                chunk = Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    source_path=source_path,
                    title=title,
                    tags=tags,
                    frontmatter=frontmatter,
                    last_modified=last_modified,
                    chunk_index=chunk_index
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
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the collection.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            count = self.collection.count()
            return {
                'collection_name': self.COLLECTION_NAME,
                'total_chunks': count,
                'embedding_dimension': self.embedding_backend.get_embedding_dimension(),
                'embedding_model': self.embedding_backend.get_model_name(),
                'vector_store_path': self.vector_store_path
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
            count = self.collection.count()
            return count == 0
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
                query_embeddings=[query_embedding],
                n_results=5,
                where=where_filter
            )
            
            # Get collection stats
            stats = self.get_collection_stats()
            
            return {
                'query': query,
                'scope': scope.dict() if scope else None,
                'filter': where_filter,
                'num_results': len(results['ids'][0]) if results['ids'] and results['ids'][0] else 0,
                'collection_stats': stats,
                'sample_results': self._results_to_chunks(results)[:3]  # First 3 results
            }
            
        except Exception as e:
            return {
                'query': query,
                'scope': scope.dict() if scope else None,
                'error': str(e)
            }
    
    def _retrieve_diary_mode(self, query: str, normalized_query: str, scope: Optional[Scope], top_k: int) -> List[Chunk]:
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
        logger.info("Using DIARY mode - prioritizing diary entries and date-based search")
        
        # First try date-based search if query contains date expressions
        is_date_query = self._is_date_query(normalized_query)
        if is_date_query:
            date_token = self._extract_date_token(normalized_query)
            logger.info(f"DIARY mode: Date query detected, extracted date token: '{date_token}'")
            logger.info("DIARY mode: Trying filename-based search first")
            filename_chunks = self._search_by_filename(date_token, top_k)
            if filename_chunks:
                logger.info(f"DIARY mode: Using {len(filename_chunks)} filename-matched chunks")
                return filename_chunks
            else:
                logger.info("DIARY mode: No filename matches found, falling back to semantic search")

        if self._is_temporal_query(query):
            logger.info("DIARY mode: Temporal query detected, using metadata-enhanced retrieval")
            return self._retrieve_temporal_query(query, normalized_query, scope, top_k, prefer_diary=True)
        
         # If no date query or no filename matches, do semantic search with diary preference
        logger.info("DIARY mode: Performing semantic search")
        query_embedding = self.embedding_backend.embed([normalized_query])[0]
        where_filter = self._build_scope_filter(scope)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(max(top_k * 5, top_k), 100),
            where=where_filter
        )
        
        logger.info(f"DIARY mode: Search found {len(results.get('ids', [[]])[0])} documents before diary prioritization")
        chunks = self._results_to_chunks(results)
        if scope and scope.folder:
            prioritized_chunks = chunks[:top_k]
        else:
            prioritized_chunks = self._prioritize_diary_chunks(chunks, top_k)
        logger.info(f"DIARY mode: Retrieved {len(prioritized_chunks)} chunks after diary prioritization")
        return prioritized_chunks
    
    def _retrieve_general_mode(self, normalized_query: str, scope: Optional[Scope], top_k: int) -> List[Chunk]:
        """
        Retrieve chunks in general mode - prioritize semantic search across all notes.
        
        Args:
            normalized_query: Normalized query string
            scope: Optional search scope
            top_k: Number of results to return
            
        Returns:
            List of relevant chunks
        """
        logger.info("Using GENERAL mode - prioritizing semantic search across all notes")

        if self._is_temporal_query(normalized_query):
            logger.info("GENERAL mode: Temporal query detected, using metadata-enhanced retrieval")
            return self._retrieve_temporal_query(normalized_query, normalized_query, scope, top_k)
        
        # Perform semantic search without diary preference
        query_embedding = self.embedding_backend.embed([normalized_query])[0]
        where_filter = self._build_scope_filter(scope)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, 100),
            where=where_filter
        )
        
        logger.info(f"GENERAL mode: Search found {len(results.get('ids', [[]])[0])} documents")
        chunks = self._results_to_chunks(results)
        logger.info(f"GENERAL mode: Retrieved {len(chunks)} chunks")
        return chunks
    
    def _retrieve_auto_mode(self, original_query: str, normalized_query: str, scope: Optional[Scope], top_k: int) -> List[Chunk]:
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
            'diary', 'diaries', 'daily', 'journal', 'journals',
            'ate', 'slept', 'woke', 'woke up', 'went to bed',
            'breakfast', 'lunch', 'dinner', 'meal', 'food',
            'day', 'today', 'yesterday', 'tomorrow', 'last week', 'last month',
            'this week', 'this month', 'last year', 'this year',
            '日記', '昨日', '今日', '明日', '一昨日', '食べた', '朝食', '昼食', '夕食'
        ]
        
        query_lower = original_query.lower()
        is_diary_related = any(keyword in query_lower for keyword in diary_keywords)
        is_date_query = self._is_date_query(normalized_query)
        
        logger.info(f"AUTO mode: is_diary_related={is_diary_related}, is_date_query={is_date_query}")
        
        # If it looks diary-related or has date expressions, use diary mode
        if is_diary_related or is_date_query:
            logger.info("AUTO mode: Detected diary-related query, using diary strategy")
            return self._retrieve_diary_mode(original_query, normalized_query, scope, top_k)
        else:
            logger.info("AUTO mode: Using general search strategy")
            return self._retrieve_general_mode(normalized_query, scope, top_k)
