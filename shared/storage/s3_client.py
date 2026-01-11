"""
S3-compatible storage client (works with AWS S3 and MinIO).
"""
import os
from typing import Optional, BinaryIO
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
        # --- Detect MinIO ---
        minio_endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()

        # If endpoint isn't provided but MinIO creds exist, assume we're in docker-compose and MinIO service is "minio"
        minio_access = (os.getenv("MINIO_ACCESS_KEY") or "").strip() or (os.getenv("MINIO_ROOT_USER") or "").strip()
        minio_secret = (os.getenv("MINIO_SECRET_KEY") or "").strip() or (os.getenv("MINIO_ROOT_PASSWORD") or "").strip()

        if not minio_endpoint and (minio_access and minio_secret):
            # default internal docker DNS name
            minio_endpoint = "minio:9000"

        self.use_minio = bool(minio_endpoint)

        if self.use_minio:
            self.bucket_name = (os.getenv("MINIO_BUCKET") or "vide-gen-local").strip()

            # For MinIO inside docker network -> usually http
            secure_env = (os.getenv("MINIO_SECURE") or "false").lower().strip()
            secure = secure_env in ("1", "true", "yes", "on")

            if not minio_access or not minio_secret:
                raise RuntimeError(
                    "MinIO credentials not found. Set MINIO_ACCESS_KEY/MINIO_SECRET_KEY "
                    "or MINIO_ROOT_USER/MINIO_ROOT_PASSWORD"
                )

            self.minio_client = Minio(
                minio_endpoint,
                access_key=minio_access,
                secret_key=minio_secret,
                secure=secure,
            )

            self._ensure_bucket_exists()
            return

        # --- AWS S3 fallback ---
        self.bucket_name = (os.getenv("S3_BUCKET") or "vide-gen-bucket").strip()

        aws_access = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
        aws_secret = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
        aws_region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1").strip()

        if not aws_access or not aws_secret:
            raise RuntimeError(
                "AWS credentials not found AND MINIO_ENDPOINT not set. "
                "Either set MINIO_ENDPOINT (+ MINIO creds) or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY."
            )

        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access,
                aws_secret_access_key=aws_secret,
                region_name=aws_region,
            )
        except NoCredentialsError:
            raise RuntimeError("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

    def _ensure_bucket_exists(self):
        if not self.use_minio:
            return
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
        metadata: Optional[dict] = None,
    ) -> bool:
        try:
            if self.use_minio:
                file_data.seek(0)
                blob = file_data.read()
                file_size = len(blob)
                file_data.seek(0)

                self.minio_client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=key,
                    data=file_data,
                    length=file_size,
                    content_type=content_type,
                    metadata=metadata or {},
                )
            else:
                extra_args = {"ContentType": content_type}
                if metadata:
                    extra_args["Metadata"] = metadata

                file_data.seek(0)
                self.s3_client.upload_fileobj(file_data, self.bucket_name, key, ExtraArgs=extra_args)

            return True
        except (S3Error, ClientError) as e:
            print(f"Error uploading file {key}: {e}")
            return False

    def download_file(self, key: str) -> Optional[bytes]:
        try:
            if self.use_minio:
                response = self.minio_client.get_object(self.bucket_name, key)
                return response.read()
            else:
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                return response["Body"].read()
        except (S3Error, ClientError) as e:
            print(f"Error downloading file {key}: {e}")
            return None

    def delete_file(self, key: str) -> bool:
        try:
            if self.use_minio:
                self.minio_client.remove_object(self.bucket_name, key)
            else:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except (S3Error, ClientError) as e:
            print(f"Error deleting file {key}: {e}")
            return False

    def file_exists(self, key: str) -> bool:
        try:
            if self.use_minio:
                self.minio_client.stat_object(self.bucket_name, key)
            else:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except (S3Error, ClientError):
            return False

    def _rewrite_minio_public_url(self, presigned_url: str) -> str:
        """
        If MINIO_PUBLIC_BASE_URL is set, rewrite:
        http://minio:9000/<bucket>/<key>?...  ->  <PUBLIC_BASE>/<bucket>/<key>?...
        Example PUBLIC_BASE: https://duutzduutz.com/minio
        """
        public_base = (os.getenv("MINIO_PUBLIC_BASE_URL") or "").strip()
        if not public_base:
            return presigned_url

        public_base = public_base.rstrip("/")
        p = urlparse(presigned_url)
        return f"{public_base}{p.path}?{p.query}" if p.query else f"{public_base}{p.path}"

    def generate_presigned_url(self, key: str, expiration: int = 3600, method: str = "GET") -> Optional[str]:
        try:
            if self.use_minio:
                from datetime import timedelta

                expires = timedelta(seconds=expiration)

                if method.upper() == "GET":
                    url = self.minio_client.presigned_get_object(self.bucket_name, key, expires=expires)
                    return self._rewrite_minio_public_url(url)
                if method.upper() == "PUT":
                    url = self.minio_client.presigned_put_object(self.bucket_name, key, expires=expires)
                    return self._rewrite_minio_public_url(url)

                raise ValueError(f"Unsupported method: {method}")

            # AWS S3
            if method.upper() == "GET":
                return self.s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": key},
                    ExpiresIn=expiration,
                )
            if method.upper() == "PUT":
                return self.s3_client.generate_presigned_url(
                    "put_object",
                    Params={"Bucket": self.bucket_name, "Key": key},
                    ExpiresIn=expiration,
                )

            raise ValueError(f"Unsupported method: {method}")

        except (S3Error, ClientError) as e:
            print(f"Error generating presigned URL for {key}: {e}")
            return None

    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list:
        try:
            files = []
            if self.use_minio:
                objects = self.minio_client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
                for obj in objects:
                    files.append(obj.object_name)
                    if len(files) >= max_keys:
                        break
            else:
                response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys)
                for obj in response.get("Contents", []):
                    files.append(obj["Key"])
            return files
        except (S3Error, ClientError) as e:
            print(f"Error listing files with prefix {prefix}: {e}")
            return []


storage_client = StorageClient()
