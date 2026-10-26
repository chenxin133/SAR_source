from __future__ import annotations

import uuid
import os
import tempfile
import math
import gc
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from PIL import Image as PILImage, ImageDraw, TiffImagePlugin
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_project
from app.models import Annotation, Image, Project, Sample, Thumbnail
from app.schemas.common import Envelope
from app.schemas.samples import SampleCreateRequest, SampleCropRequest, SampleOut
from app.config import get_settings
from app.storage import delete_object, download_object_to_file, local_object_path, presign_get_url, put_file, use_local_storage


router = APIRouter()


def _source_output_format(source_mime: str | None, source_name: str, requested: str) -> tuple[str, str, str]:
    value = requested.strip().lower()
    if value == "source":
        mime = (source_mime or "").lower()
        suffix = Path(source_name).suffix.lower()
        if "tiff" in mime or suffix in {".tif", ".tiff"}:
            return "image/tiff", ".tif", "TIFF"
        if "jpeg" in mime or suffix in {".jpg", ".jpeg"}:
            return "image/jpeg", ".jpg", "JPEG"
        if "png" in mime or suffix == ".png":
            return "image/png", ".png", "PNG"
        return "image/png", ".png", "PNG"
    if value in {"image/tiff", "tiff", "tif"}:
        return "image/tiff", ".tif", "TIFF"
    if value in {"image/jpeg", "jpeg", "jpg"}:
        return "image/jpeg", ".jpg", "JPEG"
    if value in {"image/png", "png"}:
        return "image/png", ".png", "PNG"
    raise HTTPException(status_code=400, detail="Unsupported sample output format")


def _apply_polygon_mask(crop: PILImage.Image, polygon: list[tuple[float, float]], output_format: str) -> PILImage.Image:
    if len(polygon) < 3:
        return crop
    mask = PILImage.new("L", crop.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    if np.asarray(crop).ndim == 2 and np.asarray(crop).dtype.itemsize > 1:
        masked = np.array(crop, copy=True)
        masked[np.asarray(mask) == 0] = 0
        return PILImage.fromarray(masked)
    if output_format == "PNG":
        rgba = crop.convert("RGBA")
        rgba.putalpha(mask)
        return rgba
    if output_format == "JPEG":
        rgb = crop.convert("RGB")
        return PILImage.composite(rgb, PILImage.new("RGB", rgb.size, 0), mask)
    try:
        return PILImage.composite(crop, PILImage.new(crop.mode, crop.size, 0), mask)
    except Exception:
        rgb = crop.convert("RGB")
        return PILImage.composite(rgb, PILImage.new("RGB", rgb.size, 0), mask)


def _display_image(image: PILImage.Image) -> PILImage.Image:
    array = np.asarray(image)
    if array.ndim != 2 or array.dtype == np.uint8:
        return image.copy()

    values = array.astype(np.float32, copy=False)
    finite = np.isfinite(values)
    nonzero = finite & (values != 0)
    valid_mask = nonzero if np.any(nonzero) else finite
    if not np.any(valid_mask):
        return PILImage.new("L", image.size, 0)

    valid = values[valid_mask]
    low, high = np.percentile(valid, (2, 98))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = float(valid.min()), float(valid.max())
    if high <= low:
        gray = np.zeros(values.shape, dtype=np.uint8)
        gray[valid_mask] = 192
        return PILImage.fromarray(gray, mode="L")
    gray = (np.clip((values - low) / (high - low), 0, 1) * 255).astype(np.uint8)
    gray[~valid_mask] = 0
    return PILImage.fromarray(gray, mode="L")


def _save_crop(
    image: PILImage.Image,
    path: str,
    output_format: str,
    *,
    preserve_values: bool = False,
) -> None:
    if output_format == "TIFF" and preserve_values:
        image.save(path, format="TIFF", compression="tiff_deflate")
        return

    rendered = _display_image(image)
    if output_format == "JPEG":
        rendered.convert("RGB").save(path, format="JPEG", quality=95, subsampling=0)
    elif output_format == "TIFF":
        rendered.convert("RGB").save(path, format="TIFF", compression="tiff_deflate")
    else:
        if rendered.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
            rendered = rendered.convert("RGB")
        rendered.save(path, format="PNG", compress_level=6)


def _sample_thumbnail(image: PILImage.Image) -> PILImage.Image:
    return _display_image(image).convert("RGB")


def _annotation_polygon(annotation: dict) -> list[dict[str, float]]:
    points = annotation.get("points") or []
    if len(points) >= 3:
        return [{"x": float(point["x"]), "y": float(point["y"])} for point in points]
    rect = annotation.get("rect") or {}
    x = float(rect.get("x", 0))
    y = float(rect.get("y", 0))
    width = float(rect.get("w", 0))
    height = float(rect.get("h", 0))
    if width <= 0 or height <= 0:
        return []
    return [
        {"x": x, "y": y},
        {"x": x + width, "y": y},
        {"x": x + width, "y": y + height},
        {"x": x, "y": y + height},
    ]


def _resolve_sample_geometry(db: Session, project: Project, sample: Sample) -> tuple[float, float, list[dict[str, float]]] | None:
    roi = sample.roi or {}
    polygon = roi.get("polygon") or []
    coordinate_width = float(roi.get("coordinateWidth") or 0)
    coordinate_height = float(roi.get("coordinateHeight") or 0)
    if len(polygon) >= 3 and coordinate_width > 0 and coordinate_height > 0:
        return coordinate_width, coordinate_height, polygon

    annotation_id = str(roi.get("annotationId") or "")
    if not annotation_id or annotation_id.startswith("manual:"):
        return None
    record = db.scalar(
        select(Annotation).where(
            Annotation.project_id == project.id,
            Annotation.image_id == sample.image_id,
            Annotation.type == "annotations_v1",
        )
    )
    payload = record.payload if record else {}
    annotation = next(
        (item for item in (payload.get("annotations") or []) if str(item.get("id") or "") == annotation_id),
        None,
    )
    if annotation is None:
        return None
    polygon = _annotation_polygon(annotation)
    if len(polygon) < 3:
        return None

    coordinate_width = float(payload.get("coordinateWidth") or 0)
    coordinate_height = float(payload.get("coordinateHeight") or 0)
    if coordinate_width <= 0 or coordinate_height <= 0:
        thumbnail = db.scalar(
            select(Thumbnail)
            .where(
                Thumbnail.project_id == project.id,
                Thumbnail.image_id == sample.image_id,
                Thumbnail.purpose == "preview",
            )
            .order_by(Thumbnail.level.desc())
        )
        coordinate_width = float(thumbnail.width or 0) if thumbnail else 0
        coordinate_height = float(thumbnail.height or 0) if thumbnail else 0
    if coordinate_width <= 0 or coordinate_height <= 0:
        return None
    return coordinate_width, coordinate_height, polygon


def _resolve_source_image(db: Session, project: Project, sample: Sample) -> Image | None:
    source_image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == sample.image_id))
    if source_image is not None:
        return source_image
    image_name = str((sample.roi or {}).get("imageName") or "").strip()
    if not image_name:
        return None
    matches = db.scalars(
        select(Image)
        .where(Image.project_id == project.id, Image.name == image_name)
        .order_by(Image.created_at.desc())
    ).all()
    return matches[0] if matches else None


def _render_source_crop(
    source_image: Image,
    coordinate_width: float,
    coordinate_height: float,
    polygon: list[dict[str, float]],
    output_format: str,
) -> tuple[bytes, bytes, str, str, int, int]:
    settings = get_settings()
    content_type, extension, pil_format = _source_output_format(
        source_image.mime_type,
        source_image.original_filename or source_image.name,
        output_format,
    )
    with tempfile.TemporaryDirectory() as tmp:
        source_path = os.path.join(tmp, Path(source_image.original_filename or source_image.name).name or "source")
        crop_path = os.path.join(tmp, f"image{extension}")
        thumb_path = os.path.join(tmp, "thumbnail.png")
        local_source = local_object_path(bucket=settings.s3_bucket, key=source_image.storage_key) if use_local_storage() else None
        if local_source is not None and local_source.is_file():
            source_path = str(local_source)
        else:
            download_object_to_file(bucket=settings.s3_bucket, key=source_image.storage_key, file_path=source_path)
        # This file is an already-ingested project image. Use the TIFF-specific
        # reader so very large rasters are not rejected by Pillow's global
        # decompression-bomb threshold before the small crop is decoded.
        source_type, _, _ = _source_output_format(
            source_image.mime_type, source_image.original_filename or source_image.name, "source"
        )
        if source_type == "image/tiff":
            opened = TiffImagePlugin.TiffImageFile(source_path)
        else:
            opened = PILImage.open(source_path)
        try:
            source_width, source_height = opened.size
            scale_x = source_width / coordinate_width
            scale_y = source_height / coordinate_height
            source_polygon = [
                (
                    max(0.0, min(float(point["x"]) * scale_x, float(source_width))),
                    max(0.0, min(float(point["y"]) * scale_y, float(source_height))),
                )
                for point in polygon
            ]
            min_x = max(0, math.floor(min(point[0] for point in source_polygon)))
            min_y = max(0, math.floor(min(point[1] for point in source_polygon)))
            max_x = min(source_width, math.ceil(max(point[0] for point in source_polygon)))
            max_y = min(source_height, math.ceil(max(point[1] for point in source_polygon)))
            if max_x <= min_x or max_y <= min_y:
                raise HTTPException(status_code=400, detail="Crop region is empty")

            crop = opened.crop((min_x, min_y, max_x, max_y))
            crop.load()
            crop = crop.copy()
            local_polygon = [(x - min_x, y - min_y) for x, y in source_polygon]
            crop = _apply_polygon_mask(crop, local_polygon, pil_format)
            _save_crop(
                crop,
                crop_path,
                pil_format,
                preserve_values=output_format.strip().lower() == "source",
            )

            thumb = _sample_thumbnail(crop)
            thumb.thumbnail((256, 256), resample=PILImage.Resampling.LANCZOS)
            thumb.save(thumb_path, format="PNG")
            crop_width, crop_height = crop.size
        finally:
            opened.close()
            del opened
            gc.collect()
        return (
            Path(crop_path).read_bytes(),
            Path(thumb_path).read_bytes(),
            content_type,
            extension,
            crop_width,
            crop_height,
        )


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
    extension = ".tif" if image_format == "image/tiff" else ".jpg" if image_format == "image/jpeg" else ".png"
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


@router.get("/{sample_id}/export")
def export_sample(
    sample_id: uuid.UUID,
    format: str = "source",
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    s = db.scalar(select(Sample).where(Sample.project_id == project.id, Sample.id == sample_id))
    if s is None or not s.crop_storage_key:
        raise HTTPException(status_code=404, detail="Sample file not found")
    settings = get_settings()
    source_type = str((s.roi or {}).get("format") or "application/octet-stream")
    if format.strip().lower() == "source":
        if str((s.roi or {}).get("annotationId") or "").startswith("manual:"):
            with tempfile.TemporaryDirectory() as tmp:
                original_path = os.path.join(tmp, Path(s.crop_storage_key).name)
                download_object_to_file(bucket=settings.s3_bucket, key=s.crop_storage_key, file_path=original_path)
                return Response(content=Path(original_path).read_bytes(), media_type=source_type)
        source_image = _resolve_source_image(db, project, s)
        geometry = _resolve_sample_geometry(db, project, s)
        if source_image is not None and geometry is not None:
            coordinate_width, coordinate_height, polygon = geometry
            content, _thumbnail, media_type, _extension, _width, _height = _render_source_crop(
                source_image,
                coordinate_width,
                coordinate_height,
                polygon,
                "source",
            )
            return Response(content=content, media_type=media_type)
        raise HTTPException(
            status_code=409,
            detail="Source image or annotation geometry is unavailable; regenerate this sample from the annotation page",
        )

    target_type, extension, pil_format = _source_output_format(source_type, s.crop_storage_key, format)
    with tempfile.TemporaryDirectory() as tmp:
        source_path = os.path.join(tmp, Path(s.crop_storage_key).name)
        target_path = os.path.join(tmp, f"export{extension}")
        download_object_to_file(bucket=settings.s3_bucket, key=s.crop_storage_key, file_path=source_path)
        try:
            with PILImage.open(source_path) as opened:
                _save_crop(opened, target_path, pil_format)
            return Response(content=Path(target_path).read_bytes(), media_type=target_type)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Sample cannot be converted: {exc}") from exc


@router.post("/crop", response_model=Envelope[SampleOut])
def crop_sample_from_source(
    payload: SampleCropRequest,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    source_image = db.scalar(select(Image).where(Image.project_id == project.id, Image.id == payload.image_id))
    if source_image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if payload.coordinate_width <= 0 or payload.coordinate_height <= 0 or len(payload.polygon) < 3:
        raise HTTPException(status_code=400, detail="Invalid crop coordinates")

    s = None
    if payload.sample_id is not None:
        s = db.scalar(select(Sample).where(Sample.project_id == project.id, Sample.id == payload.sample_id))
    if s is None:
        candidates = db.scalars(
            select(Sample).where(Sample.project_id == project.id, Sample.image_id == payload.image_id)
        ).all()
        s = next((item for item in candidates if (item.roi or {}).get("annotationId") == payload.annotation_id), None)
    if s is None:
        s = Sample(id=uuid.uuid4(), project_id=project.id, image_id=payload.image_id)
        db.add(s)

    settings = get_settings()
    crop_bytes, thumbnail_bytes, content_type, extension, crop_width, crop_height = _render_source_crop(
        source_image,
        payload.coordinate_width,
        payload.coordinate_height,
        payload.polygon,
        payload.output_format,
    )
    crop_key = f"samples/{payload.image_id}/{s.id}/image{extension}"
    thumb_key = f"samples/{payload.image_id}/{s.id}/thumbnail.png"

    with tempfile.TemporaryDirectory() as tmp:
        crop_path = os.path.join(tmp, f"image{extension}")
        thumb_path = os.path.join(tmp, "thumbnail.png")
        Path(crop_path).write_bytes(crop_bytes)
        Path(thumb_path).write_bytes(thumbnail_bytes)

        put_file(bucket=settings.s3_bucket, key=crop_key, file_path=crop_path, content_type=content_type)
        put_file(bucket=settings.s3_bucket, key=thumb_key, file_path=thumb_path, content_type="image/png")

    s.name = payload.name
    s.category = payload.category
    s.remark = payload.remark
    s.roi = {
        "annotationId": payload.annotation_id,
        "annotationType": payload.annotation_type,
        "imageName": source_image.name,
        "format": content_type,
        "width": crop_width,
        "height": crop_height,
        "coordinateWidth": payload.coordinate_width,
        "coordinateHeight": payload.coordinate_height,
        "polygon": payload.polygon,
        "sourceFormat": source_image.mime_type,
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
