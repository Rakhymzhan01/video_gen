"""
WAN AI video generation provider implementation.
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


class WANProvider(BaseVideoProvider):
    """WAN AI video generation provider."""
    
    def __init__(self, api_key: str, api_url: str = "https://api.wan.ai/v1"):
        super().__init__(api_key, api_url)
        self.name = "wan"
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation with WAN AI."""
        
        # Validate request first
        self.validate_request(request)
        
        # Prepare request payload for WAN AI
        payload = {
            "prompt": request.prompt,
            "duration": request.duration_seconds,
            "resolution": {
                "width": request.resolution_width,
                "height": request.resolution_height
            },
            "fps": request.fps,
            "style": "realistic"  # Default style
        }
        
        # Add image input if provided
        if request.image_url:
            payload["image_url"] = request.image_url
        
        # Add provider-specific parameters
        if request.provider_specific_params:
            payload.update(request.provider_specific_params)
        
        try:
            response = await self.client.post(
                f"{self.api_url}/videos/generate",
                json=payload
            )
            
            if response.status_code == 429:
                raise ProviderQuotaExceeded(
                    "Rate limit or quota exceeded",
                    self.name,
                    "quota_exceeded"
                )
            
            response.raise_for_status()
            data = response.json()
            
            return VideoGenerationResponse(
                generation_id=data.get("id", str(uuid.uuid4())),
                status=VideoStatus.PROCESSING,
                estimated_completion_time=request.duration_seconds * 15,  # WAN AI is typically fast
                progress_percentage=0,
                metadata={
                    "wan_job_id": data.get("id"),
                    "provider": "wan",
                    "style": payload.get("style", "realistic")
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
                error_msg = "WAN AI service temporarily unavailable"
            
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
        
        try:
            response = await self.client.get(
                f"{self.api_url}/videos/{generation_id}"
            )
            
            response.raise_for_status()
            data = response.json()
            
            status_map = {
                "pending": VideoStatus.PENDING,
                "processing": VideoStatus.PROCESSING,
                "completed": VideoStatus.COMPLETED,
                "failed": VideoStatus.FAILED
            }
            
            status = status_map.get(data.get("status", "processing"), VideoStatus.PROCESSING)
            
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=status,
                progress_percentage=data.get("progress", 0),
                video_url=data.get("video_url") if status == VideoStatus.COMPLETED else None,
                error_message=data.get("error_message") if status == VideoStatus.FAILED else None,
                metadata={
                    "provider": "wan",
                    "wan_job_id": data.get("id"),
                    "created_at": data.get("created_at")
                }
            )
                
        except Exception as e:
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                error_message=str(e),
                metadata={"provider": "wan"}
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
            response = await self.client.delete(
                f"{self.api_url}/videos/{generation_id}"
            )
            return response.status_code in [200, 204]
            
        except Exception:
            return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters for WAN AI."""
        
        capabilities = self.get_capabilities()
        
        # Check duration
        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum "
                f"{capabilities['max_duration_seconds']}s for WAN AI"
            )
        
        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")
        
        # Check resolution
        max_width = capabilities["max_resolution"][0]
        max_height = capabilities["max_resolution"][1]
        
        if request.resolution_width > max_width or request.resolution_height > max_height:
            raise ValueError(
                f"Resolution {request.resolution_width}x{request.resolution_height} "
                f"exceeds maximum {max_width}x{max_height} for WAN AI"
            )
        
        # Check prompt
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise ValueError("Prompt cannot be empty")
        
        if len(request.prompt) > 1000:
            raise ValueError("Prompt too long (max 1000 characters)")
        
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        """Get WAN AI provider capabilities."""
        return {
            "max_duration_seconds": 30,  # WAN AI supports up to 30 seconds
            "max_resolution": (1920, 1080),  # Full HD max
            "supports_image_input": True,  # WAN AI supports image-to-video
            "supported_formats": ["mp4"],
            "cost_per_second": 0.015,  # Competitive pricing
            "image_cost_multiplier": 1.2,
            "supported_resolutions": [
                "1920x1080", "1280x720", "1080x1920", "720x1280"
            ],
            "model_versions": [
                "wan-video-v1",
                "wan-video-pro"
            ],
            "supported_styles": [
                "realistic", "anime", "cinematic", "artistic"
            ],
            "features": [
                "text-to-video",
                "image-to-video", 
                "style_control",
                "fast_generation",
                "high_quality"
            ]
        }

    async def health_check(self) -> bool:
        """Check if WAN AI API is healthy."""
        try:
            response = await self.client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()