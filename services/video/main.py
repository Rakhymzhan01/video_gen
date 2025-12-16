"""
Video Service - Handles video generation requests using multiple providers including Sora.
"""
import os
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from shared.database.connection import get_db, create_tables
from shared.database.models import Video, Provider, User, Image, ProviderType, JobStatus
# Note: Auth is handled by API Gateway, not directly in video service
from shared.providers import (
    create_provider, get_available_providers, VideoGenerationRequest as ProviderRequest, VideoStatus, 
    ProviderError, ProviderTimeout, ProviderQuotaExceeded
)
# S3 storage disabled for now

# Mock provider for development when API keys are not available
class MockProvider:
    def __init__(self, provider_type):
        self.name = provider_type
        self.provider_type = provider_type
    
    def validate_request(self, request):
        print(f"Mock validation for {self.provider_type}: OK")
        return True
    
    def calculate_cost(self, request):
        return request.duration_seconds * 0.01  # Mock cost
    
    async def generate_video(self, request):
        import uuid
        from shared.providers import VideoGenerationResponse, VideoStatus
        print(f"Mock video generation for {self.provider_type}")
        return VideoGenerationResponse(
            generation_id=str(uuid.uuid4()),
            status=VideoStatus.PROCESSING,
            progress_percentage=0,
            metadata={"provider": self.provider_type, "mock": True}
        )
    
    async def get_status(self, generation_id):
        from shared.providers import VideoGenerationResponse, VideoStatus
        print(f"Mock status check for {generation_id}")
        # Use a real playable sample video for testing
        sample_video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        return VideoGenerationResponse(
            generation_id=generation_id,
            status=VideoStatus.COMPLETED,
            progress_percentage=100,
            video_url=sample_video_url,
            metadata={"provider": self.provider_type, "mock": True, "note": "Sample video for testing"}
        )
    
    async def download_video(self, generation_id):
        print(f"Mock video download for {generation_id}")
        return b"mock video content"  # Mock video bytes

# Initialize FastAPI app
app = FastAPI(
    title="Video Generation Service",
    description="AI-powered video generation with multiple provider support",
    version="1.0.0"
)

# S3 storage disabled

# Provider instances cache
provider_instances: Dict[str, Any] = {}

class VideoGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt for video generation")
    duration_seconds: int = Field(default=5, ge=1, le=20, description="Video duration in seconds")
    resolution_width: int = Field(default=1920, ge=256, le=1920, description="Video width in pixels")
    resolution_height: int = Field(default=1080, ge=256, le=1080, description="Video height in pixels")
    fps: int = Field(default=24, ge=12, le=60, description="Frames per second")
    provider: str = Field(default="sora", description="Video generation provider")
    image_id: Optional[str] = Field(None, description="Optional image ID for image-to-video generation")
    provider_specific_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Provider-specific parameters")

class VideoGenerationResponse(BaseModel):
    id: str
    status: str
    progress_percentage: int
    estimated_completion_time: Optional[int] = None
    error_message: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    credits_cost: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VideoListResponse(BaseModel):
    videos: List[VideoGenerationResponse]
    total: int
    page: int
    page_size: int

def get_provider_instance(provider_type: str, api_key: str = None) -> Any:
    """Get or create provider instance using factory pattern."""
    
    try:
        return create_provider(provider_type, api_key)
    except ValueError as e:
        print(f"Provider validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Provider error: {str(e)}")
    except RuntimeError as e:
        print(f"Provider runtime error: {e}")
        # For development, use mock provider if API key is missing or model not available
        if "API key not configured" in str(e) or provider_type in ["VEO3", "veo3"]:
            print(f"Using mock provider for {provider_type} (Veo models not available with current API key)")
            return MockProvider(provider_type)
        raise HTTPException(status_code=500, detail=f"Provider setup failed: {str(e)}")

async def process_video_generation(
    video_id: str, 
    generation_request: VideoGenerationRequest,
    image_url: Optional[str] = None
):
    """Background task to process video generation."""
    
    db = next(get_db())
    try:
        # Get video record
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
        
        # Get provider instance
        provider = get_provider_instance(generation_request.provider)
        
        # Create provider request
        provider_request = ProviderRequest(
            prompt=generation_request.prompt,
            duration_seconds=generation_request.duration_seconds,
            resolution_width=generation_request.resolution_width,
            resolution_height=generation_request.resolution_height,
            fps=generation_request.fps,
            image_url=image_url,
            provider_specific_params=generation_request.provider_specific_params
        )
        
        # Start generation
        video.status = JobStatus.PROCESSING
        video.started_at = datetime.utcnow()
        db.commit()
        
        try:
            response = await provider.generate_video(provider_request)
            
            # Update video with provider job ID
            video.provider_job_id = response.metadata.get("sora_job_id")
            db.commit()
            
            # Poll for completion
            max_attempts = 120  # 10 minutes with 5-second intervals
            attempt = 0
            
            while attempt < max_attempts:
                await asyncio.sleep(5)
                attempt += 1
                
                status_response = await provider.get_status(response.generation_id)
                
                # Update progress
                video.progress_percentage = status_response.progress_percentage
                db.commit()
                
                if status_response.status == VideoStatus.COMPLETED:
                    # Download video
                    video_content = await provider.download_video(response.generation_id)
                    
                    if video_content:
                        # For now, just mark as completed without file storage
                        video.status = JobStatus.COMPLETED
                        video.completed_at = datetime.utcnow()
                        video.file_size = len(video_content)
                        video.actual_duration = Decimal(str(generation_request.duration_seconds))
                        
                        # TODO: Implement file storage when needed
                        print(f"Video generated successfully: {len(video_content)} bytes")
                        
                        db.commit()
                        break
                    else:
                        video.status = JobStatus.FAILED
                        video.error_message = "Failed to download generated video"
                        db.commit()
                        break
                        
                elif status_response.status == VideoStatus.FAILED:
                    video.status = JobStatus.FAILED
                    video.error_message = status_response.error_message or "Video generation failed"
                    db.commit()
                    break
            
            else:
                # Timeout
                video.status = JobStatus.FAILED
                video.error_message = "Video generation timed out"
                db.commit()
                
        except (ProviderError, ProviderTimeout, ProviderQuotaExceeded) as e:
            video.status = JobStatus.FAILED
            video.error_message = str(e)
            db.commit()
            
    except Exception as e:
        # Update video with error
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = JobStatus.FAILED
            video.error_message = f"Internal error: {str(e)}"
            db.commit()
    
    finally:
        db.close()

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database and providers on startup."""
    create_tables()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    providers_info = get_available_providers()
    
    return {
        "status": "healthy",
        "service": "video-service",
        "providers": {
            name: info["available"] 
            for name, info in providers_info.items()
        }
    }

@app.get("/providers")
async def list_providers():
    """Get list of available providers and their capabilities."""
    return get_available_providers()

@app.get("/providers-public")  
async def list_providers_public():
    """Public endpoint to get list of available providers (no auth required)."""
    return get_available_providers()

@app.post("/generate", response_model=VideoGenerationResponse)
async def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    current_request: Request,
    db: Session = Depends(get_db)
):
    """Generate a video using the specified provider."""
    
    # Get user from headers (set by API gateway)
    user_id = current_request.headers.get("X-User-ID")
    user_email = current_request.headers.get("X-User-Email")
    user_tier = current_request.headers.get("X-User-Tier", "free")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Get or validate provider
    provider_record = db.query(Provider).filter(
        Provider.type == request.provider,
        Provider.is_active == True
    ).first()
    
    if not provider_record:
        raise HTTPException(status_code=400, detail=f"Provider {request.provider} not available")
    
    # Get provider instance to validate request and calculate cost
    try:
        provider = get_provider_instance(request.provider)
        
        # Create provider request for validation
        image_url = None
        if request.image_id:
            image = db.query(Image).filter(
                and_(Image.id == request.image_id, Image.user_id == user_id)
            ).first()
            if not image:
                raise HTTPException(status_code=404, detail="Image not found")
            # For now, skip image URL since S3 is not configured
            image_url = None  # TODO: Implement when S3 is setup
        
        provider_request = ProviderRequest(
            prompt=request.prompt,
            duration_seconds=request.duration_seconds,
            resolution_width=request.resolution_width,
            resolution_height=request.resolution_height,
            fps=request.fps,
            image_url=image_url,
            provider_specific_params=request.provider_specific_params
        )
        
        # Validate request
        provider.validate_request(provider_request)
        
        # Calculate cost
        credits_cost = provider.calculate_cost(provider_request)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Provider validation failed: {str(e)}")
    
    # Check user credits
    if user.credits_balance < Decimal(str(credits_cost)):
        raise HTTPException(
            status_code=402, 
            detail=f"Insufficient credits. Required: {credits_cost}, Available: {user.credits_balance}"
        )
    
    # Deduct credits
    user.credits_balance -= Decimal(str(credits_cost))
    
    # Create video record
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id,
        user_id=user_id,
        image_id=request.image_id,
        provider_id=provider_record.id,
        prompt=request.prompt,
        duration_seconds=request.duration_seconds,
        resolution_width=request.resolution_width,
        resolution_height=request.resolution_height,
        fps=request.fps,
        status=JobStatus.PENDING,
        credits_cost=Decimal(str(credits_cost))
    )
    
    db.add(video)
    db.commit()
    
    # Start background processing
    background_tasks.add_task(
        process_video_generation, 
        video_id, 
        request, 
        image_url
    )
    
    return VideoGenerationResponse(
        id=video_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
        estimated_completion_time=request.duration_seconds * 30,
        credits_cost=credits_cost,
        metadata={
            "provider": request.provider,
            "resolution": f"{request.resolution_width}x{request.resolution_height}",
            "duration": request.duration_seconds
        }
    )

@app.get("/{video_id}/status", response_model=VideoGenerationResponse)
async def get_video_status(
    video_id: str,
    current_request: Request,
    db: Session = Depends(get_db)
):
    """Get status of video generation."""
    
    # Get user from headers
    user_id = current_request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get video
    video = db.query(Video).filter(
        and_(Video.id == video_id, Video.user_id == user_id)
    ).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # For now, return sample video URL since S3 is not configured
    video_url = None
    thumbnail_url = None
    
    if video.status == JobStatus.COMPLETED:
        # Use a real playable sample video for testing
        video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    
    return VideoGenerationResponse(
        id=str(video.id),
        status=video.status.value,
        progress_percentage=video.progress_percentage,
        error_message=video.error_message,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        credits_cost=float(video.credits_cost),
        metadata={
            "provider": video.provider.type.value if video.provider else "unknown",
            "resolution": f"{video.resolution_width}x{video.resolution_height}",
            "duration": video.duration_seconds,
            "created_at": video.created_at.isoformat(),
            "completed_at": video.completed_at.isoformat() if video.completed_at else None
        }
    )

@app.get("/", response_model=VideoListResponse)
async def list_user_videos(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    current_request: Request = None,
    db: Session = Depends(get_db)
):
    """List user's videos with pagination."""
    
    # Get user from headers
    user_id = current_request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Build query
    query = db.query(Video).filter(Video.user_id == user_id)
    
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.filter(Video.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * page_size
    videos = query.order_by(Video.created_at.desc()).offset(offset).limit(page_size).all()
    
    # Convert to response format
    video_responses = []
    for video in videos:
        video_url = None
        thumbnail_url = None
        
        if video.status == JobStatus.COMPLETED:
            # Use a real playable sample video for testing
            video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        
        video_responses.append(VideoGenerationResponse(
            id=str(video.id),
            status=video.status.value,
            progress_percentage=video.progress_percentage,
            error_message=video.error_message,
            video_url=video_url,
            thumbnail_url=thumbnail_url,
            credits_cost=float(video.credits_cost),
            metadata={
                "provider": video.provider.type.value if video.provider else "unknown",
                "resolution": f"{video.resolution_width}x{video.resolution_height}",
                "duration": video.duration_seconds,
                "created_at": video.created_at.isoformat(),
                "completed_at": video.completed_at.isoformat() if video.completed_at else None
            }
        ))
    
    return VideoListResponse(
        videos=video_responses,
        total=total,
        page=page,
        page_size=page_size
    )

@app.delete("/{video_id}")
async def delete_video(
    video_id: str,
    current_request: Request,
    db: Session = Depends(get_db)
):
    """Delete a video and its associated files."""
    
    # Get user from headers
    user_id = current_request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get video
    video = db.query(Video).filter(
        and_(Video.id == video_id, Video.user_id == user_id)
    ).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # S3 file deletion disabled since S3 is not configured
    print(f"Video {video_id} deletion requested (S3 disabled)")
    
    # Delete from database
    db.delete(video)
    db.commit()
    
    return {"message": "Video deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)