from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.db_types import GUID
from app.sa_types import InetType, JsonType


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="projects_name_nonempty"),
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    satellite: Mapped[str | None] = mapped_column(Text)
    acquisition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    frequency_band: Mapped[str | None] = mapped_column(Text)
    polarization: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="images_project_fk", ondelete="RESTRICT"),
        UniqueConstraint("project_id", "id", name="images_project_id_id_uniq"),
        UniqueConstraint("project_id", "storage_key", name="ux_images_project_storage_key"),
        CheckConstraint("size_bytes >= 0", name="images_size_nonneg"),
        CheckConstraint("status IN ('uploaded','processing','ready','failed')", name="images_status_chk"),
        CheckConstraint("length(trim(storage_key)) > 0", name="images_storage_key_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="images_name_nonempty"),
        Index("ix_images_project_status_created_at", "project_id", "status", "created_at"),
        Index("ix_images_project_created_at", "project_id", "created_at"),
        Index("ix_images_project_checksum", "project_id", "checksum_sha256"),
    )


class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    image_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="preview")
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False, server_default="webp")
    quality: Mapped[int | None] = mapped_column(SmallInteger)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "image_id"],
            ["images.project_id", "images.id"],
            name="thumbnails_image_fk",
            ondelete="CASCADE",
        ),
        UniqueConstraint("project_id", "id", name="thumbnails_project_id_id_uniq"),
        UniqueConstraint("project_id", "image_id", "purpose", "level", "format", name="ux_thumbnails_image_variant"),
        CheckConstraint("level > 0", name="thumbnails_level_positive"),
        CheckConstraint("quality IS NULL OR (quality >= 1 AND quality <= 100)", name="thumbnails_quality_chk"),
        CheckConstraint("format IN ('webp','png','jpeg','jpg')", name="thumbnails_format_chk"),
        CheckConstraint("length(trim(purpose)) > 0", name="thumbnails_purpose_nonempty"),
        CheckConstraint("length(trim(storage_key)) > 0", name="thumbnails_storage_key_nonempty"),
        Index("ix_thumbnails_image", "project_id", "image_id"),
        Index("ix_thumbnails_project_created_at", "project_id", "created_at"),
    )


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    image_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    roi: Mapped[dict | None] = mapped_column(JsonType)
    crop_storage_key: Mapped[str | None] = mapped_column(Text)
    thumb_storage_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "image_id"],
            ["images.project_id", "images.id"],
            name="samples_image_fk",
            ondelete="CASCADE",
        ),
        UniqueConstraint("project_id", "id", name="samples_project_id_id_uniq"),
        CheckConstraint(
            "crop_storage_key IS NULL OR length(trim(crop_storage_key)) > 0",
            name="samples_crop_storage_key_nonempty",
        ),
        CheckConstraint(
            "thumb_storage_key IS NULL OR length(trim(thumb_storage_key)) > 0",
            name="samples_thumb_storage_key_nonempty",
        ),
        Index("ix_samples_image", "project_id", "image_id"),
        Index("ix_samples_project_created_at", "project_id", "created_at"),
        Index("ix_samples_category", "project_id", "category"),
    )


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    image_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    sample_id: Mapped[uuid.UUID | None] = mapped_column(GUID())

    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="annotations_project_id_id_uniq"),
        CheckConstraint(
            "(image_id IS NOT NULL AND sample_id IS NULL) OR (image_id IS NULL AND sample_id IS NOT NULL)",
            name="annotations_target_xor_chk",
        ),
        CheckConstraint("length(trim(type)) > 0", name="annotations_type_nonempty"),
        ForeignKeyConstraint(
            ["project_id", "image_id"],
            ["images.project_id", "images.id"],
            name="annotations_image_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "sample_id"],
            ["samples.project_id", "samples.id"],
            name="annotations_sample_fk",
            ondelete="CASCADE",
        ),
        Index("ix_annotations_image", "project_id", "image_id"),
        Index("ix_annotations_sample", "project_id", "sample_id"),
        Index("ix_annotations_project_type_created_at", "project_id", "type", "created_at"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    image_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    sample_id: Mapped[uuid.UUID | None] = mapped_column(GUID())

    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    progress: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    celery_task_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, server_default="{}")
    result: Mapped[dict | None] = mapped_column(JsonType)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="tasks_project_id_id_uniq"),
        CheckConstraint(
            "(image_id IS NOT NULL AND sample_id IS NULL) OR "
            "(image_id IS NULL AND sample_id IS NOT NULL) OR "
            "(image_id IS NULL AND sample_id IS NULL)",
            name="tasks_target_xor_chk",
        ),
        CheckConstraint("length(trim(type)) > 0", name="tasks_type_nonempty"),
        CheckConstraint("status IN ('pending','processing','succeeded','failed','canceled')", name="tasks_status_chk"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="tasks_progress_chk"),
        ForeignKeyConstraint(
            ["project_id", "image_id"],
            ["images.project_id", "images.id"],
            name="tasks_image_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "sample_id"],
            ["samples.project_id", "samples.id"],
            name="tasks_sample_fk",
            ondelete="CASCADE",
        ),
        Index("ux_tasks_celery_task_id", "celery_task_id", unique=True),
        Index("ix_tasks_project_status_created_at", "project_id", "status", "created_at"),
        Index("ix_tasks_image", "project_id", "image_id"),
        Index("ix_tasks_sample", "project_id", "sample_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    ip: Mapped[str | None] = mapped_column(InetType)
    user_agent: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JsonType)
    after: Mapped[dict | None] = mapped_column(JsonType)
    meta: Mapped[dict] = mapped_column(JsonType, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="audit_logs_project_fk", ondelete="RESTRICT"),
        CheckConstraint("length(trim(action)) > 0", name="audit_logs_action_nonempty"),
        CheckConstraint("length(trim(entity_type)) > 0", name="audit_logs_entity_type_nonempty"),
        CheckConstraint("length(trim(actor_type)) > 0", name="audit_logs_actor_type_nonempty"),
        Index("ix_audit_logs_project_created_at", "project_id", "created_at"),
        Index("ix_audit_logs_entity", "project_id", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_actor", "project_id", "actor_type", "actor_id", "created_at"),
        Index("ix_audit_logs_correlation", "project_id", "correlation_id"),
    )
