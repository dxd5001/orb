"""
FastAPI application entry point for Orb - RAG Chatbot for Obsidian Vaults.

This module provides the main FastAPI application with configuration,
initialization, and static file serving.
"""

import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Add backend to path for imports
sys.path.append(str(Path(__file__).parent))

from config import ConfigManager
from ingestion.obsidian import ObsidianIngestor
from indexing.indexer import Indexer
from retrieval.retriever import Retriever
from generation.generator import Generator
from embedding.base import EmbeddingBackendFactory
from llm.base import LLMBackendFactory
from feedback.store import FeedbackStore
from feedback.retriever import RuleRetriever

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Startup
    logger.info("Starting Orb - RAG Chatbot for Obsidian Vaults...")

    try:
        # Initialize configuration
        config_manager = ConfigManager()

        # Validate required configuration
        missing_configs = config_manager.validate_config()
        if missing_configs:
            logger.error(f"Missing required configuration: {missing_configs}")
            logger.error("Please set these environment variables or update .env file")
            raise ValueError(f"Missing required configuration: {missing_configs}")

        # Validate vault path
        vault_path = config_manager.get_config("VAULT_PATH")
        if not config_manager.validate_vault_path(vault_path):
            logger.error(f"Invalid vault path: {vault_path}")
            raise ValueError(f"Invalid vault path: {vault_path}")

        # Log configuration
        logger.info(f"Vault path: {vault_path}")
        logger.info(f"LLM provider: {config_manager.get_config('LLM_PROVIDER')}")
        logger.info(
            f"Embedding provider: {config_manager.get_config('EMBEDDING_PROVIDER')}"
        )

        # Warn about cloud LLM usage
        if config_manager.is_cloud_llm_enabled():
            logger.warning(
                "Cloud LLM backend is configured. "
                "Vault text data will be sent to external API. "
                "Ensure you are comfortable with this before proceeding."
            )

        # Initialize components
        app.state.config_manager = config_manager

        # Initialize embedding backend
        embedding_config = config_manager.get_embedding_config()
        app.state.embedding_backend = EmbeddingBackendFactory.create_backend(
            embedding_config["provider"],
            embedding_config["model"],
            **{
                k: v
                for k, v in embedding_config.items()
                if k not in ["provider", "model"]
            },
        )
        logger.info(
            f"Embedding backend initialized: {app.state.embedding_backend.get_model_name()}"
        )

        # Initialize LLM backend
        llm_config = config_manager.get_llm_config()
        app.state.llm_backend = LLMBackendFactory.create_backend(
            llm_config["provider"],
            llm_config["model"],
            **{k: v for k, v in llm_config.items() if k not in ["provider", "model"]},
        )
        logger.info(
            f"LLM backend initialized: {app.state.llm_backend.get_model_name()}"
        )

        # Initialize ingestor
        app.state.ingestor = ObsidianIngestor()

        # Initialize indexer (with LLM backend for proposition generation)
        vector_store_path = config_manager.get_config("VECTOR_STORE_PATH")
        from indexing.parallel_indexer import ParallelIndexer

        app.state.indexer = ParallelIndexer(
            app.state.embedding_backend,
            vector_store_path,
            llm_backend=app.state.llm_backend,
            max_workers=4,  # Optimal number of workers for MacBook Pro
        )

        # Initialize retriever (with LLM backend for HyDE query expansion)
        app.state.retriever = Retriever(
            app.state.embedding_backend,
            vector_store_path,
            llm_backend=app.state.llm_backend,
        )

        # Initialize feedback store and rule retriever
        feedback_db_path = str(Path(__file__).parent / "feedback.db")
        app.state.feedback_store = FeedbackStore(db_path=feedback_db_path)
        app.state.rule_retriever = RuleRetriever(
            store=app.state.feedback_store,
            embedding_backend=app.state.embedding_backend,
        )
        logger.info("FeedbackStore and RuleRetriever initialized")

        # Initialize generator with rule retriever
        app.state.generator = Generator(
            app.state.llm_backend, rule_retriever=app.state.rule_retriever
        )

        logger.info("All components initialized successfully")

        yield

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

    finally:
        # Shutdown
        logger.info("Shutting down Orb - RAG Chatbot for Obsidian Vaults...")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Orb - RAG Chatbot for Obsidian Vaults",
        description="A private RAG chatbot for Obsidian vaults",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from routers.chat import router as chat_router
    from routers.index import router as index_router
    from routers.status import router as status_router
    from routers.config import router as config_router
    from routers.feedback import router as feedback_router

    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(index_router, prefix="/api", tags=["index"])
    app.include_router(status_router, prefix="/api", tags=["status"])
    app.include_router(config_router, prefix="/api", tags=["config"])
    app.include_router(feedback_router, prefix="/api", tags=["feedback"])

    # Mount static files for frontend
    frontend_path = Path(__file__).parent.parent / "frontend"
    if frontend_path.exists():
        app.mount(
            "/", StaticFiles(directory=str(frontend_path), html=True), name="static"
        )
        logger.info(f"Frontend mounted from: {frontend_path}")
    else:
        logger.warning(f"Frontend directory not found: {frontend_path}")

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "Orb - RAG Chatbot for Obsidian Vaults API",
            "version": "0.1.0",
        }

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


def main():
    """
    Main entry point for running the application.
    """
    try:
        # Initialize configuration
        config_manager = ConfigManager()

        # Get server configuration
        host = "127.0.0.1"  # Default to localhost for security
        port = int(config_manager.get_config("API_PORT") or "8000")

        # Create FastAPI app
        app = create_app()

        # Log startup information
        logger.info(f"Starting server on http://{host}:{port}")
        logger.info(f"API documentation available at http://{host}:{port}/docs")

        # Run server with extended timeout for LLM responses
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            timeout_keep_alive=1800,  # 30 minutes keep-alive
            timeout_graceful_shutdown=30,  # 30 seconds graceful shutdown
        )

    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
