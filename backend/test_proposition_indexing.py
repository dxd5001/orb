#!/usr/bin/env python3
"""
Proposition Indexing Test Script

This script tests the Proposition Indexing functionality:
1. Indexing with proposition generation
2. Query type detection
3. Different search strategies (proposition, context, hybrid)

Usage:
    python test_proposition_indexing.py
"""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.append(str(Path(__file__).parent))

from indexing.indexer import Indexer
from ingestion.obsidian import ObsidianIngestor
from retrieval.retriever import Retriever
from embedding.base import EmbeddingBackendFactory
from llm.base import LLMBackendFactory
from config import ConfigManager
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_indexing():
    """Test indexing with proposition generation."""
    print("\n=== Testing Proposition Indexing ===")

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

        print("Backends initialized successfully")

        # Ingest notes
        ingestor = ObsidianIngestor()
        ingest_result = ingestor.ingest(vault_path)
        print(f"Ingested {len(ingest_result.notes)} notes")

        # Limit to first 10 notes for stable testing
        limited_notes = ingest_result.notes[:10]
        print(f"🚀 Limited to {len(limited_notes)} notes for stable testing")

        # Create limited ingest result
        from models import IngestResult

        limited_ingest_result = IngestResult(
            notes=limited_notes,
            total_count=len(limited_notes),
            skipped_count=0,
            errors=[],
        )

        # Index with propositions
        indexer = Indexer(embedding_backend, vector_store_path, llm_backend)
        index_result = indexer.index(limited_ingest_result)

        print(f"Indexing completed:")
        print(f"  Notes: {index_result.note_count}")
        print(f"  Chunks: {index_result.chunk_count}")
        print(f"  Propositions: {index_result.proposition_count}")

        return True

    except Exception as e:
        print(f"Indexing failed: {e}")
        return False


def test_retrieval():
    """Test different retrieval strategies."""
    print("\n=== Testing Retrieval Strategies ===")

    try:
        # Load configuration
        config = ConfigManager()
        embedding_config = config.get_embedding_config()
        llm_config = config.get_llm_config()
        vector_store_path = config.get_config("VECTOR_STORE_PATH")

        # Initialize backends
        embedding_backend = EmbeddingBackendFactory.create_backend(
            embedding_config["provider"], embedding_config["model"]
        )
        llm_backend = LLMBackendFactory.create_backend(
            llm_config["provider"],
            llm_config["model"],
            **{k: v for k, v in llm_config.items() if k not in ["provider", "model"]},
        )

        # Initialize retriever
        retriever = Retriever(embedding_backend, vector_store_path, llm_backend)

        # Test queries for different strategies
        test_queries = [
            (
                "最後にビールを飲んだのはいつ？",
                "Fact query - should use proposition search",
            ),
            (
                "実家での畑仕事について教えて",
                "Context query - should use regular search",
            ),
            ("ビールのこと", "Ambiguous query - should use hybrid search"),
            ("いつ映画を見た？", "Another fact query"),
        ]

        for query, description in test_queries:
            print(f"\n--- Query: {query} ---")
            print(f"Expected: {description}")

            try:
                chunks = retriever.retrieve(query, top_k=3)
                print(f"Found {len(chunks)} chunks")

                for i, chunk in enumerate(chunks[:2]):  # Show first 2 chunks
                    is_proposition = getattr(chunk, "is_proposition", False)
                    chunk_type = "Proposition" if is_proposition else "Regular"
                    print(f"  Chunk {i + 1} ({chunk_type}): {chunk.text[:80]}...")

            except Exception as e:
                print(f"  Error: {e}")

        return True

    except Exception as e:
        print(f"Retrieval test failed: {e}")
        return False


def test_query_classification():
    """Test query type detection."""
    print("\n=== Testing Query Classification ===")

    try:
        # Load configuration
        config = ConfigManager()
        embedding_config = config.get_embedding_config()
        llm_config = config.get_llm_config()
        vector_store_path = config.get_config("VECTOR_STORE_PATH")

        # Initialize backends
        embedding_backend = EmbeddingBackendFactory.create_backend(
            embedding_config["provider"], embedding_config["model"]
        )
        llm_backend = LLMBackendFactory.create_backend(
            llm_config["provider"],
            llm_config["model"],
            **{k: v for k, v in llm_config.items() if k not in ["provider", "model"]},
        )

        # Initialize retriever
        retriever = Retriever(embedding_backend, vector_store_path, llm_backend)

        # Test query classification
        test_cases = [
            ("いつビールを飲んだ？", True, False),  # fact, not context
            ("ビールについて教えて", False, True),  # not fact, context
            ("ビールのこと", False, False),  # not fact, not context (hybrid)
            ("最後に映画を見たのはいつ？", True, False),
            ("旅行の様子を説明して", False, True),
        ]

        for query, expected_fact, expected_context in test_cases:
            is_fact = retriever._is_fact_query(query)
            is_context = retriever._is_context_query(query)

            status = (
                "✓"
                if (is_fact == expected_fact and is_context == expected_context)
                else "✗"
            )
            print(f"  {status} '{query}' -> fact:{is_fact} context:{is_context}")

        return True

    except Exception as e:
        print(f"Query classification test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Proposition Indexing Test Suite")
    print("=" * 50)

    # Run tests
    tests = [
        ("Indexing", test_indexing),
        ("Query Classification", test_query_classification),
        ("Retrieval", test_retrieval),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\nRunning {test_name} test...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{test_name} test crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\nPassed: {passed}/{len(results)} tests")

    if passed == len(results):
        print("🎉 All tests passed! Proposition Indexing is working correctly.")
    else:
        print("❌ Some tests failed. Check the logs above for details.")


if __name__ == "__main__":
    main()
