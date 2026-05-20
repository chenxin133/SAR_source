from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.storage import local_object_path, use_local_storage

router = APIRouter()


@router.get("/{bucket}/{key:path}")
def get_local_storage_object(bucket: str, key: str):
    if not use_local_storage():
        raise HTTPException(status_code=404, detail="Not available")
    try:
        p = local_object_path(bucket=bucket, key=key)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid key")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Object not found")
    return FileResponse(str(p))
