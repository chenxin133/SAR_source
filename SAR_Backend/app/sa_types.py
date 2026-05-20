from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import INET, JSONB


JsonType = JSON().with_variant(JSONB, "postgresql")
InetType = String(45).with_variant(INET, "postgresql")
