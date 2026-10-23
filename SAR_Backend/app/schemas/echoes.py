from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EchoEdit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    remark: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class EchoSimulation(EchoEdit):
    name: str = Field(default="仿真回波", min_length=1, max_length=200)
    na: int = Field(default=256, ge=1, le=4096)
    nr: int = Field(default=512, ge=8, le=8192)
    seed: int = Field(default=20261023, ge=0, le=4294967295)
    noise_std: float = Field(default=300, ge=0, le=5000, allow_inf_nan=False)
    gate_start: int = Field(default=1000, ge=0, le=4294967295)
    frequency_band: Literal["C", "X", "Ku", "Ka"] = "X"

    @model_validator(mode="after")
    def sample_limit(self):
        if self.na * self.nr > 4_194_304:
            raise ValueError("单次仿真最多 4194304 个复采样点")
        return self


class EchoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    original_filename: str
    remark: str
    source: Literal["imported", "simulated"]
    frequency_band: str | None
    center_frequency_ghz: float | None
    na: int
    nr: int
    byte_order: str
    iq_offset: int
    gate_min: int
    gate_max: int
    size_bytes: int
    checksum_sha256: str
    simulation: dict | None
    created_at: datetime
    updated_at: datetime
    preview_url: str
    download_url: str
