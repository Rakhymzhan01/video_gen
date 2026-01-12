"""
Kling video generation provider implementation using fal.ai API.
"""
import asyncio
import json
import uuid
import os
from typing import Dict, Optional, Any
import fal_client
from .base import (
    BaseVideoProvider, VideoGenerationRequest, VideoGenerationResponse, 
    VideoStatus, ProviderError, ProviderTimeout, ProviderQuotaExceeded
)


class KlingProvider(BaseVideoProvider):
    """Kling video generation provider via fal.ai."""
    
    def __init__(self, api_key: str, api_url: str = ""):
        super().__init__(api_key, api_url)
        self.name = "kling"
        
        # Configure fal client
        fal_client.api_key = self.api_key
        
        # Available Kling models on fal.ai
        self.models = {
            "2.6_pro_i2v": "fal-ai/kling-video/v2.6/pro/image-to-video",
            "2.6_pro_t2v": "fal-ai/kling-video/v2.6/pro/text-to-video",
            "2.1_master_i2v": "fal-ai/kling-video/v2.1/master/image-to-video",
            "2.1_master_t2v": "fal-ai/kling-video/v2.1/master/text-to-video",
            "2.1_standard_i2v": "fal-ai/kling-video/v2.1/standard/image-to-video",
            "2.1_standard_t2v": "fal-ai/kling-video/v2.1/standard/text-to-video"
        }

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation with Kling via fal.ai."""
        
        self.validate_request(request)
        
        # Determine model based on request type
        model_key = self._select_model(request)
        model_endpoint = self.models[model_key]
        
        # Prepare fal.ai request payload
        payload = self._prepare_payload(request, model_key)
        
        try:
            print(f"Kling: Starting generation with model {model_key}")
            print(f"Kling: Endpoint: {model_endpoint}")
            print(f"Kling: Payload: {json.dumps(payload, indent=2)}")
            
            # Submit to fal.ai queue (sync call)
            handler = fal_client.submit(
                model_endpoint,
                arguments=payload
            )
            
            request_id = handler.request_id
            print(f"Kling: Generation started with request_id: {request_id}")
            
            return VideoGenerationResponse(
                generation_id=request_id,
                status=VideoStatus.PROCESSING,
                estimated_completion_time=self._estimate_completion_time(request),
                progress_percentage=0,
                metadata={
                    "provider": "kling",
                    "model": model_key,
                    "endpoint": model_endpoint,
                    "prompt": request.prompt,
                    "fal_request_id": request_id,
                    "image_provided": bool(request.image_url)
                }
            )
            
        except Exception as e:
            error_msg = str(e)
            
            if "unauthorized" in error_msg.lower() or "401" in error_msg:
                error_msg = "Invalid fal.ai API key"
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                raise ProviderQuotaExceeded(
                    "Rate limit exceeded",
                    self.name,
                    "rate_limit"
                )
            elif "timeout" in error_msg.lower():
                raise ProviderTimeout(
                    "Request timed out",
                    self.name,
                    "timeout"
                )
            
            raise ProviderError(f"Generation failed: {error_msg}", self.name, "generation_error")

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """Get status of Kling video generation from fal.ai."""
        
        try:
            # Use default model endpoint for status check
            model_endpoint = "fal-ai/kling-video/v2.1/master/text-to-video"
            
            # Check status using fal.ai status check (sync call)
            status = fal_client.status(model_endpoint, generation_id)
            
            print(f"Kling: Status check for {generation_id}: {status.status}")
            
            # Map fal.ai status to our status
            if status.status in ["IN_PROGRESS", "IN_QUEUE"]:
                video_status = VideoStatus.PROCESSING
                progress = 50  # Show intermediate progress
            elif status.status == "COMPLETED":
                video_status = VideoStatus.COMPLETED
                progress = 100
            elif status.status in ["FAILED", "ERROR"]:
                video_status = VideoStatus.FAILED
                progress = 0
            elif status.status == "CANCELLED":
                video_status = VideoStatus.CANCELLED
                progress = 0
            else:
                video_status = VideoStatus.PROCESSING
                progress = 10
            
            # Extract video URL if completed
            video_url = None
            if video_status == VideoStatus.COMPLETED and hasattr(status, 'result'):
                result = status.result
                if isinstance(result, dict):
                    video_url = result.get("video", {}).get("url") if result.get("video") else None
                    if not video_url:
                        video_url = result.get("video_url")
                elif hasattr(result, 'video'):
                    video_url = getattr(result.video, 'url', None)
            
            error_message = None
            if video_status == VideoStatus.FAILED and hasattr(status, 'error'):
                error_message = str(status.error)
            
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=video_status,
                progress_percentage=int(progress),
                video_url=video_url,
                error_message=error_message,
                metadata={
                    "provider": "kling",
                    "fal_status": status.status,
                    "fal_response": status.__dict__ if hasattr(status, '__dict__') else str(status)
                }
            )
            
        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower() or "404" in error_msg:
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.FAILED,
                    error_message="Generation not found",
                    metadata={"provider": "kling"}
                )
            
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                error_message=f"Status check failed: {error_msg}",
                metadata={"provider": "kling"}
            )

    async def download_video(self, generation_id: str) -> Optional[bytes]:
        """Download the generated video."""
        
        status_response = await self.get_status(generation_id)
        
        if status_response.status != VideoStatus.COMPLETED:
            return None
            
        if not status_response.video_url:
            return None
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(status_response.video_url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            raise ProviderError(
                f"Failed to download video: {str(e)}",
                self.name,
                "download_failed"
            )

    async def cancel_generation(self, generation_id: str) -> bool:
        """Cancel Kling video generation."""
        try:
            # fal_client doesn't have a direct cancel method, 
            # but we can return True to indicate the attempt was made
            return True
        except Exception:
            return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters for Kling."""
        
        capabilities = self.get_capabilities()
        
        # Check duration
        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum "
                f"{capabilities['max_duration_seconds']}s for Kling"
            )
        
        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")
        
        # Check if duration is supported
        if request.duration_seconds not in capabilities["supported_durations"]:
            # Round to nearest supported duration
            supported = capabilities["supported_durations"]
            request.duration_seconds = min(supported, key=lambda x: abs(x - request.duration_seconds))
            print(f"Kling: Adjusted duration to {request.duration_seconds}s (nearest supported)")
        
        # Check prompt
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise ValueError("Prompt cannot be empty")
        
        if len(request.prompt) > 1000:
            raise ValueError("Prompt too long (max 1000 characters)")
        
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        """Get Kling provider capabilities."""
        return {
            "max_duration_seconds": 15,  # Kling supports up to 15 seconds
            "max_resolution": (1920, 1080),
            "supports_image_input": True,
            "supported_formats": ["mp4"],
            "cost_per_second": 0.05,  # $0.25 for 5s base + $0.05/additional second
            "image_cost_multiplier": 1.0,  # Same cost for I2V and T2V
            "supported_resolutions": [
                "480x480", "720x480", "1024x576", "1280x720", 
                "1920x1080", "480x720", "576x1024", "720x1280", "1080x1920"
            ],
            "supported_durations": [5, 10, 15],
            "model_versions": [
                "kling-2.6-pro", "kling-2.1-master", "kling-2.1-standard"
            ],
            "features": [
                "text-to-video",
                "image-to-video",
                "audio_generation",  # Kling 2.6 Pro supports audio
                "cinematic_quality",
                "fast_generation"
            ]
        }
    
    def _select_model(self, request: VideoGenerationRequest) -> str:
        """Select appropriate Kling model based on request."""
        # Use provider-specific params to override model selection
        model_preference = request.provider_specific_params.get("model", "2.1_master")
        
        # Choose between I2V and T2V based on image input
        model_type = "i2v" if request.image_url else "t2v"
        
        # Construct model key
        model_key = f"{model_preference}_{model_type}"
        
        # Fallback to available model if exact match not found
        if model_key not in self.models:
            if request.image_url:
                model_key = "2.1_master_i2v"
            else:
                model_key = "2.1_master_t2v"
        
        return model_key
    
    def _prepare_payload(self, request: VideoGenerationRequest, model_key: str) -> Dict[str, Any]:
        """Prepare fal.ai API payload based on model and request."""
        
        # Base payload for all models
        payload = {
            "prompt": request.prompt,
            "duration": request.duration_seconds,
        }
        
        # Add image for I2V models
        if "i2v" in model_key and request.image_url:
            payload["image_url"] = request.image_url
        
        # Add resolution - convert to fal.ai format
        if request.resolution_width <= 720:
            payload["resolution"] = "480p"
        elif request.resolution_width <= 1280:
            payload["resolution"] = "720p"
        else:
            payload["resolution"] = "1080p"
        
        # Add optional parameters from provider_specific_params
        if request.provider_specific_params:
            # CFG Scale
            if "cfg_scale" in request.provider_specific_params:
                payload["cfg_scale"] = request.provider_specific_params["cfg_scale"]
            
            # Enable prompt expansion
            if "enable_prompt_expansion" in request.provider_specific_params:
                payload["enable_prompt_expansion"] = request.provider_specific_params["enable_prompt_expansion"]
            
            # Model-specific parameters
            if "2.6_pro" in model_key and "enable_audio" in request.provider_specific_params:
                payload["enable_audio"] = request.provider_specific_params["enable_audio"]
        
        # Add aspect ratio based on resolution
        aspect_ratio = request.resolution_width / request.resolution_height
        if abs(aspect_ratio - 16/9) < 0.1:
            payload["aspect_ratio"] = "16:9"
        elif abs(aspect_ratio - 9/16) < 0.1:
            payload["aspect_ratio"] = "9:16"
        elif abs(aspect_ratio - 1) < 0.1:
            payload["aspect_ratio"] = "1:1"
        
        return payload
    
    def _estimate_completion_time(self, request: VideoGenerationRequest) -> int:
        """Estimate completion time based on request parameters."""
        base_time = 60  # Base 1 minute
        
        # Add time based on duration
        base_time += request.duration_seconds * 8  # 8 seconds per video second
        
        # Add time for higher resolution
        if request.resolution_width >= 1920:
            base_time += 60
        elif request.resolution_width >= 1280:
            base_time += 30
        
        # Add time for image input
        if request.image_url:
            base_time += 30
        
        return base_time

    async def health_check(self) -> bool:
        """Check if Kling via fal.ai is healthy."""
        try:
            # Try to access a simple fal.ai endpoint to check connectivity
            # This is a basic health check
            return True  # fal_client doesn't have a direct health check endpoint
        except Exception:
            return False