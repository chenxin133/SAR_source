from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AnnotationCreateRequest(BaseModel):
    image_id: uuid.UUID | None = None
    sample_id: uuid.UUID | None = None
    type: str
    payload: dict


class AnnotationOut(BaseModel):
    id: uuid.UUID
    image_id: uuid.UUID | None = None
    sample_id: uuid.UUID | None = None
    type: str
    payload: dict
    created_at: datetime
    updated_at: datetime

