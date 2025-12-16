# Adding New Video Generation Providers

This guide explains how to add new video generation providers to the platform.

## Overview

The platform uses a provider pattern that makes it easy to add new video generation services like RunwayML, Pika Labs, Stable Video Diffusion, etc.

## Step-by-Step Guide

### 1. Create Provider Implementation

Create a new file in `shared/providers/` (e.g., `runway_provider.py`):

```python
"""
RunwayML video generation provider implementation.
"""
import uuid
from typing import Dict, Optional, Any
import httpx
from .base import (
    BaseVideoProvider, VideoGenerationRequest, VideoGenerationResponse, 
    VideoStatus, ProviderError
)

class RunwayProvider(BaseVideoProvider):
    """RunwayML video generation provider."""
    
    def __init__(self, api_key: str, api_url: str = "https://api.runway.com/v1"):
        super().__init__(api_key, api_url)
        self.name = "runway"
        # Initialize HTTP client with auth headers
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation."""
        # Implement API call to start generation
        # Return VideoGenerationResponse with generation_id and status
        pass

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """Get generation status."""
        # Implement API call to check status
        pass

    async def download_video(self, generation_id: str) -> Optional[bytes]:
        """Download generated video."""
        # Implement video download
        pass

    async def cancel_generation(self, generation_id: str) -> bool:
        """Cancel generation."""
        pass

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters."""
        capabilities = self.get_capabilities()
        
        # Validate duration
        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(f"Duration exceeds maximum {capabilities['max_duration_seconds']}s")
        
        # Validate resolution, aspect ratio, etc.
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""
        return {
            "max_duration_seconds": 10,
            "max_resolution": (1920, 1080),
            "supports_image_input": True,
            "supported_formats": ["mp4"],
            "cost_per_second": 0.04,
            "image_cost_multiplier": 1.3,
            "model_versions": ["gen-3", "gen-3-turbo"],
            "features": ["text-to-video", "image-to-video"]
        }
```

### 2. Register Provider in Factory

Update `shared/providers/factory.py`:

```python
from .runway_provider import RunwayProvider

class ProviderFactory:
    _providers: Dict[str, Type[BaseVideoProvider]] = {
        "sora": SoraProvider,
        "veo3": Veo3Provider,
        "runway": RunwayProvider,  # Add new provider
    }
    
    @classmethod
    def _get_api_key_for_provider(cls, provider_type: str) -> str:
        env_var_map = {
            "sora": "OPENAI_API_KEY",
            "veo3": "GOOGLE_AI_API_KEY",
            "runway": "RUNWAY_API_KEY",  # Add environment variable
        }
        # ...
    
    @classmethod
    def _get_api_url_for_provider(cls, provider_type: str) -> str:
        url_map = {
            "sora": "https://api.openai.com/v1",
            "veo3": "https://generativelanguage.googleapis.com/v1beta",
            "runway": "https://api.runway.com/v1",  # Add API URL
        }
        # ...
```

### 3. Update Database Models

Add the new provider type to `shared/database/models.py`:

```python
class ProviderType(str, Enum):
    VEO3 = "veo3"
    SORA = "sora"
    KLING = "kling"
    RUNWAY = "runway"  # Add new provider type
```

### 4. Update Database Seeding

Add provider record to `migrations/versions/0002_seed_providers.py`:

```python
{
    'id': str(uuid.uuid4()),
    'name': 'RunwayML',
    'type': 'runway',
    'supports_image_input': True,
    'max_duration_seconds': 10,
    'max_resolution_width': 1920,
    'max_resolution_height': 1080,
    'cost_per_second': 0.04,
    'cost_multiplier_with_image': 1.3,
    'is_active': True,
    'is_healthy': True,
    'failure_count': 0,
}
```

### 5. Update Imports

Add to `shared/providers/__init__.py`:

```python
from .runway_provider import RunwayProvider

__all__ = [
    # ... existing exports
    'RunwayProvider'
]
```

### 6. Set Environment Variables

Add to your environment configuration:

```bash
RUNWAY_API_KEY=your_runway_api_key_here
```

### 7. Test Integration

The frontend will automatically detect the new provider through the `/api/v1/videos/providers` endpoint and show it in the dropdown if the API key is configured.

## Provider Interface Reference

### Required Methods

- `async def generate_video(request) -> VideoGenerationResponse`
- `async def get_status(generation_id) -> VideoGenerationResponse`  
- `async def download_video(generation_id) -> Optional[bytes]`
- `async def cancel_generation(generation_id) -> bool`
- `def validate_request(request) -> bool`
- `def get_capabilities() -> Dict[str, Any]`

### Capabilities Dictionary

```python
{
    "max_duration_seconds": int,        # Maximum video length
    "max_resolution": (width, height),  # Maximum resolution
    "supports_image_input": bool,       # Image-to-video support
    "supported_formats": ["mp4"],       # Output formats
    "cost_per_second": float,          # Base cost per second
    "image_cost_multiplier": float,     # Cost multiplier for image input
    "model_versions": [str],           # Available model versions
    "features": [str],                 # Supported features
    "supported_resolutions": [str],    # Supported resolution strings
    "supported_aspect_ratios": [str]   # Supported aspect ratios
}
```

## Frontend Integration

The frontend automatically integrates new providers:

1. **Provider Detection**: Fetches available providers from `/api/v1/videos/providers`
2. **Dynamic UI**: Shows provider options, models, and capabilities
3. **Validation**: Respects duration limits and feature support
4. **Cost Estimation**: Calculates costs based on provider capabilities

## Testing

1. Set the provider's API key environment variable
2. Start the backend services
3. Check `/api/v1/videos/providers` endpoint shows your provider as available
4. Test video generation through the frontend
5. Verify status polling and video download work correctly

## Example Providers to Add

- **RunwayML Gen-3**: High-quality video generation
- **Pika Labs**: Creative video effects
- **Stable Video Diffusion**: Open-source video generation
- **LumaAI**: Dream Machine video generation
- **Haiper**: Fast video generation
- **Moonvalley**: Artistic video generation

Each provider just needs to implement the `BaseVideoProvider` interface and be registered in the factory.