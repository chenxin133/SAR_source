from __future__ import annotations

import tempfile
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_project
from app.upload_filenames import storage_filename
from app.duplicate_files import DuplicateAction, import_lock, reuse_duplicate
from app.echo_service import (
    BAND_FREQUENCIES_GHZ, BANDWIDTH_HZ, MAX_ECHO_BYTES, PRF_HZ, SAMPLE_RATE_HZ,
    create_preview, pulse_preview, sha256_file, simulate_echo,
)
from app.models import EchoSignal, Project
from app.schemas.common import Envelope
from app.schemas.echoes import EchoEdit, EchoOut, EchoSimulation
from app.storage import delete_object, download_object_to_file, presign_get_url, put_file


router = APIRouter()


def output(row: EchoSignal) -> EchoOut:
    bucket = get_settings().s3_bucket
    values = {field: getattr(row, field) for field in EchoOut.model_fields
              if field not in ("preview_url", "download_url")}
    return EchoOut(**values, preview_url=presign_get_url(bucket=bucket, key=row.preview_key),
                   download_url=presign_get_url(bucket=bucket, key=row.storage_key))


def find_echo(db: Session, project: Project, echo_id: uuid.UUID) -> EchoSignal:
    row = db.scalar(select(EchoSignal).where(EchoSignal.id == echo_id, EchoSignal.project_id == project.id))
    if row is None:
        raise HTTPException(404, "回波信号不存在")
    return row


def save_echo(db: Session, project: Project, path: Path, *, name: str, filename: str, remark: str,
              source: str, byte_order: str, iq_offset: int, simulation: dict | None = None,
              frequency_band: str | None = None, center_frequency_ghz: float | None = None,
              checksum: str | None = None, existing: EchoSignal | None = None) -> EchoSignal:
    settings = get_settings()
    preview = path.with_suffix(".png")
    try:
        metadata = create_preview(path, preview, byte_order, iq_offset)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    echo_id = existing.id if existing is not None else uuid.uuid4()
    previous_keys = {existing.storage_key, existing.preview_key} if existing is not None else set()
    stem = name[:-4] if name.lower().endswith('.dat') else name
    filename_leaf = storage_filename(stem + '.dat')
    key = f"echoes/{project.id}/{echo_id}/{filename_leaf}"
    preview_key = f"echoes/{project.id}/{echo_id}/{Path(filename_leaf).stem}_amplitude.png"
    if existing is None:
        row = EchoSignal(id=echo_id, project_id=project.id, source=source, simulation=simulation, created_at=datetime.now(timezone.utc))
    else:
        row = existing
    row.name, row.original_filename, row.remark = name, filename, remark
    row.byte_order, row.iq_offset = byte_order, iq_offset
    row.storage_key, row.preview_key = key, preview_key
    row.size_bytes, row.checksum_sha256 = path.stat().st_size, checksum or sha256_file(path)
    for field, value in metadata.items():
        setattr(row, field, value)
    row.frequency_band, row.center_frequency_ghz = frequency_band, center_frequency_ghz
    row.updated_at = datetime.now(timezone.utc)
    try:
        put_file(bucket=settings.s3_bucket, key=key, file_path=str(path), content_type="application/octet-stream")
        put_file(bucket=settings.s3_bucket, key=preview_key, file_path=str(preview), content_type="image/png")
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        for failed_key in {key, preview_key} - previous_keys:
            delete_object(bucket=settings.s3_bucket, key=failed_key)
        raise
    for old_key in previous_keys - {key, preview_key}:
        delete_object(bucket=settings.s3_bucket, key=old_key)
    return row


@router.get("")
def list_echoes(request: Request, q: str = Query(default="", max_length=200),
                source: Literal["imported", "simulated"] | None = None,
                frequency_band: Literal["C", "X", "Ku", "Ka"] | None = None,
                limit: int = Query(default=20, ge=1, le=200), offset: int = Query(default=0, ge=0),
                db: Session = Depends(get_db), project: Project = Depends(get_project)):
    filters = [EchoSignal.project_id == project.id]
    if q.strip():
        filters.append(EchoSignal.name.contains(q.strip(), autoescape=True))
    if source:
        filters.append(EchoSignal.source == source)
    if frequency_band:
        filters.append(EchoSignal.frequency_band == frequency_band)
    total = db.scalar(select(func.count()).select_from(EchoSignal).where(*filters))
    rows = db.scalars(select(EchoSignal).where(*filters)
                      .order_by(EchoSignal.created_at.desc(), EchoSignal.id).offset(offset).limit(limit)).all()
    return {"data": [output(row) for row in rows], "total": total,
            "request_id": getattr(request.state, "request_id", None)}


@router.post("/upload", response_model=Envelope[EchoOut], status_code=201)
def upload_echo(request: Request, duplicate_action: DuplicateAction = Form(default="ask"), file: UploadFile = File(...), name: str = Form(default="", max_length=200),
                remark: str = Form(default="", max_length=2000),
                byte_order: Literal["little", "big"] = Form(default="little"),
                iq_offset: int = Form(default=32768),
                frequency_band: Literal["", "C", "X", "Ku", "Ka"] = Form(default=""),
                db: Session = Depends(get_db), project: Project = Depends(get_project)):
    if iq_offset not in (0, 32768):
        raise HTTPException(422, "I/Q 偏置必须为 0 或 32768")
    filename = (file.filename or "signal.dat").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".dat"):
        raise HTTPException(400, "请选择二进制 .dat 回波文件")
    with tempfile.TemporaryDirectory(prefix="sar-echo-") as tmp:
        path = Path(tmp) / "signal.dat"
        try:
            with path.open("wb") as stream:
                size = 0
                digest = hashlib.sha256()
                while block := file.file.read(1024 * 1024):
                    size += len(block)
                    if size > MAX_ECHO_BYTES:
                        raise HTTPException(413, "回波文件不能超过 64 MiB")
                    stream.write(block)
                    digest.update(block)
            checksum = digest.hexdigest()
            with import_lock:
                existing = db.scalar(select(EchoSignal).where(
                    EchoSignal.project_id == project.id, EchoSignal.checksum_sha256 == checksum,
                ).order_by(EchoSignal.created_at, EchoSignal.id))
                if reuse_duplicate(existing, duplicate_action) and duplicate_action == 'reuse':
                    return Envelope(data=output(existing), request_id=getattr(request.state, "request_id", None))
                row = save_echo(db, project, path, name=name.strip() or filename[:200], filename=filename,
                                remark=remark, source="imported", byte_order=byte_order, iq_offset=iq_offset,
                                frequency_band=frequency_band or None, checksum=checksum, existing=existing if duplicate_action == 'update' else None)
        finally:
            file.file.close()
    return Envelope(data=output(row), request_id=getattr(request.state, "request_id", None))


@router.post("/simulate", response_model=Envelope[EchoOut], status_code=201)
def simulate(request: Request, payload: EchoSimulation,
             db: Session = Depends(get_db), project: Project = Depends(get_project)):
    parameters = payload.model_dump(exclude={"name", "remark"})
    with tempfile.TemporaryDirectory(prefix="sar-echo-") as tmp:
        path = Path(tmp) / "signal.dat"
        simulate_echo(path, **parameters)
        row = save_echo(db, project, path, name=payload.name,
                        filename=f"echo_{payload.frequency_band}_{payload.na}x{payload.nr}.dat",
                        remark=payload.remark, source="simulated", byte_order="little", iq_offset=32768,
                        frequency_band=payload.frequency_band,
                        center_frequency_ghz=BAND_FREQUENCIES_GHZ[payload.frequency_band],
                        simulation={"model": "baseband-lfm-three-point-targets-v2", **parameters,
                                    "center_frequency_ghz": BAND_FREQUENCIES_GHZ[payload.frequency_band],
                                    "sample_rate_hz": SAMPLE_RATE_HZ, "bandwidth_hz": BANDWIDTH_HZ,
                                    "prf_hz": PRF_HZ})
    return Envelope(data=output(row), request_id=getattr(request.state, "request_id", None))


@router.get("/{echo_id}", response_model=Envelope[EchoOut])
def get_echo(echo_id: uuid.UUID, db: Session = Depends(get_db), project: Project = Depends(get_project)):
    return Envelope(data=output(find_echo(db, project, echo_id)))


@router.get("/{echo_id}/pulse")
def get_pulse(echo_id: uuid.UUID, pulse: int = Query(default=0, ge=0),
              db: Session = Depends(get_db), project: Project = Depends(get_project)):
    row = find_echo(db, project, echo_id)
    if pulse >= row.na:
        raise HTTPException(400, "脉冲索引超出范围")
    with tempfile.TemporaryDirectory(prefix="sar-echo-") as tmp:
        path = Path(tmp) / "signal.dat"
        download_object_to_file(bucket=get_settings().s3_bucket, key=row.storage_key, file_path=str(path))
        data = pulse_preview(path, row.byte_order, row.iq_offset, pulse)
    return {"data": data}


@router.get("/{echo_id}/download")
def download(echo_id: uuid.UUID, db: Session = Depends(get_db), project: Project = Depends(get_project)):
    row = find_echo(db, project, echo_id)
    return RedirectResponse(presign_get_url(bucket=get_settings().s3_bucket, key=row.storage_key))


@router.patch("/{echo_id}", response_model=Envelope[EchoOut])
def edit(echo_id: uuid.UUID, payload: EchoEdit,
         db: Session = Depends(get_db), project: Project = Depends(get_project)):
    row = find_echo(db, project, echo_id)
    previous = {row.storage_key, row.preview_key}
    if row.name != payload.name:
        stem = payload.name[:-4] if payload.name.lower().endswith('.dat') else payload.name
        leaf = storage_filename(stem + '.dat')
        folder = f'echoes/{project.id}/{row.id}'
        keys = (f'{folder}/{leaf}', f'{folder}/{Path(leaf).stem}_amplitude.png')
        with tempfile.TemporaryDirectory() as tmp:
            for old, new, mime in ((row.storage_key, keys[0], 'application/octet-stream'), (row.preview_key, keys[1], 'image/png')):
                if old != new:
                    path = str(Path(tmp) / Path(old).name)
                    download_object_to_file(bucket=get_settings().s3_bucket, key=old, file_path=path)
                    put_file(bucket=get_settings().s3_bucket, key=new, file_path=path, content_type=mime)
        row.storage_key, row.preview_key = keys
    row.name, row.remark = payload.name, payload.remark
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    for old in previous - {row.storage_key, row.preview_key}:
        delete_object(bucket=get_settings().s3_bucket, key=old)
    return Envelope(data=output(row))


@router.delete("/{echo_id}")
def delete(echo_id: uuid.UUID, db: Session = Depends(get_db), project: Project = Depends(get_project)):
    row = find_echo(db, project, echo_id)
    bucket = get_settings().s3_bucket
    delete_object(bucket=bucket, key=row.storage_key)
    delete_object(bucket=bucket, key=row.preview_key)
    db.delete(row)
    db.commit()
    return {"data": {"deleted": True}}
