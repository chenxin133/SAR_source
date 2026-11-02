from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.duplicate_files import DuplicateAction

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    satellite: str | None = None
    acquisition_at: datetime | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    resolution: str | None = None
    frequency_band: str | None = None
    polarization: str | None = None
    description: str | None = None
    status: Literal["uploaded", "processing", "ready", "failed"] | None = None
    error_message: str | None = None

    @field_validator("name", "size_bytes", "status")
    @classmethod
    def require_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("此字段不能为空")
        return value.strip() if isinstance(value, str) else value


class ImageOut(BaseModel):
    metadata_xml_url: str | None = None
    metadata_xml_filename: str | None = None
    scene_metadata: dict | None = None
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
    metadata_xml_base64: str | None = Field(default=None, max_length=2796212)
    metadata_xml_filename: str | None = None
    duplicate_action: DuplicateAction = "ask"
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
    reused: bool = False
    updated: bool = False
