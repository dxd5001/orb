#!/usr/bin/env python3
"""
Fast debug script for Proposition Indexing with limited notes
"""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.append(str(Path(__file__).parent))

from indexing.indexer import Indexer
from ingestion.obsidian import ObsidianIngestor
from embedding.base import EmbeddingBackendFactory
from llm.base import LLMBackendFactory
from config import ConfigManager
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def debug_indexing_fast():
    """Fast indexing debug with limited notes."""
    print("=== Fast Indexing Debug (Limited Notes) ===")

    try:
        # Load configuration
        config = ConfigManager()
        embedding_config = config.get_embedding_config()
        llm_config = config.get_llm_config()
        vault_path = config.get_config("VAULT_PATH")
        vector_store_path = config.get_config("VECTOR_STORE_PATH")

        print(f"Vault path: {vault_path}")
        print(f"Vector store path: {vector_store_path}")

        # Initialize backends
        embedding_backend = EmbeddingBackendFactory.create_backend(
            embedding_config["provider"], embedding_config["model"]
        )
        llm_backend = LLMBackendFactory.create_backend(
            llm_config["provider"],
            llm_config["model"],
            **{k: v for k, v in llm_config.items() if k not in ["provider", "model"]},
        )
        print("✓ Backends initialized")

        # Ingest notes
        ingestor = ObsidianIngestor()
        ingest_result = ingestor.ingest(vault_path)
        print(f"✓ Ingested {len(ingest_result.notes)} notes")

        # Limit to first 5 notes for fast debugging
        limited_notes = ingest_result.notes[:5]
        print(f"🚀 Limited to {len(limited_notes)} notes for fast debugging")

        # Create limited ingest result
        from models import IngestResult

        limited_ingest_result = IngestResult(
            notes=limited_notes,
            total_count=len(limited_notes),
            skipped_count=0,
            errors=[],
        )

        # Initialize indexer
        indexer = Indexer(embedding_backend, vector_store_path, llm_backend)
        print("✓ Indexer initialized")

        # Index with limited notes
        print(f"🚀 Starting fast indexing with {len(limited_notes)} notes...")
        index_result = indexer.index(limited_ingest_result)

        print(f"\n✅ Fast indexing completed:")
        print(f"  Notes: {index_result.note_count}")
        print(f"  Chunks: {index_result.chunk_count}")
        print(f"  Propositions: {index_result.proposition_count}")

        # Check collections
        try:
            main_collection = indexer.collection
            if main_collection:
                main_count = main_collection.count()
                print(f"✓ Main collection: {main_count} items")
        except Exception as e:
            print(f"✗ Main collection error: {e}")

        try:
            prop_collection = indexer.proposition_collection
            if prop_collection:
                prop_count = prop_collection.count()
                print(f"✓ Proposition collection: {prop_count} items")
        except Exception as e:
            print(f"✗ Proposition collection error: {e}")

        return True

    except Exception as e:
        print(f"Fast indexing debug failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    debug_indexing_fast()
