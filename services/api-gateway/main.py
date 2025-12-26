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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs (in production these would be service discovery)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL", "http://image-service:8002")
VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://video-service:8003")
VIDEO_NODE_SERVICE_URL = os.getenv("VIDEO_NODE_SERVICE_URL", "http://host.docker.internal:8006")
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

# Public video providers endpoint (no auth required) - MUST be before catch-all route
@app.get("/api/v1/videos/providers-public")
async def video_providers_public(request: Request):
    """Get available video providers (no authentication required)."""
    return await forward_request(request, VIDEO_SERVICE_URL, "/providers-public")

# Public video generation endpoint for testing (no auth required) - MUST be before catch-all route
@app.post("/api/v1/videos/generate-public")
async def video_generate_public(request: Request):
    """Generate video without authentication using real VEO API via Node.js service."""
    print("🎬 Public video generation endpoint hit - using Node.js VEO service")
    async with httpx.AsyncClient(timeout=180.0) as client:  # Longer timeout for video generation
        try:
            # Get request body from frontend
            body = await request.json()
            print(f"📝 Received request body: {body}")
            
            # Transform frontend request to Node.js service format
            node_request = {
                "prompt": body.get("prompt", "A happy cat playing with a ball of yarn"),
                "duration": body.get("duration", 5),
                "resolution": body.get("resolution", "1280x720"),
                "provider": body.get("provider", "VEO3")
            }
            
            print(f"🚀 Sending to Node.js VEO service: {node_request}")
            
            # Forward to Node.js video service for real VEO API
            response = await client.post(
                f"{VIDEO_NODE_SERVICE_URL}/generate",
                json=node_request,
                timeout=60.0  # Initial request timeout
            )
            
            return JSONResponse(
                content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text},
                status_code=response.status_code
            )
        except Exception as e:
            return JSONResponse(
                content={"error": str(e)},
                status_code=500
            )

# Public video status endpoint for testing (no auth required) - MUST be before catch-all route
@app.get("/api/v1/videos/{video_id}/status-public")
async def video_status_public(video_id: str):
    """Get video status without authentication using Redis shared state."""
    print(f"📊 Public video status check for {video_id} - using Redis shared state")
    
    try:
        import redis
        # Connect to Redis
        redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        
        # Get operation status from Redis
        operation_data = redis_client.get(f"video_op:{video_id}")
        
        if not operation_data:
            return JSONResponse(
                content={"error": "Operation not found"},
                status_code=404
            )
        
        import json
        operation = json.loads(operation_data)
        
        # Format response to match expected structure
        response_data = {
            "id": video_id,
            "status": operation.get("status", "processing"),
            "progress_percentage": operation.get("progress", 0),
            "video_url": operation.get("video_url"),
            "error_message": operation.get("error_message"),
            "metadata": operation.get("metadata", {
                "provider": "VEO3",
                "model": "veo-3.1-fast-generate-preview", 
                "prompt": operation.get("prompt", ""),
                "real_api": True,
                "node_service": True,
                "created_at": operation.get("createdAt"),
                "completed_at": operation.get("completedAt"),
                "image_provided": operation.get("imageProvided", False)
            })
        }
        
        print(f"✅ Retrieved status from Redis: {operation.get('status')}")
        return JSONResponse(content=response_data, status_code=200)
        
    except Exception as e:
        print(f"❌ Error checking Redis: {str(e)}")
        # Fallback to Node.js service if Redis fails
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(
                    f"{VIDEO_NODE_SERVICE_URL}/{video_id}/status",
                    timeout=30.0
                )
                
                return JSONResponse(
                    content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text},
                    status_code=response.status_code
                )
            except Exception as fallback_error:
                print(f"❌ Fallback to Node.js also failed: {str(fallback_error)}")
                return JSONResponse(
                    content={"error": str(e)},
                    status_code=500
                )

# Video routes (require authentication) - catch-all route must be AFTER specific routes
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