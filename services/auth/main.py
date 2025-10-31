"""
Authentication Service - Handles user registration, login, and JWT token management.
"""
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.connection import get_db, create_tables
from shared.database.models import User, SubscriptionTier
from shared.auth.jwt_handler import (
    hash_password, verify_password, create_token_pair, 
    refresh_access_token, verify_token
)

# Initialize FastAPI app
app = FastAPI(
    title="Video Generation - Auth Service",
    description="Authentication and user management service",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") == "development" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") == "development" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENVIRONMENT") == "development" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Pydantic models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    @validator('username')
    def validate_username(cls, v):
        if v and len(v) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if v and not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    subscription_tier: str
    credits_balance: float
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class VerifyEmailRequest(BaseModel):
    token: str


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup."""
    create_tables()


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "auth"}


# Authentication endpoints
@app.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Register a new user account.
    
    - **email**: Valid email address (will be used for login)
    - **password**: Strong password (min 8 chars, upper, lower, digit)
    - **first_name**: Optional first name
    - **last_name**: Optional last name  
    - **username**: Optional username (min 3 chars, alphanumeric + _ -)
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == user_data.email) | 
            (User.username == user_data.username if user_data.username else False)
        ).first()
        
        if existing_user:
            if existing_user.email == user_data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
        
        # Create new user
        hashed_password = hash_password(user_data.password)
        verification_token = secrets.token_urlsafe(32)
        
        user = User(
            email=user_data.email,
            username=user_data.username,
            password_hash=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            subscription_tier=SubscriptionTier.FREE,
            credits_balance=100,  # Free tier gets 100 credits to start
            verification_token=verification_token,
            is_verified=False  # Require email verification
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Send verification email (background task)
        background_tasks.add_task(send_verification_email, user.email, verification_token)
        
        # Create tokens
        tokens = create_token_pair(
            user_id=user.id,
            email=user.email,
            subscription_tier=user.subscription_tier.value
        )
        
        return TokenResponse(
            **tokens,
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                subscription_tier=user.subscription_tier.value,
                credits_balance=float(user.credits_balance),
                is_verified=user.is_verified,
                created_at=user.created_at
            )
        )
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or username already exists"
        )


@app.post("/login", response_model=TokenResponse)
async def login_user(
    user_credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return access/refresh tokens.
    
    - **email**: Registered email address
    - **password**: User's password
    """
    # Find user by email
    user = db.query(User).filter(User.email == user_credentials.email).first()
    
    if not user or not verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated"
        )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Create tokens
    tokens = create_token_pair(
        user_id=user.id,
        email=user.email,
        subscription_tier=user.subscription_tier.value
    )
    
    return TokenResponse(
        **tokens,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            subscription_tier=user.subscription_tier.value,
            credits_balance=float(user.credits_balance),
            is_verified=user.is_verified,
            created_at=user.created_at
        )
    )


@app.post("/refresh", response_model=dict)
async def refresh_token(refresh_request: RefreshRequest):
    """
    Refresh access token using refresh token.
    
    - **refresh_token**: Valid refresh token
    """
    tokens = refresh_access_token(refresh_request.refresh_token)
    
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    return tokens


@app.post("/verify-email", response_model=dict)
async def verify_email(
    verify_request: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Verify user's email address using verification token.
    
    - **token**: Email verification token sent to user's email
    """
    user = db.query(User).filter(
        User.verification_token == verify_request.token,
        User.is_verified == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    # Mark user as verified
    user.is_verified = True
    user.verification_token = None
    db.commit()
    
    return {"message": "Email verified successfully"}


@app.post("/request-password-reset", response_model=dict)
async def request_password_reset(
    reset_request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Request password reset email.
    
    - **email**: Registered email address
    """
    user = db.query(User).filter(User.email == reset_request.email).first()
    
    if user:
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user.verification_token = reset_token  # Reuse verification_token field
        db.commit()
        
        # Send reset email (background task)
        background_tasks.add_task(send_password_reset_email, user.email, reset_token)
    
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a password reset link has been sent"}


@app.post("/reset-password", response_model=dict)
async def reset_password(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    """
    Reset password using reset token.
    
    - **token**: Password reset token from email
    - **new_password**: New password
    """
    user = db.query(User).filter(User.verification_token == reset_data.token).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update password
    user.password_hash = hash_password(reset_data.new_password)
    user.verification_token = None  # Clear token
    db.commit()
    
    return {"message": "Password reset successfully"}


@app.post("/validate-token", response_model=dict)
async def validate_token(token: str):
    """
    Validate JWT token and return payload.
    Used by other services to validate tokens.
    
    - **token**: JWT access token to validate
    """
    payload = verify_token(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    return {
        "valid": True,
        "user_id": payload.get("user_id"),
        "email": payload.get("email"),
        "subscription_tier": payload.get("subscription_tier")
    }


# Helper functions for background tasks
async def send_verification_email(email: str, token: str):
    """Send email verification email (mock implementation)."""
    # In production, integrate with SendGrid, SES, etc.
    print(f"Sending verification email to {email} with token: {token}")
    print(f"Verification URL: http://localhost:3000/verify-email?token={token}")


async def send_password_reset_email(email: str, token: str):
    """Send password reset email (mock implementation)."""
    # In production, integrate with SendGrid, SES, etc.
    print(f"Sending password reset email to {email} with token: {token}")
    print(f"Reset URL: http://localhost:3000/reset-password?token={token}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)