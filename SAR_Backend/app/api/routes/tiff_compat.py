from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_project
from app.models import Image, Project, Task
from app.storage import presign_get_url, put_file
from app.workers.client import enqueue_process_image


router = APIRouter()


@router.post("/upload", status_code=202)
async def upload_tiff_compat(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    if not (file.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(status_code=400, detail="Only TIFF files are supported")

    settings = get_settings()
    image_id = uuid.uuid4()
    name = file.filename or f"{image_id}.tif"
    storage_key = f"raw/{image_id}/{name}"

    with tempfile.TemporaryDirectory() as tmp:
        local_path = os.path.join(tmp, "upload.tif")
        content = await file.read()
        with open(local_path, "wb") as f:
            f.write(content)
        put_file(
            bucket=settings.s3_bucket,
            key=storage_key,
            file_path=local_path,
            content_type=file.content_type or "image/tiff",
        )

    image = Image(
        id=image_id,
        project_id=project.id,
        name=name,
        original_filename=name,
        mime_type=file.content_type or "image/tiff",
        size_bytes=len(content),
        storage_key=storage_key,
        status="uploaded",
    )
    db.add(image)
    db.commit()

    task_id = enqueue_process_image(db=db, project_id=project.id, image_id=image_id)
    return {"task_id": str(task_id), "status": "pending", "message": "File uploaded, compression task started."}


@router.get("/tasks/{task_id}")
def get_task_status_compat(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    t = db.scalar(select(Task).where(Task.project_id == project.id, Task.id == task_id))
    if t is None:
        raise HTTPException(status_code=404, detail="Task not found")

    response = {
        "task_id": str(t.id),
        "status": t.status,
        "progress": float(t.progress or 0),
        "result_url": None,
        "error": t.error_message,
    }
    if t.status == "succeeded" and t.result and isinstance(t.result, dict):
        thumbs = t.result.get("thumbnails") or {}
        settings = get_settings()
        for k in sorted(thumbs.keys(), reverse=True):
            response["result_url"] = presign_get_url(bucket=settings.s3_bucket, key=thumbs[k])
            break
    return response
