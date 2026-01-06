"""
OpenAI Sora video generation provider implementation.
"""
from typing import Dict, Optional, Any, Tuple

import httpx

from .base import (
    BaseVideoProvider,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStatus,
    ProviderError,
    ProviderTimeout,
    ProviderQuotaExceeded,
)


class SoraProvider(BaseVideoProvider):
    """OpenAI Sora video generation provider."""

    # UI/alias -> API model id
    MODEL_MAP = {
        "sora-2": "sora-2",
        "SORA2": "sora-2",
        "Sora 2": "sora-2",
        "Sora 2 Turbo": "sora-2",
        "Sora 1.0 Turbo": "sora-2",  # часто UI так пишет — на API мапим в sora-2
        "sora2": "sora-2",
    }

    # что НЕ разрешаем перезаписывать из provider_specific_params
    RESERVED_KEYS = {"model", "prompt", "size", "seconds", "image_url"}

    # реальные размеры (по ошибке от API)
    # ВАЖНО: у тебя в одной ошибке было 4 размера, в другой — только 2.
    # Мы оставляем 4, а нормализацию делаем в 2 "безопасных" (720x1280 / 1280x720).
    ALLOWED_SIZES = ("720x1280", "1280x720", "1024x1792", "1792x1024")
    SAFE_SIZES = ("720x1280", "1280x720")

    def __init__(self, api_key: str, api_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, api_url)
        self.name = "sora"
        # IMPORTANT: do NOT set Content-Type globally
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _normalize_model(self, model_value: Optional[str]) -> str:
        if not model_value:
            return "sora-2"
        m = str(model_value).strip()
        return self.MODEL_MAP.get(m, "sora-2")

    def _normalize_seconds(self, duration_seconds: Any) -> str:
        try:
            d = int(round(float(duration_seconds)))
        except Exception:
            d = 4

        if d <= 4:
            return "4"
        if d <= 8:
            return "8"
        return "12"

    def _normalize_size(self, w: Any, h: Any) -> str:
        """
        Sora-2 у тебя реально принимает только фиксированные size.
        Мы маппим любое входное разрешение в одно из SAFE_SIZES:
        - landscape -> 1280x720
        - portrait  -> 720x1280
        """
        try:
            ww = int(w)
            hh = int(h)
        except Exception:
            ww, hh = 1280, 720

        # защита от деления на 0
        if hh <= 0 or ww <= 0:
            return "1280x720"

        if ww >= hh:
            return "1280x720"
        return "720x1280"

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Start video generation with Sora."""
        self.validate_request(request)

        # normalize model from UI/provider params
        model_ui = (request.provider_specific_params or {}).get("model")
        model = self._normalize_model(model_ui)

        # normalize size for API
        normalized_size = self._normalize_size(request.resolution_width, request.resolution_height)

        # what we send
        req_payload: Dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            "size": normalized_size,
            "seconds": self._normalize_seconds(request.duration_seconds),
        }

        if request.image_url:
            req_payload["image_url"] = request.image_url

        # allow extra provider params BUT don't override reserved keys
        if request.provider_specific_params:
            for k, v in request.provider_specific_params.items():
                if k in self.RESERVED_KEYS:
                    continue
                req_payload[k] = v

        try:
            response = await self.client.post(f"{self.api_url}/videos", json=req_payload)

            if response.status_code == 429:
                raise ProviderQuotaExceeded("Rate limit or quota exceeded", self.name, "quota_exceeded")

            response.raise_for_status()
            resp_payload = response.json()

            sora_id = resp_payload.get("id")
            if not sora_id:
                raise ProviderError("Sora response missing id", self.name, "bad_response")

            status_raw = (resp_payload.get("status") or "").lower()
            status = VideoStatus.COMPLETED if status_raw == "completed" else VideoStatus.PROCESSING

            # progress sometimes absent
            progress_val = resp_payload.get("progress")
            try:
                progress = int(progress_val) if progress_val is not None else 0
            except Exception:
                progress = 0

            return VideoGenerationResponse(
                generation_id=sora_id,
                status=status,
                estimated_completion_time=int(request.duration_seconds) * 30,
                progress_percentage=progress,
                metadata={
                    "sora_job_id": sora_id,
                    "provider": "sora",
                    "model": resp_payload.get("model") or req_payload["model"],
                    # важно: возвращаем тот size, который реально отправили
                    "size": resp_payload.get("size") or req_payload["size"],
                    "seconds": resp_payload.get("seconds") or req_payload["seconds"],
                    "raw_status": resp_payload.get("status"),
                },
            )

        except httpx.TimeoutException:
            raise ProviderTimeout("Request timed out", self.name, "timeout")

        except httpx.HTTPStatusError as e:
            status_code = str(e.response.status_code)
            msg = "Unknown error"

            # Try to parse OpenAI-style error json
            try:
                raw = e.response.json()
                msg = raw.get("error", {}).get("message") or raw.get("message") or msg
            except Exception:
                try:
                    msg = (e.response.text or msg).strip()
                except Exception:
                    pass

            if e.response.status_code == 401:
                msg = "Invalid API key (401)"
            elif e.response.status_code == 403:
                msg = "Access denied / forbidden (403)"
            elif e.response.status_code == 404:
                msg = "Sora endpoint not found (404) — check API URL/path"
            elif e.response.status_code >= 500:
                msg = "Sora service temporarily unavailable (5xx)"

            raise ProviderError(msg, self.name, status_code)

        except Exception as e:
            raise ProviderError(f"Unexpected error: {str(e)}", self.name, "unexpected")

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        """Get status of video generation."""
        try:
            response = await self.client.get(f"{self.api_url}/videos/{generation_id}")
            response.raise_for_status()
            payload = response.json()

            status_raw = (payload.get("status") or "queued").lower()
            progress_val = payload.get("progress")
            try:
                progress = int(progress_val) if progress_val is not None else 0
            except Exception:
                progress = 0

            if status_raw == "completed":
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.COMPLETED,
                    progress_percentage=100,
                    metadata={"provider": "sora", "raw_status": status_raw},
                )

            if status_raw in ("failed", "canceled", "cancelled"):
                err = payload.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.FAILED,
                    progress_percentage=progress,
                    error_message=msg or "Video generation failed",
                    metadata={"provider": "sora", "raw_status": status_raw},
                )

            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.PROCESSING,
                progress_percentage=progress,
                metadata={"provider": "sora", "raw_status": status_raw},
            )

        except httpx.TimeoutException:
            raise ProviderTimeout("Status request timed out", self.name, "timeout")
        except Exception as e:
            raise ProviderError(f"Failed to get status: {str(e)}", self.name, "status_failed")

    async def download_video(self, generation_id: str) -> Optional[bytes]:
        """Download the generated video."""
        status_response = await self.get_status(generation_id)
        if status_response.status != VideoStatus.COMPLETED:
            return None

        try:
            r = await self.client.get(f"{self.api_url}/videos/{generation_id}/content")
            r.raise_for_status()
            return r.content
        except Exception as e:
            raise ProviderError(f"Failed to download video: {str(e)}", self.name, "download_failed")

    async def cancel_generation(self, generation_id: str) -> bool:
        """Cancel video generation."""
        try:
            # if you have a real cancel endpoint, implement it here
            return True
        except Exception:
            return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        """Validate request parameters for Sora."""
        capabilities = self.get_capabilities()

        if request.duration_seconds > capabilities["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum {capabilities['max_duration_seconds']}s for Sora"
            )
        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")

        # не валим по 1920x1080, потому что мы всё равно нормализуем size в generate_video()
        # но проверим аспект, чтобы совсем мусор не прилетал
        if request.resolution_width <= 0 or request.resolution_height <= 0:
            raise ValueError("Resolution must be positive")

        aspect_ratio = request.resolution_width / request.resolution_height
        valid_aspects = [16 / 9, 9 / 16]
        if not any(abs(aspect_ratio - v) < 0.15 for v in valid_aspects):
            # допускаем небольшой люфт
            raise ValueError("Aspect ratio not supported by Sora (expected ~16:9 or ~9:16)")

        if not request.prompt or not request.prompt.strip():
            raise ValueError("Prompt cannot be empty")
        if len(request.prompt) > 1000:
            raise ValueError("Prompt too long (max 1000 characters)")

        return True

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "max_duration_seconds": 20,
            "max_resolution": (1792, 1792),
            "supports_image_input": True,
            "supported_formats": ["mp4"],
            "cost_per_second": 0.05,
            "image_cost_multiplier": 1.8,
            "supported_resolutions": [
                "720x1280",
                "1280x720",
                "1024x1792",
                "1792x1024",
            ],
            "model_versions": ["sora-2"],
            "features": ["text-to-video", "image-to-video"],
        }

    async def health_check(self) -> bool:
        try:
            r = await self.client.get(f"{self.api_url}/models")
            return r.status_code == 200
        except Exception:
            return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
