"""
Tests for the main FastAPI application.

This module tests the application initialization and basic functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import create_app


class TestMainApplication:
    """Test cases for the main FastAPI application."""
    
    def setup_method(self):
        """Set up test environment."""
        self.app = create_app()
        self.client = TestClient(self.app)
    
    @patch('backend.main.ConfigManager')
    @patch('backend.main.EmbeddingBackendFactory')
    @patch('backend.main.LLMBackendFactory')
    @patch('backend.main.ObsidianIngestor')
    @patch('backend.main.Indexer')
    @patch('backend.main.Retriever')
    @patch('backend.main.Generator')
    def test_app_creation_success(self, mock_generator, mock_retriever, mock_indexer,
                                 mock_ingestor, mock_llm_factory, mock_embedding_factory,
                                 mock_config_manager):
        """Test successful application creation."""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.validate_config.return_value = []
        mock_config_instance.validate_vault_path.return_value = True
        mock_config_instance.get_config.side_effect = lambda key, default=None: {
            'VAULT_PATH': '/test/vault',
            'LLM_PROVIDER': 'openai',
            'EMBEDDING_PROVIDER': 'openai',
            'VECTOR_STORE_PATH': '/test/vector_store',
            'API_PORT': '8000'
        }.get(key, default)
        mock_config_instance.is_cloud_llm_enabled.return_value = False
        mock_config_manager.return_value = mock_config_instance
        
        mock_embedding_backend = MagicMock()
        mock_embedding_backend.get_model_name.return_value = 'test-embedding'
        mock_embedding_factory.create_backend.return_value = mock_embedding_backend
        
        mock_llm_backend = MagicMock()
        mock_llm_backend.get_model_name.return_value = 'test-llm'
        mock_llm_factory.create_backend.return_value = mock_llm_backend
        
        # Create app with mocked lifespan
        with patch('backend.main.lifespan') as mock_lifespan:
            app = create_app()
            
            assert app.title == "Obsidian RAG Chatbot"
            assert app.version == "1.0.0"
    
    def test_root_endpoint(self):
        """Test root endpoint."""
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Obsidian RAG Chatbot API"
        assert data["version"] == "1.0.0"
    
    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_cors_middleware(self):
        """Test CORS middleware is present."""
        response = self.client.options("/api/status")
        # Should allow CORS headers
        assert response.status_code == 200
    
    @patch('backend.main.ConfigManager')
    def test_lifespan_missing_config(self, mock_config_manager):
        """Test lifespan with missing configuration."""
        mock_config_instance = MagicMock()
        mock_config_instance.validate_config.return_value = ['VAULT_PATH', 'LLM_PROVIDER']
        mock_config_manager.return_value = mock_config_instance
        
        app = create_app()
        
        # Test startup failure
        with pytest.raises(ValueError, match="Missing required configuration"):
            with app.router.lifespan_context(app) as context:
                pass
    
    @patch('backend.main.ConfigManager')
    def test_lifespan_invalid_vault_path(self, mock_config_manager):
        """Test lifespan with invalid vault path."""
        mock_config_instance = MagicMock()
        mock_config_instance.validate_config.return_value = []
        mock_config_instance.validate_vault_path.return_value = False
        mock_config_instance.get_config.return_value = '/invalid/path'
        mock_config_manager.return_value = mock_config_instance
        
        app = create_app()
        
        # Test startup failure
        with pytest.raises(ValueError, match="Invalid vault path"):
            with app.router.lifespan_context(app) as context:
                pass
    
    def test_api_endpoints_exist(self):
        """Test that all API endpoints are registered."""
        # These should return 401/500 rather than 404 if properly registered
        endpoints = [
            "/api/chat",
            "/api/index",
            "/api/status",
            "/api/config"
        ]
        
        for endpoint in endpoints:
            response = self.client.post(endpoint, json={})
            # Should not be 404 (endpoint not found)
            assert response.status_code != 404, f"Endpoint {endpoint} not found"


class TestMainFunction:
    """Test cases for the main function."""
    
    @patch('backend.main.uvicorn.run')
    @patch('backend.main.ConfigManager')
    @patch('backend.main.create_app')
    def test_main_success(self, mock_create_app, mock_config_manager, mock_uvicorn):
        """Test successful main function execution."""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.get_config.return_value = "8000"
        mock_config_manager.return_value = mock_config_instance
        
        mock_app = MagicMock()
        mock_create_app.return_value = mock_app
        
        # Import and run main
        from backend.main import main
        main()
        
        # Verify uvicorn.run was called
        mock_uvicorn.run.assert_called_once()
        call_args = mock_uvicorn.run.call_args
        assert call_args.kwargs['host'] == "127.0.0.1"
        assert call_args.kwargs['port'] == 8000
        assert call_args.kwargs['log_level'] == "info"
    
    @patch('backend.main.sys.exit')
    @patch('backend.main.uvicorn.run')
    @patch('backend.main.ConfigManager')
    def test_main_exception(self, mock_config_manager, mock_uvicorn, mock_sys_exit):
        """Test main function with exception."""
        # Setup mock to raise exception
        mock_config_manager.side_effect = Exception("Test error")
        
        # Import and run main
        from backend.main import main
        main()
        
        # Verify sys.exit was called
        mock_sys_exit.assert_called_once_with(1)


if __name__ == '__main__':
    pytest.main([__file__])
