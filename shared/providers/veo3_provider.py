"""
Google Veo 3 video generation provider implementation.
"""
import asyncio
import json
import uuid
from typing import Dict, Optional, Any
import httpx
from .base import (
    BaseVideoProvider, VideoGenerationRequest, VideoGenerationResponse, 
    VideoStatus, ProviderError, ProviderTimeout, ProviderQuotaExceeded
)


class Veo3Provider(BaseVideoProvider):
    """Google Veo 3 video generation provider."""
    
    def __init__(self, api_key: str, api_url: str = "https://generativelanguage.googleapis.com/v1beta"):
        super().__init__(api_key, api_url)
        self.name = "veo3"
        self.client = httpx.AsyncClient(
            timeout=60.0,
            params={"key": self.api_key}  # Google AI uses key as query param
        )

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation with Veo 3."""
        
        # Validate request first
        self.validate_request(request)
        
        # Prepare request payload for Google AI
        payload = {
            "model": "models/veo-3.1-fast-generate-preview",
            "prompt": request.prompt,
            "config": {
                "numberOfVideos": 1,
                "aspectRatio": self._get_aspect_ratio_string(
                    request.resolution_width, 
                    request.resolution_height
                )
            }
        }
        
        # Add image input if provided (matching frontend format)
        if request.image_url:
            payload["image"] = {
                "imageBytes": request.image_url,  # For now, assume base64 format
                "mimeType": "image/jpeg"  # Default mime type
            }
        
        # Add provider-specific parameters
        if request.provider_specific_params:
            if "model" in request.provider_specific_params:
                payload["model"] = f"models/{request.provider_specific_params['model']}"
            payload["config"].update(request.provider_specific_params.get("config", {}))
        
        try:
            # Use the correct Veo3 endpoint
            response = await self.client.post(
                f"{self.api_url}/models/veo-3.1-fast-generate-preview:generateVideos",
                json=payload,
                headers={
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 429:
                raise ProviderQuotaExceeded(
                    "Rate limit or quota exceeded",
                    self.name,
                    "quota_exceeded"
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Generate internal ID for tracking
            generation_id = str(uuid.uuid4())
            
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.PROCESSING,
                estimated_completion_time=request.duration_seconds * 20,  # Veo is typically faster
                progress_percentage=0,
                metadata={
                    "veo3_operation_name": data.get("name"),
                    "provider": "veo3",
                    "model": "veo-3.1-fast-generate-preview"
                }
            )
            
        except httpx.TimeoutException:
            raise ProviderTimeout(
                "Request timed out",
                self.name,
                "timeout"
            )
        except httpx.HTTPStatusError as e:
            error_msg = "Unknown error"
            try:
                if e.response.text:
                    error_data = e.response.json()
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {e.response.status_code}")
                else:
                    error_msg = f"HTTP {e.response.status_code} - No response body"
            except:
                error_msg = f"HTTP {e.response.status_code} - {e.response.text[:200]}"
            
            if e.response.status_code == 400:
                error_msg = f"Invalid request: {error_msg}"
            elif e.response.status_code == 401:
                error_msg = "Invalid API key"
            elif e.response.status_code == 403:
                error_msg = "Access denied or quota exceeded"
            elif e.response.status_code >= 500:
                error_msg = "Google Veo service temporarily unavailable"
            
            raise ProviderError(
                error_msg,
                self.name,
                str(e.response.status_code)
            )
        except Exception as e:
            raise ProviderError(
                f"Unexpected error: {str(e)}",
                self.name,
                "unknown_error"
            )

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """Get status of video generation."""
        
        # In a real implementation, you would track the mapping between 
        # generation_id and veo3_operation_name, but for this example we'll simulate
        try:
            # This is a mock implementation - in reality you'd call:
            # response = await self.client.get(f"{self.api_url}/operations/{operation_name}")
            
            # For demo purposes, simulate different statuses
            import random
            
            # Simulate processing with random progress
            if random.random() < 0.8:  # 80% chance still processing
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.PROCESSING,
                    progress_percentage=min(90, random.randint(10, 80)),
                    metadata={"provider": "veo3"}
                )
            else:  # 20% chance completed
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.COMPLETED,
                    progress_percentage=100,
                    video_url=f"https://veo-videos.googleapis.com/video_{generation_id}.mp4",
                    metadata={"provider": "veo3"}
                )
                
        except Exception as e:
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                error_message=str(e),
                metadata={"provider": "veo3"}
            )

    async def download_video(self, generation_id: str) -> Optional[bytes]:
        """Download the generated video."""
        
        status_response = await self.get_status(generation_id)
        
        if status_response.status != VideoStatus.COMPLETED or not status_response.video_url:
            return None
        
        try:
            response = await self.client.get(status_response.video_url)
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            raise ProviderError(
                f"Failed to download video: {str(e)}",
                self.name,
                "download_failed"
            )

    async def cancel_generation(self, generation_id: str) -> bool:
        """Cancel video generation."""
        try:
            # In a real implementation, you would call:
            # response = await self.client.delete(f"{self.api_url}/operations/{operation_name}")
            
            # For demo purposes, always return True
            return True
            
        except Exception:
            return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters for Veo 3."""
        
        capabilities = self.get_capabilities()
        
        # Check duration
        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum "
                f"{capabilities['max_duration_seconds']}s for Veo 3"
            )
        
        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")
        
        # Check resolution
        max_width = capabilities["max_resolution"][0]
        max_height = capabilities["max_resolution"][1]
        
        if request.resolution_width > max_width or request.resolution_height > max_height:
            raise ValueError(
                f"Resolution {request.resolution_width}x{request.resolution_height} "
                f"exceeds maximum {max_width}x{max_height} for Veo 3"
            )
        
        # Check aspect ratio (Veo 3 supports specific ratios)
        aspect_ratio = request.resolution_width / request.resolution_height
        valid_aspects = [16/9, 9/16]  # Veo 3 supports 16:9 and 9:16
        
        if not any(abs(aspect_ratio - valid) < 0.1 for valid in valid_aspects):
            raise ValueError(
                "Veo 3 only supports 16:9 and 9:16 aspect ratios"
            )
        
        # Check prompt
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise ValueError("Prompt cannot be empty")
        
        if len(request.prompt) > 2000:
            raise ValueError("Prompt too long (max 2000 characters)")
        
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        """Get Veo 3 provider capabilities."""
        return {
            "max_duration_seconds": 60,  # Veo 3 supports up to 60 seconds
            "max_resolution": (1920, 1080),  # Full HD max
            "supports_image_input": True,  # Veo 3 supports image-to-video
            "supported_formats": ["mp4"],
            "cost_per_second": 0.02,  # Lower cost than Sora
            "image_cost_multiplier": 1.5,
            "supported_resolutions": [
                "1920x1080", "1080x1920",  # 16:9 and 9:16 only
            ],
            "model_versions": [
                "veo-3.1-fast-generate-preview",
                "veo-3.1-generate-preview"
            ],
            "supported_aspect_ratios": ["16:9", "9:16"],
            "features": [
                "text-to-video",
                "image-to-video", 
                "long_duration",
                "fast_generation",
                "temporal_consistency"
            ]
        }

    def _get_aspect_ratio_string(self, width: int, height: int) -> str:
        """Convert resolution to aspect ratio string for Google AI API."""
        aspect_ratio = width / height
        
        if abs(aspect_ratio - 16/9) < 0.1:
            return "16:9"
        elif abs(aspect_ratio - 9/16) < 0.1:
            return "9:16"
        else:
            # Default to 16:9 if not supported
            return "16:9"

    async def health_check(self) -> bool:
        """Check if Veo 3 API is healthy."""
        try:
            response = await self.client.get(f"{self.api_url}/models")
            return response.status_code == 200
        except Exception:
            return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()