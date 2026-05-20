from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    request_id: str | None = None

