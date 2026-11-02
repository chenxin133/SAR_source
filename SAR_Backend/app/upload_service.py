from __future__ import annotations

import hashlib
import json
import os
import pathlib
import uuid

from app.config import get_settings
from fastapi import HTTPException


def _upload_dir(upload_id: uuid.UUID) -> pathlib.Path:
    settings = get_settings()
    return pathlib.Path(settings.upload_tmp_dir) / str(upload_id)


def init_upload(*, filename: str, total_size: int, project_id: uuid.UUID | None = None) -> dict:
    upload_id = uuid.uuid4()
    d = _upload_dir(upload_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "upload.json").write_text(json.dumps({"filename": filename, "project_id": str(project_id) if project_id else None}, ensure_ascii=False), encoding="utf-8")
    settings = get_settings()
    return {
        "upload_id": str(upload_id),
        "part_size": settings.max_upload_part_bytes,
        "filename": filename,
        "total_size": total_size,
    }


def require_upload_project(upload_id: uuid.UUID, project_id: uuid.UUID) -> None:
    try:
        info = json.loads((_upload_dir(upload_id) / "upload.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "Upload not found")
    if info.get("project_id") not in (None, str(project_id)):
        raise HTTPException(404, "Upload not found")


def get_upload_filename(upload_id: uuid.UUID) -> str | None:
    try:
        info = json.loads((_upload_dir(upload_id) / "upload.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None  # Uploads started before filename metadata was introduced.
    return str(info["filename"])


def write_part(*, upload_id: uuid.UUID, part_no: int, data: bytes) -> int:
    d = _upload_dir(upload_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "assembled.json").unlink(missing_ok=True)
    p = d / f"part_{part_no:06d}"
    p.write_bytes(data)
    return p.stat().st_size


def has_part(*, upload_id: uuid.UUID, part_no: int) -> bool:
    p = _upload_dir(upload_id) / f"part_{part_no:06d}"
    return p.exists()


def assemble(*, upload_id: uuid.UUID, total_parts: int) -> tuple[str, str, int]:
    d = _upload_dir(upload_id)
    out_path = d / "assembled.bin"
    cache = d / "assembled.json"
    if cache.exists() and out_path.exists():
        info = json.loads(cache.read_text(encoding="utf-8"))
        if info["total_parts"] == total_parts and info["size"] == out_path.stat().st_size:
            return str(out_path), info["sha256"], info["size"]
    h = hashlib.sha256()
    size = 0
    with out_path.open("wb") as out:
        for part_no in range(1, total_parts + 1):
            part_path = d / f"part_{part_no:06d}"
            if not part_path.exists():
                raise FileNotFoundError(f"missing part {part_no}")
            chunk = part_path.read_bytes()
            out.write(chunk)
            h.update(chunk)
            size += len(chunk)
    cache.write_text(json.dumps({"total_parts": total_parts, "sha256": h.hexdigest(), "size": size}), encoding="utf-8")
    return str(out_path), h.hexdigest(), size


def cleanup(upload_id: uuid.UUID) -> None:
    d = _upload_dir(upload_id)
    if not d.exists():
        return
    for root, dirs, files in os.walk(d, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except OSError:
                pass
        for dd in dirs:
            try:
                os.rmdir(os.path.join(root, dd))
            except OSError:
                pass
    try:
        os.rmdir(d)
    except OSError:
        pass
