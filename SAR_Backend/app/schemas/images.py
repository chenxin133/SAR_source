from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ImageOut(BaseModel):
    id: uuid.UUID
    name: str
    size_bytes: int
    mime_type: str | None = None
    satellite: str | None = None
    acquisition_at: datetime | None = None
    resolution: str | None = None
    frequency_band: str | None = None
    polarization: str | None = None
    description: str | None = None
    width: int | None = None
    height: int | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ThumbnailOut(BaseModel):
    id: uuid.UUID
    purpose: str
    level: int
    format: str
    quality: int | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    url: str | None = None


class ImageDetailOut(ImageOut):
    thumbnails: list[ThumbnailOut] = []


class UploadInitRequest(BaseModel):
    filename: str
    total_size: int


class UploadInitResponse(BaseModel):
    upload_id: str
    part_size: int


class UploadCompleteRequest(BaseModel):
    total_parts: int
    name: str | None = None
    mime_type: str | None = None
    satellite: str | None = None
    acquisition_at: datetime | None = None
    resolution: str | None = None
    frequency_band: str | None = None
    polarization: str | None = None
    description: str | None = None


class UploadCompleteResponse(BaseModel):
    image_id: uuid.UUID
