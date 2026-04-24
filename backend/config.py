"""
Configuration management for Obsidian RAG Chatbot.

This module provides configuration management with support for:
- .env file loading via python-dotenv
- OS keychain integration via keyring (optional)
- Validation of required configuration items
- Vault path validation
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    keyring = None


logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Manages configuration for the Obsidian RAG Chatbot.
    
    Supports loading from .env files, environment variables, and optional OS keychain.
    """
    
    # Required configuration items
    REQUIRED_CONFIGS = [
        'VAULT_PATH',
        'LLM_PROVIDER', 
        'LLM_MODEL',
        'EMBEDDING_PROVIDER',
        'EMBEDDING_MODEL',
        'VECTOR_STORE_PATH'
    ]
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize ConfigManager.
        
        Args:
            env_file: Path to .env file. If None, looks for .env in current directory.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()  # Look for .env in current directory
            
        self.use_keyring = os.getenv('USE_KEYRING', 'false').lower() == 'true'
        
        if self.use_keyring and not KEYRING_AVAILABLE:
            logger.warning(
                "USE_KEYRING=true but keyring library not available. "
                "Falling back to environment variables."
            )
            self.use_keyring = False
    
    def get_config(self, key: str) -> Optional[str]:
        """
        Get configuration value.
        
        Args:
            key: Configuration key name
            
        Returns:
            Configuration value or None if not found
        """
        # For API keys, try keyring first if enabled
        if key.endswith('_API_KEY') and self.use_keyring:
            try:
                service_name = key.replace('_API_KEY', '').lower()
                value = keyring.get_password(service_name, 'api_key')
                if value:
                    return value
            except Exception as e:
                logger.warning(f"Failed to get {key} from keyring: {e}")
        
        # Fall back to environment variable
        return os.getenv(key)
    
    def set_config(self, key: str, value: str) -> None:
        """
        Set configuration value.
        
        Args:
            key: Configuration key name
            value: Configuration value
        """
        if key.endswith('_API_KEY') and self.use_keyring:
            try:
                service_name = key.replace('_API_KEY', '').lower()
                keyring.set_password(service_name, 'api_key', value)
                logger.info(f"Saved {key} to keychain")
                return
            except Exception as e:
                logger.warning(f"Failed to save {key} to keyring: {e}")
        
        # Set environment variable
        os.environ[key] = value
        logger.info(f"Set {key} in environment")
    
    def get_api_key(self, service: str) -> Optional[str]:
        """
        Get API key for a service.
        
        Args:
            service: Service name (e.g., 'openai')
            
        Returns:
            API key or None if not found
        """
        key_name = f"{service.upper()}_API_KEY"
        return self.get_config(key_name)
    
    def set_api_key(self, service: str, key: str) -> None:
        """
        Set API key for a service.
        
        Args:
            service: Service name (e.g., 'openai')
            key: API key value
        """
        key_name = f"{service.upper()}_API_KEY"
        self.set_config(key_name, key)
    
    def validate_config(self) -> List[str]:
        """
        Validate that all required configuration items are present.
        
        Returns:
            List of missing required configuration items
        """
        missing = []
        
        for config_key in self.REQUIRED_CONFIGS:
            value = self.get_config(config_key)
            if not value:
                missing.append(config_key)
        
        return missing
    
    def validate_vault_path(self, vault_path: str) -> bool:
        """
        Validate that the vault path exists and is a directory.
        
        Args:
            vault_path: Path to validate
            
        Returns:
            True if path exists and is a directory, False otherwise
        """
        try:
            path = Path(vault_path)
            return path.exists() and path.is_dir()
        except Exception as e:
            logger.error(f"Error validating vault path '{vault_path}': {e}")
            return False
    
    def get_all_configs(self) -> Dict[str, Any]:
        """
        Get all configuration values (excluding sensitive data).
        
        Returns:
            Dictionary of configuration values
        """
        configs = {}
        
        # Non-sensitive configurations
        safe_configs = [
            'VAULT_PATH',
            'LLM_PROVIDER',
            'LLM_MODEL', 
            'LLM_BASE_URL',
            'EMBEDDING_PROVIDER',
            'EMBEDDING_MODEL',
            'VECTOR_STORE_PATH',
            'API_PORT',
            'USE_KEYRING'
        ]
        
        for key in safe_configs:
            value = self.get_config(key)
            if value:
                configs[key] = value
        
        # Add masked API keys to show they are configured
        api_keys = ['OPENAI_API_KEY']
        for key in api_keys:
            value = self.get_config(key)
            if value:
                configs[key] = '***configured***'
        
        return configs
    
    def is_cloud_llm_enabled(self) -> bool:
        """
        Check if cloud LLM backend is configured.
        
        Returns:
            True if cloud LLM is enabled, False for local LLM
        """
        provider = self.get_config('LLM_PROVIDER')
        return provider and provider.lower() != 'local'
    
    def get_llm_config(self) -> Dict[str, Any]:
        """
        Get LLM configuration.
        
        Returns:
            Dictionary with LLM configuration
        """
        provider = self.get_config('LLM_PROVIDER')
        model = self.get_config('LLM_MODEL')
        
        if not provider or not model:
            raise ValueError("LLM_PROVIDER and LLM_MODEL must be configured")
        
        config = {
            'provider': provider.lower(),
            'model': model
        }
        
        if provider.lower() == 'local':
            base_url = self.get_config('LLM_BASE_URL')
            if not base_url:
                raise ValueError("LLM_BASE_URL must be configured for local LLM")
            config['base_url'] = base_url
        else:
            api_key = self.get_api_key(provider)
            if not api_key:
                raise ValueError(f"{provider.upper()}_API_KEY must be configured for cloud LLM")
            config['api_key'] = api_key
        
        return config
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """
        Get embedding configuration.
        
        Returns:
            Dictionary with embedding configuration
        """
        provider = self.get_config('EMBEDDING_PROVIDER')
        model = self.get_config('EMBEDDING_MODEL')
        
        if not provider or not model:
            raise ValueError("EMBEDDING_PROVIDER and EMBEDDING_MODEL must be configured")
        
        config = {
            'provider': provider.lower(),
            'model': model
        }
        
        if provider.lower() == 'local':
            # Local embedding might use sentence-transformers or Ollama
            pass
        else:
            api_key = self.get_api_key(provider)
            if not api_key:
                raise ValueError(f"{provider.upper()}_API_KEY must be configured for cloud embedding")
            config['api_key'] = api_key
        
        return config
