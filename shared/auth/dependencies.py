"""
FastAPI authentication dependencies.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.database.connection import get_db
from shared.database.models import User, APIKey
from .jwt_handler import verify_token

# Security scheme for Bearer tokens
# auto_error=False важно: иначе если нет Authorization заголовка,
# FastAPI сразу вернет ошибку и мы не сможем прочитать cookie.
security = HTTPBearer(auto_error=False)


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_access_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """
    Extract access token from:
    1) Authorization: Bearer <token>
    2) Cookie: access_token=<token>
    """
    if credentials and credentials.scheme and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
        if token:
            return token

    # fallback to cookie
    token = request.cookies.get("access_token")
    if token:
        return token

    return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token.
    Token can come from Authorization header or access_token cookie.

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = _extract_access_token(request, credentials)
    if not token:
        raise _credentials_exception()

    payload = verify_token(token, expected_type="access")
    if payload is None:
        raise _credentials_exception()

    user_id = payload.get("user_id")
    if user_id is None:
        raise _credentials_exception()

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise _credentials_exception()

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise _credentials_exception()

    if not user.is_active:
        raise _credentials_exception("User account is deactivated")

    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get the current authenticated user, but don't raise exception if not authenticated.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    token = _extract_access_token(request, credentials)
    if not token:
        return None

    try:
        payload = verify_token(token, expected_type="access")
        if payload is None:
            return None

        user_id = payload.get("user_id")
        if not user_id:
            return None

        user_uuid = UUID(user_id)
        user = db.query(User).filter(User.id == user_uuid).first()
        if not user or not user.is_active:
            return None

        return user
    except Exception:
        return None


async def get_current_verified_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current user and ensure they are verified.
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
    """
    from .jwt_handler import hash_password  # Reuse hashing for API keys

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"X-API-Key": "required"},
    )

    if not api_key:
        raise credentials_exception

    api_key_obj = db.query(APIKey).filter(
        APIKey.key_hash == hash_password(api_key),
        APIKey.is_active == True
    ).first()

    if not api_key_obj:
        raise credentials_exception

    from datetime import datetime, timezone
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired"
        )

    api_key_obj.last_used = datetime.now(timezone.utc)
    db.commit()

    user = db.query(User).filter(User.id == api_key_obj.user_id).first()
    if not user or not user.is_active:
        raise credentials_exception

    return user


def require_subscription_tier(required_tier: str):
    """
    Dependency factory to require specific subscription tier.
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
    """
    if current_user:
        return f"user:{current_user.id}"
    return "anonymous"
