"""
Base provider interface for video generation services.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from enum import Enum

class VideoStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class VideoGenerationRequest:
    """Request object for video generation."""
    
    def __init__(
        self,
        prompt: str,
        duration_seconds: int,
        resolution_width: int,
        resolution_height: int,
        fps: int = 24,
        image_url: Optional[str] = None,
        provider_specific_params: Optional[Dict[str, Any]] = None
    ):
        self.prompt = prompt
        self.duration_seconds = duration_seconds
        self.resolution_width = resolution_width
        self.resolution_height = resolution_height
        self.fps = fps
        self.image_url = image_url
        self.provider_specific_params = provider_specific_params or {}

class VideoGenerationResponse:
    """Response object for video generation."""
    
    def __init__(
        self,
        generation_id: str,
        status: VideoStatus,
        estimated_completion_time: Optional[int] = None,
        progress_percentage: int = 0,
        error_message: Optional[str] = None,
        video_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.generation_id = generation_id
        self.status = status
        self.estimated_completion_time = estimated_completion_time
        self.progress_percentage = progress_percentage
        self.error_message = error_message
        self.video_url = video_url
        self.metadata = metadata or {}

class BaseVideoProvider(ABC):
    """
    Abstract base class for video generation providers.
    Each provider (Veo 3, Sora 2, Kling) implements this interface.
    """
    
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """
        Start video generation process.
        
        Args:
            request: Video generation request parameters
            
        Returns:
            Initial response with generation ID and status
            
        Raises:
            ProviderError: If generation fails to start
        """
        pass
    
    @abstractmethod
    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """
        Get current status of video generation.
        
        Args:
            generation_id: ID returned from generate_video
            
        Returns:
            Current status and progress information
            
        Raises:
            ProviderError: If status check fails
        """
        pass
    
    @abstractmethod
    async def download_video(self, generation_id: str) -> Optional[bytes]:
        """
        Download generated video content.
        
        Args:
            generation_id: ID of completed generation
            
        Returns:
            Video content as bytes, or None if not ready
            
        Raises:
            ProviderError: If download fails
        """
        pass
    
    @abstractmethod
    async def cancel_generation(self, generation_id: str) -> bool:
        """
        Cancel ongoing video generation.
        
        Args:
            generation_id: ID of generation to cancel
            
        Returns:
            True if cancellation successful, False otherwise
        """
        pass
    
    @abstractmethod
    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """
        Validate request parameters against provider capabilities.
        
        Args:
            request: Video generation request to validate
            
        Returns:
            True if request is valid for this provider
            
        Raises:
            ValueError: If request parameters are invalid
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get provider capabilities and limits.
        
        Returns:
            Dictionary with provider capabilities:
            - max_duration_seconds: Maximum video duration
            - max_resolution: Maximum resolution (width, height)
            - supports_image_input: Whether image input is supported
            - supported_formats: List of supported output formats
            - cost_per_second: Cost per second of video
        """
        pass
    
    def calculate_cost(self, request: VideoGenerationRequest) -> float:
        """
        Calculate estimated cost for video generation.
        
        Args:
            request: Video generation request
            
        Returns:
            Estimated cost in credits
        """
        capabilities = self.get_capabilities()
        base_cost = request.duration_seconds * capabilities.get('cost_per_second', 0.02)
        
        # Apply image input multiplier if applicable
        if request.image_url and capabilities.get('supports_image_input', False):
            image_multiplier = capabilities.get('image_cost_multiplier', 1.5)
            base_cost *= image_multiplier
        
        # Apply resolution multiplier
        resolution_multiplier = self._get_resolution_multiplier(
            request.resolution_width, 
            request.resolution_height
        )
        base_cost *= resolution_multiplier
        
        return round(base_cost, 2)
    
    def _get_resolution_multiplier(self, width: int, height: int) -> float:
        """Get cost multiplier based on resolution."""
        total_pixels = width * height
        
        if total_pixels <= 720 * 480:  # SD
            return 1.0
        elif total_pixels <= 1280 * 720:  # HD
            return 1.5
        elif total_pixels <= 1920 * 1080:  # Full HD
            return 2.0
        elif total_pixels <= 3840 * 2160:  # 4K
            return 3.0
        else:
            return 4.0  # Ultra HD
    
    async def health_check(self) -> bool:
        """
        Check if provider service is healthy.
        
        Returns:
            True if provider is accessible and healthy
        """
        try:
            # Each provider should implement specific health check
            # Default implementation returns True
            return True
        except Exception:
            return False

class ProviderError(Exception):
    """Exception raised by video providers."""
    
    def __init__(self, message: str, provider_name: str, error_code: Optional[str] = None):
        self.message = message
        self.provider_name = provider_name
        self.error_code = error_code
        super().__init__(f"[{provider_name}] {message}")

class ProviderTimeout(ProviderError):
    """Exception raised when provider request times out."""
    pass

class ProviderQuotaExceeded(ProviderError):
    """Exception raised when provider quota is exceeded."""
    pass

class ProviderInvalidRequest(ProviderError):
    """Exception raised when request parameters are invalid."""
    pass