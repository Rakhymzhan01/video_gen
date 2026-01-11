"""
API Gateway - Main entry point for all client requests.
Routes requests to appropriate microservices.
"""
import os
import time
from typing import Optional, Any, AsyncIterator, Dict, Tuple, List

import httpx
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from shared.database.connection import create_tables
from shared.database.models import User
from shared.auth.dependencies import get_current_user, get_current_user_optional

app = FastAPI(
    title="Video Generation Platform",
    description="AI-powered video generation platform with multi-provider support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

origins = [
    "https://duutzduutz.com",
    "https://www.duutzduutz.com",
]

if os.getenv("ENVIRONMENT") == "development":
    origins += ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL", "http://image-service:8002")
VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://video-service:8003")
BILLING_SERVICE_URL = os.getenv("BILLING_SERVICE_URL", "http://billing-service:8004")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8005")

# общий клиент (для JSON/обычных запросов)
http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0))
rate_limit_storage = {}


def _get_cookie_token(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if token and isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _scope_get_header(scope_headers: List[Tuple[bytes, bytes]], name: str) -> Optional[str]:
    """
    Read header from request.scope["headers"] WITHOUT touching request.headers (it caches).
    """
    key = name.lower().encode("utf-8")
    for k, v in scope_headers:
        if k == key:
            try:
                return v.decode("utf-8")
            except Exception:
                return None
    return None


def _scope_has_authorization(scope_headers: List[Tuple[bytes, bytes]]) -> bool:
    return _scope_get_header(scope_headers, "authorization") is not None


@app.middleware("http")
async def cookie_to_auth_header_middleware(request: Request, call_next):
    """
    IMPORTANT FIX:
    Do NOT use request.headers here (it is cached).
    Work directly with request.scope["headers"].
    """
    scope_headers = list(request.scope.get("headers", []))

    if not _scope_has_authorization(scope_headers):
        token = _get_cookie_token(request)
        if token:
            scope_headers.append((b"authorization", f"Bearer {token}".encode("utf-8")))
            request.scope["headers"] = scope_headers

    return await call_next(request)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    print(f"📨 {request.method} {request.url.path} - {request.client.host if request.client else 'unknown'}")
    response = await call_next(request)
    process_time = time.time() - start_time
    print(f"⏱️  {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    return response


@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    cutoff_time = current_time - 60
    rate_limit_storage[client_ip] = [
        timestamp for timestamp in rate_limit_storage.get(client_ip, [])
        if timestamp > cutoff_time
    ]

    if len(rate_limit_storage.get(client_ip, [])) >= 60:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Try again later."}
        )

    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []
    rate_limit_storage[client_ip].append(current_time)

    return await call_next(request)


@app.on_event("startup")
async def startup_event():
    create_tables()


@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway", "timestamp": time.time()}


async def forward_request(
    request: Request,
    service_url: str,
    path: str,
    user: Optional[User] = None
):
    """
    Forward request to downstream service.
    Supports non-JSON (video/mp4, images, etc) responses.
    """
    headers = dict(request.headers)
    if user:
        headers["X-User-ID"] = str(user.id)
        headers["X-User-Email"] = user.email
        headers["X-User-Tier"] = user.subscription_tier.value

    headers.pop("host", None)
    headers.pop("content-length", None)

    url = f"{service_url}{path}"
    method = request.method
    params = dict(request.query_params)

    try:
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")

            if "application/json" in content_type:
                body = await request.json()
                resp = await http_client.request(method, url, json=body, headers=headers, params=params)
            elif "multipart/form-data" in content_type:
                form_data = await request.form()
                files = {}
                data = {}
                for key, value in form_data.items():
                    if hasattr(value, "file"):
                        files[key] = (value.filename, value.file, value.content_type)
                    else:
                        data[key] = value
                resp = await http_client.request(method, url, files=files, data=data, headers=headers, params=params)
            else:
                body = await request.body()
                resp = await http_client.request(method, url, content=body, headers=headers, params=params)
        else:
            resp = await http_client.request(method, url, headers=headers, params=params)

        content_type = resp.headers.get("content-type", "")
        response_headers = dict(resp.headers)
        response_headers.pop("content-length", None)

        if content_type.startswith("application/json"):
            return JSONResponse(content=resp.json(), status_code=resp.status_code, headers=response_headers)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
            media_type=content_type.split(";")[0] if content_type else None
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=f"Service timeout: {service_url}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Service unavailable: {str(e)}")


def _build_user_headers(user: User) -> Dict[str, str]:
    return {
        "X-User-ID": str(user.id),
        "X-User-Email": user.email,
        "X-User-Tier": user.subscription_tier.value,
    }


def _pass_range_headers(request: Request) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for h in ["range", "if-range"]:
        v = request.headers.get(h) or request.headers.get(h.title())
        if v:
            out[h.title()] = v
    return out


@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def auth_proxy(request: Request, path: str):
    normalized = path.strip("/").lower()

    if request.method == "POST" and normalized in ("login", "refresh"):
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)

        headers.pop("authorization", None)
        headers.pop("Authorization", None)

        url = f"{AUTH_SERVICE_URL}/{path}"
        params = dict(request.query_params)

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            resp = await http_client.request("POST", url, json=body, headers=headers, params=params)
        else:
            raw = await request.body()
            resp = await http_client.request("POST", url, content=raw, headers=headers, params=params)

        response_headers = dict(resp.headers)
        response_headers.pop("content-length", None)

        data: Any
        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
        else:
            data = resp.text

        out = JSONResponse(content=data, status_code=resp.status_code, headers=response_headers)

        if isinstance(data, dict):
            token = data.get("access_token") or data.get("token")
            if token:
                out.set_cookie(
                    key="access_token",
                    value=str(token),
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    path="/",
                    domain=".duutzduutz.com",
                )
        return out

    return await forward_request(request, AUTH_SERVICE_URL, f"/{path}")


@app.api_route("/api/v1/images/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def images_proxy(request: Request, path: str, user: User = Depends(get_current_user)):
    return await forward_request(request, IMAGE_SERVICE_URL, f"/{path}", user)


@app.get("/api/v1/images/view/{image_id}")
async def view_image_proxy(request: Request, image_id: str, user: Optional[User] = Depends(get_current_user_optional)):
    return await forward_request(request, IMAGE_SERVICE_URL, f"/view/{image_id}", user)


@app.post("/api/v1/videos/generate-public")
@app.post("/api/v1/videos/generate-public/")
async def generate_video_public_proxy(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
):
    return await forward_request(request, VIDEO_SERVICE_URL, "/generate", user)


@app.get("/api/v1/videos/{video_id}/status-public")
@app.get("/api/v1/videos/{video_id}/status-public/")
async def video_status_public_proxy(
    request: Request,
    video_id: str,
    user: Optional[User] = Depends(get_current_user_optional),
):
    return await forward_request(request, VIDEO_SERVICE_URL, f"/{video_id}/status", user)


# ✅ FIX: file endpoint must be PUBLIC-friendly and must NOT depend on /status
# - user optional
# - direct stream from video-service /{video_id}/file
@app.get("/api/v1/videos/{video_id}/file")
@app.get("/api/v1/videos/{video_id}/file/")
async def video_file_proxy(
    request: Request,
    video_id: str,
    user: Optional[User] = Depends(get_current_user_optional),
):
    target_url = f"{VIDEO_SERVICE_URL}/{video_id}/file"

    upstream_headers: Dict[str, str] = {}
    if user:
        upstream_headers.update(_build_user_headers(user))

    upstream_headers.update(_pass_range_headers(request))

    stream_timeout = httpx.Timeout(60.0, read=3600.0)

    async def streamer() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            async with client.stream("GET", target_url, headers=upstream_headers, follow_redirects=True) as upstream:
                async for chunk in upstream.aiter_bytes():
                    yield chunk

    async with httpx.AsyncClient(timeout=stream_timeout) as client:
        async with client.stream("GET", target_url, headers=upstream_headers, follow_redirects=True) as upstream:
            out_headers: Dict[str, str] = {}
            for h in [
                "content-type",
                "content-length",
                "accept-ranges",
                "content-range",
                "etag",
                "last-modified",
                "cache-control",
                "content-disposition",
            ]:
                v = upstream.headers.get(h)
                if v:
                    out_headers[h] = v

            media_type = upstream.headers.get("content-type", "video/mp4").split(";")[0]
            status_code = upstream.status_code

    return StreamingResponse(
        streamer(),
        status_code=status_code,
        headers=out_headers,
        media_type=media_type,
    )


@app.get("/api/v1/videos/providers-public")
@app.get("/api/v1/videos/providers-public/")
async def video_providers_public_proxy(request: Request):
    return await forward_request(request, VIDEO_SERVICE_URL, "/providers-public")


@app.api_route("/api/v1/videos/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def videos_proxy(request: Request, path: str, user: User = Depends(get_current_user)):
    return await forward_request(request, VIDEO_SERVICE_URL, f"/{path}", user)


@app.api_route("/api/v1/billing/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def billing_proxy(request: Request, path: str, user: User = Depends(get_current_user)):
    return await forward_request(request, BILLING_SERVICE_URL, f"/{path}", user)


@app.api_route("/api/v1/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def notifications_proxy(request: Request, path: str, user: User = Depends(get_current_user)):
    return await forward_request(request, NOTIFICATION_SERVICE_URL, f"/{path}", user)


@app.api_route("/api/v1/webhooks/{path:path}", methods=["POST"])
async def webhooks_proxy(request: Request, path: str):
    return await forward_request(request, NOTIFICATION_SERVICE_URL, f"/webhooks/{path}")


@app.get("/api/v1/user/profile")
async def get_user_profile(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "subscription_tier": user.subscription_tier.value,
        "credits_balance": float(user.credits_balance),
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


@app.get("/api/v1/docs/openapi.json")
async def get_openapi_spec():
    return app.openapi()
