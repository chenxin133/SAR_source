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
