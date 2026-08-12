from __future__ import annotations

import uuid
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_project
from app.models import Image, Project, Sample
from app.schemas.common import Envelope
from app.schemas.samples import SampleCreateRequest, SampleOut
from app.config import get_settings
from app.storage import delete_object, presign_get_url, put_file


router = APIRouter()


def _sample_out(s: Sample) -> SampleOut:
    settings = get_settings()
    return SampleOut(
        id=s.id,
        image_id=s.image_id,
        name=s.name,
        category=s.category,
        remark=s.remark,
        roi=s.roi,
        crop_storage_key=s.crop_storage_key,
        thumb_storage_key=s.thumb_storage_key,
        image_url=presign_get_url(bucket=settings.s3_bucket, key=s.crop_storage_key) if s.crop_storage_key else None,
        thumbnail_url=presign_get_url(bucket=settings.s3_bucket, key=s.thumb_storage_key) if s.thumb_storage_key else None,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


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
    out = [_sample_out(s) for s in rows]
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

    return Envelope(data=_sample_out(s), request_id=getattr(request.state, "request_id", None))


@router.post("/upload", response_model=Envelope[SampleOut])
async def upload_sample(
    request: Request,
    image_id: uuid.UUID = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    remark: str = Form(""),
    annotation_id: str = Form(...),
    annotation_type: str = Form("rect"),
    image_name: str = Form(""),
    image_format: str = Form("image/png"),
    width: int = Form(...),
    height: int = Form(...),
    sample_id: uuid.UUID | None = Form(default=None),
    image: UploadFile = File(...),
    thumbnail: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    source_image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == image_id))
    if source_image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    s = None
    if sample_id is not None:
        s = db.scalar(select(Sample).where(Sample.project_id == project.id, Sample.id == sample_id))
    if s is None:
        candidates = db.scalars(select(Sample).where(Sample.project_id == project.id, Sample.image_id == image_id)).all()
        s = next((item for item in candidates if (item.roi or {}).get("annotationId") == annotation_id), None)
    if s is None:
        s = Sample(id=uuid.uuid4(), project_id=project.id, image_id=image_id)
        db.add(s)

    settings = get_settings()
    extension = ".jpg" if image_format == "image/jpeg" else ".png"
    crop_key = f"samples/{image_id}/{s.id}/image{extension}"
    thumb_key = f"samples/{image_id}/{s.id}/thumbnail.png"

    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, f"image{extension}")
        with open(image_path, "wb") as f:
            f.write(await image.read())
        put_file(bucket=settings.s3_bucket, key=crop_key, file_path=image_path, content_type=image_format)
        if thumbnail is not None:
            thumb_path = os.path.join(tmp, "thumbnail.png")
            with open(thumb_path, "wb") as f:
                f.write(await thumbnail.read())
            put_file(bucket=settings.s3_bucket, key=thumb_key, file_path=thumb_path, content_type="image/png")
        else:
            thumb_key = crop_key

    s.name = name
    s.category = category
    s.remark = remark
    s.roi = {
        "annotationId": annotation_id,
        "annotationType": annotation_type,
        "imageName": image_name or source_image.name,
        "format": image_format,
        "width": width,
        "height": height,
    }
    s.crop_storage_key = crop_key
    s.thumb_storage_key = thumb_key
    db.commit()
    db.refresh(s)
    return Envelope(data=_sample_out(s), request_id=getattr(request.state, "request_id", None))


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
    settings = get_settings()
    if s.crop_storage_key:
        delete_object(bucket=settings.s3_bucket, key=s.crop_storage_key)
    if s.thumb_storage_key and s.thumb_storage_key != s.crop_storage_key:
        delete_object(bucket=settings.s3_bucket, key=s.thumb_storage_key)
    db.delete(s)
    db.commit()
    return Envelope(data={"deleted": True}, request_id=getattr(request.state, "request_id", None))
