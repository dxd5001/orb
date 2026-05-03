#!/usr/bin/env python3
"""
Test script for parallel proposition indexing
"""

import sys
import time
from pathlib import Path

# Add backend to path for imports
sys.path.append(str(Path(__file__).parent))

from indexing.parallel_indexer import ParallelIndexer
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


def test_parallel_indexing():
    """Test parallel indexing performance"""
    print("=== Parallel Indexing Performance Test ===")
    
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
        
        # Test with different worker counts
        worker_counts = [1, 2, 4, 8]
        limited_notes = ingest_result.notes[:20]  # Limit to 20 notes for testing
        
        from models import IngestResult
        limited_ingest_result = IngestResult(
            notes=limited_notes,
            total_count=len(limited_notes),
            skipped_count=0,
            errors=[]
        )
        
        print(f"🚀 Testing with {len(limited_notes)} notes")
        
        results = []
        
        for workers in worker_counts:
            print(f"\n--- Testing with {workers} workers ---")
            
            # Initialize parallel indexer
            indexer = ParallelIndexer(
                embedding_backend, 
                vector_store_path, 
                llm_backend, 
                max_workers=workers
            )
            
            # Measure performance
            start_time = time.time()
            index_result = indexer.index_parallel(limited_ingest_result, batch_size=5)
            end_time = time.time()
            
            duration = end_time - start_time
            
            results.append({
                'workers': workers,
                'duration': duration,
                'notes': index_result.note_count,
                'chunks': index_result.chunk_count,
                'propositions': index_result.proposition_count,
                'notes_per_second': index_result.note_count / duration
            })
            
            print(f"✓ Completed in {duration:.2f} seconds")
            print(f"  Notes: {index_result.note_count}")
            print(f"  Chunks: {index_result.chunk_count}")
            print(f"  Propositions: {index_result.proposition_count}")
            print(f"  Speed: {index_result.note_count / duration:.2f} notes/second")
        
        # Performance summary
        print(f"\n=== Performance Summary ===")
        print(f"{'Workers':<8} {'Duration':<10} {'Notes/sec':<12} {'Speedup':<8}")
        print("-" * 42)
        
        baseline = results[0]['duration']
        for result in results:
            speedup = baseline / result['duration']
            print(f"{result['workers']:<8} {result['duration']:<10.2f} {result['notes_per_second']:<12.2f} {speedup:<8.2f}x")
        
        return True
        
    except Exception as e:
        print(f"Parallel indexing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_parallel_indexing()
