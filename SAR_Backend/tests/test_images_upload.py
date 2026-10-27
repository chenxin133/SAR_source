from __future__ import annotations

import hashlib
import uuid

from app.config import get_settings
from app.models import Image


def test_chunk_upload_flow(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.images.put_file", lambda **_kwargs: None, raising=False)

    init = client.post("/api/v1/images/upload/init", json={"filename": "a.tif", "total_size": 10})
    assert init.status_code == 200
    upload_id = init.json()["data"]["upload_id"]

    part1 = client.put(f"/api/v1/images/upload/{upload_id}/part/1", data=b"12345")
    assert part1.status_code == 200
    part2 = client.put(f"/api/v1/images/upload/{upload_id}/part/2", data=b"67890")
    assert part2.status_code == 200

    done = client.post(
        f"/api/v1/images/upload/{upload_id}/complete",
        json={"total_parts": 2, "name": "a.tif", "mime_type": "image/tiff", "frequency_band": "X"},
    )
    assert done.status_code == 200
    image_id = done.json()["data"]["image_id"]
    assert image_id

    lst = client.get("/api/v1/images")
    assert lst.status_code == 200
    uploaded = next(x for x in lst.json()["data"] if str(x["id"]) == image_id)
    assert uploaded["frequency_band"] == "X"


def test_upload_keeps_filename_separate_from_display_name(client, db_session, tmp_path):
    settings = get_settings()
    settings.storage_backend = "local"
    settings.local_storage_dir = str(tmp_path / "storage")
    filename = "原始双通道影像.TIFF"
    display_name = "SAR:试验/" + "长名称" * 100
    original = b"II*\x00original-raster-bytes"
    upload_id = client.post("/api/v1/images/upload/init", json={
        "filename": filename, "total_size": len(original),
    }).json()["data"]["upload_id"]
    assert client.put(f"/api/v1/images/upload/{upload_id}/part/1", content=original).status_code == 200
    response = client.post(f"/api/v1/images/upload/{upload_id}/complete", json={
        "total_parts": 1, "name": display_name,
    })
    assert response.status_code == 200
    image = db_session.get(Image, uuid.UUID(response.json()["data"]["image_id"]))
    assert image.name == display_name
    assert image.original_filename == filename
    assert image.mime_type == "image/tiff"
    assert image.storage_key == f"raw/{image.id}/source.tiff"
    assert (tmp_path / "storage/sar" / image.storage_key).read_bytes() == original
    assert image.checksum_sha256 == hashlib.sha256(original).hexdigest()


def test_failed_storage_write_keeps_upload_for_retry(client, db_session, monkeypatch, tmp_path):
    from pathlib import Path

    before = db_session.query(Image).count()
    upload_id = client.post("/api/v1/images/upload/init", json={
        "filename": "source.tif", "total_size": 5,
    }).json()["data"]["upload_id"]
    client.put(f"/api/v1/images/upload/{upload_id}/part/1", content=b"12345")
    def missing_destination(**_kwargs):
        raise FileNotFoundError("destination unavailable")
    monkeypatch.setattr("app.api.routes.images.put_file", missing_destination)
    response = client.post(f"/api/v1/images/upload/{upload_id}/complete", json={"total_parts": 1, "name": "source.tif"})
    assert response.status_code == 500
    assert "无法写入数据目录" in response.json()["detail"]
    assert db_session.query(Image).count() == before
    assert (Path(get_settings().upload_tmp_dir) / upload_id / "part_000001").read_bytes() == b"12345"
