from __future__ import annotations

import errno
import hashlib
import shutil
import uuid

import numpy as np
import pytest
from PIL import Image as PILImage

from app.config import get_settings
from app.models import Image, Project, Task, Thumbnail
from app.storage import put_file
from app.workers import tasks


def test_consumed_local_upload_moves_without_copying(client, monkeypatch, tmp_path):
    settings = get_settings()
    settings.storage_backend = "local"
    settings.local_storage_dir = str(tmp_path / "storage")
    source = tmp_path / "assembled.bin"
    original = b"full-precision-original" * 1024
    source.write_bytes(original)
    def unnecessary_copy(*_args, **_kwargs):
        raise AssertionError("Same-volume upload should not copy the entire file")
    monkeypatch.setattr("app.storage.shutil.copy2", unnecessary_copy)
    result = put_file(bucket="sar", key="raw/test/source.tif", file_path=str(source), consume_source=True)
    assert result.key == "raw/test/source.tif"
    assert not source.exists()
    assert (tmp_path / "storage/sar/raw/test/source.tif").read_bytes() == original


def test_consumed_upload_on_other_volume_falls_back_without_losing_source(client, monkeypatch, tmp_path):
    settings = get_settings()
    settings.storage_backend = "local"
    settings.local_storage_dir = str(tmp_path / "storage")
    source = tmp_path / "assembled.bin"
    source.write_bytes(b"original")
    def other_volume(*_args, **_kwargs):
        raise OSError(errno.EXDEV, "different volume")
    monkeypatch.setattr("app.storage.os.replace", other_volume)
    put_file(bucket="sar", key="raw/test/source.tif", file_path=str(source), consume_source=True)
    assert source.read_bytes() == b"original"
    assert (tmp_path / "storage/sar/raw/test/source.tif").read_bytes() == b"original"


@pytest.mark.parametrize("storage_backend", ["local", "s3"])
def test_image_preview_reads_original_once_and_preserves_all_levels(client, db_session, monkeypatch, tmp_path, storage_backend):
    settings = get_settings()
    settings.storage_backend = storage_backend
    settings.local_storage_dir = str(tmp_path / "storage")
    settings.thumbnail_levels = "64,32,16"
    settings.task_max_retries = 0
    project = db_session.query(Project).filter(Project.name == settings.default_project_name).one()
    image_id, task_id = uuid.uuid4(), uuid.uuid4()
    key = f"raw/{image_id}/source.tif"
    source = tmp_path / "storage/sar" / key
    source.parent.mkdir(parents=True)
    PILImage.fromarray(np.arange(80 * 100, dtype=np.uint16).reshape(80, 100)).save(source, format="TIFF")
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    db_session.add(Image(id=image_id, project_id=project.id, name="performance.tif", original_filename="performance.tif",
                         mime_type="image/tiff", storage_key=key, size_bytes=source.stat().st_size, status="uploaded"))
    db_session.add(Task(id=task_id, project_id=project.id, image_id=image_id, type="process_image",
                        status="pending", progress=0, payload={}))
    db_session.commit()
    calls, downloads = [], []
    real_build = tasks._build_preview_rgb
    def build_once(path, max_size):
        calls.append(max_size)
        return real_build(path, max_size)
    def download(**kwargs):
        downloads.append(kwargs["key"])
        assert storage_backend == "s3", "Local previews must read the stored original directly"
        shutil.copy2(source, kwargs["file_path"])
    monkeypatch.setattr(tasks, "_build_preview_rgb", build_once)
    monkeypatch.setattr(tasks, "download_object_to_file", download)
    if storage_backend == "s3":
        monkeypatch.setattr(tasks, "put_file", lambda **_kwargs: None)

    tasks.process_image.run(task_id=str(task_id), project_id=str(project.id), image_id=str(image_id))
    db_session.expire_all()
    assert calls == [64]
    assert downloads == ([] if storage_backend == "local" else [key])
    assert db_session.get(Task, task_id).status == "succeeded"
    image = db_session.get(Image, image_id)
    assert image.status == "ready" and (image.width, image.height) == (100, 80)
    thumbnails = db_session.query(Thumbnail).filter(Thumbnail.image_id == image_id).all()
    assert sorted(thumb.level for thumb in thumbnails) == [16, 32, 64]
    assert all(max(thumb.width, thumb.height) <= thumb.level for thumb in thumbnails)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
