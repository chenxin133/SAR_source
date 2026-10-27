from __future__ import annotations

import mimetypes
import logging
import os
import tempfile
import uuid
from pathlib import Path, PureWindowsPath

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from PIL import Image as PILImage, TiffImagePlugin
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
from app.storage import (
    delete_object,
    download_object_to_file,
    guess_content_type,
    local_object_path,
    presign_get_url,
    put_file,
    read_object_bytes,
    use_local_storage,
)
from app.upload_service import assemble, cleanup, get_upload_filename, init_upload, write_part
from app.workers.client import enqueue_process_image


router = APIRouter()
logger = logging.getLogger(__name__)


def _region_to_rgb(crop: PILImage.Image) -> PILImage.Image:
    array = np.asarray(crop)
    if array.ndim == 2:
        values = array.astype(np.float32, copy=False)
        finite = np.isfinite(values)
        if not np.any(finite):
            gray = np.zeros(values.shape, dtype=np.uint8)
        else:
            valid = values[finite]
            low, high = np.percentile(valid, (2, 98))
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                low, high = float(valid.min()), float(valid.max())
            if high <= low:
                high = low + 1.0
            gray = (np.clip((values - low) / (high - low), 0, 1) * 255).astype(np.uint8)
            gray[~finite] = 0
        return PILImage.fromarray(gray, mode="L").convert("RGB")
    return crop.convert("RGB")


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
            frequency_band=r.frequency_band,
            polarization=r.polarization,
            description=r.description,
            width=r.width,
            height=r.height,
            status=r.status,
            error_message=r.error_message,
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
        frequency_band=image.frequency_band,
        polarization=image.polarization,
        description=image.description,
        width=image.width,
        height=image.height,
        status=image.status,
        error_message=image.error_message,
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

    original_filename = PureWindowsPath(get_upload_filename(upload_id) or payload.name or "source.bin").name
    name = payload.name or original_filename
    image_id = uuid.uuid4()
    suffix = Path(original_filename).suffix.lower()
    if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
        suffix = ".bin"
    # Display names can contain Windows path characters or be very long.
    # Keep the original filename as metadata and use a short storage leaf.
    storage_key = f"raw/{image_id}/source{suffix}"
    mime_type = payload.mime_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    try:
        put_file(bucket=settings.s3_bucket, key=storage_key, file_path=assembled_path, content_type=mime_type)
    except OSError as exc:
        logger.exception("Cannot store upload %s: key=%s storage_dir=%s", upload_id, storage_key, settings.local_storage_dir)
        raise HTTPException(
            status_code=500,
            detail="上传文件无法写入数据目录，请检查目录是否存在、路径长度、磁盘空间和写入权限后重试。上传分片已保留。",
        ) from exc

    image = Image(
        id=image_id,
        project_id=project.id,
        name=name,
        original_filename=original_filename,
        mime_type=mime_type,
        satellite=payload.satellite,
        acquisition_at=payload.acquisition_at,
        resolution=payload.resolution,
        frequency_band=payload.frequency_band,
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
    if not media_type or media_type == "application/octet-stream":
        media_type = guess_content_type(t.storage_key)
    if not media_type or media_type == "application/octet-stream":
        media_type = f"image/{(t.format or 'webp').lower()}"
    return Response(content=content, media_type=media_type)


@router.get("/{image_id}/region")
def get_image_region(
    image_id: uuid.UUID,
    x: int = Query(ge=0),
    y: int = Query(ge=0),
    width: int = Query(gt=0),
    height: int = Query(gt=0),
    max_size: int = Query(default=3072, ge=256, le=4096),
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == image_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if width * height > 64_000_000:
        raise HTTPException(status_code=400, detail="Requested region is too large")

    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        local_source = local_object_path(bucket=settings.s3_bucket, key=image.storage_key) if use_local_storage() else None
        if local_source is not None and local_source.is_file():
            source_path = str(local_source)
        else:
            source_path = os.path.join(tmp, os.path.basename(image.original_filename or image.name) or "source")
            download_object_to_file(bucket=settings.s3_bucket, key=image.storage_key, file_path=source_path)
        is_tiff = "tiff" in str(image.mime_type or "").lower() or source_path.lower().endswith((".tif", ".tiff"))
        opened = TiffImagePlugin.TiffImageFile(source_path) if is_tiff else PILImage.open(source_path)
        try:
            source_width, source_height = opened.size
            right = min(source_width, x + width)
            bottom = min(source_height, y + height)
            if x >= right or y >= bottom:
                raise HTTPException(status_code=400, detail="Region is outside the image")
            crop = opened.crop((x, y, right, bottom))
            crop.load()
            rendered = _region_to_rgb(crop)
            rendered.thumbnail((max_size, max_size), resample=PILImage.Resampling.LANCZOS)
            output_path = os.path.join(tmp, "region.webp")
            rendered.save(output_path, format="WEBP", quality=95, method=4)
            return Response(content=Path(output_path).read_bytes(), media_type="image/webp")
        finally:
            opened.close()
