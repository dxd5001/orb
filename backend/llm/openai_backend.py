"""
OpenAI LLM backend implementation.

This module provides LLM generation using OpenAI's API.
"""

import logging
from typing import List
import time

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None
    OpenAI = None

from .base import LLMBackend

logger = logging.getLogger(__name__)


class OpenAILLMBackend(LLMBackend):
    """
    OpenAI LLM backend using OpenAI's API.
    
    This backend provides text generation using OpenAI's hosted models
    such as GPT-3.5-turbo, GPT-4, etc.
    """
    
    def __init__(self, api_key: str, model_name: str = 'gpt-3.5-turbo', base_url: str = None, timeout: int = 60):
        """
        Initialize OpenAI LLM backend.
        
        Args:
            api_key: OpenAI API key
            model_name: Name of the OpenAI model
            base_url: Custom base URL (for compatible APIs)
            timeout: Request timeout in seconds
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai library is not available. "
                "Install it with: pip install openai"
            )
        
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout
        
        # Initialize OpenAI client
        client_kwargs = {'api_key': api_key, 'timeout': timeout}
        if base_url:
            client_kwargs['base_url'] = base_url
        
        self.client = OpenAI(**client_kwargs)
    
    def generate(self, prompt: str) -> str:
        """
        Generate text response using OpenAI API.
        
        Args:
            prompt: Input prompt for the LLM
            
        Returns:
            Generated text response
        """
        self.validate_prompt(prompt)
        self.log_generation_request(len(prompt))
        
        try:
            # Truncate prompt if needed
            truncated_prompt = self.truncate_prompt(prompt)
            
            # Prepare messages for chat completion
            messages = [
                {
                    "role": "user",
                    "content": truncated_prompt
                }
            ]
            
            # Make API request
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                timeout=self.timeout
            )
            
            if not response.choices:
                raise RuntimeError("No choices returned from OpenAI API")
            
            choice = response.choices[0]
            if not choice.message or not choice.message.content:
                raise RuntimeError("Invalid response format from OpenAI API")
            
            generated_text = choice.message.content
            
            self.log_generation_response(len(generated_text))
            
            return generated_text
            
        except openai.RateLimitError as e:
            raise RuntimeError(f"OpenAI API rate limit exceeded: {e}")
        except openai.AuthenticationError as e:
            raise RuntimeError(f"OpenAI API authentication error: {e}")
        except openai.APIError as e:
            raise RuntimeError(f"OpenAI API error: {e}")
        except Exception as e:
            logger.error(f"Failed to generate text with OpenAI: {e}")
            raise RuntimeError(f"OpenAI generation failed: {e}")
    
    def get_model_name(self) -> str:
        """
        Get the name of the LLM model.
        
        Returns:
            Name of the LLM model
        """
        return self.model_name
    
    def get_provider_name(self) -> str:
        """
        Get the name of the LLM provider.
        
        Returns:
            Name of the LLM provider
        """
        return "openai"
    
    def get_supported_models(self) -> List[str]:
        """
        Get list of supported OpenAI models.
        
        Returns:
            List of supported model names
        """
        return [
            'gpt-3.5-turbo',
            'gpt-3.5-turbo-16k',
            'gpt-4',
            'gpt-4-32k',
            'gpt-4-turbo-preview',
            'gpt-4o',
            'gpt-4o-mini'
        ]
    
    def validate_api_key(self) -> bool:
        """
        Validate that the API key is working.
        
        Returns:
            True if API key is valid, False otherwise
        """
        try:
            # Try a simple completion
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
                timeout=10
            )
            return response.choices and len(response.choices) > 0
        except Exception as e:
            logger.error(f"API key validation failed: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """
        Get information about the current model configuration.
        
        Returns:
            Dictionary with model information
        """
        info = {
            'model_name': self.model_name,
            'provider': 'openai',
            'base_url': self.base_url or 'https://api.openai.com/v1',
            'timeout': self.timeout
        }
        
        return info
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text using tiktoken if available.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self.model_name)
            return len(encoding.encode(text))
        except ImportError:
            # Fallback to rough approximation
            return len(text) // 4
        except Exception:
            return len(text) // 4
    
    def get_context_length(self) -> int:
        """
        Get context window size for the model.
        
        Returns:
            Context window size in tokens
        """
        context_lengths = {
            'gpt-3.5-turbo': 4096,
            'gpt-3.5-turbo-16k': 16384,
            'gpt-4': 8192,
            'gpt-4-32k': 32768,
            'gpt-4-turbo-preview': 128000,
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000
        }
        
        return context_lengths.get(self.model_name, 4096)
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Estimate cost for the API call.
        
        Args:
            prompt_tokens: Number of tokens in prompt
            completion_tokens: Number of tokens in completion
            
        Returns:
            Estimated cost in USD
        """
        # Pricing per 1K tokens (approximate, check OpenAI for current pricing)
        pricing = {
            'gpt-3.5-turbo': {'prompt': 0.0005, 'completion': 0.0015},
            'gpt-3.5-turbo-16k': {'prompt': 0.003, 'completion': 0.004},
            'gpt-4': {'prompt': 0.03, 'completion': 0.06},
            'gpt-4-32k': {'prompt': 0.06, 'completion': 0.12},
            'gpt-4-turbo-preview': {'prompt': 0.01, 'completion': 0.03},
            'gpt-4o': {'prompt': 0.005, 'completion': 0.015},
            'gpt-4o-mini': {'prompt': 0.00015, 'completion': 0.0006}
        }
        
        model_pricing = pricing.get(self.model_name, pricing['gpt-3.5-turbo'])
        
        prompt_cost = (prompt_tokens / 1000) * model_pricing['prompt']
        completion_cost = (completion_tokens / 1000) * model_pricing['completion']
        
        return prompt_cost + completion_cost
    
    def get_usage_stats(self) -> dict:
        """
        Get usage statistics from OpenAI (if available).
        
        Returns:
            Dictionary with usage statistics
        """
        try:
            # This would require admin API access, which most users don't have
            # Returning placeholder for now
            return {
                'note': 'Usage statistics require OpenAI admin API access'
            }
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {}
    
    def test_connection(self) -> bool:
        """
        Test connection to OpenAI API.
        
        Returns:
            True if connection is successful, False otherwise
        """
        return self.validate_api_key()
