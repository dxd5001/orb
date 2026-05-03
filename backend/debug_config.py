#!/usr/bin/env python3
"""
Debug script to check configuration loading
"""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.append(str(Path(__file__).parent))

from config import ConfigManager


def debug_config():
    """Debug configuration loading."""
    print("=== Configuration Debug ===")

    try:
        config = ConfigManager()

        # Check all configurations
        print("Available configurations:")
        try:
            # Try to access the internal config manager
            if hasattr(config, "_config_manager"):
                all_configs = config._config_manager.items()
            elif hasattr(config, "config"):
                all_configs = config.config.items()
            else:
                # Just check specific configs we know exist
                important_configs = [
                    "VAULT_PATH",
                    "LLM_PROVIDER",
                    "LLM_MODEL",
                    "LLM_BASE_URL",
                    "EMBEDDING_PROVIDER",
                    "EMBEDDING_MODEL",
                ]
                for key in important_configs:
                    value = config.get_config(key)
                    print(f"  {key}: {value}")
                all_configs = []

            for key, value in all_configs:
                print(f"  {key}: {value}")
        except Exception as e:
            print(f"  Error accessing all configs: {e}")

        # Check specific LLM config
        print("\nLLM Configuration:")
        llm_config = config.get_llm_config()
        for key, value in llm_config.items():
            print(f"  {key}: {value}")

        # Check if base_url is present
        if "base_url" in llm_config:
            print(f"\n✓ base_url found: {llm_config['base_url']}")
        else:
            print(f"\n✗ base_url NOT found in LLM config")
            print(f"Available keys: {list(llm_config.keys())}")

        return True

    except Exception as e:
        print(f"Configuration debug failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    debug_config()
