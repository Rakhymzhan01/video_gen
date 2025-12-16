"""
OpenAI Sora video generation provider implementation.
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


class SoraProvider(BaseVideoProvider):
    """OpenAI Sora video generation provider."""
    
    def __init__(self, api_key: str, api_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, api_url)
        self.name = "sora"
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation with Sora."""
        
        # Validate request first
        self.validate_request(request)
        
        # Prepare request payload
        payload = {
            "model": "sora-1.0-turbo",
            "prompt": request.prompt,
            "size": f"{request.resolution_width}x{request.resolution_height}",
            "duration": request.duration_seconds,
        }
        
        # Add image input if provided
        if request.image_url:
            payload["image"] = request.image_url
        
        # Add provider-specific parameters
        if request.provider_specific_params:
            payload.update(request.provider_specific_params)
        
        try:
            response = await self.client.post(
                f"{self.api_url}/video/generations",
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
            
            # Generate internal ID for tracking
            generation_id = str(uuid.uuid4())
            
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.PROCESSING,
                estimated_completion_time=request.duration_seconds * 30,  # Rough estimate
                progress_percentage=0,
                metadata={
                    "sora_job_id": data.get("id"),
                    "provider": "sora",
                    "model": "sora-1.0-turbo"
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
            if e.response.status_code == 400:
                error_data = e.response.json() if e.response.text else {}
                error_msg = error_data.get("error", {}).get("message", "Invalid request")
            elif e.response.status_code == 401:
                error_msg = "Invalid API key"
            elif e.response.status_code == 403:
                error_msg = "Access denied"
            elif e.response.status_code >= 500:
                error_msg = "Sora service temporarily unavailable"
            
            raise ProviderError(
                error_msg,
                self.name,
                str(e.response.status_code)
            )

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """Get status of video generation."""
        
        # In a real implementation, you would track the mapping between 
        # generation_id and sora_job_id, but for this example we'll simulate
        try:
            # This is a mock implementation - in reality you'd call:
            # response = await self.client.get(f"{self.api_url}/video/generations/{sora_job_id}")
            
            # For demo purposes, simulate different statuses
            import random
            
            # Simulate processing with random progress
            if random.random() < 0.8:  # 80% chance still processing
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.PROCESSING,
                    progress_percentage=min(90, random.randint(10, 80)),
                    metadata={"provider": "sora"}
                )
            else:  # 20% chance completed
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.COMPLETED,
                    progress_percentage=100,
                    video_url=f"https://sora-videos.openai.com/video_{generation_id}.mp4",
                    metadata={"provider": "sora"}
                )
                
        except Exception as e:
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                error_message=str(e),
                metadata={"provider": "sora"}
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
            # response = await self.client.delete(f"{self.api_url}/video/generations/{sora_job_id}")
            
            # For demo purposes, always return True
            return True
            
        except Exception:
            return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters for Sora."""
        
        capabilities = self.get_capabilities()
        
        # Check duration
        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum "
                f"{capabilities['max_duration_seconds']}s for Sora"
            )
        
        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")
        
        # Check resolution
        max_width = capabilities["max_resolution"][0]
        max_height = capabilities["max_resolution"][1]
        
        if request.resolution_width > max_width or request.resolution_height > max_height:
            raise ValueError(
                f"Resolution {request.resolution_width}x{request.resolution_height} "
                f"exceeds maximum {max_width}x{max_height} for Sora"
            )
        
        # Check aspect ratio (Sora supports specific ratios)
        supported_ratios = ["1920x1080", "1080x1920", "1216x832", "832x1216", "1344x768", "768x1344"]
        current_ratio = f"{request.resolution_width}x{request.resolution_height}"
        
        if current_ratio not in supported_ratios:
            # Check if it's a close match to a supported ratio
            aspect_ratio = request.resolution_width / request.resolution_height
            
            # Allow 16:9, 9:16, and some other common ratios
            valid_aspects = [16/9, 9/16, 4/3, 3/4, 1.75, 1/1.75]
            if not any(abs(aspect_ratio - valid) < 0.1 for valid in valid_aspects):
                raise ValueError(
                    f"Aspect ratio not supported by Sora. "
                    f"Supported resolutions: {', '.join(supported_ratios)}"
                )
        
        # Check prompt
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise ValueError("Prompt cannot be empty")
        
        if len(request.prompt) > 1000:
            raise ValueError("Prompt too long (max 1000 characters)")
        
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        """Get Sora provider capabilities."""
        return {
            "max_duration_seconds": 20,  # Sora supports up to 20 seconds
            "max_resolution": (1920, 1080),  # Full HD max
            "supports_image_input": True,  # Sora supports image-to-video
            "supported_formats": ["mp4"],
            "cost_per_second": 0.05,  # Higher cost for Sora
            "image_cost_multiplier": 1.8,
            "supported_resolutions": [
                "1920x1080", "1080x1920",  # 16:9 and 9:16
                "1216x832", "832x1216",    # 3:2 and 2:3  
                "1344x768", "768x1344"     # 7:4 and 4:7
            ],
            "model_versions": ["sora-1.0-turbo"],
            "features": [
                "text-to-video",
                "image-to-video", 
                "high_quality_output",
                "realistic_physics",
                "temporal_consistency"
            ]
        }

    async def health_check(self) -> bool:
        """Check if Sora API is healthy."""
        try:
            response = await self.client.get(f"{self.api_url}/models")
            return response.status_code == 200
        except Exception:
            return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()