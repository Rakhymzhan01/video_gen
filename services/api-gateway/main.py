"""
API Gateway - Main entry point for all client requests.
Routes requests to appropriate microservices.
"""
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database.connection import get_db, create_tables
from shared.database.models import User
from shared.auth.dependencies import get_current_user, get_current_user_optional

# Initialize FastAPI app
app = FastAPI(
    title="Video Generation Platform",
    description="AI-powered video generation platform with multi-provider support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENVIRONMENT") == "development" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs (in production these would be service discovery)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL", "http://image-service:8002")
VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://video-service:8003")
BILLING_SERVICE_URL = os.getenv("BILLING_SERVICE_URL", "http://billing-service:8004")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8005")

# HTTP client for service communication
http_client = httpx.AsyncClient(timeout=30.0)

# Rate limiting storage (in production use Redis)
rate_limit_storage = {}

# Middleware for request logging and timing
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Log request
    print(f"📨 {request.method} {request.url.path} - {request.client.host if request.client else 'unknown'}")
    
    response = await call_next(request)
    
    # Log response time
    process_time = time.time() - start_time
    print(f"⏱️  {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    
    return response

# Middleware for rate limiting
@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Simple rate limiting (in production, use Redis with sliding window)
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Clean old entries (older than 1 minute)
    cutoff_time = current_time - 60
    rate_limit_storage[client_ip] = [
        timestamp for timestamp in rate_limit_storage.get(client_ip, [])
        if timestamp > cutoff_time
    ]
    
    # Check rate limit (60 requests per minute for anonymous users)
    if len(rate_limit_storage.get(client_ip, [])) >= 60:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Try again later."}
        )
    
    # Add current request
    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []
    rate_limit_storage[client_ip].append(current_time)
    
    response = await call_next(request)
    return response

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    create_tables()

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up HTTP client."""
    await http_client.aclose()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancer."""
    return {
        "status": "healthy",
        "service": "api-gateway",
        "timestamp": time.time()
    }

# Service health check
@app.get("/health/services")
async def services_health_check():
    """Check health of all downstream services."""
    services = {
        "auth": AUTH_SERVICE_URL,
        "image": IMAGE_SERVICE_URL,
        "video": VIDEO_SERVICE_URL,
        "billing": BILLING_SERVICE_URL,
        "notification": NOTIFICATION_SERVICE_URL,
    }
    
    health_status = {}
    
    for service_name, service_url in services.items():
        try:
            response = await http_client.get(f"{service_url}/health", timeout=5.0)
            health_status[service_name] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_time": response.elapsed.total_seconds()
            }
        except Exception as e:
            health_status[service_name] = {
                "status": "unhealthy",
                "error": str(e)
            }
    
    overall_healthy = all(
        service["status"] == "healthy" 
        for service in health_status.values()
    )
    
    return {
        "overall_status": "healthy" if overall_healthy else "degraded",
        "services": health_status
    }

# Helper function to forward requests
async def forward_request(
    request: Request,
    service_url: str,
    path: str,
    user: Optional[User] = None
) -> JSONResponse:
    """Forward request to downstream service."""
    
    # Prepare headers
    headers = dict(request.headers)
    if user:
        headers["X-User-ID"] = str(user.id)
        headers["X-User-Email"] = user.email
        headers["X-User-Tier"] = user.subscription_tier.value
    
    # Remove headers that cause conflicts
    headers.pop("host", None)
    headers.pop("content-length", None)  # Let httpx calculate this
    
    # Prepare request data
    url = f"{service_url}{path}"
    method = request.method
    params = dict(request.query_params)
    
    try:
        # Handle different content types
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            
            if "application/json" in content_type:
                body = await request.json()
                response = await http_client.request(
                    method, url, json=body, headers=headers, params=params
                )
            elif "multipart/form-data" in content_type:
                # For file uploads
                form_data = await request.form()
                files = {}
                data = {}
                
                for key, value in form_data.items():
                    if hasattr(value, 'file'):  # It's a file
                        files[key] = (value.filename, value.file, value.content_type)
                    else:
                        data[key] = value
                
                response = await http_client.request(
                    method, url, files=files, data=data, headers=headers, params=params
                )
            else:
                body = await request.body()
                response = await http_client.request(
                    method, url, content=body, headers=headers, params=params
                )
        else:
            response = await http_client.request(
                method, url, headers=headers, params=params
            )
        
        # Forward response
        response_headers = dict(response.headers)
        response_headers.pop("content-length", None)  # Let FastAPI handle this
        
        return JSONResponse(
            content=response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            status_code=response.status_code,
            headers=response_headers
        )
        
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Service request timed out"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

# Authentication routes (proxy to auth service)
@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def auth_proxy(request: Request, path: str):
    """Proxy authentication requests to auth service."""
    return await forward_request(request, AUTH_SERVICE_URL, f"/{path}")

# Image routes (require authentication for most endpoints)
@app.api_route("/api/v1/images/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def images_proxy(
    request: Request, 
    path: str, 
    user: User = Depends(get_current_user)
):
    """Proxy image requests to image service."""
    return await forward_request(request, IMAGE_SERVICE_URL, f"/{path}", user)

# Public image endpoint (for viewing images)
@app.get("/api/v1/images/view/{image_id}")
async def view_image_proxy(
    request: Request, 
    image_id: str,
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Proxy public image viewing to image service."""
    return await forward_request(request, IMAGE_SERVICE_URL, f"/view/{image_id}", user)

# Video routes (require authentication)
@app.api_route("/api/v1/videos/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def videos_proxy(
    request: Request, 
    path: str, 
    user: User = Depends(get_current_user)
):
    """Proxy video requests to video service."""
    return await forward_request(request, VIDEO_SERVICE_URL, f"/{path}", user)

# Billing routes (require authentication)
@app.api_route("/api/v1/billing/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def billing_proxy(
    request: Request, 
    path: str, 
    user: User = Depends(get_current_user)
):
    """Proxy billing requests to billing service."""
    return await forward_request(request, BILLING_SERVICE_URL, f"/{path}", user)

# Notification routes (require authentication)
@app.api_route("/api/v1/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def notifications_proxy(
    request: Request, 
    path: str, 
    user: User = Depends(get_current_user)
):
    """Proxy notification requests to notification service."""
    return await forward_request(request, NOTIFICATION_SERVICE_URL, f"/{path}", user)

# Public webhooks endpoint (no auth required)
@app.api_route("/api/v1/webhooks/{path:path}", methods=["POST"])
async def webhooks_proxy(request: Request, path: str):
    """Proxy webhook requests to notification service."""
    return await forward_request(request, NOTIFICATION_SERVICE_URL, f"/webhooks/{path}")

# Public video providers endpoint (no auth required)
@app.get("/api/v1/videos/providers-public")
async def video_providers_public(request: Request):
    """Get available video providers (no authentication required)."""
    return await forward_request(request, VIDEO_SERVICE_URL, "/providers-public")

# User profile endpoints
@app.get("/api/v1/user/profile")
async def get_user_profile(user: User = Depends(get_current_user)):
    """Get current user's profile."""
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "subscription_tier": user.subscription_tier.value,
        "credits_balance": float(user.credits_balance),
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None
    }

# API documentation endpoints
@app.get("/api/v1/docs/openapi.json")
async def get_openapi_schema():
    """Get OpenAPI schema for the entire platform."""
    return app.openapi()

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)