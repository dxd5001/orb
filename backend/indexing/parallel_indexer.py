"""
Parallel Proposition Indexer for improved performance
"""

import concurrent.futures
from typing import List, Tuple
import logging
from dataclasses import dataclass

from indexing.indexer import Indexer
from models import NoteDocument, IndexResult, create_chunk_id

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of batch processing"""

    note_index: int
    note: NoteDocument
    propositions: List[str]
    proposition_chunks: List
    error: str = None


class ParallelIndexer(Indexer):
    """Enhanced Indexer with parallel processing capabilities"""

    def __init__(
        self,
        embedding_backend,
        vector_store_path: str,
        llm_backend,
        max_workers: int = 4,
    ):
        super().__init__(embedding_backend, vector_store_path, llm_backend)
        self.max_workers = max_workers

    def _generate_propositions_batch(
        self, notes_batch: List[Tuple[int, NoteDocument]]
    ) -> List[BatchResult]:
        """
        Generate propositions for a batch of notes in parallel

        Args:
            notes_batch: List of (index, note) tuples

        Returns:
            List of BatchResult objects
        """

        def process_single_note(note_data: Tuple[int, NoteDocument]) -> BatchResult:
            note_index, note = note_data

            try:
                # Generate propositions using parent method
                propositions = self._generate_propositions(note.body)

                # Create proposition chunks
                proposition_chunks = self._create_proposition_chunks(note, propositions)

                return BatchResult(
                    note_index=note_index,
                    note=note,
                    propositions=propositions,
                    proposition_chunks=proposition_chunks,
                )

            except Exception as e:
                logger.error(f"Failed to process note {note.file_path}: {e}")
                return BatchResult(
                    note_index=note_index,
                    note=note,
                    propositions=[],
                    proposition_chunks=[],
                    error=str(e),
                )

        # Process notes in parallel
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            results = list(executor.map(process_single_note, notes_batch))

        return results

    def index_parallel(self, ingest_result, batch_size: int = 20) -> "IndexResult":
        """
        Index notes with parallel proposition generation

        Args:
            ingest_result: Result from ingestion process
            batch_size: Number of notes to process in each batch

        Returns:
            IndexResult with statistics
        """
        # IndexResult already imported at top

        logger.info(
            f"Starting parallel indexing of {len(ingest_result.notes)} notes with {self.max_workers} workers"
        )

        # Clear existing collections
        self._clear_collections()

        # Process notes in batches to manage memory
        all_chunks = []
        all_proposition_chunks = []
        processed_notes = 0
        failed_notes = 0

        for i in range(0, len(ingest_result.notes), batch_size):
            batch = ingest_result.notes[i : i + batch_size]
            batch_with_indices = [(i + j, note) for j, note in enumerate(batch)]

            logger.info(
                f"Processing batch {i // batch_size + 1}/{(len(ingest_result.notes) + batch_size - 1) // batch_size}"
            )

            # Generate propositions in parallel
            batch_results = self._generate_propositions_batch(batch_with_indices)

            # Process results
            for result in batch_results:
                if result.error:
                    failed_notes += 1
                    logger.warning(
                        f"Failed to process note {result.note.file_path}: {result.error}"
                    )
                    continue

                # Create regular chunks for this note
                regular_chunks = self._create_chunks(result.note)
                all_chunks.extend(regular_chunks)

                # Add proposition chunks
                all_proposition_chunks.extend(result.proposition_chunks)

                processed_notes += 1

            logger.info(
                f"Batch completed: {processed_notes} notes processed, {failed_notes} failed"
            )

        # Generate embeddings for all chunks first
        all_chunks_combined = all_chunks + all_proposition_chunks
        all_texts = [chunk.text for chunk in all_chunks_combined]

        # Filter out empty texts and corresponding chunks
        valid_chunks = []
        valid_texts = []
        for chunk, text in zip(all_chunks_combined, all_texts):
            if text and text.strip():  # Only include non-empty texts
                valid_chunks.append(chunk)
                valid_texts.append(text)
            else:
                logger.warning(f"Skipping empty chunk from {chunk.source_path}")

        embeddings = self.embedding_backend.embed(valid_texts)

        logger.info(
            f"Generated {len(embeddings)} embeddings of dimension {len(embeddings[0]) if embeddings else 0}"
        )

        # Split valid chunks and embeddings by type
        valid_regular_chunks = [
            chunk for chunk in valid_chunks if not chunk.is_proposition
        ]
        valid_proposition_chunks = [
            chunk for chunk in valid_chunks if chunk.is_proposition
        ]

        # Split embeddings accordingly
        regular_count = len(valid_regular_chunks)
        regular_embeddings = embeddings[:regular_count]
        proposition_embeddings = embeddings[regular_count:]

        # Store all chunks in vector database
        logger.info(f"Storing {len(valid_regular_chunks)} regular chunks...")
        self._store_chunks(valid_regular_chunks, regular_embeddings)

        logger.info(f"Storing {len(valid_proposition_chunks)} proposition chunks...")
        self._store_proposition_chunks(valid_proposition_chunks, proposition_embeddings)

        # Create result
        index_result = IndexResult(
            note_count=processed_notes,
            chunk_count=len(all_chunks),
            proposition_count=len(all_proposition_chunks),
        )

        logger.info(
            f"Parallel indexing completed: {index_result.note_count} notes, "
            f"{index_result.chunk_count} chunks, {index_result.proposition_count} propositions"
        )

        return index_result

    def _clear_collections(self):
        """Clear existing collections for idempotent indexing"""
        self._clear_collection()
        self._clear_proposition_collection()

    def _create_chunks(self, note: NoteDocument) -> List:
        """Create regular chunks for a note"""
        # Use parent's chunking method
        return super()._chunk_note(note)
