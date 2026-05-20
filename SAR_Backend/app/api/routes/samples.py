from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_project
from app.models import Image, Project, Sample
from app.schemas.common import Envelope
from app.schemas.samples import SampleCreateRequest, SampleOut


router = APIRouter()


@router.get("", response_model=Envelope[list[SampleOut]])
def list_samples(
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = db.scalars(
        select(Sample)
        .where(Sample.project_id == project.id)
        .order_by(Sample.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    out = [
        SampleOut(
            id=s.id,
            image_id=s.image_id,
            name=s.name,
            category=s.category,
            remark=s.remark,
            roi=s.roi,
            crop_storage_key=s.crop_storage_key,
            thumb_storage_key=s.thumb_storage_key,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in rows
    ]
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.post("", response_model=Envelope[SampleOut])
def create_sample(
    payload: SampleCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    img = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == payload.image_id))
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")

    s = Sample(
        project_id=project.id,
        image_id=payload.image_id,
        name=payload.name,
        category=payload.category,
        remark=payload.remark,
        roi=payload.roi,
        crop_storage_key=payload.crop_storage_key,
        thumb_storage_key=payload.thumb_storage_key,
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    out = SampleOut(
        id=s.id,
        image_id=s.image_id,
        name=s.name,
        category=s.category,
        remark=s.remark,
        roi=s.roi,
        crop_storage_key=s.crop_storage_key,
        thumb_storage_key=s.thumb_storage_key,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.delete("/{sample_id}", response_model=Envelope[dict])
def delete_sample(
    sample_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    s = db.scalar(select(Sample).where(Sample.project_id == project.id, Sample.id == sample_id))
    if s is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db.delete(s)
    db.commit()
    return Envelope(data={"deleted": True}, request_id=getattr(request.state, "request_id", None))
