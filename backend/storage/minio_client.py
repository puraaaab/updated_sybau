import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minio_admin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minio_password")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

RECORDINGS_BUCKET = "vms-recordings"
SNAPSHOTS_BUCKET = "vms-snapshots"

_s3_client = None
_client_initialized = False

def get_minio_client():
    """Returns initialized MinIO S3 client or None if MinIO is unavailable."""
    global _s3_client, _client_initialized
    if _client_initialized:
        return _s3_client

    try:
        import boto3
        from botocore.config import Config

        endpoint_url = f"http{'s' if MINIO_SECURE else ''}://{MINIO_ENDPOINT}"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1"
        )
        
        # Verify buckets exist or create them
        for b in [RECORDINGS_BUCKET, SNAPSHOTS_BUCKET]:
            try:
                client.head_bucket(Bucket=b)
            except Exception:
                try:
                    client.create_bucket(Bucket=b)
                    logger.info(f"[MinIO] Created missing S3 bucket: {b}")
                except Exception as cb_err:
                    logger.warning(f"[MinIO] Could not create bucket {b}: {cb_err}")

        _s3_client = client
        logger.info(f"[MinIO] S3 Storage Client connected to {endpoint_url}")
    except Exception as e:
        logger.info(f"[MinIO] S3 Storage not active ({e}). Falling back to local filesystem storage.")
        _s3_client = None

    _client_initialized = True
    return _s3_client

def upload_file_to_storage(local_path: str, bucket_name: str, object_name: str) -> bool:
    """Uploads a local file to MinIO S3 bucket if available."""
    client = get_minio_client()
    if client is None:
        return False
    try:
        client.upload_file(local_path, bucket_name, object_name)
        return True
    except Exception as e:
        logger.warning(f"[MinIO] Failed to upload {local_path} to {bucket_name}/{object_name}: {e}")
        return False
