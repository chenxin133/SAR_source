from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.deps import get_project
from app.models import Project, Task
from app.schemas.common import Envelope
from app.schemas.tasks import TaskOut


router = APIRouter()


@router.get("/{task_id}", response_model=Envelope[TaskOut])
def get_task(
    task_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
):
    t = db.scalar(select(Task).where(Task.project_id == project.id, Task.id == task_id))
    if t is None:
        raise HTTPException(status_code=404, detail="Task not found")

    out = TaskOut(
        id=t.id,
        type=t.type,
        status=t.status,
        progress=float(t.progress or 0),
        error_message=t.error_message,
        created_at=t.created_at,
        started_at=t.started_at,
        finished_at=t.finished_at,
        result=t.result,
    )
    return Envelope(data=out, request_id=getattr(request.state, "request_id", None))


@router.get("/stream/{task_id}")
def stream_task(
    task_id: uuid.UUID,
    request: Request,
    project: Project = Depends(get_project),
):
    def event_stream():
        try:
            while True:
                # Use a short-lived session per tick so task status/progress updates
                # from worker are always visible (avoid stale identity-map values).
                db = SessionLocal()
                try:
                    t = db.scalar(select(Task).where(Task.project_id == project.id, Task.id == task_id))
                finally:
                    db.close()

                if t is None:
                    yield "event: error\ndata: " + json.dumps({"detail": "Task not found"}) + "\n\n"
                    return

                payload = {
                    "status": t.status,
                    "progress": float(t.progress or 0),
                    "error": t.error_message,
                    "result": t.result,
                }
                s = json.dumps(payload, ensure_ascii=False)
                yield "data: " + s + "\n\n"

                if t.status in ("succeeded", "failed", "canceled"):
                    return

                time.sleep(1)
        finally:
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")
