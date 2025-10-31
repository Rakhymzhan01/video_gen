"""
S3-compatible storage client (works with AWS S3 and MinIO).
"""
import os
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional, Tuple, BinaryIO
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from minio import Minio
from minio.error import S3Error

class StorageClient:
    """
    Unified storage client that works with both AWS S3 and MinIO.
    """
    
    def __init__(self):
        # Check if we're using MinIO (local development) or AWS S3
        minio_endpoint = os.getenv("MINIO_ENDPOINT")
        
        if minio_endpoint:
            # MinIO configuration
            self.use_minio = True
            self.bucket_name = os.getenv("MINIO_BUCKET", "vide-gen-local")
            self.minio_client = Minio(
                minio_endpoint,
                access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                secure=False  # Use HTTP for local development
            )
            
            # Ensure bucket exists
            self._ensure_bucket_exists()
            
        else:
            # AWS S3 configuration
            self.use_minio = False
            self.bucket_name = os.getenv("S3_BUCKET", "vide-gen-bucket")
            
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.getenv("AWS_REGION", "us-east-1")
                )
            except NoCredentialsError:
                raise RuntimeError("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    
    def _ensure_bucket_exists(self):
        """Ensure the MinIO bucket exists."""
        if self.use_minio:
            try:
                if not self.minio_client.bucket_exists(self.bucket_name):
                    self.minio_client.make_bucket(self.bucket_name)
                    print(f"Created MinIO bucket: {self.bucket_name}")
            except S3Error as e:
                print(f"Error creating MinIO bucket: {e}")
    
    def upload_file(
        self, 
        file_data: BinaryIO, 
        key: str, 
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None
    ) -> bool:
        """
        Upload a file to storage.
        
        Args:
            file_data: File-like object to upload
            key: Storage key/path for the file
            content_type: MIME type of the file
            metadata: Optional metadata dictionary
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            if self.use_minio:
                # MinIO upload
                file_data.seek(0)  # Reset file pointer
                file_size = len(file_data.read())
                file_data.seek(0)  # Reset again
                
                self.minio_client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=key,
                    data=file_data,
                    length=file_size,
                    content_type=content_type,
                    metadata=metadata or {}
                )
            else:
                # AWS S3 upload
                extra_args = {
                    'ContentType': content_type
                }
                if metadata:
                    extra_args['Metadata'] = metadata
                
                file_data.seek(0)
                self.s3_client.upload_fileobj(
                    file_data,
                    self.bucket_name,
                    key,
                    ExtraArgs=extra_args
                )
            
            return True
            
        except (S3Error, ClientError) as e:
            print(f"Error uploading file {key}: {e}")
            return False
    
    def download_file(self, key: str) -> Optional[bytes]:
        """
        Download a file from storage.
        
        Args:
            key: Storage key/path of the file
            
        Returns:
            File content as bytes, or None if not found
        """
        try:
            if self.use_minio:
                # MinIO download
                response = self.minio_client.get_object(self.bucket_name, key)
                return response.read()
            else:
                # AWS S3 download
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                return response['Body'].read()
                
        except (S3Error, ClientError) as e:
            print(f"Error downloading file {key}: {e}")
            return None
    
    def delete_file(self, key: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            key: Storage key/path of the file
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            if self.use_minio:
                # MinIO delete
                self.minio_client.remove_object(self.bucket_name, key)
            else:
                # AWS S3 delete
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            
            return True
            
        except (S3Error, ClientError) as e:
            print(f"Error deleting file {key}: {e}")
            return False
    
    def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            key: Storage key/path of the file
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            if self.use_minio:
                # MinIO check
                self.minio_client.stat_object(self.bucket_name, key)
            else:
                # AWS S3 check
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            
            return True
            
        except (S3Error, ClientError):
            return False
    
    def get_file_info(self, key: str) -> Optional[dict]:
        """
        Get file metadata.
        
        Args:
            key: Storage key/path of the file
            
        Returns:
            Dictionary with file info, or None if not found
        """
        try:
            if self.use_minio:
                # MinIO stat
                stat = self.minio_client.stat_object(self.bucket_name, key)
                return {
                    'size': stat.size,
                    'last_modified': stat.last_modified,
                    'etag': stat.etag,
                    'content_type': stat.content_type,
                    'metadata': stat.metadata
                }
            else:
                # AWS S3 head
                response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                return {
                    'size': response['ContentLength'],
                    'last_modified': response['LastModified'],
                    'etag': response['ETag'],
                    'content_type': response['ContentType'],
                    'metadata': response.get('Metadata', {})
                }
                
        except (S3Error, ClientError) as e:
            print(f"Error getting file info for {key}: {e}")
            return None
    
    def generate_presigned_url(
        self, 
        key: str, 
        expiration: int = 3600,
        method: str = "GET"
    ) -> Optional[str]:
        """
        Generate a presigned URL for file access.
        
        Args:
            key: Storage key/path of the file
            expiration: URL expiration time in seconds (default: 1 hour)
            method: HTTP method (GET, PUT, POST)
            
        Returns:
            Presigned URL string, or None if error
        """
        try:
            if self.use_minio:
                # MinIO presigned URL
                from datetime import timedelta
                expires = timedelta(seconds=expiration)
                
                if method.upper() == "GET":
                    return self.minio_client.presigned_get_object(
                        self.bucket_name, key, expires=expires
                    )
                elif method.upper() == "PUT":
                    return self.minio_client.presigned_put_object(
                        self.bucket_name, key, expires=expires
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")
            else:
                # AWS S3 presigned URL
                if method.upper() == "GET":
                    return self.s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.bucket_name, 'Key': key},
                        ExpiresIn=expiration
                    )
                elif method.upper() == "PUT":
                    return self.s3_client.generate_presigned_url(
                        'put_object',
                        Params={'Bucket': self.bucket_name, 'Key': key},
                        ExpiresIn=expiration
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")
                    
        except (S3Error, ClientError) as e:
            print(f"Error generating presigned URL for {key}: {e}")
            return None
    
    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list:
        """
        List files in storage with optional prefix filter.
        
        Args:
            prefix: Key prefix to filter by
            max_keys: Maximum number of keys to return
            
        Returns:
            List of file keys
        """
        try:
            files = []
            
            if self.use_minio:
                # MinIO list
                objects = self.minio_client.list_objects(
                    self.bucket_name, 
                    prefix=prefix,
                    recursive=True
                )
                for obj in objects:
                    files.append(obj.object_name)
                    if len(files) >= max_keys:
                        break
            else:
                # AWS S3 list
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
                for obj in response.get('Contents', []):
                    files.append(obj['Key'])
            
            return files
            
        except (S3Error, ClientError) as e:
            print(f"Error listing files with prefix {prefix}: {e}")
            return []


# Global storage client instance
storage_client = StorageClient()