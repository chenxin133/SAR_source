from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Project


def get_project(
    db: Session = Depends(get_db),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
) -> Project:
    settings = get_settings()
    if x_project_id:
        try:
            pid = uuid.UUID(x_project_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Project-Id")
        project = db.scalar(select(Project).where(Project.id == pid))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    project = db.scalar(select(Project).where(Project.name == settings.default_project_name))
    if project is None:
        raise HTTPException(status_code=500, detail="Default project not initialized")
    return project
