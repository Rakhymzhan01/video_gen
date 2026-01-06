"""
Video Service - Handles video generation requests using multiple providers including Sora.
"""
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from shared.database.connection import get_db, create_tables
from shared.database.models import Video, Provider, User, Image, JobStatus
from shared.providers import (
    create_provider, get_available_providers,
    VideoGenerationRequest as ProviderRequest,
    VideoStatus,
    ProviderError, ProviderTimeout, ProviderQuotaExceeded
)
from shared.storage.s3_client import storage_client  # ✅ add

app = FastAPI(
    title="Video Generation Service",
    description="AI-powered video generation with multiple provider support",
    version="1.0.0"
)

provider_instances: Dict[str, Any] = {}


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt for video generation")
    duration_seconds: int = Field(default=5, ge=1, le=20, description="Video duration in seconds")
    resolution_width: int = Field(default=1920, ge=256, le=1920, description="Video width in pixels")
    resolution_height: int = Field(default=1080, ge=256, le=1920, description="Video height in pixels")
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
    key = f"{provider_type}:{api_key or ''}"
    if key in provider_instances:
        return provider_instances[key]
    try:
        inst = create_provider(provider_type, api_key)
        provider_instances[key] = inst
        return inst
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Provider error: {str(e)}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Provider setup failed: {str(e)}")


def _normalize_provider_url(url: str) -> str:
    """
    Some providers may return:
    - absolute url: https://...
    - protocol-relative: //...
    - relative path: /files/...
    For absolute and protocol-relative we keep it,
    for relative we keep it as-is (gateway will redirect to it if needed).
    """
    if not url:
        return url
    u = str(url).strip()
    if u.startswith("//"):
        return "https:" + u
    return u


async def process_video_generation(video_id: str, generation_request: VideoGenerationRequest, image_url: Optional[str] = None):
    db = next(get_db())
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return

        provider = get_provider_instance(generation_request.provider)

        provider_request = ProviderRequest(
            prompt=generation_request.prompt,
            duration_seconds=generation_request.duration_seconds,
            resolution_width=generation_request.resolution_width,
            resolution_height=generation_request.resolution_height,
            fps=generation_request.fps,
            image_url=image_url,
            provider_specific_params=generation_request.provider_specific_params
        )

        video.status = JobStatus.PROCESSING
        video.started_at = datetime.utcnow()
        db.commit()

        try:
            response = await provider.generate_video(provider_request)

            # id джобы провайдера
            video.provider_job_id = response.metadata.get("sora_job_id") or response.generation_id
            db.commit()

            max_attempts = 120  # 120 * 5s = 10 min
            for _ in range(max_attempts):
                await asyncio.sleep(5)

                status_response = await provider.get_status(response.generation_id)

                video.progress_percentage = status_response.progress_percentage
                db.commit()

                if status_response.status == VideoStatus.COMPLETED:
                    # скачиваем байты видео от провайдера
                    video_content = await provider.download_video(response.generation_id)

                    if not video_content:
                        video.status = JobStatus.FAILED
                        video.error_message = "Failed to download generated video"
                        db.commit()
                        return

                    # ✅ upload to MinIO/S3
                    s3_key = f"videos/{video.user_id}/{video.id}/generated.mp4"
                    ok = storage_client.upload_file(
                        file_data=BytesIO(video_content),
                        key=s3_key,
                        content_type="video/mp4",
                        metadata={
                            "video_id": str(video.id),
                            "provider": str(generation_request.provider),
                        }
                    )
                    if not ok:
                        video.status = JobStatus.FAILED
                        video.error_message = "Failed to upload generated video to storage"
                        db.commit()
                        return

                    video.s3_key = s3_key
                    video.status = JobStatus.COMPLETED
                    video.completed_at = datetime.utcnow()
                    video.file_size = len(video_content)
                    video.actual_duration = Decimal(str(generation_request.duration_seconds))

                    # если провайдер вернул URL — сохраним (если есть)
                    if getattr(status_response, "video_url", None):
                        video.provider_video_id = _normalize_provider_url(status_response.video_url)

                    db.commit()
                    return

                if status_response.status == VideoStatus.FAILED:
                    video.status = JobStatus.FAILED
                    video.error_message = status_response.error_message or "Video generation failed"
                    db.commit()
                    return

            video.status = JobStatus.FAILED
            video.error_message = "Video generation timed out"
            db.commit()

        except (ProviderError, ProviderTimeout, ProviderQuotaExceeded) as e:
            video.status = JobStatus.FAILED
            video.error_message = str(e)
            db.commit()

    except Exception as e:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = JobStatus.FAILED
            video.error_message = f"Internal error: {str(e)}"
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    create_tables()


@app.get("/health")
async def health_check():
    providers_info = get_available_providers()
    return {
        "status": "healthy",
        "service": "video-service",
        "providers": {name: info["available"] for name, info in providers_info.items()}
    }


@app.get("/providers")
async def list_providers():
    return get_available_providers()


@app.get("/providers-public")
async def list_providers_public():
    return get_available_providers()


@app.post("/generate", response_model=VideoGenerationResponse)
async def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    current_request: Request,
    db: Session = Depends(get_db)
):
    user_id = current_request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    provider_map = {
        "SORA2": "SORA",
        "SORA": "SORA",
        "sora": "SORA",
        "VEO3": "VEO3",
        "veo3": "VEO3",
        "WAN": "WAN",
        "wan": "WAN",
        "KLING": "KLING",
        "kling": "KLING",
    }
    request.provider = provider_map.get(request.provider, request.provider)

    provider_record = db.query(Provider).filter(
        Provider.type == request.provider,
        Provider.is_active == True
    ).first()
    if not provider_record:
        raise HTTPException(status_code=400, detail=f"Provider {request.provider} not available")

    image_url = None
    if request.image_id:
        image = db.query(Image).filter(and_(Image.id == request.image_id, Image.user_id == user_id)).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        image_url = None  # TODO: when S3 exists

    try:
        provider = get_provider_instance(request.provider)

        provider_request = ProviderRequest(
            prompt=request.prompt,
            duration_seconds=request.duration_seconds,
            resolution_width=request.resolution_width,
            resolution_height=request.resolution_height,
            fps=request.fps,
            image_url=image_url,
            provider_specific_params=request.provider_specific_params
        )

        provider.validate_request(provider_request)
        credits_cost = provider.calculate_cost(provider_request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Provider validation failed: {str(e)}")

    if user.credits_balance < Decimal(str(credits_cost)):
        raise HTTPException(status_code=402, detail=f"Insufficient credits. Required: {credits_cost}, Available: {user.credits_balance}")

    user.credits_balance -= Decimal(str(credits_cost))

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

    background_tasks.add_task(process_video_generation, video_id, request, image_url)

    return VideoGenerationResponse(
        id=video_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
        estimated_completion_time=request.duration_seconds * 30,
        credits_cost=float(credits_cost),
        metadata={
            "provider": request.provider,
            "resolution": f"{request.resolution_width}x{request.resolution_height}",
            "duration": request.duration_seconds
        }
    )


@app.get("/{video_id}/status", response_model=VideoGenerationResponse)
async def get_video_status(video_id: str, current_request: Request, db: Session = Depends(get_db)):
    user_id = current_request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    video = db.query(Video).filter(and_(Video.id == video_id, Video.user_id == user_id)).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video_url = None
    if video.status == JobStatus.COMPLETED:
        # 1) если провайдер дал URL -> отдаём его
        if getattr(video, "provider_video_id", None):
            video_url = _normalize_provider_url(video.provider_video_id)

        # 2) иначе если есть s3_key -> отдаём FILE на ЭТОМ сервисе
        elif getattr(video, "s3_key", None):
            # ВАЖНО: НЕ "/api/v1/videos/.../file" (это путь gateway и даёт петлю)
            # Тут отдаём путь video-service:
            video_url = f"/{video_id}/file"

    return VideoGenerationResponse(
        id=str(video.id),
        status=video.status.value,
        progress_percentage=video.progress_percentage,
        error_message=video.error_message,
        video_url=video_url,
        thumbnail_url=None,
        credits_cost=float(video.credits_cost),
        metadata={
            "provider": video.provider.type.value if video.provider else "unknown",
            "resolution": f"{video.resolution_width}x{video.resolution_height}",
            "duration": video.duration_seconds,
            "created_at": video.created_at.isoformat(),
            "completed_at": video.completed_at.isoformat() if video.completed_at else None
        }
    )


# ✅ FIXED: stream file from MinIO/S3
# - Если есть X-User-ID -> проверяем владельца (как раньше)
# - Если X-User-ID НЕТ -> разрешаем публичную отдачу (чтобы <video> работал без Bearer)
@app.get("/{video_id}/file")
async def stream_video_file(video_id: str, current_request: Request, db: Session = Depends(get_db)):
    user_id = current_request.headers.get("X-User-ID")

    if user_id:
        # приватный режим (через gateway): проверяем владельца
        video = db.query(Video).filter(and_(Video.id == video_id, Video.user_id == user_id)).first()
    else:
        # публичный режим (браузер <video> без auth): просто по video_id
        video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status != JobStatus.COMPLETED or not video.s3_key:
        raise HTTPException(status_code=404, detail="Video file not available yet")

    data = storage_client.download_file(video.s3_key)
    if not data:
        raise HTTPException(status_code=404, detail="Video file not found in storage")

    return StreamingResponse(
        iter([data]),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{video_id}.mp4"',
            # полезно для браузеров
            "Cache-Control": "private, max-age=0, no-cache",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

