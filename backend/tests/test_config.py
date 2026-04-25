"""
Tests for ConfigManager.

This module includes both example-based tests and property-based tests using hypothesis.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, settings, strategies as st
from hypothesis import assume

from backend.config import ConfigManager


class TestConfigManagerExample:
    """Example-based tests for ConfigManager."""
    
    def test_init_with_env_file(self):
        """Test initialization with custom env file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST_VAR=test_value\n")
            f.flush()
            
            try:
                config = ConfigManager(env_file=f.name)
                assert config.get_config('TEST_VAR') == 'test_value'
            finally:
                os.unlink(f.name)
    
    def test_init_without_env_file(self):
        """Test initialization without custom env file."""
        config = ConfigManager()
        assert config is not None
    
    def test_get_config_missing(self):
        """Test getting missing configuration."""
        config = ConfigManager()
        assert config.get_config('NON_EXISTENT_KEY') is None
    
    def test_set_and_get_config(self):
        """Test setting and getting configuration."""
        config = ConfigManager()
        config.set_config('TEST_KEY', 'test_value')
        assert config.get_config('TEST_KEY') == 'test_value'
    
    def test_validate_vault_path_valid_directory(self):
        """Test vault path validation with valid directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ConfigManager()
            assert config.validate_vault_path(temp_dir) is True
    
    def test_validate_vault_path_invalid_file(self):
        """Test vault path validation with file instead of directory."""
        with tempfile.NamedTemporaryFile() as temp_file:
            config = ConfigManager()
            assert config.validate_vault_path(temp_file.name) is False
    
    def test_validate_vault_path_nonexistent(self):
        """Test vault path validation with nonexistent path."""
        config = ConfigManager()
        assert config.validate_vault_path('/nonexistent/path') is False
    
    def test_validate_config_all_present(self):
        """Test config validation with all required items present."""
        with patch.dict(os.environ, {
            'VAULT_PATH': '/test/path',
            'LLM_PROVIDER': 'local',
            'LLM_MODEL': 'test_model',
            'EMBEDDING_PROVIDER': 'local', 
            'EMBEDDING_MODEL': 'test_model',
            'VECTOR_STORE_PATH': '/test/vector'
        }):
            config = ConfigManager()
            missing = config.validate_config()
            assert len(missing) == 0
    
    def test_validate_config_missing_items(self):
        """Test config validation with missing required items."""
        # Clear environment to ensure missing items
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager()
            missing = config.validate_config()
            assert len(missing) == len(config.REQUIRED_CONFIGS)
            assert 'VAULT_PATH' in missing
            assert 'LLM_PROVIDER' in missing
    
    def test_get_all_configs_masks_api_keys(self):
        """Test that get_all_configs masks API keys."""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'secret_key',
            'VAULT_PATH': '/test/path'
        }):
            config = ConfigManager()
            all_configs = config.get_all_configs()
            assert all_configs['OPENAI_API_KEY'] == '***configured***'
            assert all_configs['VAULT_PATH'] == '/test/path'
    
    def test_is_cloud_llm_enabled_local(self):
        """Test cloud LLM detection with local provider."""
        with patch.dict(os.environ, {'LLM_PROVIDER': 'local'}):
            config = ConfigManager()
            assert config.is_cloud_llm_enabled() is False
    
    def test_is_cloud_llm_enabled_cloud(self):
        """Test cloud LLM detection with cloud provider."""
        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai'}):
            config = ConfigManager()
            assert config.is_cloud_llm_enabled() is True
    
    def test_get_llm_config_local(self):
        """Test getting LLM config for local provider."""
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'local',
            'LLM_MODEL': 'llama2',
            'LLM_BASE_URL': 'http://localhost:11434'
        }):
            config = ConfigManager()
            llm_config = config.get_llm_config()
            assert llm_config['provider'] == 'local'
            assert llm_config['model'] == 'llama2'
            assert llm_config['base_url'] == 'http://localhost:11434'
    
    def test_get_llm_config_cloud(self):
        """Test getting LLM config for cloud provider."""
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'openai',
            'LLM_MODEL': 'gpt-4o-mini',
            'OPENAI_API_KEY': 'test_key'
        }):
            config = ConfigManager()
            llm_config = config.get_llm_config()
            assert llm_config['provider'] == 'openai'
            assert llm_config['model'] == 'gpt-4o-mini'
            assert llm_config['api_key'] == 'test_key'
    
    def test_get_llm_config_missing_base_url(self):
        """Test error when local LLM config missing base URL."""
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'local',
            'LLM_MODEL': 'llama2'
        }, clear=True):
            config = ConfigManager()
            with pytest.raises(ValueError, match="LLM_BASE_URL must be configured"):
                config.get_llm_config()
    
    def test_get_llm_config_missing_api_key(self):
        """Test error when cloud LLM config missing API key."""
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'openai',
            'LLM_MODEL': 'gpt-4o-mini'
        }, clear=True):
            config = ConfigManager()
            with pytest.raises(ValueError, match="OPENAI_API_KEY must be configured"):
                config.get_llm_config()


class TestConfigManagerWithKeyring:
    """Tests for ConfigManager with keyring integration."""
    
    @patch('backend.config.keyring')
    @patch.dict(os.environ, {'USE_KEYRING': 'true'})
    def test_get_api_key_from_keyring(self, mock_keyring):
        """Test getting API key from keyring."""
        mock_keyring.get_password.return_value = 'secret_key'
        
        config = ConfigManager()
        key = config.get_api_key('openai')
        
        assert key == 'secret_key'
        mock_keyring.get_password.assert_called_once_with('openai', 'api_key')
    
    @patch('backend.config.keyring')
    @patch.dict(os.environ, {'USE_KEYRING': 'true'})
    def test_set_api_key_to_keyring(self, mock_keyring):
        """Test setting API key to keyring."""
        config = ConfigManager()
        config.set_api_key('openai', 'secret_key')
        
        mock_keyring.set_password.assert_called_once_with('openai', 'api_key', 'secret_key')
    
    @patch('backend.config.keyring')
    @patch.dict(os.environ, {'USE_KEYRING': 'true'})
    def test_keyring_fallback_to_env_on_error(self, mock_keyring):
        """Test fallback to environment when keyring fails."""
        mock_keyring.get_password.side_effect = Exception("Keyring error")
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'env_key'}):
            config = ConfigManager()
            key = config.get_api_key('openai')
            
            assert key == 'env_key'
    
    @patch.dict(os.environ, {'USE_KEYRING': 'false'})
    def test_keyring_disabled(self):
        """Test that keyring is not used when disabled."""
        config = ConfigManager()
        assert config.use_keyring is False


class TestConfigManagerPropertyBased:
    """Property-based tests for ConfigManager using hypothesis."""
    
    @given(st.text(min_size=1))
    @settings(max_examples=100)
    def test_property_1_vault_path_validation(self, path_str):
        """
        Property 1: Vault path validation.
        
        For any path string, validate_vault_path should only accept
        existing directories and reject non-existent paths, files, and empty strings.
        """
        # Feature: orb, Property 1: Vault path validation
        config = ConfigManager()
        
        # Test with non-existent path (should be False)
        assume(not Path(path_str).exists())
        result = config.validate_vault_path(path_str)
        assert result is False
        
        # Test with empty string (should be False)
        result = config.validate_vault_path("")
        assert result is False
    
    @given(st.dictionaries(
        keys=st.sampled_from(['VAULT_PATH', 'LLM_PROVIDER', 'LLM_MODEL', 
                             'EMBEDDING_PROVIDER', 'EMBEDDING_MODEL', 'VECTOR_STORE_PATH']),
        values=st.one_of(st.just(''), st.none())
    ))
    @settings(max_examples=100)
    def test_property_2_config_validation_completeness(self, env_dict):
        """
        Property 2: Configuration validation completeness.
        
        For any combination of configuration items, validate_config should
        enumerate all missing required items without omission.
        """
        # Feature: orb, Property 2: Configuration validation completeness
        with patch.dict(os.environ, env_dict, clear=True):
            config = ConfigManager()
            missing = config.validate_config()
            
            # Check that all required items that are empty/None in env_dict are in missing
            for required_key in config.REQUIRED_CONFIGS:
                env_value = env_dict.get(required_key)
                if not env_value:  # Empty string or None
                    assert required_key in missing
                else:
                    assert required_key not in missing
            
            # Check that missing list contains no extra items
            for missing_key in missing:
                assert missing_key in config.REQUIRED_CONFIGS
                env_value = env_dict.get(missing_key)
                assert not env_value  # Should be empty or None


if __name__ == '__main__':
    pytest.main([__file__])
