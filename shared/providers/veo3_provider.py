"""
Google Veo video generation provider via Gemini API (generativelanguage.googleapis.com v1beta).

REST flow:
- POST /v1beta/models/{model}:predictLongRunning?key=API_KEY -> returns {"name": ".../operations/XXXX"}
- GET  /v1beta/{operation_name}?key=API_KEY                 -> returns {"done": bool, ...}

Notes:
- Response schema may evolve; we try multiple fields to extract a video URL / output URI.
"""

from typing import Dict, Optional, Any, Tuple
import json
from urllib.parse import urlparse, parse_qs

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


class Veo3Provider(BaseVideoProvider):
    """Google Veo video generation provider."""

    # UI can send 5s; for some preview models durations are constrained.
    ALLOWED_DURATIONS = {4, 6, 8}

    DEFAULT_MODEL = "models/veo-3.1-fast-generate-preview"

    def __init__(self, api_key: str, api_url: str = "https://generativelanguage.googleapis.com/v1beta"):
        super().__init__(api_key, api_url)
        self.name = "veo3"

        # Client ONLY for Veo/Gemini API (needs ?key=)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=20.0),
            params={"key": self.api_key},  # Google AI Studio key uses query param
            follow_redirects=True,
        )

    # -------------------------
    # Helpers
    # -------------------------
    def _normalize_duration(self, d: Any) -> int:
        try:
            d = int(d)
        except Exception:
            return 4
        if d in self.ALLOWED_DURATIONS:
            return d
        allowed = sorted(self.ALLOWED_DURATIONS)
        return min(allowed, key=lambda x: (abs(x - d), x))

    def _get_aspect_ratio_string(self, width: int, height: int) -> str:
        ar = width / max(1, height)
        if abs(ar - 16 / 9) < 0.1:
            return "16:9"
        if abs(ar - 9 / 16) < 0.1:
            return "9:16"
        return "16:9"

    def _extract_base64_image(self, image_str: str) -> Tuple[str, str]:
        """
        Accepts:
        - raw base64
        - data URL: data:image/png;base64,....
        Returns: (base64_string, mime_type)
        """
        s = (image_str or "").strip()
        if s.startswith("data:"):
            head, b64 = s.split(",", 1)
            mime = "image/jpeg"
            try:
                mime = head.split(";")[0].split(":", 1)[1]
            except Exception:
                pass
            return b64.strip(), mime
        return s, "image/jpeg"

    def _extract_video_url_from_operation(self, op_json: Dict[str, Any]) -> Optional[str]:
        """
        Tries to find a direct downloadable URL in completed operation response.
        Handles multiple known schemas.
        """
        resp = op_json.get("response") or op_json.get("result") or op_json

        # --- (A) NEW REAL SCHEMA you have:
        # response.generateVideoResponse.generatedSamples[0].video.uri
        try:
            gvr = resp.get("generateVideoResponse") or resp.get("generate_video_response") or {}
            if isinstance(gvr, dict):
                samples = gvr.get("generatedSamples") or gvr.get("generated_samples")
                if isinstance(samples, list) and samples:
                    v = (samples[0] or {}).get("video") or {}
                    if isinstance(v, dict):
                        uri = v.get("uri") or v.get("url")
                        if uri:
                            return uri
        except Exception:
            pass

        # --- (B) other possible schemas:
        # response.generatedVideos[0].video.uri
        try:
            gvs = resp.get("generatedVideos") or resp.get("generated_videos")
            if isinstance(gvs, list) and gvs:
                v = (gvs[0] or {}).get("video") or {}
                uri = v.get("uri") or v.get("url")
                if uri:
                    return uri
        except Exception:
            pass

        # response.videos[0].uri
        try:
            vids = resp.get("videos")
            if isinstance(vids, list) and vids:
                uri = (vids[0] or {}).get("uri") or (vids[0] or {}).get("url")
                if uri:
                    return uri
        except Exception:
            pass

        # common single fields
        for k in (
            "outputVideoUri",
            "output_video_uri",
            "videoUri",
            "video_uri",
            "videoUrl",
            "video_url",
            "uri",
            "url",
        ):
            if isinstance(resp, dict) and resp.get(k):
                return resp.get(k)

        return None

    def _extract_output_uri_from_operation(self, op_json: Dict[str, Any]) -> Optional[str]:
        """
        Tries to find output storage URI (GCS / etc.) in completed operation response.
        """
        resp = op_json.get("response") or op_json.get("result") or op_json

        for k in (
            "outputUri",
            "output_uri",
            "outputVideoUri",
            "output_video_uri",
            "gcsUri",
            "gcs_uri",
            "gsUri",
            "gs_uri",
        ):
            if isinstance(resp, dict) and resp.get(k):
                return resp.get(k)

        try:
            out = resp.get("output") or resp.get("outputs") or {}
            if isinstance(out, dict):
                for k in ("uri", "gcsUri", "outputUri"):
                    if out.get(k):
                        return out.get(k)
        except Exception:
            pass

        return None

    def _as_operation_name(self, s: str) -> Optional[str]:
        """
        Accepts:
        - "models/.../operations/xxx"
        - "operations/xxx"
        Returns normalized op name that can be GETed as /v1beta/{op_name}
        """
        if not s:
            return None
        s = str(s).strip()
        if "/operations/" in s:
            return s
        if s.startswith("operations/"):
            return s
        return None

    def _is_signed_url(self, url: str) -> bool:
        """
        Detect signed URLs (GCS / S3). Adding extra query params breaks them.
        """
        try:
            q = parse_qs(urlparse(url).query)
            if "X-Goog-Signature" in q or "X-Goog-Credential" in q:
                return True
            if "X-Amz-Signature" in q or "X-Amz-Credential" in q:
                return True
        except Exception:
            pass
        return False

    async def _download_bytes(self, url: str) -> bytes:
        """
        Download video bytes safely:
        - If it's Veo/Gemini file endpoint -> use self.client (needs key in query)
        - If it's signed URL -> use raw client WITHOUT adding params
        - Else -> raw client
        """
        if not url:
            raise ProviderError("Empty video URL", self.name, "download_failed")

        if url.startswith("gs://"):
            raise ProviderError(f"Got GCS URI (not downloadable as HTTP): {url}", self.name, "download_failed")

        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        # Signed URL must be fetched WITHOUT adding any params
        if self._is_signed_url(url):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=30.0),
                follow_redirects=True,
            ) as raw:
                r = await raw.get(url)
                r.raise_for_status()
                return r.content

        # Veo/Gemini file endpoint often requires key, use self.client
        if "generativelanguage.googleapis.com" in host:
            r = await self.client.get(url)
            r.raise_for_status()
            return r.content

        # Default: raw HTTP fetch
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            follow_redirects=True,
        ) as raw:
            r = await raw.get(url)
            r.raise_for_status()
            return r.content

    # -------------------------
    # Provider methods
    # -------------------------
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        self.validate_request(request)

        request.duration_seconds = self._normalize_duration(request.duration_seconds)

        model = self.DEFAULT_MODEL
        if request.provider_specific_params and request.provider_specific_params.get("model"):
            m = str(request.provider_specific_params["model"]).strip()
            model = m if m.startswith("models/") else f"models/{m}"

        instance: Dict[str, Any] = {"prompt": request.prompt}

        if request.image_url:
            b64, mime = self._extract_base64_image(request.image_url)
            instance["image"] = {"imageBytes": b64, "mimeType": mime}

        parameters: Dict[str, Any] = {"sampleCount": 1}
        parameters["durationSeconds"] = request.duration_seconds
        parameters["aspectRatio"] = self._get_aspect_ratio_string(request.resolution_width, request.resolution_height)

        if request.provider_specific_params:
            p = request.provider_specific_params.get("parameters")
            if isinstance(p, dict):
                parameters.update(p)

        payload: Dict[str, Any] = {"instances": [instance], "parameters": parameters}

        model_name = model.split("models/", 1)[1] if model.startswith("models/") else model
        url = f"{self.api_url}/models/{model_name}:predictLongRunning"

        try:
            r = await self.client.post(url, json=payload, headers={"Content-Type": "application/json"})

            if r.status_code == 429:
                raise ProviderQuotaExceeded("Rate limit or quota exceeded", self.name, "quota_exceeded")
            if r.status_code == 403:
                msg = "Access denied or billing/quota issue"
                try:
                    j = r.json()
                    msg = j.get("error", {}).get("message", msg)
                except Exception:
                    pass
                raise ProviderError(msg, self.name, "403")
            if r.status_code == 401:
                raise ProviderError("Invalid API key", self.name, "401")

            r.raise_for_status()
            data = r.json()

            operation_name = data.get("name") or data.get("operation") or data.get("operationName")
            operation_name = self._as_operation_name(operation_name) or operation_name

            if not operation_name:
                raise ProviderError(f"Unexpected response (no operation name): {data}", self.name, "bad_response")

            generation_id = operation_name

            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.PROCESSING,
                estimated_completion_time=request.duration_seconds * 25,
                progress_percentage=0,
                metadata={
                    "provider": "veo3",
                    "model": model,
                    "veo_operation_name": operation_name,
                },
            )

        except httpx.TimeoutException:
            raise ProviderTimeout("Request timed out", self.name, "timeout")
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}"
            try:
                j = e.response.json()
                msg = j.get("error", {}).get("message", msg)
            except Exception:
                if e.response.text:
                    msg = e.response.text[:300]
            raise ProviderError(msg, self.name, str(e.response.status_code))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Unexpected error: {e}", self.name, "unknown_error")

    async def get_status(self, generation_id: str) -> VideoGenerationResponse:
        try:
            op_name = self._as_operation_name(generation_id)
            if not op_name:
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.PROCESSING,
                    progress_percentage=0,
                    metadata={"provider": "veo3", "note": "No operation name to poll"},
                )

            url = f"{self.api_url}/{op_name}"
            r = await self.client.get(url)

            if r.status_code == 429:
                raise ProviderQuotaExceeded("Rate limit or quota exceeded", self.name, "quota_exceeded")
            if r.status_code == 403:
                msg = "Access denied or billing/quota issue"
                try:
                    j = r.json()
                    msg = j.get("error", {}).get("message", msg)
                except Exception:
                    pass
                raise ProviderError(msg, self.name, "403")

            r.raise_for_status()
            op = r.json()

            if op.get("error") or bool(op.get("done")):
                try:
                    print("VEO3 OPERATION RAW:", json.dumps(op, ensure_ascii=False)[:5000])
                except Exception:
                    pass

            if op.get("error"):
                err = op["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.FAILED,
                    progress_percentage=0,
                    error_message=msg,
                    metadata={"provider": "veo3", "operation": op_name},
                )

            if not bool(op.get("done")):
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.PROCESSING,
                    progress_percentage=50,
                    metadata={"provider": "veo3", "operation": op_name},
                )

            video_url = self._extract_video_url_from_operation(op)
            output_uri = self._extract_output_uri_from_operation(op)

            if not video_url:
                # completed but no direct URL
                return VideoGenerationResponse(
                    generation_id=generation_id,
                    status=VideoStatus.COMPLETED,
                    progress_percentage=100,
                    video_url=None,
                    metadata={
                        "provider": "veo3",
                        "operation": op_name,
                        "output_uri": output_uri,
                        "note": "Completed without direct video_url; use output_uri/storage",
                    },
                )

            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.COMPLETED,
                progress_percentage=100,
                video_url=video_url,
                metadata={"provider": "veo3", "operation": op_name, "output_uri": output_uri},
            )

        except ProviderError as e:
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                progress_percentage=0,
                error_message=str(e),
                metadata={"provider": "veo3"},
            )
        except Exception as e:
            return VideoGenerationResponse(
                generation_id=generation_id,
                status=VideoStatus.FAILED,
                progress_percentage=0,
                error_message=str(e),
                metadata={"provider": "veo3"},
            )

    async def download_video(self, generation_id: str) -> Optional[bytes]:
        status = await self.get_status(generation_id)
        if status.status != VideoStatus.COMPLETED:
            return None
        if not status.video_url:
            return None
        try:
            return await self._download_bytes(status.video_url)
        except Exception as e:
            raise ProviderError(f"Failed to download video: {e}", self.name, "download_failed")

    async def cancel_generation(self, generation_id: str) -> bool:
        return False

    def validate_request(self, request: VideoGenerationRequest) -> bool:
        caps = self.get_capabilities()

        if request.duration_seconds <= 0:
            raise ValueError("Duration must be positive")
        if request.duration_seconds > caps["max_duration_seconds"]:
            raise ValueError(
                f"Duration {request.duration_seconds}s exceeds maximum {caps['max_duration_seconds']}s for Veo"
            )

        max_w, max_h = caps["max_resolution"]
        if request.resolution_width > max_w or request.resolution_height > max_h:
            raise ValueError(
                f"Resolution {request.resolution_width}x{request.resolution_height} exceeds maximum {max_w}x{max_h}"
            )

        ar = request.resolution_width / max(1, request.resolution_height)
        valid = [16 / 9, 9 / 16]
        if not any(abs(ar - v) < 0.1 for v in valid):
            raise ValueError("Veo supports only 16:9 and 9:16 aspect ratios")

        if not request.prompt or not request.prompt.strip():
            raise ValueError("Prompt cannot be empty")
        if len(request.prompt) > 2000:
            raise ValueError("Prompt too long (max 2000 characters)")

        return True

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "max_duration_seconds": 60,
            "max_resolution": (1920, 1080),
            "supports_image_input": True,
            "supported_formats": ["mp4"],
            "cost_per_second": 0.02,
            "image_cost_multiplier": 1.5,
            "supported_resolutions": ["1920x1080", "1080x1920"],
            "model_versions": ["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"],
            "supported_aspect_ratios": ["16:9", "9:16"],
            "features": ["text-to-video", "image-to-video", "fast_generation"],
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
