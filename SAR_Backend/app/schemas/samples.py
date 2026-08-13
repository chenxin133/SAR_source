from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SampleCreateRequest(BaseModel):
    image_id: uuid.UUID
    name: str | None = None
    category: str | None = None
    remark: str | None = None
    roi: dict | None = None
    crop_storage_key: str | None = None
    thumb_storage_key: str | None = None


class SampleCropRequest(BaseModel):
    image_id: uuid.UUID
    name: str
    category: str = ""
    remark: str = ""
    annotation_id: str
    annotation_type: str = "rect"
    output_format: str = "source"
    coordinate_width: float
    coordinate_height: float
    polygon: list[dict[str, float]]
    sample_id: uuid.UUID | None = None


class SampleOut(BaseModel):
    id: uuid.UUID
    image_id: uuid.UUID
    name: str | None = None
    category: str | None = None
    remark: str | None = None
    roi: dict | None = None
    crop_storage_key: str | None = None
    thumb_storage_key: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    created_at: datetime
    updated_at: datetime
