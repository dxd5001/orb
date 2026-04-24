"""
Dependency injection for API routers.

This module provides dependency functions for accessing application components.
"""

from fastapi import Depends
from functools import lru_cache

from config import ConfigManager
from embedding.base import EmbeddingBackend, EmbeddingBackendFactory
from llm.base import LLMBackend, LLMBackendFactory
from ingestion.obsidian import ObsidianIngestor
from indexing.indexer import Indexer
from retrieval.retriever import Retriever
from generation.generator import Generator


def get_config_manager() -> ConfigManager:
    """
    Get the configuration manager instance.
    
    Returns:
        ConfigManager instance
    """
    # In a real application, this would be injected from the app state
    # For now, we'll create a new instance
    return ConfigManager()


def get_embedding_backend(config_manager: ConfigManager = Depends(get_config_manager)) -> EmbeddingBackend:
    """
    Get the embedding backend instance.
    
    Args:
        config_manager: Configuration manager
        
    Returns:
        EmbeddingBackend instance
    """
    from embedding.base import EmbeddingBackendFactory
    
    embedding_config = config_manager.get_embedding_config()
    return EmbeddingBackendFactory.create_backend(
        embedding_config['provider'],
        embedding_config['model'],
        **{k: v for k, v in embedding_config.items() if k not in ['provider', 'model']}
    )


def get_llm_backend(config_manager: ConfigManager = Depends(get_config_manager)) -> LLMBackend:
    """
    Get the LLM backend instance.
    
    Args:
        config_manager: Configuration manager
        
    Returns:
        LLMBackend instance
    """
    llm_config = config_manager.get_llm_config()
    return LLMBackendFactory.create_backend(
        llm_config['provider'],
        llm_config['model'],
        **{k: v for k, v in llm_config.items() if k not in ['provider', 'model']}
    )


def get_ingestor() -> ObsidianIngestor:
    """
    Get the ingestor instance.
    
    Returns:
        ObsidianIngestor instance
    """
    return ObsidianIngestor()


def get_indexer(
    embedding_backend: EmbeddingBackend = Depends(get_embedding_backend),
    config_manager: ConfigManager = Depends(get_config_manager)
) -> Indexer:
    """
    Get the indexer instance.
    
    Args:
        embedding_backend: Embedding backend
        config_manager: Configuration manager
        
    Returns:
        Indexer instance
    """
    from indexing.indexer import Indexer
    
    vector_store_path = config_manager.get_config('VECTOR_STORE_PATH')
    return Indexer(embedding_backend, vector_store_path)


def get_retriever(
    embedding_backend: EmbeddingBackend = Depends(get_embedding_backend),
    config_manager: ConfigManager = Depends(get_config_manager)
) -> Retriever:
    """
    Get the retriever instance.
    
    Args:
        embedding_backend: Embedding backend
        config_manager: Configuration manager
        
    Returns:
        Retriever instance
    """
    from retrieval.retriever import Retriever
    
    vector_store_path = config_manager.get_config('VECTOR_STORE_PATH')
    return Retriever(embedding_backend, vector_store_path)


def get_generator(llm_backend: LLMBackend = Depends(get_llm_backend)) -> Generator:
    """
    Get the generator instance.
    
    Args:
        llm_backend: LLM backend
        
    Returns:
        Generator instance
    """
    from generation.generator import Generator
    
    return Generator(llm_backend)


@lru_cache()
def get_components() -> dict:
    """
    Get all application components as a dictionary.
    
    Returns:
        Dictionary of component instances
    """
    config_manager = get_config_manager()
    embedding_backend = get_embedding_backend(config_manager)
    llm_backend = get_llm_backend(config_manager)
    ingestor = get_ingestor()
    indexer = get_indexer(embedding_backend, config_manager)
    retriever = get_retriever(embedding_backend, config_manager)
    generator = get_generator(llm_backend)
    
    return {
        'config_manager': config_manager,
        'embedding_backend': embedding_backend,
        'llm_backend': llm_backend,
        'ingestor': ingestor,
        'indexer': indexer,
        'retriever': retriever,
        'generator': generator
    }
