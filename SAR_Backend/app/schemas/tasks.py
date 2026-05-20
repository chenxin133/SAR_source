from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    progress: float
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict | None = None

