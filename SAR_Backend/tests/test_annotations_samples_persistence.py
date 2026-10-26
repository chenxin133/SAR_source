from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import numpy as np
from PIL import Image as PILImage, TiffImagePlugin

from app.config import get_settings
from app.models import Annotation, Image, Project, Sample, Thumbnail


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


def test_crop_sample_from_source_preserves_tiff_format(client, db_session, monkeypatch, tmp_path):
    image_id = _create_image(db_session)
    source_path = tmp_path / "source.tif"
    source_data = np.arange(100 * 80, dtype=np.uint16).reshape(80, 100) + 1000
    PILImage.fromarray(source_data, mode="I;16").save(source_path, format="TIFF")
    monkeypatch.setattr(PILImage, "MAX_IMAGE_PIXELS", 1_000)
    stored: dict[str, bytes] = {}

    monkeypatch.setattr(
        "app.api.routes.samples.download_object_to_file",
        lambda **kwargs: shutil.copy2(source_path, kwargs["file_path"]),
    )
    monkeypatch.setattr(
        "app.api.routes.samples.put_file",
        lambda **kwargs: stored.__setitem__(kwargs["key"], Path(kwargs["file_path"]).read_bytes()),
    )
    monkeypatch.setattr("app.api.routes.samples.presign_get_url", lambda **kwargs: f"/objects/{kwargs['key']}")

    response = client.post(
        "/api/v1/samples/crop",
        json={
            "image_id": str(image_id),
            "name": "source-crop",
            "category": "target",
            "remark": "full resolution",
            "annotation_id": "ANN_TIFF",
            "annotation_type": "rect",
            "output_format": "source",
            "coordinate_width": 10,
            "coordinate_height": 8,
            "polygon": [
                {"x": 2, "y": 1},
                {"x": 5, "y": 1},
                {"x": 5, "y": 4},
                {"x": 2, "y": 4},
            ],
        },
    )

    assert response.status_code == 200
    sample = response.json()["data"]
    assert sample["roi"]["format"] == "image/tiff"
    assert sample["roi"]["width"] == 30
    assert sample["roi"]["height"] == 30
    crop_key = sample["crop_storage_key"]
    assert crop_key.endswith(".tif")
    thumbnail_key = sample["thumb_storage_key"]

    crop_path = tmp_path / "crop.tif"
    crop_path.write_bytes(stored[crop_key])
    with TiffImagePlugin.TiffImageFile(crop_path) as crop:
        assert crop.format == "TIFF"
        assert crop.size == (30, 30)
        crop_data = np.asarray(crop)
        assert np.all(crop_data[:, 0] > 0)
        assert np.all(crop_data[:, -1] > 0)

    thumbnail_path = tmp_path / "thumbnail.png"
    thumbnail_path.write_bytes(stored[thumbnail_key])
    with PILImage.open(thumbnail_path) as thumbnail:
        assert thumbnail.mode == "RGB"
        assert thumbnail.getextrema() != ((0, 0), (0, 0), (0, 0))


def test_float_tiff_sample_exports_visible_png_jpeg_and_tiff(client, db_session, monkeypatch, tmp_path):
    image_id = _create_image(db_session)
    project = db_session.query(Project).filter(Project.name == get_settings().default_project_name).first()
    sample_id = uuid.uuid4()
    float_data = np.geomspace(20_000, 2_000_000_000, num=40 * 30, dtype=np.float32).reshape(30, 40)
    source_path = tmp_path / "float-sample.tif"
    PILImage.fromarray(float_data, mode="F").save(source_path, format="TIFF")
    db_session.add(
        Sample(
            id=sample_id,
            project_id=project.id,
            image_id=image_id,
            name="float-sample",
            roi={"format": "image/tiff"},
            crop_storage_key=f"samples/{image_id}/{sample_id}/image.tif",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.api.routes.samples.download_object_to_file",
        lambda **kwargs: shutil.copy2(source_path, kwargs["file_path"]),
    )

    for requested, expected_type, expected_format in (
        ("image/png", "image/png", "PNG"),
        ("image/jpeg", "image/jpeg", "JPEG"),
        ("image/tiff", "image/tiff", "TIFF"),
    ):
        response = client.get(f"/api/v1/samples/{sample_id}/export", params={"format": requested})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(expected_type)
        exported_path = tmp_path / f"export-{expected_format.lower()}"
        exported_path.write_bytes(response.content)
        with PILImage.open(exported_path) as exported:
            assert exported.format == expected_format
            extrema = exported.convert("L").getextrema()
            assert extrema[0] < extrema[1]
            assert extrema != (255, 255)


def test_old_png_sample_exports_from_source_tiff(client, db_session, monkeypatch, tmp_path):
    image_id = _create_image(db_session)
    project = db_session.query(Project).filter(Project.name == get_settings().default_project_name).first()
    source_path = tmp_path / "legacy-source.tif"
    PILImage.new("I;16", (100, 80), 4096).save(source_path, format="TIFF")
    sample_id = uuid.uuid4()
    db_session.add(
        Annotation(
            project_id=project.id,
            image_id=image_id,
            type="annotations_v1",
            payload={
                "version": 1,
                "imageId": str(image_id),
                "exportedAt": 1,
                "annotations": [
                    {
                        "id": "ANN_OLD",
                        "type": "rect",
                        "rect": {"x": 2, "y": 1, "w": 3, "h": 3},
                    }
                ],
            },
        )
    )
    db_session.add(
        Thumbnail(
            project_id=project.id,
            image_id=image_id,
            purpose="preview",
            level=2048,
            format="webp",
            storage_key=f"thumbnails/{image_id}/preview_2048.webp",
            width=10,
            height=8,
        )
    )
    db_session.add(
        Sample(
            id=sample_id,
            project_id=project.id,
            image_id=image_id,
            name="legacy-png",
            roi={
                "annotationId": "ANN_OLD",
                "annotationType": "rect",
                "format": "image/png",
                "width": 3,
                "height": 3,
            },
            crop_storage_key=f"samples/{image_id}/{sample_id}/image.png",
            thumb_storage_key=f"samples/{image_id}/{sample_id}/thumbnail.png",
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.api.routes.samples.download_object_to_file",
        lambda **kwargs: shutil.copy2(source_path, kwargs["file_path"]),
    )

    response = client.get(f"/api/v1/samples/{sample_id}/export?format=source")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/tiff")
    exported_path = tmp_path / "legacy-export.tif"
    exported_path.write_bytes(response.content)
    with PILImage.open(exported_path) as exported:
        assert exported.format == "TIFF"
        assert exported.size == (30, 30)


def test_old_sample_relinks_to_reuploaded_image_by_name(client, db_session, monkeypatch, tmp_path):
    old_image_id = _create_image(db_session)
    project = db_session.query(Project).filter(Project.name == get_settings().default_project_name).first()
    old_image = db_session.query(Image).filter(Image.id == old_image_id).one()
    old_image.name = "reuploaded.tif"
    old_image.original_filename = "reuploaded.tif"
    sample_id = uuid.uuid4()
    db_session.add(
        Annotation(
            project_id=project.id,
            image_id=old_image_id,
            type="annotations_v1",
            payload={
                "version": 1,
                "imageId": str(old_image_id),
                "exportedAt": 1,
                "annotations": [{"id": "ANN_RELINK", "type": "rect", "rect": {"x": 2, "y": 1, "w": 3, "h": 3}}],
            },
        )
    )
    db_session.add(
        Thumbnail(
            project_id=project.id,
            image_id=old_image_id,
            purpose="preview",
            level=2048,
            format="webp",
            storage_key=f"thumbnails/{old_image_id}/preview_2048.webp",
            width=10,
            height=8,
        )
    )
    db_session.add(
        Sample(
            id=sample_id,
            project_id=project.id,
            image_id=old_image_id,
            name="legacy-relinked",
            roi={"annotationId": "ANN_RELINK", "annotationType": "rect", "imageName": "reuploaded.tif", "format": "image/png"},
            crop_storage_key=f"samples/{old_image_id}/{sample_id}/image.png",
        )
    )
    db_session.flush()
    db_session.delete(old_image)
    new_image_id = uuid.uuid4()
    db_session.add(
        Image(
            id=new_image_id,
            project_id=project.id,
            name="reuploaded.tif",
            original_filename="reuploaded.tif",
            mime_type="image/tiff",
            size_bytes=4,
            storage_key=f"raw/{new_image_id}/reuploaded.tif",
            status="ready",
        )
    )
    db_session.commit()

    source_path = tmp_path / "reuploaded.tif"
    PILImage.new("I;16", (100, 80), 8192).save(source_path, format="TIFF")
    monkeypatch.setattr(
        "app.api.routes.samples.download_object_to_file",
        lambda **kwargs: shutil.copy2(source_path, kwargs["file_path"]),
    )

    response = client.get(f"/api/v1/samples/{sample_id}/export?format=source")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/tiff")


def test_crop_png_source_to_tiff_uses_png_reader(client, db_session, monkeypatch, tmp_path):
    image_id = _create_image(db_session)
    image = db_session.query(Image).filter(Image.id == image_id).one()
    image.name = image.original_filename = "source.png"
    image.mime_type = "image/png"
    db_session.commit()
    source_path = tmp_path / "source.png"
    PILImage.new("RGB", (100, 80), (40, 80, 120)).save(source_path)
    stored = {}
    monkeypatch.setattr("app.api.routes.samples.download_object_to_file", lambda **kw: shutil.copy2(source_path, kw["file_path"]))
    monkeypatch.setattr("app.api.routes.samples.put_file", lambda **kw: stored.__setitem__(kw["key"], Path(kw["file_path"]).read_bytes()))
    monkeypatch.setattr("app.api.routes.samples.presign_get_url", lambda **kw: f"/objects/{kw['key']}")
    response = client.post("/api/v1/samples/crop", json={
        "image_id": str(image_id), "name": "png-to-tiff", "annotation_id": "ANN_PNG_TIFF",
        "output_format": "image/tiff", "coordinate_width": 100, "coordinate_height": 80,
        "polygon": [{"x": 10, "y": 15}, {"x": 70, "y": 15}, {"x": 70, "y": 65}, {"x": 10, "y": 65}],
    })
    assert response.status_code == 200
    sample = response.json()["data"]
    output = tmp_path / "crop.tif"
    output.write_bytes(stored[sample["crop_storage_key"]])
    with PILImage.open(output) as crop:
        assert crop.format == "TIFF"
        assert crop.size == (60, 50)
        assert crop.getpixel((20, 20)) == (40, 80, 120)
