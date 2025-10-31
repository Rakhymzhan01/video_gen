"""
FastAPI authentication dependencies.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.database.connection import get_db
from shared.database.models import User, APIKey
from .jwt_handler import verify_token

# Security scheme for Bearer tokens
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Verify token
    payload = verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception
    
    # Get user from database
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise credentials_exception
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated"
        )
    
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current authenticated user, but don't raise exception if not authenticated.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def get_current_verified_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current user and ensure they are verified.
    
    Raises:
        HTTPException: If user is not verified
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email verification required"
        )
    
    return current_user


async def get_current_user_from_api_key(
    api_key: str,
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate user using API key.
    
    Args:
        api_key: Raw API key from header
        
    Returns:
        User object if valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    from .jwt_handler import hash_password  # Reuse hashing for API keys
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"X-API-Key": "required"},
    )
    
    if not api_key:
        raise credentials_exception
    
    # Hash the provided key to compare with stored hash
    # Note: In production, you might want a different approach for API key hashing
    api_key_obj = db.query(APIKey).filter(
        APIKey.key_hash == hash_password(api_key),
        APIKey.is_active == True
    ).first()
    
    if not api_key_obj:
        raise credentials_exception
    
    # Check if API key is expired
    from datetime import datetime, timezone
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired"
        )
    
    # Update last used timestamp
    api_key_obj.last_used = datetime.now(timezone.utc)
    db.commit()
    
    # Get the user
    user = db.query(User).filter(User.id == api_key_obj.user_id).first()
    if not user or not user.is_active:
        raise credentials_exception
    
    return user


def require_subscription_tier(required_tier: str):
    """
    Dependency factory to require specific subscription tier.
    
    Usage:
        @app.get("/premium-feature")
        async def premium_endpoint(
            user: User = Depends(require_subscription_tier("pro"))
        ):
            return {"message": "Premium feature"}
    """
    async def _check_subscription(
        current_user: User = Depends(get_current_verified_user)
    ) -> User:
        tier_hierarchy = {
            "free": 0,
            "pro": 1,
            "enterprise": 2
        }
        
        user_tier_level = tier_hierarchy.get(current_user.subscription_tier.value.lower(), -1)
        required_tier_level = tier_hierarchy.get(required_tier.lower(), 999)
        
        if user_tier_level < required_tier_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Subscription tier '{required_tier}' or higher required"
            )
        
        return current_user
    
    return _check_subscription


async def get_rate_limit_key(
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> str:
    """
    Get rate limiting key for the current request.
    
    Returns:
        Rate limit key string (user_id if authenticated, otherwise IP-based)
    """
    if current_user:
        return f"user:{current_user.id}"
    else:
        # In a real implementation, you'd get the client IP
        # For now, return a generic key for anonymous users
        return "anonymous"