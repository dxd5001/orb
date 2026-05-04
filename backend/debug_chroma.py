#!/usr/bin/env python3
"""
Debug script to inspect ChromaDB collections.
This script allows you to inspect the contents of ChromaDB collections.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chromadb import PersistentClient
from config import Config


def inspect_collection(collection_name: str, limit: int = 10):
    """Inspect a ChromaDB collection."""
    config = Config()
    vector_store_path = config.vector_store_path
    
    client = PersistentClient(path=vector_store_path)
    
    try:
        collection = client.get_collection(name=collection_name)
        print(f"\n=== Collection: {collection_name} ===")
        print(f"Total documents: {collection.count()}")
        
        # Get all documents
        results = collection.get(
            include=["documents", "metadatas", "ids"],
            limit=limit
        )
        
        print(f"\nShowing first {limit} documents:")
        print("-" * 80)
        
        for i, (doc_id, doc, metadata) in enumerate(zip(
            results["ids"], 
            results["documents"], 
            results["metadatas"]
        )):
            print(f"\n[{i+1}] ID: {doc_id}")
            print(f"Source: {metadata.get('source_path', 'N/A')}")
            print(f"Title: {metadata.get('title', 'N/A')}")
            print(f"Last Modified: {metadata.get('last_modified', 'N/A')}")
            print(f"Content preview: {doc[:200]}...")
            
    except Exception as e:
        print(f"Error inspecting collection {collection_name}: {e}")


def list_collections():
    """List all ChromaDB collections."""
    config = Config()
    vector_store_path = config.vector_store_path
    
    client = PersistentClient(path=vector_store_path)
    
    try:
        collections = client.list_collections()
        print("\n=== Available Collections ===")
        for collection in collections:
            print(f"- {collection.name} ({collection.count()} documents)")
    except Exception as e:
        print(f"Error listing collections: {e}")


def search_documents(collection_name: str, query: str, limit: int = 5):
    """Search for documents in a collection."""
    from embedding.base import BaseEmbeddingBackend
    from embedding.local import LocalEmbeddingBackend
    
    config = Config()
    vector_store_path = config.vector_store_path
    
    client = PersistentClient(path=vector_store_path)
    
    try:
        collection = client.get_collection(name=collection_name)
        
        # Generate embedding
        embedding_backend = LocalEmbeddingBackend()
        query_embedding = embedding_backend.embed([query])[0]
        
        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "ids", "distances"]
        )
        
        print(f"\n=== Search Results for: '{query}' ===")
        print(f"Found {len(results['ids'][0])} results")
        
        for i, (doc_id, doc, metadata, distance) in enumerate(zip(
            results["ids"][0], 
            results["documents"][0], 
            results["metadatas"][0],
            results["distances"][0]
        )):
            print(f"\n[{i+1}] ID: {doc_id} (distance: {distance:.4f})")
            print(f"Source: {metadata.get('source_path', 'N/A')}")
            print(f"Title: {metadata.get('title', 'N/A')}")
            print(f"Content: {doc[:300]}...")
            
    except Exception as e:
        print(f"Error searching collection {collection_name}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_chroma.py list                          # List all collections")
        print("  python debug_chroma.py inspect <collection_name>       # Inspect a collection")
        print("  python debug_chroma.py search <collection_name> <query> # Search in a collection")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        list_collections()
    elif command == "inspect":
        if len(sys.argv) < 3:
            print("Usage: python debug_chroma.py inspect <collection_name>")
            sys.exit(1)
        collection_name = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        inspect_collection(collection_name, limit)
    elif command == "search":
        if len(sys.argv) < 4:
            print("Usage: python debug_chroma.py search <collection_name> <query>")
            sys.exit(1)
        collection_name = sys.argv[2]
        query = sys.argv[3]
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        search_documents(collection_name, query, limit)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
