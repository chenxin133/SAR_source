from __future__ import annotations

import math
import os
import tempfile
import uuid
from datetime import datetime
from zipfile import ZipFile

import numpy as np
from celery import Task as CeleryTask
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Annotation, Image, Sample, Thumbnail, Task
from app.storage import download_object_to_file, put_file
from app.workers.celery_app import celery_app


def _levels() -> list[int]:
    settings = get_settings()
    levels = []
    for part in settings.thumbnail_levels.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            levels.append(int(part))
        except ValueError:
            continue
    return sorted(set([x for x in levels if x > 0]), reverse=True) or [1024, 512, 256]


def _parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _update_task(
    *,
    db,
    task_id: uuid.UUID,
    status: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    result: dict | None = None,
):
    t = db.scalar(select(Task).where(Task.id == task_id))
    if t is None:
        return
    if status is not None:
        t.status = status
    if progress is not None:
        t.progress = float(progress)
    if error is not None:
        t.error_message = error
    if result is not None:
        t.result = result
    if status in ("succeeded", "failed", "canceled"):
        t.finished_at = datetime.utcnow()
    db.commit()


def _update_image_status(*, db, image_id: uuid.UUID, status: str, error: str | None = None):
    img = db.scalar(select(Image).where(Image.id == image_id))
    if img is None:
        return
    img.status = status
    img.error_message = error
    db.commit()


def _read_preview_with_gdal(path: str, max_size: int) -> np.ndarray:
    try:
        from osgeo import gdal
    except Exception as e:
        raise RuntimeError("GDAL not available") from e

    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError("Failed to open raster")

    w = ds.RasterXSize
    h = ds.RasterYSize
    ratio = min(max_size / w, max_size / h) if (w > max_size or h > max_size) else 1.0
    tw = max(1, int(w * ratio))
    th = max(1, int(h * ratio))

    arr = ds.ReadAsArray(buf_xsize=tw, buf_ysize=th)
    if arr is None:
        raise RuntimeError("Failed to read raster")
    return arr


def _sample_raster_for_preview(arr: np.ndarray, max_size: int) -> np.ndarray:
    arr = np.squeeze(arr)
    if arr.ndim == 2:
        step_y = max(1, math.ceil(arr.shape[0] / max_size))
        step_x = max(1, math.ceil(arr.shape[1] / max_size))
        return np.asarray(arr[::step_y, ::step_x])
    if arr.ndim == 3:
        if arr.shape[0] <= 4:
            step_y = max(1, math.ceil(arr.shape[1] / max_size))
            step_x = max(1, math.ceil(arr.shape[2] / max_size))
            return np.asarray(arr[:, ::step_y, ::step_x])
        if arr.shape[-1] <= 4:
            step_y = max(1, math.ceil(arr.shape[0] / max_size))
            step_x = max(1, math.ceil(arr.shape[1] / max_size))
            return np.asarray(np.moveaxis(arr[::step_y, ::step_x, :], -1, 0))
    raise RuntimeError(f"Unsupported TIFF shape: {arr.shape!r}")


def _read_preview_with_pillow(path: str, max_size: int) -> np.ndarray:
    try:
        from PIL import Image as PILImage
    except Exception as e:
        raise RuntimeError("Pillow not available") from e

    with PILImage.open(path) as img:
        try:
            img.draft("RGB", (max_size, max_size))
        except Exception:
            pass
        img.thumbnail((max_size, max_size), resample=PILImage.Resampling.BILINEAR)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        arr = np.asarray(img)
    return _normalize_raster_shape(arr)


def _read_preview_with_tifffile(path: str, max_size: int) -> np.ndarray:
    try:
        import tifffile
    except Exception as e:
        raise RuntimeError("tifffile not available") from e

    try:
        arr = tifffile.memmap(path)
    except Exception:
        with tifffile.TiffFile(path) as tif:
            if tif.series:
                series = tif.series[0]
                levels = list(getattr(series, "levels", None) or [series])
                arr = None
                for level in reversed(levels):
                    try:
                        arr = level.asarray()
                        if arr is not None:
                            break
                    except Exception:
                        continue
                if arr is None:
                    arr = series.asarray()
            else:
                arr = tif.asarray()
    if arr is None:
        raise RuntimeError("Failed to read TIFF with tifffile")
    return _sample_raster_for_preview(arr, max_size=max_size)


def _normalize_raster_shape(arr: np.ndarray) -> np.ndarray:
    arr = np.squeeze(np.asarray(arr))
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        if arr.shape[0] <= 4:
            return arr
        if arr.shape[-1] <= 4:
            return np.moveaxis(arr, -1, 0)
    raise RuntimeError(f"Unsupported TIFF shape: {arr.shape!r}")


def _to_uint8_gray(data: np.ndarray) -> np.ndarray:
    if np.iscomplexobj(data):
        data = np.abs(data)

    data = data.astype(np.float32, copy=False)
    valid = np.isfinite(data)
    if not np.any(valid):
        return np.zeros_like(data, dtype=np.uint8)

    v = data[valid]
    vmin, vmax = np.percentile(v, (2, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin = float(np.min(v))
        vmax = float(np.max(v))
        if vmax <= vmin:
            vmax = vmin + 1.0

    clipped = np.clip(data, vmin, vmax)
    norm = (clipped - vmin) / (vmax - vmin)
    out = (norm * 255.0).astype(np.uint8)
    out[~valid] = 0
    return out


def _to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        g = _to_uint8_gray(arr)
        return np.stack([g, g, g], axis=-1)

    if arr.ndim == 3 and arr.shape[0] >= 3:
        rgb = arr[:3, :, :]
        if np.iscomplexobj(rgb):
            rgb = np.abs(rgb)
        rgb = rgb.astype(np.float32, copy=False)
        out = np.zeros((rgb.shape[1], rgb.shape[2], 3), dtype=np.uint8)
        for i in range(3):
            out[:, :, i] = _to_uint8_gray(rgb[i, :, :])
        return out

    if arr.ndim == 3 and arr.shape[0] == 1:
        g = _to_uint8_gray(arr[0, :, :])
        return np.stack([g, g, g], axis=-1)

    raise RuntimeError("Unsupported raster shape")


def _resize_rgb(rgb_u8: np.ndarray, max_size: int) -> np.ndarray:
    h, w = rgb_u8.shape[:2]
    if w <= max_size and h <= max_size:
        return rgb_u8

    ratio = min(max_size / w, max_size / h)
    tw = max(1, int(w * ratio))
    th = max(1, int(h * ratio))

    from PIL import Image as PILImage

    img = PILImage.fromarray(rgb_u8, mode="RGB")
    resized = img.resize((tw, th), resample=PILImage.Resampling.BILINEAR)
    return np.asarray(resized)


def _build_preview_rgb(path: str, max_size: int) -> np.ndarray:
    try:
        arr = _read_preview_with_gdal(path, max_size=max_size)
        rgb = _to_uint8_rgb(arr)
    except Exception:
        try:
            arr = _read_preview_with_tifffile(path, max_size=max_size)
            rgb = _to_uint8_rgb(_normalize_raster_shape(arr))
        except Exception:
            rgb = _to_uint8_rgb(_read_preview_with_pillow(path, max_size=max_size))
    return _resize_rgb(rgb, max_size=max_size)


def _save_webp(rgb_u8: np.ndarray, out_path: str, quality: int):
    from PIL import Image as PILImage

    img = PILImage.fromarray(rgb_u8, mode="RGB")
    img.save(out_path, format="WEBP", quality=int(quality), method=6)


@celery_app.task(bind=True, name="app.workers.tasks.process_image", acks_late=True)
def process_image(self: CeleryTask, task_id: str, project_id: str, image_id: str):
    settings = get_settings()
    task_uuid = uuid.UUID(task_id)
    image_uuid = uuid.UUID(image_id)
    bucket = settings.s3_bucket

    db = SessionLocal()
    try:
        img = db.scalar(select(Image).where(Image.project_id == uuid.UUID(project_id), Image.id == image_uuid))
        if img is None:
            _update_task(db=db, task_id=task_uuid, status="failed", progress=100, error="Image not found")
            return

        _update_image_status(db=db, image_id=image_uuid, status="processing")
        _update_task(db=db, task_id=task_uuid, status="processing", progress=1)

        quality = int(settings.thumbnail_quality)
        levels = _levels()

        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "raw.tif")
            download_object_to_file(bucket=bucket, key=img.storage_key, file_path=local_path)

            produced: dict[str, str] = {}
            for idx, level in enumerate(levels):
                p = 5 + (idx / max(1, len(levels))) * 80
                _update_task(db=db, task_id=task_uuid, status="processing", progress=p)

                rgb = _build_preview_rgb(local_path, max_size=level)
                out_path = os.path.join(tmp, f"preview_{level}.webp")
                _save_webp(rgb, out_path, quality=quality)

                storage_key = f"thumbnails/{image_uuid}/preview_{level}.webp"
                put_file(bucket=bucket, key=storage_key, file_path=out_path, content_type="image/webp")

                thumb = db.scalar(
                    select(Thumbnail).where(
                        Thumbnail.project_id == uuid.UUID(project_id),
                        Thumbnail.image_id == image_uuid,
                        Thumbnail.purpose == "preview",
                        Thumbnail.level == level,
                        Thumbnail.format == "webp",
                    )
                )
                if thumb is None:
                    thumb = Thumbnail(
                        project_id=uuid.UUID(project_id),
                        image_id=image_uuid,
                        purpose="preview",
                        level=level,
                        format="webp",
                        quality=quality,
                        storage_key=storage_key,
                        width=int(rgb.shape[1]),
                        height=int(rgb.shape[0]),
                        size_bytes=os.path.getsize(out_path),
                    )
                    db.add(thumb)
                else:
                    thumb.storage_key = storage_key
                    thumb.quality = quality
                    thumb.width = int(rgb.shape[1])
                    thumb.height = int(rgb.shape[0])
                    thumb.size_bytes = os.path.getsize(out_path)
                db.commit()
                produced[str(level)] = storage_key

        img.status = "ready"
        img.updated_at = datetime.utcnow()
        db.commit()
        _update_task(db=db, task_id=task_uuid, status="succeeded", progress=100, result={"thumbnails": produced})
        return {"ok": True, "thumbnails": produced}
    except Exception as e:
        try:
            _update_task(db=db, task_id=task_uuid, status="failed", progress=100, error=str(e))
            _update_image_status(db=db, image_id=image_uuid, status="failed", error=str(e))
        except Exception:
            pass

        retries = getattr(self.request, "retries", 0)
        if retries < settings.task_max_retries:
            countdown = int(math.pow(2, retries))
            raise self.retry(exc=e, countdown=countdown, max_retries=settings.task_max_retries)
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="app.workers.tasks.import_package", acks_late=True)
def import_package(self: CeleryTask, task_id: str, project_id: str, storage_key: str):
    settings = get_settings()
    task_uuid = uuid.UUID(task_id)
    project_uuid = uuid.UUID(project_id)

    db = SessionLocal()
    bucket = settings.s3_bucket

    try:
        _update_task(db=db, task_id=task_uuid, status="processing", progress=1)

        with tempfile.TemporaryDirectory() as tmp:
            local_zip = os.path.join(tmp, "package.zip")
            download_object_to_file(bucket=bucket, key=storage_key, file_path=local_zip)

            with ZipFile(local_zip, "r") as z:
                if "manifest.json" not in z.namelist():
                    raise RuntimeError("manifest.json not found")

                manifest = z.read("manifest.json").decode("utf-8")
                data = __import__("json").loads(manifest)

                mapping: dict[str, uuid.UUID] = {}
                raw_images = data.get("raw_images") or []
                total = max(1, len(raw_images))

                for idx, item in enumerate(raw_images):
                    progress = 5 + (idx / total) * 50
                    _update_task(db=db, task_id=task_uuid, status="processing", progress=progress)

                    legacy_id = str(item.get("id") or "")
                    meta_path = f"raw_images/{legacy_id}/metadata.json"
                    file_path = f"raw_images/{legacy_id}/file.bin"

                    meta = {}
                    if meta_path in z.namelist():
                        meta = __import__("json").loads(z.read(meta_path).decode("utf-8"))

                    name = str(meta.get("name") or legacy_id or "imported")
                    mime_type = str(meta.get("mime_type") or "application/octet-stream")
                    satellite = meta.get("satellite")
                    acquisition_at = meta.get("acquisition_at") or meta.get("acquisitionDate")
                    resolution = meta.get("resolution")
                    polarization = meta.get("polarization")
                    description = meta.get("description")

                    image_uuid = uuid.uuid4()
                    mapping[legacy_id] = image_uuid

                    if file_path in z.namelist():
                        raw_bytes = z.read(file_path)
                        raw_local = os.path.join(tmp, f"{image_uuid}.bin")
                        with open(raw_local, "wb") as f:
                            f.write(raw_bytes)
                        raw_key = f"raw/{image_uuid}/{name}"
                        put_file(bucket=bucket, key=raw_key, file_path=raw_local, content_type=mime_type)
                        size_bytes = len(raw_bytes)
                    else:
                        raw_key = f"raw/{image_uuid}/{name}"
                        size_bytes = 0

                    img = Image(
                        id=image_uuid,
                        project_id=project_uuid,
                        name=name,
                        original_filename=name,
                        mime_type=mime_type,
                        satellite=str(satellite) if satellite is not None else None,
                        acquisition_at=_parse_datetime(acquisition_at),
                        resolution=str(resolution) if resolution is not None else None,
                        polarization=str(polarization) if polarization is not None else None,
                        description=str(description) if description is not None else None,
                        size_bytes=size_bytes,
                        storage_key=raw_key,
                        status="uploaded",
                    )
                    db.add(img)
                    db.commit()

                    preview_path = f"raw_images/{legacy_id}/preview.bin"
                    thumb_path = f"raw_images/{legacy_id}/thumbnail.bin"
                    if preview_path in z.namelist():
                        preview_bytes = z.read(preview_path)
                        preview_local = os.path.join(tmp, f"{image_uuid}_preview.bin")
                        with open(preview_local, "wb") as f:
                            f.write(preview_bytes)
                        key = f"thumbnails/{image_uuid}/preview_1024.webp"
                        put_file(bucket=bucket, key=key, file_path=preview_local, content_type="image/webp")
                        db.add(
                            Thumbnail(
                                project_id=project_uuid,
                                image_id=image_uuid,
                                purpose="preview",
                                level=1024,
                                format="webp",
                                quality=80,
                                storage_key=key,
                                size_bytes=len(preview_bytes),
                            )
                        )
                        db.commit()

                    if thumb_path in z.namelist():
                        thumb_bytes = z.read(thumb_path)
                        thumb_local = os.path.join(tmp, f"{image_uuid}_thumb.bin")
                        with open(thumb_local, "wb") as f:
                            f.write(thumb_bytes)
                        key = f"thumbnails/{image_uuid}/thumb_256.webp"
                        put_file(bucket=bucket, key=key, file_path=thumb_local, content_type="image/webp")
                        db.add(
                            Thumbnail(
                                project_id=project_uuid,
                                image_id=image_uuid,
                                purpose="preview",
                                level=256,
                                format="webp",
                                quality=80,
                                storage_key=key,
                                size_bytes=len(thumb_bytes),
                            )
                        )
                        db.commit()

                annotations = data.get("annotations") or []
                for idx, item in enumerate(annotations):
                    legacy_id = str(item.get("id") or "")
                    p = f"annotations/{legacy_id}/annotation.json"
                    if p not in z.namelist():
                        continue
                    payload = __import__("json").loads(z.read(p).decode("utf-8"))
                    legacy_image_id = str(payload.get("imageId") or payload.get("image_id") or "")
                    image_uuid = mapping.get(legacy_image_id)
                    if image_uuid is None:
                        continue
                    a = Annotation(
                        project_id=project_uuid,
                        image_id=image_uuid,
                        sample_id=None,
                        type="annotations_v1",
                        payload=payload,
                    )
                    db.add(a)
                    db.commit()

                samples = data.get("samples") or []
                for idx, item in enumerate(samples):
                    legacy_id = str(item.get("id") or "")
                    p = f"samples/{legacy_id}/sample.json"
                    if p not in z.namelist():
                        continue
                    payload = __import__("json").loads(z.read(p).decode("utf-8"))
                    legacy_image_id = str(payload.get("imageId") or payload.get("image_id") or "")
                    image_uuid = mapping.get(legacy_image_id)
                    if image_uuid is None:
                        continue

                    crop_key = None
                    thumb_key = None

                    img_blob_path = payload.get("image")
                    if img_blob_path and isinstance(img_blob_path, str) and img_blob_path in z.namelist():
                        b = z.read(img_blob_path)
                        lp = os.path.join(tmp, f"{legacy_id}_sample.bin")
                        with open(lp, "wb") as f:
                            f.write(b)
                        crop_key = f"samples/{image_uuid}/{legacy_id}/crop.bin"
                        put_file(
                            bucket=bucket,
                            key=crop_key,
                            file_path=lp,
                            content_type=str(payload.get("format") or "application/octet-stream"),
                        )

                    thumb_blob_path = payload.get("thumbnail")
                    if thumb_blob_path and isinstance(thumb_blob_path, str) and thumb_blob_path in z.namelist():
                        b = z.read(thumb_blob_path)
                        lp = os.path.join(tmp, f"{legacy_id}_thumb.bin")
                        with open(lp, "wb") as f:
                            f.write(b)
                        thumb_key = f"samples/{image_uuid}/{legacy_id}/thumb.bin"
                        put_file(bucket=bucket, key=thumb_key, file_path=lp, content_type="application/octet-stream")

                    s = Sample(
                        project_id=project_uuid,
                        image_id=image_uuid,
                        name=payload.get("name"),
                        category=payload.get("category"),
                        remark=payload.get("remark"),
                        roi=None,
                        crop_storage_key=crop_key,
                        thumb_storage_key=thumb_key,
                    )
                    db.add(s)
                    db.commit()

        _update_task(db=db, task_id=task_uuid, status="succeeded", progress=100, result={"imported": True})
        return {"ok": True}
    except Exception as e:
        _update_task(db=db, task_id=task_uuid, status="failed", progress=100, error=str(e))
        raise
    finally:
        db.close()
