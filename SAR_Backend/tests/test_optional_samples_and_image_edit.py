from __future__ import annotations

from contextlib import closing
import io
import sqlite3
import uuid

import numpy as np
import pytest
import tifffile
from sqlalchemy import MetaData, create_engine, event, inspect, text

from app.config import get_settings
from app.db import Base
from app.models import Image, Project, Sample
from app.schema_updates import allow_samples_without_source


def test_independent_tiff_upload_export_delete(client, db_session, tmp_path):
    settings = get_settings()
    settings.storage_backend = "local"
    settings.local_storage_dir = str(tmp_path / "storage")
    original = io.BytesIO()
    tifffile.imwrite(original, np.arange(80, dtype=np.uint16).reshape(8, 10))
    response = client.post("/api/v1/samples/upload", data={
        "name": "独立样本", "annotation_id": f"manual:{uuid.uuid4()}",
        "image_format": "image/tiff", "width": "10", "height": "8",
    }, files={"image": ("sample.tif", original.getvalue(), "image/tiff")})
    assert response.status_code == 200, response.text
    sample = response.json()["data"]
    assert sample["image_id"] is None
    assert sample["crop_storage_key"].startswith("samples/local/")
    assert db_session.get(Sample, uuid.UUID(sample["id"])).image_id is None
    assert any(row["id"] == sample["id"] for row in client.get("/api/v1/samples").json()["data"])
    exported = client.get(f'/api/v1/samples/{sample["id"]}/export?format=source')
    assert exported.status_code == 200 and exported.content == original.getvalue()
    assert client.delete(f'/api/v1/samples/{sample["id"]}').status_code == 200
    assert db_session.get(Sample, uuid.UUID(sample["id"])) is None


def test_supplied_missing_source_still_rejected(client):
    response = client.post("/api/v1/samples/upload", data={
        "image_id": str(uuid.uuid4()), "name": "bad", "annotation_id": "manual:bad", "width": 1, "height": 1,
    }, files={"image": ("sample.png", b"test", "image/png")})
    assert response.status_code == 404


def test_patch_image_metadata_keeps_identity_and_objects(client, db_session):
    project = db_session.query(Project).filter_by(name=get_settings().default_project_name).one()
    image = Image(id=uuid.uuid4(), project_id=project.id, name="before.tif", original_filename="original.tif",
                  storage_key="raw/fixed/source.tif", checksum_sha256="a" * 64, status="ready", size_bytes=1024)
    db_session.add(image)
    db_session.commit()
    response = client.patch(f"/api/v1/images/{image.id}", json={
        "name": "新名称", "satellite": "珞珈二号", "acquisition_at": "2026-10-28T10:00:00Z",
        "description": "地区：北京\n备注：测试", "frequency_band": "Ku", "resolution": "1 m",
        "polarization": "HH", "size_bytes": 2048, "status": "failed", "error_message": "说明",
    })
    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "新名称"
    db_session.refresh(image)
    assert (image.storage_key, image.original_filename, image.checksum_sha256) == ("raw/fixed/source.tif", "original.tif", "a" * 64)
    assert image.size_bytes == 2048
    for forbidden in ["id", "thumbnails", "storage_key", "project_id", "thumbnail_url"]:
        assert client.patch(f"/api/v1/images/{image.id}", json={forbidden: "changed"}).status_code == 422
    for invalid in [{"name": " "}, {"name": None}, {"size_bytes": -1}, {"status": "unknown"}]:
        assert client.patch(f"/api/v1/images/{image.id}", json=invalid).status_code == 422
    assert client.patch(f"/api/v1/images/{uuid.uuid4()}", json={"name": "none"}).status_code == 404
    assert client.patch(f"/api/v1/images/{image.id}", json={"acquisition_at": None, "description": ""}).status_code == 200
    assert client.get(f"/api/v1/images/{image.id}").json()["data"]["acquisition_at"] is None


@pytest.mark.parametrize("fail_copy", [False, True])
def test_legacy_migration_preserves_rows_constraints_and_foreign_keys(tmp_path, fail_copy):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(legacy)
    legacy.tables["samples"].c.image_id.nullable = False
    legacy.create_all(engine)
    project, image, sample, annotation = (str(uuid.uuid4()) for _ in range(4))
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(text("INSERT INTO projects(id,name) VALUES (:id,'legacy')"), {"id": project})
        connection.execute(text("INSERT INTO images(id,project_id,name,storage_key) VALUES (:id,:project,'source','raw/fixed')"), {"id": image, "project": project})
        connection.execute(text("INSERT INTO samples(id,project_id,image_id,name) VALUES (:id,:project,:image,'saved')"), {"id": sample, "project": project, "image": image})
        connection.execute(text("INSERT INTO annotations(id,project_id,sample_id,type,payload) VALUES (:id,:project,:sample,'rect','{}')"), {"id": annotation, "project": project, "sample": sample})
        connection.exec_driver_sql("CREATE TABLE sample_audit(name TEXT)")
        connection.exec_driver_sql("CREATE TRIGGER sample_saved AFTER INSERT ON samples BEGIN INSERT INTO sample_audit VALUES (new.name); END")

    def interrupt_copy(connection, cursor, statement, parameters, context, executemany):
        if fail_copy and statement.startswith("INSERT INTO _alembic_tmp_samples"):
            raise RuntimeError("simulated migration failure")
    event.listen(engine, "before_cursor_execute", interrupt_copy)
    if fail_copy:
        with pytest.raises(RuntimeError, match="simulated"):
            allow_samples_without_source(engine)
    else:
        allow_samples_without_source(engine)
        allow_samples_without_source(engine)
    event.remove(engine, "before_cursor_execute", interrupt_copy)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.execute(text("SELECT name FROM samples WHERE id=:id"), {"id": sample}).scalar() == "saved"
        assert connection.execute(text("SELECT sample_id FROM annotations WHERE id=:id"), {"id": annotation}).scalar() == sample
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        nullable = next(c for c in inspect(connection).get_columns("samples") if c["name"] == "image_id")["nullable"]
        assert nullable is (not fail_copy)
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM sqlite_master WHERE name='sample_saved'").scalar() == 1
        assert any(index["name"] == "ix_samples_image" for index in inspect(connection).get_indexes("samples"))
        if not fail_copy:
            connection.execute(text("INSERT INTO samples(id,project_id,name) VALUES (:id,:project,'independent')"), {"id": str(uuid.uuid4()), "project": project})
            assert connection.exec_driver_sql("SELECT name FROM sample_audit").scalar() == "independent"
            connection.commit()
    engine.dispose()
    with closing(sqlite3.connect(str(path) + ".before-optional-sample-source.bak")) as backup:
        assert backup.execute("SELECT name FROM samples").fetchall() == [("saved",)]
