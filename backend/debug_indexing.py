#!/usr/bin/env python3
"""
Debug script to check indexing process step by step
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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def debug_indexing():
    """Debug indexing process step by step."""
    print("=== Indexing Debug ===")
    
    try:
        # Load configuration
        config = ConfigManager()
        embedding_config = config.get_embedding_config()
        llm_config = config.get_llm_config()
        vault_path = config.get_config("VAULT_PATH")
        vector_store_path = config.get_config("VECTOR_STORE_PATH")
        
        print(f"Vault path: {vault_path}")
        print(f"Vector store path: {vector_store_path}")
        
        # Step 1: Initialize backends
        print("\n--- Step 1: Initializing backends ---")
        embedding_backend = EmbeddingBackendFactory.create_backend(
            embedding_config["provider"], embedding_config["model"]
        )
        print("✓ Embedding backend initialized")
        
        llm_backend = LLMBackendFactory.create_backend(
            llm_config["provider"], llm_config["model"], 
            **{k: v for k, v in llm_config.items() if k not in ["provider", "model"]}
        )
        print("✓ LLM backend initialized")
        
        # Step 2: Ingest notes
        print("\n--- Step 2: Ingesting notes ---")
        ingestor = ObsidianIngestor()
        ingest_result = ingestor.ingest(vault_path)
        print(f"✓ Ingested {len(ingest_result.notes)} notes")
        
        # Step 3: Initialize indexer
        print("\n--- Step 3: Initializing indexer ---")
        indexer = Indexer(embedding_backend, vector_store_path, llm_backend)
        print("✓ Indexer initialized")
        
        # Step 4: Check collections before indexing
        print("\n--- Step 4: Checking collections before indexing ---")
        try:
            main_collection = indexer.collection
            print(f"✓ Main collection: {main_collection.name if main_collection else 'None'}")
        except Exception as e:
            print(f"✗ Main collection error: {e}")
        
        try:
            prop_collection = indexer.proposition_collection
            print(f"✓ Proposition collection: {prop_collection.name if prop_collection else 'None'}")
        except Exception as e:
            print(f"✗ Proposition collection error: {e}")
        
        # Step 5: Index with detailed logging
        print("\n--- Step 5: Starting indexing ---")
        print("This may take a while...")
        
        # Enable debug logging for indexer
        indexer_logger = logging.getLogger('indexing.indexer')
        indexer_logger.setLevel(logging.DEBUG)
        
        index_result = indexer.index(ingest_result)
        
        print(f"\n✓ Indexing completed:")
        print(f"  Notes: {index_result.note_count}")
        print(f"  Chunks: {index_result.chunk_count}")
        print(f"  Propositions: {index_result.proposition_count}")
        
        # Step 6: Check collections after indexing
        print("\n--- Step 6: Checking collections after indexing ---")
        try:
            main_collection = indexer.collection
            if main_collection:
                count = main_collection.count()
                print(f"✓ Main collection '{main_collection.name}' has {count} items")
            else:
                print("✗ Main collection is None")
        except Exception as e:
            print(f"✗ Main collection error: {e}")
        
        try:
            prop_collection = indexer.proposition_collection
            if prop_collection:
                count = prop_collection.count()
                print(f"✓ Proposition collection '{prop_collection.name}' has {count} items")
            else:
                print("✗ Proposition collection is None")
        except Exception as e:
            print(f"✗ Proposition collection error: {e}")
        
        return True
        
    except Exception as e:
        print(f"Indexing debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    debug_indexing()
