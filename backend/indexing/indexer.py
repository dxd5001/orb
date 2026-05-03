"""
Indexer implementation for chunking and vector storage.

This module handles the indexing process including text chunking,
embedding generation, and storage in ChromaDB vector database.
"""

import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import uuid
import json
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

from models import NoteDocument, Chunk, IndexResult
from embedding.base import EmbeddingBackend
from models import create_chunk_id

if TYPE_CHECKING:
    from llm.base import LLMBackend

logger = logging.getLogger(__name__)


class Indexer:
    """
    Indexer for processing notes into chunks and storing them in vector database.

    This class handles the complete indexing pipeline:
    1. Chunking documents into smaller pieces
    2. Generating embeddings for chunks
    3. Storing chunks with metadata in ChromaDB
    4. Managing collection lifecycle and updates
    """

    # Chunking parameters as specified in requirements
    CHUNK_SIZE = 1000  # characters
    CHUNK_OVERLAP = 200  # characters

    # ChromaDB collection name
    COLLECTION_NAME = "obsidian_vault"
    PROPOSITION_COLLECTION_NAME = "obsidian_vault_propositions"

    def __init__(
        self,
        embedding_backend: EmbeddingBackend,
        vector_store_path: str,
        llm_backend: Optional["LLMBackend"] = None,
    ):
        """
        Initialize the indexer.

        Args:
            embedding_backend: Backend for generating embeddings
            vector_store_path: Path for ChromaDB storage
            llm_backend: Optional LLM backend for proposition generation
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
            self._collection = self._get_or_create_collection()
        return self._collection

    @property
    def proposition_collection(self):
        """Lazy loading of proposition collection."""
        if self._proposition_collection is None:
            self._proposition_collection = self._get_or_create_proposition_collection()
        return self._proposition_collection

    def _get_or_create_collection(self):
        """Get existing collection or create new one."""
        try:
            # Try to get existing collection
            collection = self.client.get_collection(name=self.COLLECTION_NAME)
            logger.info(f"Using existing collection: {self.COLLECTION_NAME}")
            return collection
        except Exception:
            # Create new collection if it doesn't exist
            logger.info(f"Creating new collection: {self.COLLECTION_NAME}")
            collection = self.client.create_collection(name=self.COLLECTION_NAME)
            return collection

    def _get_or_create_proposition_collection(self):
        """Get existing proposition collection or create new one."""
        try:
            # Try to get existing collection
            collection = self.client.get_collection(
                name=self.PROPOSITION_COLLECTION_NAME
            )
            logger.info(
                f"Using existing proposition collection: {self.PROPOSITION_COLLECTION_NAME}"
            )
            return collection
        except Exception:
            # Create new collection if it doesn't exist
            logger.info(
                f"Creating new proposition collection: {self.PROPOSITION_COLLECTION_NAME}"
            )
            collection = self.client.create_collection(
                name=self.PROPOSITION_COLLECTION_NAME
            )
            return collection

    def _generate_propositions(self, note_text: str) -> List[str]:
        """
        Generate propositions from note text using LLM.

        Args:
            note_text: Original note text

        Returns:
            List of propositions (one fact per proposition)
        """
        if self.llm_backend is None:
            logger.info("No LLM backend available, skipping proposition generation")
            return []

        try:
            prompt = f"""以下の日記テキストから、ユーザーが後から「いつ〇〇したか」と問いかけそうな
短い命題を箇条書きで列挙してください。
1命題1事実、体言止めまたは短文で記述してください。

テキスト:
{note_text}

命題リスト:"""

            result = self.llm_backend.generate(prompt)
            result = result.strip()

            # Parse propositions from the result
            propositions = []
            for line in result.split("\n"):
                line = line.strip()
                # Remove common list markers and clean up
                if line and (
                    line.startswith("-")
                    or line.startswith("•")
                    or line.startswith("*")
                    or (line[0].isdigit() and ("." in line or ")" in line))
                ):
                    # Remove list markers
                    clean_line = line
                    clean_line = clean_line.lstrip("-•*")
                    clean_line = clean_line.lstrip("0123456789.")
                    clean_line = clean_line.lstrip("0123456789)")
                    clean_line = clean_line.strip()

                    if clean_line and len(clean_line) >= 3:  # Minimum length filter
                        propositions.append(clean_line)
                elif line and len(line) >= 3 and not line.startswith("命題リスト"):
                    # Handle non-bulleted lines that might be propositions
                    propositions.append(line)

            logger.info(f"Generated {len(propositions)} propositions from note text")
            return propositions[:10]  # Limit to 10 propositions max

        except Exception as e:
            logger.warning(f"Failed to generate propositions: {e}")
            return []

    def _create_proposition_chunks(
        self, note: NoteDocument, propositions: List[str]
    ) -> List[Chunk]:
        """
        Create proposition chunks from a note and its propositions.

        Args:
            note: Original note document
            propositions: List of proposition strings

        Returns:
            List of proposition chunks
        """
        proposition_chunks = []
        for i, proposition in enumerate(propositions):
            chunk_id = create_chunk_id(note.file_path, f"prop_{i}")
            chunk = Chunk(
                chunk_id=chunk_id,
                text=proposition,
                source_path=note.file_path,
                title=note.title,
                tags=note.tags,
                frontmatter=note.frontmatter,
                last_modified=note.last_modified,
                chunk_index=f"prop_{i}",
                is_proposition=True,
            )
            proposition_chunks.append(chunk)

        return proposition_chunks

    def _clear_proposition_collection(self):
        """Clear existing proposition collection for idempotent indexing."""
        try:
            self.client.delete_collection(name=self.PROPOSITION_COLLECTION_NAME)
            self._proposition_collection = None  # Force recreation
            logger.info("Cleared existing proposition collection")
        except Exception as e:
            logger.warning(f"Failed to clear proposition collection: {e}")

    def _store_proposition_chunks(
        self, chunks: List[Chunk], embeddings: List[List[float]]
    ):
        """
        Store proposition chunks with embeddings in the proposition collection.

        Args:
            chunks: List of proposition chunks to store
            embeddings: List of embedding vectors
        """
        if not chunks or not embeddings:
            logger.warning("No chunks or embeddings to store")
            return

        if len(chunks) != len(embeddings):
            error_msg = f"Number of chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must match"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Prepare data for ChromaDB
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = []

        for chunk in chunks:
            metadata = {
                "source_path": chunk.source_path,
                "title": chunk.title,
                "tags": json.dumps(chunk.tags) if chunk.tags else "[]",
                "frontmatter": json.dumps(chunk.frontmatter, default=str)
                if chunk.frontmatter
                else "{}",
                "last_modified": chunk.last_modified.isoformat()
                if chunk.last_modified
                else "",
                "chunk_index": chunk.chunk_index,
                "is_proposition": True,
                "original_note_path": chunk.source_path,
            }
            metadatas.append(metadata)

        # Store in proposition collection
        try:
            self.proposition_collection.add(
                ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
            )
            logger.info(f"Stored {len(chunks)} proposition chunks in vector database")
        except Exception as e:
            logger.error(f"Failed to store proposition chunks: {e}")
            raise

    def index(self, ingest_result: IngestResult) -> IndexResult:
        """
        Index ingested notes into vector store.

        Args:
            ingest_result: Result from the ingestion process

        Returns:
            IndexResult with indexing statistics

        Raises:
            ValueError: If no notes to index
            RuntimeError: If indexing fails
        """
        if not ingest_result.notes:
            raise ValueError("No notes to index")

        logger.info(f"Starting indexing of {len(ingest_result.notes)} notes")

        try:
            # Clear existing collections for idempotent indexing
            self._clear_collection()
            self._clear_proposition_collection()

            # Process all notes into chunks and propositions
            all_chunks = []
            all_propositions = []

            for note in ingest_result.notes:
                # Generate regular chunks
                chunks = self._chunk_note(note)
                all_chunks.extend(chunks)

                # Generate propositions if LLM backend is available
                if self.llm_backend:
                    propositions = self._generate_propositions(note.body)
                    if propositions:
                        proposition_chunks = self._create_proposition_chunks(
                            note, propositions
                        )
                        all_propositions.extend(proposition_chunks)

            logger.info(
                f"Created {len(all_chunks)} chunks and {len(all_propositions)} propositions from {len(ingest_result.notes)} notes"
            )

            # Process regular chunks
            valid_chunks = [
                chunk for chunk in all_chunks if chunk.text and chunk.text.strip()
            ]
            logger.info(f"Filtered {len(all_chunks) - len(valid_chunks)} empty chunks")

            # Process proposition chunks
            valid_propositions = [
                chunk for chunk in all_propositions if chunk.text and chunk.text.strip()
            ]
            logger.info(
                f"Filtered {len(all_propositions) - len(valid_propositions)} empty propositions"
            )

            # Generate embeddings for regular chunks
            if valid_chunks:
                chunk_texts = [chunk.text for chunk in valid_chunks]
                chunk_embeddings = self.embedding_backend.embed(chunk_texts)
                self._store_chunks(valid_chunks, chunk_embeddings)

            # Generate embeddings for proposition chunks
            if valid_propositions:
                proposition_texts = [chunk.text for chunk in valid_propositions]
                proposition_embeddings = self.embedding_backend.embed(proposition_texts)
                self._store_proposition_chunks(
                    valid_propositions, proposition_embeddings
                )

            result = IndexResult(
                note_count=len(ingest_result.notes),
                chunk_count=len(valid_chunks),
                proposition_count=len(valid_propositions),
            )

            logger.info(
                f"Indexing completed: {result.note_count} notes, {result.chunk_count} chunks"
            )
            return result

        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            raise RuntimeError(f"Indexing failed: {e}")

    def _clear_collection(self):
        """Clear existing collection for idempotent indexing."""
        try:
            self.client.delete_collection(name=self.COLLECTION_NAME)
            self._collection = None  # Force recreation
            logger.info("Cleared existing collection")
        except Exception as e:
            logger.warning(f"Failed to clear collection: {e}")

    def _chunk_note(self, note: NoteDocument) -> List[Chunk]:
        """
        Split a note document into chunks.

        Args:
            note: Note document to chunk

        Returns:
            List of chunks
        """
        chunks = []
        text = note.body

        # If text is shorter than chunk size, create single chunk
        if len(text) <= self.CHUNK_SIZE:
            chunk = Chunk(
                chunk_id=create_chunk_id(note.file_path, 0),
                text=text,
                source_path=note.file_path,
                title=note.title,
                tags=note.tags,
                frontmatter=note.frontmatter,
                last_modified=note.last_modified,
                chunk_index=0,
            )
            chunks.append(chunk)
            return chunks

        # Split text into chunks with overlap
        start = 0
        chunk_index = 0

        while start < len(text):
            # Calculate chunk end position
            end = start + self.CHUNK_SIZE

            # If this is not the last chunk, try to break at word boundary
            if end < len(text):
                # Look for whitespace near the chunk boundary
                boundary = end
                for i in range(
                    min(100, self.CHUNK_SIZE // 10)
                ):  # Look back up to 100 chars
                    if text[end - i].isspace():
                        boundary = end - i
                        break

                end = boundary

            # Extract chunk text
            chunk_text = text[start:end].strip()

            if chunk_text:  # Only add non-empty chunks
                chunk = Chunk(
                    chunk_id=create_chunk_id(note.file_path, chunk_index),
                    text=chunk_text,
                    source_path=note.file_path,
                    title=note.title,
                    tags=note.tags,
                    frontmatter=note.frontmatter,
                    last_modified=note.last_modified,
                    chunk_index=chunk_index,
                )
                chunks.append(chunk)
                chunk_index += 1

            # Move start position with overlap
            start = max(start + 1, end - self.CHUNK_OVERLAP)

        return chunks

    def _store_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]):
        """
        Store chunks and their embeddings in ChromaDB.

        Args:
            chunks: List of chunks to store
            embeddings: List of embedding vectors
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks and embeddings must match")

        # Prepare data for ChromaDB
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [self._chunk_to_metadata(chunk) for chunk in chunks]

        # Add to collection
        self.collection.add(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
        )

        logger.info(f"Stored {len(chunks)} chunks in vector database")

    def _chunk_to_metadata(self, chunk: Chunk) -> Dict[str, Any]:
        """
        Convert chunk to ChromaDB metadata format.

        Args:
            chunk: Chunk to convert

        Returns:
            Metadata dictionary
        """

        def safe_json_serialize(obj):
            """Safely serialize objects that may contain dates"""
            try:
                return json.dumps(obj, default=str)
            except (TypeError, ValueError):
                return json.dumps({})

        metadata = {
            "source_path": chunk.source_path,
            "title": chunk.title,
            "tags": json.dumps(chunk.tags),  # Serialize tags as JSON string
            "frontmatter": safe_json_serialize(
                chunk.frontmatter
            ),  # Serialize frontmatter safely
            "last_modified": chunk.last_modified.isoformat()
            if chunk.last_modified
            else None,
            "chunk_index": chunk.chunk_index,
        }

        return metadata

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            count = self.collection.count()
            return {
                "collection_name": self.COLLECTION_NAME,
                "total_chunks": count,
                "embedding_dimension": self.embedding_backend.get_embedding_dimension(),
                "embedding_model": self.embedding_backend.get_model_name(),
                "vector_store_path": self.vector_store_path,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}

    def validate_indexing(self) -> bool:
        """
        Validate that indexing was successful.

        Returns:
            True if indexing is valid, False otherwise
        """
        try:
            stats = self.get_collection_stats()
            return stats.get("total_chunks", 0) > 0
        except Exception as e:
            logger.error(f"Indexing validation failed: {e}")
            return False

    def delete_collection(self):
        """Delete the entire collection."""
        try:
            self.client.delete_collection(name=self.COLLECTION_NAME)
            self._collection = None
            logger.info(f"Deleted collection: {self.COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")

    def get_sample_chunks(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get sample chunks from the collection for debugging.

        Args:
            limit: Maximum number of chunks to retrieve

        Returns:
            List of sample chunk data
        """
        try:
            results = self.collection.get(limit=limit)

            sample_chunks = []
            for i in range(len(results["ids"])):
                chunk_data = {
                    "id": results["ids"][i],
                    "text": results["documents"][i]
                    if i < len(results["documents"])
                    else None,
                    "metadata": results["metadatas"][i]
                    if i < len(results["metadatas"])
                    else None,
                }
                sample_chunks.append(chunk_data)

            return sample_chunks

        except Exception as e:
            logger.error(f"Failed to get sample chunks: {e}")
            return []
