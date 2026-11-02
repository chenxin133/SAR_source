"""Saved samples remain exportable after their annotation/source is unavailable."""
import io
import uuid
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import tifffile

from app.config import get_settings
from app.models import Image, Project, Sample
from app.storage import local_object_path


def legacy_sample(client, db_session, tmp_path, *, geometry=False):
    settings = get_settings()
    settings.storage_backend = 'local'
    settings.local_storage_dir = str(tmp_path / 'storage')
    project = db_session.query(Project).filter_by(name=settings.default_project_name).one()
    source = Image(id=uuid.uuid4(), project_id=project.id, name='missing-source.tif',
                   storage_key=f'raw/{uuid.uuid4()}/missing.tif', resolution='1m')
    db_session.add(source)
    db_session.commit()
    original = io.BytesIO()
    tifffile.imwrite(original, np.arange(324, dtype=np.uint16).reshape(18, 18))
    uploaded = client.post('/api/v1/samples/upload', data={
        'image_id': str(source.id), 'annotation_id': f'manual:{uuid.uuid4()}',
        'name': '旧样本', 'category': '舰船', 'frequency_band': 'C', 'resolution': '1m',
        'width': 18, 'height': 18, 'image_format': 'image/tiff', 'duplicate_action': 'import',
    }, files={'image': ('old.tif', original.getvalue(), 'image/tiff')})
    assert uploaded.status_code == 200, uploaded.text
    sample = db_session.get(Sample, uuid.UUID(uploaded.json()['data']['id']))
    roi = {**sample.roi, 'annotationId': 'deleted-annotation'}
    if geometry:
        roi.update(coordinateWidth=100, coordinateHeight=100,
                   polygon=[{'x': 1, 'y': 1}, {'x': 19, 'y': 1}, {'x': 19, 'y': 19}, {'x': 1, 'y': 19}])
    sample.roi = roi
    db_session.commit()
    return sample, original.getvalue()


@pytest.mark.parametrize('geometry', [False, True])
def test_legacy_source_export_uses_saved_native_file_without_source_or_annotation(client, db_session, tmp_path, geometry):
    sample, original = legacy_sample(client, db_session, tmp_path, geometry=geometry)
    roi_before = dict(sample.roi)
    response = client.get(f'/api/v1/samples/{sample.id}/export')
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('image/tiff')
    assert response.content == original
    response = client.post('/api/v1/samples/export', json={'sample_ids': [str(sample.id)], 'target_resolution': 3})
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 2
        tif_name = next(name for name in archive.namelist() if name.endswith('.tif'))
        assert '_3m_' in tif_name
        pixels = tifffile.imread(io.BytesIO(archive.read(tif_name)))
        assert pixels.dtype == np.uint16 and pixels.shape == (6, 6)
        expected = np.rint(np.arange(324).reshape(6, 3, 6, 3).mean(axis=(1, 3))).astype(np.uint16)
        np.testing.assert_array_equal(pixels, expected)
        xml = ET.fromstring(archive.read(tif_name[:-4] + '.xml'))
        assert xml.findtext('resolution') == '3'
        assert xml.findtext('imageSize/width') == '6'
        assert xml.findtext('imageSize/height') == '6'
    db_session.refresh(sample)
    assert sample.roi == roi_before
    stored = local_object_path(bucket=get_settings().s3_bucket, key=sample.crop_storage_key)
    assert stored.read_bytes() == original


def test_missing_saved_file_returns_the_failing_sample_in_a_readable_batch_error(client, db_session, tmp_path):
    sample, _ = legacy_sample(client, db_session, tmp_path)
    stored = local_object_path(bucket=get_settings().s3_bucket, key=sample.crop_storage_key)
    stored.unlink()
    response = client.post('/api/v1/samples/export', json={'sample_ids': [str(sample.id)]})
    assert response.status_code == 404
    detail = response.json()['detail']
    assert str(sample.id) in detail and sample.name in detail and '样本文件缺失' in detail


def test_invalid_source_crop_is_not_silently_replaced_by_the_saved_sample(client, db_session, tmp_path, monkeypatch):
    sample, _ = legacy_sample(client, db_session, tmp_path, geometry=True)
    from fastapi import HTTPException
    def invalid_crop(*args):
        raise HTTPException(400, 'Crop region is empty')
    monkeypatch.setattr('app.api.routes.samples._render_source_crop', invalid_crop)
    response = client.get(f'/api/v1/samples/{sample.id}/export')
    assert response.status_code == 400
    assert response.json()['detail'] == 'Crop region is empty'
