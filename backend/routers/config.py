"""
Configuration API router for Orb - RAG Chatbot for Obsidian Vaults.
"""

import logging
from fastapi import APIRouter, HTTPException, Request

from models import (
    ConfigGetResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config", response_model=ConfigGetResponse)
async def get_config(request: Request) -> ConfigGetResponse:
    try:
        config_manager = request.app.state.config_manager
        all_configs = config_manager.get_all_configs()
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
async def update_config(body: ConfigUpdateRequest, request: Request) -> ConfigUpdateResponse:
    try:
        config_manager = request.app.state.config_manager
        updated_fields = []
        errors = []

        if body.vault_path is not None:
            if not config_manager.validate_vault_path(body.vault_path):
                errors.append("Invalid vault path")
            else:
                config_manager.set_config('VAULT_PATH', body.vault_path)
                updated_fields.append('vault_path')

        if body.llm_provider is not None:
            config_manager.set_config('LLM_PROVIDER', body.llm_provider)
            updated_fields.append('llm_provider')

        if body.llm_model is not None:
            config_manager.set_config('LLM_MODEL', body.llm_model)
            updated_fields.append('llm_model')

        if body.openai_api_key is not None:
            config_manager.set_api_key('openai', body.openai_api_key)
            updated_fields.append('openai_api_key')

        if body.llm_base_url is not None:
            config_manager.set_config('LLM_BASE_URL', body.llm_base_url)
            updated_fields.append('llm_base_url')

        if body.embedding_provider is not None:
            config_manager.set_config('EMBEDDING_PROVIDER', body.embedding_provider)
            updated_fields.append('embedding_provider')

        if body.embedding_model is not None:
            config_manager.set_config('EMBEDDING_MODEL', body.embedding_model)
            updated_fields.append('embedding_model')

        if body.api_port is not None:
            config_manager.set_config('API_PORT', str(body.api_port))
            updated_fields.append('api_port')

        if body.vector_store_path is not None:
            config_manager.set_config('VECTOR_STORE_PATH', body.vector_store_path)
            updated_fields.append('vector_store_path')

        if body.use_keyring is not None:
            config_manager.set_config('USE_KEYRING', str(body.use_keyring))
            updated_fields.append('use_keyring')

        if errors:
            return ConfigUpdateResponse(
                success=False,
                message=f"Update completed with {len(errors)} errors",
                updated_fields=updated_fields,
                errors=errors
            )

        return ConfigUpdateResponse(
            success=True,
            message="Configuration updated successfully",
            updated_fields=updated_fields,
            errors=[]
        )

    except Exception as e:
        logger.error(f"Configuration update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
