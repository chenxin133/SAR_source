from __future__ import annotations

import threading
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Task
from app.workers.celery_app import celery_app


def _run_process_image_inline_async(*, task_id: uuid.UUID, project_id: uuid.UUID, image_id: uuid.UUID) -> None:
    from app.workers.tasks import process_image as process_image_task

    process_image_task.run(task_id=str(task_id), project_id=str(project_id), image_id=str(image_id))


def enqueue_process_image(*, db: Session, project_id: uuid.UUID, image_id: uuid.UUID) -> uuid.UUID:
    settings = get_settings()
    task = Task(
        id=uuid.uuid4(),
        project_id=project_id,
        image_id=image_id,
        type="process_image",
        status="pending",
        progress=0,
        payload={},
        started_at=None,
        finished_at=None,
    )
    db.add(task)
    db.commit()

    task.started_at = datetime.utcnow()
    task.status = "processing"
    db.commit()

    if settings.task_execution_mode.strip().lower() == "inline":
        worker = threading.Thread(
            target=_run_process_image_inline_async,
            kwargs={"task_id": task.id, "project_id": project_id, "image_id": image_id},
            daemon=True,
            name=f"process-image-{task.id}",
        )
        worker.start()
        return task.id

    res = celery_app.send_task(
        "app.workers.tasks.process_image",
        kwargs={"task_id": str(task.id), "project_id": str(project_id), "image_id": str(image_id)},
    )
    task.celery_task_id = res.id
    db.commit()
    return task.id
