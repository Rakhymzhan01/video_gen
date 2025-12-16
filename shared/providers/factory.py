"""
Provider factory for creating video generation provider instances.
"""
import os
from typing import Dict, Type
from .base import BaseVideoProvider
from .sora_provider import SoraProvider
from .veo3_provider import Veo3Provider
from .wan_provider import WANProvider


class ProviderFactory:
    """Factory class for creating video generation provider instances."""
    
    # Registry of available providers
    _providers: Dict[str, Type[BaseVideoProvider]] = {
        "sora": SoraProvider,
        "veo3": Veo3Provider,
        "wan": WANProvider,
        "SORA2": SoraProvider,  # Database enum mapping
        "VEO3": Veo3Provider,   # Database enum mapping
        "WAN": WANProvider,     # Database enum mapping
    }
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseVideoProvider]):
        """Register a new provider class."""
        cls._providers[name] = provider_class
    
    @classmethod
    def create_provider(cls, provider_type: str, api_key: str = None) -> BaseVideoProvider:
        """
        Create a provider instance.
        
        Args:
            provider_type: Type of provider (sora, veo3, etc.)
            api_key: API key for the provider (optional, will use env vars if not provided)
            
        Returns:
            Provider instance
            
        Raises:
            ValueError: If provider type is not supported
            RuntimeError: If API key is not available
        """
        if provider_type not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unsupported provider: {provider_type}. Available: {available}")
        
        # Get API key from environment if not provided
        if not api_key:
            api_key = cls._get_api_key_for_provider(provider_type)
        
        if not api_key:
            raise RuntimeError(f"API key not configured for provider: {provider_type}")
        
        provider_class = cls._providers[provider_type]
        
        # Create instance with appropriate API URL
        api_url = cls._get_api_url_for_provider(provider_type)
        return provider_class(api_key=api_key, api_url=api_url)
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, Dict[str, any]]:
        """
        Get list of available providers with their capabilities.
        
        Returns:
            Dictionary mapping provider names to their capabilities
        """
        providers_info = {}
        
        for name, provider_class in cls._providers.items():
            try:
                # Try to create instance to get capabilities
                api_key = cls._get_api_key_for_provider(name)
                if api_key:
                    api_url = cls._get_api_url_for_provider(name)
                    provider = provider_class(api_key=api_key, api_url=api_url)
                    providers_info[name] = {
                        "available": True,
                        "capabilities": provider.get_capabilities(),
                        "name": provider.name
                    }
                else:
                    providers_info[name] = {
                        "available": False,
                        "error": "API key not configured",
                        "name": name
                    }
            except Exception as e:
                providers_info[name] = {
                    "available": False,
                    "error": str(e),
                    "name": name
                }
        
        return providers_info
    
    @classmethod
    def _get_api_key_for_provider(cls, provider_type: str) -> str:
        """Get API key for specific provider from environment variables."""
        env_var_map = {
            "sora": "OPENAI_API_KEY",
            "veo3": "GOOGLE_AI_API_KEY",
            "wan": "WAN_API_KEY",
            "SORA2": "OPENAI_API_KEY",
            "VEO3": "GOOGLE_AI_API_KEY",
            "WAN": "WAN_API_KEY",
        }
        
        env_var = env_var_map.get(provider_type)
        if env_var:
            return os.getenv(env_var)
        
        return None
    
    @classmethod
    def _get_api_url_for_provider(cls, provider_type: str) -> str:
        """Get API URL for specific provider."""
        url_map = {
            "sora": "https://api.openai.com/v1",
            "veo3": "https://generativelanguage.googleapis.com/v1beta",
            "wan": "https://api.wan.ai/v1",
            "SORA2": "https://api.openai.com/v1",
            "VEO3": "https://generativelanguage.googleapis.com/v1beta",
            "WAN": "https://api.wan.ai/v1",
        }
        
        return url_map.get(provider_type, "")


# Convenience functions
def create_provider(provider_type: str, api_key: str = None) -> BaseVideoProvider:
    """Create a provider instance using the factory."""
    return ProviderFactory.create_provider(provider_type, api_key)


def get_available_providers() -> Dict[str, Dict[str, any]]:
    """Get list of available providers."""
    return ProviderFactory.get_available_providers()


def register_provider(name: str, provider_class: Type[BaseVideoProvider]):
    """Register a new provider class."""
    ProviderFactory.register_provider(name, provider_class)