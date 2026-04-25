"""
Configuration API router for Orb - RAG Chatbot for Obsidian Vaults.

This module provides the /api/config endpoints for managing configuration.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends

from models import (
    ConfigGetResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse
)
from routers.dependencies import get_components

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config", response_model=ConfigGetResponse)
async def get_config(components: dict = Depends(get_components)) -> ConfigGetResponse:
    """
    Get current configuration.
    
    Args:
        components: Application components (config_manager)
        
    Returns:
        Current configuration
        
    Raises:
        HTTPException: If config retrieval fails
    """
    try:
        config_manager = components['config_manager']
        
        logger.info("Getting current configuration...")
        
        # Get all configurations
        all_configs = config_manager.get_all_configs()
        
        # Mask sensitive values
        masked_configs = {}
        for key, value in all_configs.items():
            if 'key' in key.lower() or 'secret' in key.lower():
                masked_configs[key] = "***" if value else None
            else:
                masked_configs[key] = value
        
        return ConfigGetResponse(config=masked_configs)
        
    except Exception as e:
        logger.error(f"Config retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config", response_model=ConfigUpdateResponse)
async def update_config(
    request: ConfigUpdateRequest,
    components: dict = Depends(get_components)
) -> ConfigUpdateResponse:
    """
    Update configuration values.
    
    Args:
        request: Configuration update request
        components: Application components (config_manager)
        
    Returns:
        Update response
        
    Raises:
        HTTPException: If config update fails
    """
    try:
        config_manager = components['config_manager']
        
        logger.info("Updating configuration...")
        
        updated_fields = []
        errors = []
        
        # Update vault path
        if request.vault_path is not None:
            if not config_manager.validate_vault_path(request.vault_path):
                errors.append("Invalid vault path")
            else:
                config_manager.set_config('VAULT_PATH', request.vault_path)
                updated_fields.append('vault_path')
        
        # Update LLM configuration
        if request.llm_provider is not None:
            config_manager.set_config('LLM_PROVIDER', request.llm_provider)
            updated_fields.append('llm_provider')
        
        if request.llm_model is not None:
            config_manager.set_config('LLM_MODEL', request.llm_model)
            updated_fields.append('llm_model')
        
        if request.openai_api_key is not None:
            config_manager.set_api_key('openai', request.openai_api_key)
            updated_fields.append('openai_api_key')
        
        if request.llm_base_url is not None:
            config_manager.set_config('LLM_BASE_URL', request.llm_base_url)
            updated_fields.append('llm_base_url')
        
        # Update embedding configuration
        if request.embedding_provider is not None:
            config_manager.set_config('EMBEDDING_PROVIDER', request.embedding_provider)
            updated_fields.append('embedding_provider')
        
        if request.embedding_model is not None:
            config_manager.set_config('EMBEDDING_MODEL', request.embedding_model)
            updated_fields.append('embedding_model')
        
                
        # Update API port
        if request.api_port is not None:
            config_manager.set_config('API_PORT', str(request.api_port))
            updated_fields.append('api_port')
        
        # Update vector store path
        if request.vector_store_path is not None:
            config_manager.set_config('VECTOR_STORE_PATH', request.vector_store_path)
            updated_fields.append('vector_store_path')
        
        # Update keyring usage
        if request.use_keyring is not None:
            config_manager.set_config('USE_KEYRING', str(request.use_keyring))
            updated_fields.append('use_keyring')
        
        if errors:
            logger.warning(f"Configuration update completed with {len(errors)} errors")
            return ConfigUpdateResponse(
                success=False,
                message=f"Update completed with {len(errors)} errors",
                updated_fields=updated_fields,
                errors=errors
            )
        
        logger.info(f"Configuration updated successfully: {updated_fields}")
        
        return ConfigUpdateResponse(
            success=True,
            message="Configuration updated successfully",
            updated_fields=updated_fields,
            errors=[]
        )
        
    except Exception as e:
        logger.error(f"Configuration update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
