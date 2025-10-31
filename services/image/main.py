"""
Image Service - Complete image upload, processing, and management.
"""
import hashlib
import io
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database.connection import get_db, create_tables
from shared.database.models import Image as ImageModel, User
from shared.storage.s3_client import storage_client

# Initialize FastAPI app
app = FastAPI(
    title="Video Generation - Image Service",
    description="Image upload, processing, and management service",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") == "development" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENVIRONMENT") == "development" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"]
ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
MIN_RESOLUTION = (256, 256)
MAX_RESOLUTION = (4096, 4096)
THUMBNAIL_SIZE = (512, 512)

# Pydantic models
class ImageResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_size: int
    content_type: str
    width: int
    height: int
    format: str
    moderation_status: str
    created_at: datetime
    thumbnail_url: Optional[str] = None
    download_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class ImageListResponse(BaseModel):
    images: List[ImageResponse]
    total: int
    page: int
    per_page: int

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup."""
    create_tables()

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "image"}

# Helper functions
def get_current_user_from_headers(
    user_id: str = None,
    user_email: str = None,
    db: Session = Depends(get_db)
) -> User:
    """Get user from request headers (set by API Gateway)."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID"
        )
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

def validate_image_file(file: UploadFile) -> None:
    """Validate uploaded image file."""
    # Check file size
    if hasattr(file, 'size') and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Check content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )
    
    # Check file extension
    if file.filename:
        ext = os.path.splitext(file.filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
            )

def calculate_file_hash(content: bytes) -> str:
    """Calculate SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()

def extract_image_metadata(image: Image.Image) -> dict:
    """Extract metadata from PIL Image."""
    metadata = {
        'width': image.width,
        'height': image.height,
        'format': image.format,
        'mode': image.mode,
        'has_transparency': image.mode in ('RGBA', 'LA') or 'transparency' in image.info
    }
    
    # Extract EXIF data
    exif_data = {}
    if hasattr(image, '_getexif') and image._getexif() is not None:
        exif = image._getexif()
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            # Convert non-serializable values to strings
            if isinstance(value, (bytes, tuple)):
                value = str(value)
            exif_data[tag] = value
    
    metadata['exif'] = exif_data
    return metadata

def validate_image_dimensions(image: Image.Image) -> None:
    """Validate image dimensions."""
    width, height = image.size
    
    if width < MIN_RESOLUTION[0] or height < MIN_RESOLUTION[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too small. Minimum resolution is {MIN_RESOLUTION[0]}x{MIN_RESOLUTION[1]}"
        )
    
    if width > MAX_RESOLUTION[0] or height > MAX_RESOLUTION[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large. Maximum resolution is {MAX_RESOLUTION[0]}x{MAX_RESOLUTION[1]}"
        )

def create_thumbnail(image: Image.Image) -> io.BytesIO:
    """Create thumbnail from image."""
    # Convert to RGB if necessary (for JPEG output)
    if image.mode in ('RGBA', 'LA', 'P'):
        # Create white background
        rgb_image = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = rgb_image
    
    # Create thumbnail
    image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    
    # Save to BytesIO
    thumbnail_io = io.BytesIO()
    image.save(thumbnail_io, format='JPEG', quality=85, optimize=True)
    thumbnail_io.seek(0)
    
    return thumbnail_io

async def moderate_image(image_content: bytes) -> dict:
    """
    Mock content moderation function.
    In production, integrate with AWS Rekognition, Google Vision API, etc.
    """
    # Mock moderation result
    # Real implementation would analyze the image for inappropriate content
    return {
        'status': 'approved',  # approved, rejected, pending
        'confidence': 0.95,
        'labels': [],
        'moderation_confidence': 0.02  # Low confidence of inappropriate content
    }

# Image upload endpoint
@app.post("/upload", response_model=ImageResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    user_email: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload and process an image file.
    
    - **file**: Image file (JPEG, PNG, WEBP, max 10MB)
    - **user_id**: User ID (provided by API Gateway)
    - **user_email**: User email (provided by API Gateway)
    """
    # Get user (normally from auth headers via API Gateway)
    user = get_current_user_from_headers(user_id, user_email, db)
    
    # Validate file
    validate_image_file(file)
    
    # Read file content
    content = await file.read()
    
    # Validate actual file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Calculate file hash for deduplication
    file_hash = calculate_file_hash(content)
    
    # Check for duplicate
    existing_image = db.query(ImageModel).filter(
        ImageModel.file_hash == file_hash,
        ImageModel.user_id == user.id
    ).first()
    
    if existing_image:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Image already exists"
        )
    
    # Process image with PIL
    try:
        image = Image.open(io.BytesIO(content))
        image.load()  # Verify image can be opened
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {str(e)}"
        )
    
    # Validate dimensions
    validate_image_dimensions(image)
    
    # Extract metadata
    metadata = extract_image_metadata(image)
    
    # Content moderation
    moderation_result = await moderate_image(content)
    
    if moderation_result['status'] == 'rejected':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image rejected by content moderation"
        )
    
    # Generate unique filename
    image_id = uuid.uuid4()
    file_extension = os.path.splitext(file.filename or "image.jpg")[1].lower()
    stored_filename = f"{image_id}{file_extension}"
    
    # Create storage keys
    s3_key = f"images/{user.id}/{image_id}/original{file_extension}"
    s3_thumbnail_key = f"images/{user.id}/{image_id}/thumbnail.jpg"
    
    # Upload original image
    original_io = io.BytesIO(content)
    upload_success = storage_client.upload_file(
        file_data=original_io,
        key=s3_key,
        content_type=file.content_type or "image/jpeg",
        metadata={
            'user_id': str(user.id),
            'original_filename': file.filename or "image",
            'file_hash': file_hash
        }
    )
    
    if not upload_success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image"
        )
    
    # Create and upload thumbnail
    try:
        thumbnail_io = create_thumbnail(image.copy())
        thumbnail_success = storage_client.upload_file(
            file_data=thumbnail_io,
            key=s3_thumbnail_key,
            content_type="image/jpeg",
            metadata={
                'user_id': str(user.id),
                'type': 'thumbnail'
            }
        )
        
        if not thumbnail_success:
            print(f"Warning: Failed to upload thumbnail for image {image_id}")
            s3_thumbnail_key = None
            
    except Exception as e:
        print(f"Warning: Failed to create thumbnail for image {image_id}: {e}")
        s3_thumbnail_key = None
    
    # Save to database
    image_record = ImageModel(
        id=image_id,
        user_id=user.id,
        filename=stored_filename,
        original_filename=file.filename or "image",
        file_size=len(content),
        content_type=file.content_type or "image/jpeg",
        file_hash=file_hash,
        width=image.width,
        height=image.height,
        format=image.format or "JPEG",
        s3_key=s3_key,
        s3_thumbnail_key=s3_thumbnail_key,
        moderation_status=moderation_result['status'],
        moderation_labels=str(moderation_result.get('labels', [])),
        moderation_confidence=moderation_result.get('moderation_confidence'),
        exif_data=str(metadata.get('exif', {}))
    )
    
    db.add(image_record)
    db.commit()
    db.refresh(image_record)
    
    # Generate response with URLs
    thumbnail_url = None
    download_url = None
    
    if s3_thumbnail_key:
        thumbnail_url = storage_client.generate_presigned_url(s3_thumbnail_key, expiration=7200)
    
    download_url = storage_client.generate_presigned_url(s3_key, expiration=7200)
    
    return ImageResponse(
        id=str(image_record.id),
        filename=image_record.filename,
        original_filename=image_record.original_filename,
        file_size=image_record.file_size,
        content_type=image_record.content_type,
        width=image_record.width,
        height=image_record.height,
        format=image_record.format,
        moderation_status=image_record.moderation_status,
        created_at=image_record.created_at,
        thumbnail_url=thumbnail_url,
        download_url=download_url
    )

# Get image by ID
@app.get("/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: str,
    user_id: str = None,
    user_email: str = None,
    db: Session = Depends(get_db)
):
    """Get image details by ID."""
    user = get_current_user_from_headers(user_id, user_email, db)
    
    try:
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image ID"
        )
    
    image = db.query(ImageModel).filter(
        ImageModel.id == image_uuid,
        ImageModel.user_id == user.id
    ).first()
    
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Generate URLs
    thumbnail_url = None
    download_url = None
    
    if image.s3_thumbnail_key:
        thumbnail_url = storage_client.generate_presigned_url(image.s3_thumbnail_key, expiration=7200)
    
    download_url = storage_client.generate_presigned_url(image.s3_key, expiration=7200)
    
    return ImageResponse(
        id=str(image.id),
        filename=image.filename,
        original_filename=image.original_filename,
        file_size=image.file_size,
        content_type=image.content_type,
        width=image.width,
        height=image.height,
        format=image.format,
        moderation_status=image.moderation_status,
        created_at=image.created_at,
        thumbnail_url=thumbnail_url,
        download_url=download_url
    )

# List user images
@app.get("/", response_model=ImageListResponse)
async def list_images(
    page: int = 1,
    per_page: int = 20,
    user_id: str = None,
    user_email: str = None,
    db: Session = Depends(get_db)
):
    """List user's images with pagination."""
    user = get_current_user_from_headers(user_id, user_email, db)
    
    # Validate pagination
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20
    
    # Get total count
    total = db.query(ImageModel).filter(ImageModel.user_id == user.id).count()
    
    # Get paginated images
    offset = (page - 1) * per_page
    images = db.query(ImageModel).filter(
        ImageModel.user_id == user.id
    ).order_by(
        ImageModel.created_at.desc()
    ).offset(offset).limit(per_page).all()
    
    # Build response with URLs
    image_responses = []
    for image in images:
        thumbnail_url = None
        download_url = None
        
        if image.s3_thumbnail_key:
            thumbnail_url = storage_client.generate_presigned_url(image.s3_thumbnail_key, expiration=7200)
        
        download_url = storage_client.generate_presigned_url(image.s3_key, expiration=7200)
        
        image_responses.append(ImageResponse(
            id=str(image.id),
            filename=image.filename,
            original_filename=image.original_filename,
            file_size=image.file_size,
            content_type=image.content_type,
            width=image.width,
            height=image.height,
            format=image.format,
            moderation_status=image.moderation_status,
            created_at=image.created_at,
            thumbnail_url=thumbnail_url,
            download_url=download_url
        ))
    
    return ImageListResponse(
        images=image_responses,
        total=total,
        page=page,
        per_page=per_page
    )

# Delete image
@app.delete("/{image_id}")
async def delete_image(
    image_id: str,
    user_id: str = None,
    user_email: str = None,
    db: Session = Depends(get_db)
):
    """Delete an image."""
    user = get_current_user_from_headers(user_id, user_email, db)
    
    try:
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image ID"
        )
    
    image = db.query(ImageModel).filter(
        ImageModel.id == image_uuid,
        ImageModel.user_id == user.id
    ).first()
    
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Delete from storage
    storage_client.delete_file(image.s3_key)
    if image.s3_thumbnail_key:
        storage_client.delete_file(image.s3_thumbnail_key)
    
    # Delete from database
    db.delete(image)
    db.commit()
    
    return {"message": "Image deleted successfully"}

# Public view endpoint (for viewing images without authentication)
@app.get("/view/{image_id}")
async def view_image(image_id: str, db: Session = Depends(get_db)):
    """Public endpoint to view an image (returns the image file)."""
    try:
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image ID"
        )
    
    image = db.query(ImageModel).filter(ImageModel.id == image_uuid).first()
    
    if not image or image.moderation_status != 'approved':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Get image content from storage
    content = storage_client.download_file(image.s3_key)
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found"
        )
    
    return StreamingResponse(
        io.BytesIO(content),
        media_type=image.content_type,
        headers={"Content-Disposition": f"inline; filename={image.filename}"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)