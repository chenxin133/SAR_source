from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_project
from app.models import Project, Task
from app.schemas.common import Envelope
from app.storage import put_file
from app.workers.celery_app import celery_app


router = APIRouter()


@router.post("", response_model=Envelope[dict], status_code=202)
async def import_package(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip is supported")

    settings = get_settings()
    task_id = uuid.uuid4()
    storage_key = f"imports/{task_id}/package.zip"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "package.zip")
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)
        put_file(bucket=settings.s3_bucket, key=storage_key, file_path=path, content_type="application/zip")

    t = Task(
        id=task_id,
        project_id=project.id,
        type="import_package",
        status="pending",
        progress=0,
        payload={"storage_key": storage_key},
    )
    db.add(t)
    db.commit()

    if settings.task_execution_mode.strip().lower() == "inline":
        from app.workers.tasks import import_package as import_package_task

        import_package_task.run(task_id=str(task_id), project_id=str(project.id), storage_key=storage_key)
    else:
        celery_app.send_task(
            "app.workers.tasks.import_package",
            kwargs={"task_id": str(task_id), "project_id": str(project.id), "storage_key": storage_key},
        )

    return Envelope(data={"task_id": str(task_id)}, request_id=getattr(request.state, "request_id", None))
