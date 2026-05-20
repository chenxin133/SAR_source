from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_project
from app.models import Annotation, Project
from app.schemas.annotations import AnnotationCreateRequest, AnnotationOut
from app.schemas.common import Envelope


router = APIRouter()


@router.get("", response_model=Envelope[list[AnnotationOut]])
def list_annotations(
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    image_id: uuid.UUID | None = None,
    sample_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    q = select(Annotation).where(Annotation.project_id == project.id)
    if image_id is not None:
        q = q.where(Annotation.image_id == image_id)
    if sample_id is not None:
        q = q.where(Annotation.sample_id == sample_id)
    q = q.order_by(Annotation.created_at.desc()).limit(limit).offset(offset)

    rows = db.scalars(q).all()
    out = [
        AnnotationOut(
            id=a.id,
            image_id=a.image_id,
            sample_id=a.sample_id,
            type=a.type,
            payload=a.payload,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in rows
    ]
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.post("", response_model=Envelope[AnnotationOut])
def create_annotation(
    payload: AnnotationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    if (payload.image_id is None and payload.sample_id is None) or (
        payload.image_id is not None and payload.sample_id is not None
    ):
        raise HTTPException(status_code=400, detail="Provide exactly one of image_id or sample_id")

    a = Annotation(
        project_id=project.id,
        image_id=payload.image_id,
        sample_id=payload.sample_id,
        type=payload.type,
        payload=payload.payload,
    )
    db.add(a)
    db.commit()
    db.refresh(a)

    out = AnnotationOut(
        id=a.id,
        image_id=a.image_id,
        sample_id=a.sample_id,
        type=a.type,
        payload=a.payload,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.delete("/{annotation_id}", response_model=Envelope[dict])
def delete_annotation(
    annotation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    a = db.scalar(select(Annotation).where(Annotation.project_id == project.id, Annotation.id == annotation_id))
    if a is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    db.delete(a)
    db.commit()
    return Envelope(data={"deleted": True}, request_id=getattr(request.state, "request_id", None))
