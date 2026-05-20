from __future__ import annotations

import mimetypes
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_project
from app.models import Image, Project, Thumbnail
from app.schemas.common import Envelope
from app.schemas.images import (
    ImageDetailOut,
    ImageOut,
    ThumbnailOut,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitRequest,
    UploadInitResponse,
)
from app.storage import delete_object, presign_get_url, put_file, read_object_bytes
from app.upload_service import assemble, cleanup, init_upload, write_part
from app.workers.client import enqueue_process_image


router = APIRouter()


@router.get("", response_model=Envelope[list[ImageOut]])
def list_images(
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = (
        select(Image)
        .where(Image.project_id == project.id)
        .order_by(Image.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.scalars(q).all()
    out = [
        ImageOut(
            id=r.id,
            name=r.name,
            size_bytes=int(r.size_bytes or 0),
            mime_type=r.mime_type,
            satellite=r.satellite,
            acquisition_at=r.acquisition_at,
            resolution=r.resolution,
            polarization=r.polarization,
            description=r.description,
            width=r.width,
            height=r.height,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.get("/{image_id}", response_model=Envelope[ImageDetailOut])
def get_image(
    image_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == image_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    thumbs = db.scalars(
        select(Thumbnail).where(Thumbnail.project_id == project.id, Thumbnail.image_id == image_id)
    ).all()
    settings = get_settings()
    thumb_out = [
        ThumbnailOut(
            id=t.id,
            purpose=t.purpose,
            level=t.level,
            format=t.format,
            quality=t.quality,
            width=t.width,
            height=t.height,
            size_bytes=t.size_bytes,
            url=presign_get_url(bucket=settings.s3_bucket, key=t.storage_key),
        )
        for t in thumbs
    ]
    out = ImageDetailOut(
        id=image.id,
        name=image.name,
        size_bytes=int(image.size_bytes or 0),
        mime_type=image.mime_type,
        satellite=image.satellite,
        acquisition_at=image.acquisition_at,
        resolution=image.resolution,
        polarization=image.polarization,
        description=image.description,
        width=image.width,
        height=image.height,
        status=image.status,
        created_at=image.created_at,
        updated_at=image.updated_at,
        thumbnails=thumb_out,
    )
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.delete("/{image_id}", response_model=Envelope[dict])
def delete_image(
    image_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    settings = get_settings()
    image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == image_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    thumbs = db.scalars(
        select(Thumbnail).where(Thumbnail.project_id == project.id, Thumbnail.image_id == image_id)
    ).all()
    for t in thumbs:
        delete_object(bucket=settings.s3_bucket, key=t.storage_key)
    delete_object(bucket=settings.s3_bucket, key=image.storage_key)

    db.delete(image)
    db.commit()
    return Envelope(data={"deleted": True}, request_id=getattr(request.state, "request_id", None))


@router.post("/upload/init", response_model=Envelope[UploadInitResponse])
def upload_init(
    payload: UploadInitRequest,
    request: Request,
    project: Project = Depends(get_project),
):
    info = init_upload(filename=payload.filename, total_size=payload.total_size)
    return Envelope(
        data=UploadInitResponse(upload_id=info["upload_id"], part_size=int(info["part_size"])),
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/upload/{upload_id}/part/{part_no}", response_model=Envelope[dict])
async def upload_part(
    upload_id: uuid.UUID,
    part_no: int,
    request: Request,
    project: Project = Depends(get_project),
):
    if part_no <= 0:
        raise HTTPException(status_code=400, detail="Invalid part number")
    settings = get_settings()
    body = await request.body()
    if len(body) <= 0 or len(body) > settings.max_upload_part_bytes:
        raise HTTPException(status_code=400, detail="Invalid part size")
    stored = write_part(upload_id=upload_id, part_no=part_no, data=body)
    return Envelope(data={"stored_bytes": stored}, request_id=getattr(request.state, "request_id", None))


@router.post("/upload/{upload_id}/complete", response_model=Envelope[UploadCompleteResponse])
def upload_complete(
    upload_id: uuid.UUID,
    payload: UploadCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    settings = get_settings()
    if payload.total_parts <= 0:
        raise HTTPException(status_code=400, detail="Invalid total_parts")

    try:
        assembled_path, sha256, size_bytes = assemble(upload_id=upload_id, total_parts=payload.total_parts)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    name = payload.name or os.path.basename(assembled_path)
    image_id = uuid.uuid4()
    storage_key = f"raw/{image_id}/{name}"
    mime_type = payload.mime_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    put_file(bucket=settings.s3_bucket, key=storage_key, file_path=assembled_path, content_type=mime_type)

    image = Image(
        id=image_id,
        project_id=project.id,
        name=name,
        original_filename=name,
        mime_type=mime_type,
        satellite=payload.satellite,
        acquisition_at=payload.acquisition_at,
        resolution=payload.resolution,
        polarization=payload.polarization,
        description=payload.description,
        size_bytes=size_bytes,
        checksum_sha256=sha256,
        storage_key=storage_key,
        status="uploaded",
    )
    db.add(image)
    db.commit()

    cleanup(upload_id)
    return Envelope(
        data=UploadCompleteResponse(image_id=image_id),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/{image_id}/process", response_model=Envelope[dict])
def process_image(
    image_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == image_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    task_id = enqueue_process_image(db=db, project_id=project.id, image_id=image_id)
    return Envelope(data={"task_id": str(task_id)}, request_id=getattr(request.state, "request_id", None))


@router.get("/{image_id}/thumbnails", response_model=Envelope[list[ThumbnailOut]])
def get_thumbnails(
    image_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    settings = get_settings()
    thumbs = db.scalars(
        select(Thumbnail).where(Thumbnail.project_id == project.id, Thumbnail.image_id == image_id)
    ).all()
    out = [
        ThumbnailOut(
            id=t.id,
            purpose=t.purpose,
            level=t.level,
            format=t.format,
            quality=t.quality,
            width=t.width,
            height=t.height,
            size_bytes=t.size_bytes,
            url=presign_get_url(bucket=settings.s3_bucket, key=t.storage_key),
        )
        for t in thumbs
    ]
    out.sort(key=lambda x: -x.level)
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.get("/{image_id}/preview")
def get_preview_content(
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    t = db.scalar(
        select(Thumbnail)
        .where(Thumbnail.project_id == project.id, Thumbnail.image_id == image_id, Thumbnail.purpose == "preview")
        .order_by(Thumbnail.level.desc())
    )
    if t is None:
        raise HTTPException(status_code=404, detail="Preview not found")

    try:
        settings = get_settings()
        content, media_type = read_object_bytes(bucket=settings.s3_bucket, key=t.storage_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Preview object not found")
    if not media_type:
        media_type = f"image/{(t.format or 'webp').lower()}"
    return Response(content=content, media_type=media_type)
