from __future__ import annotations

import mimetypes
import errno
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import get_settings


@dataclass(frozen=True)
class PutObjectResult:
    bucket: str
    key: str


_s3 = None
_s3_presign = None
_KNOWN_CONTENT_TYPES = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def use_local_storage() -> bool:
    settings = get_settings()
    return settings.storage_backend.strip().lower() == "local"


def _local_bucket_dir(bucket: str) -> Path:
    settings = get_settings()
    base = Path(settings.local_storage_dir).resolve()
    return (base / bucket).resolve()


def guess_content_type(name: str | Path | None) -> str:
    if not name:
        return "application/octet-stream"
    suffix = Path(name).suffix.lower()
    if suffix in _KNOWN_CONTENT_TYPES:
        return _KNOWN_CONTENT_TYPES[suffix]
    return mimetypes.guess_type(str(name))[0] or "application/octet-stream"


def local_object_path(*, bucket: str, key: str) -> Path:
    key_norm = key.replace("\\", "/").lstrip("/")
    p = (_local_bucket_dir(bucket) / key_norm).resolve()
    root = _local_bucket_dir(bucket)
    if not str(p).startswith(str(root)):
        raise ValueError("Invalid storage key")
    return p


def get_s3_client():
    if use_local_storage():
        return None
    global _s3
    if _s3 is None:
        settings = get_settings()
        _s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
    return _s3


def get_s3_presign_client():
    if use_local_storage():
        return None
    global _s3_presign
    if _s3_presign is None:
        settings = get_settings()
        endpoint_url = settings.s3_presign_endpoint_url.strip() or settings.s3_endpoint_url
        _s3_presign = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
    return _s3_presign


def ensure_bucket_exists(bucket: str) -> None:
    if use_local_storage():
        _local_bucket_dir(bucket).mkdir(parents=True, exist_ok=True)
        return
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError:
        pass

    s3.create_bucket(Bucket=bucket)


def put_file(
    *, bucket: str, key: str, file_path: str, content_type: str | None = None, consume_source: bool = False
) -> PutObjectResult:
    if use_local_storage():
        dst = local_object_path(bucket=bucket, key=key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if consume_source:
            try:
                # Only upload-owned assembled files opt in. Same-volume rename
                # avoids copying multi-GB originals after chunk assembly.
                os.replace(file_path, dst)
                return PutObjectResult(bucket=bucket, key=key)
            except OSError as exc:
                if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
                    raise
        shutil.copy2(file_path, dst)
        return PutObjectResult(bucket=bucket, key=key)
    s3 = get_s3_client()
    ct = content_type or guess_content_type(file_path)
    s3.upload_file(file_path, bucket, key, ExtraArgs={"ContentType": ct})
    return PutObjectResult(bucket=bucket, key=key)


def presign_get_url(*, bucket: str, key: str, expires_seconds: int = 900) -> str:
    if use_local_storage():
        return f"/api/v1/storage/{bucket}/{key.lstrip('/')}"
    s3 = get_s3_presign_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )


def delete_object(*, bucket: str, key: str) -> None:
    if use_local_storage():
        p = local_object_path(bucket=bucket, key=key)
        if p.exists() and p.is_file():
            p.unlink()
        return
    s3 = get_s3_client()
    s3.delete_object(Bucket=bucket, Key=key)


def download_object_to_file(*, bucket: str, key: str, file_path: str) -> None:
    if use_local_storage():
        src = local_object_path(bucket=bucket, key=key)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, file_path)
        return
    s3 = get_s3_client()
    s3.download_file(bucket, key, file_path)


def read_object_bytes(*, bucket: str, key: str) -> tuple[bytes, str]:
    if use_local_storage():
        p = local_object_path(bucket=bucket, key=key)
        data = p.read_bytes()
        ct = guess_content_type(p)
        return data, ct
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"
