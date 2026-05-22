from __future__ import annotations

import uuid


def test_process_creates_task_id(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.images.put_file", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr("app.api.routes.images.enqueue_process_image", lambda **_kwargs: uuid.uuid4(), raising=False)

    init = client.post("/api/v1/images/upload/init", json={"filename": "a.tif", "total_size": 5})
    upload_id = init.json()["data"]["upload_id"]
    client.put(f"/api/v1/images/upload/{upload_id}/part/1", data=b"12345")
    done = client.post(
        f"/api/v1/images/upload/{upload_id}/complete",
        json={"total_parts": 1, "name": "a.tif", "mime_type": "image/tiff"},
    )
    image_id = done.json()["data"]["image_id"]

    r = client.post(f"/api/v1/images/{image_id}/process")
    assert r.status_code == 200
    assert r.json()["data"]["task_id"]


def test_preview_uses_thumbnail_format_when_local_storage_returns_octet_stream(client, db_session, monkeypatch):
    from app.config import get_settings
    from app.models import Image, Project, Thumbnail

    settings = get_settings()
    project = db_session.query(Project).filter(Project.name == settings.default_project_name).first()
    image_id = uuid.uuid4()

    db_session.add(
        Image(
            id=image_id,
            project_id=project.id,
            name="demo.tif",
            original_filename="demo.tif",
            mime_type="image/tiff",
            size_bytes=16,
            storage_key=f"raw/{image_id}/demo.tif",
            status="ready",
        )
    )
    db_session.add(
        Thumbnail(
            project_id=project.id,
            image_id=image_id,
            purpose="preview",
            level=1024,
            format="webp",
            storage_key=f"thumbnails/{image_id}/preview_1024.webp",
            size_bytes=12,
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.api.routes.images.read_object_bytes",
        lambda **_kwargs: (b"RIFFdemoWEBPVP8 ", "application/octet-stream"),
        raising=False,
    )

    r = client.get(f"/api/v1/images/{image_id}/preview")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/webp")
