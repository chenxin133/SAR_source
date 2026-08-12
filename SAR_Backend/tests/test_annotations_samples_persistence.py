from __future__ import annotations

import uuid

from app.config import get_settings
from app.models import Image, Project


def _create_image(db_session) -> uuid.UUID:
    project = db_session.query(Project).filter(Project.name == get_settings().default_project_name).first()
    image_id = uuid.uuid4()
    db_session.add(
        Image(
            id=image_id,
            project_id=project.id,
            name="shared.tif",
            original_filename="shared.tif",
            mime_type="image/tiff",
            size_bytes=4,
            storage_key=f"raw/{image_id}/shared.tif",
            status="ready",
        )
    )
    db_session.commit()
    return image_id


def test_upsert_shared_annotations(client, db_session):
    image_id = _create_image(db_session)
    payload = {
        "version": 1,
        "imageId": str(image_id),
        "exportedAt": 1,
        "annotations": [{"id": "ANN_1", "type": "rect"}],
    }

    saved = client.put(f"/api/v1/annotations/image/{image_id}", json=payload)
    assert saved.status_code == 200

    rows = client.get(f"/api/v1/annotations?image_id={image_id}")
    assert rows.status_code == 200
    assert rows.json()["data"][0]["payload"]["annotations"][0]["id"] == "ANN_1"


def test_upload_and_delete_shared_sample(client, db_session, monkeypatch):
    image_id = _create_image(db_session)
    stored: list[str] = []
    deleted: list[str] = []
    monkeypatch.setattr("app.api.routes.samples.put_file", lambda **kwargs: stored.append(kwargs["key"]))
    monkeypatch.setattr("app.api.routes.samples.delete_object", lambda **kwargs: deleted.append(kwargs["key"]))
    monkeypatch.setattr("app.api.routes.samples.presign_get_url", lambda **kwargs: f"/objects/{kwargs['key']}")

    response = client.post(
        "/api/v1/samples/upload",
        data={
            "image_id": str(image_id),
            "name": "ship",
            "category": "target",
            "remark": "shared",
            "annotation_id": "ANN_1",
            "annotation_type": "polygon",
            "image_name": "shared.tif",
            "image_format": "image/png",
            "width": "10",
            "height": "8",
        },
        files={
            "image": ("image.png", b"PNG", "image/png"),
            "thumbnail": ("thumbnail.png", b"THUMB", "image/png"),
        },
    )
    assert response.status_code == 200
    sample = response.json()["data"]
    assert sample["roi"]["annotationId"] == "ANN_1"
    assert sample["roi"]["annotationType"] == "polygon"
    assert len(stored) == 2

    removed = client.delete(f"/api/v1/samples/{sample['id']}")
    assert removed.status_code == 200
    assert sorted(deleted) == sorted(stored)
