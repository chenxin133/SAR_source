import hashlib
import io
import struct
import uuid
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image as PILImage
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.models import Image, Project, Sample
from app.schema_updates import add_sample_import_metadata
from app.upload_filenames import storage_filename


@pytest.fixture
def local(client, tmp_path):
    settings = get_settings()
    settings.storage_backend = 'local'
    settings.local_storage_dir = str(tmp_path / 'storage')
    settings.rate_limit_requests = 0
    return client


def raw_upload(client, content, filename='原始影像.tif', headers=None):
    upload = client.post('/api/v1/images/upload/init', json={'filename': filename, 'total_size': len(content)}, headers=headers).json()['data']['upload_id']
    assert client.put(f'/api/v1/images/upload/{upload}/part/1', content=content, headers=headers).status_code == 200
    return upload


def test_raw_choices_cached_hash_cancel_names_and_project_isolation(local, db_session, monkeypatch):
    data = b'original-' + uuid.uuid4().bytes
    first = raw_upload(local, data)
    row = local.post(f'/api/v1/images/upload/{first}/complete', json={'resolution': '1m', 'total_parts': 1, 'name': 'first'}).json()['data']
    image = db_session.get(Image, uuid.UUID(row['image_id']))
    assert image.storage_key.endswith('/原始影像.tif')
    second = raw_upload(local, data, 'different-name.tiff')
    route = f'/api/v1/images/upload/{second}/complete'
    response = local.post(route, json={'resolution': '1m', 'total_parts': 1, 'name': 'second'})
    assert response.status_code == 409 and response.json()['detail']['existing']['id'] == row['image_id']
    with monkeypatch.context() as patch:
        patch.setattr('app.upload_service.hashlib.sha256', lambda: pytest.fail('must reuse completed hash'))
        reused = local.post(route, json={'resolution': '1m', 'total_parts': 1, 'duplicate_action': 'reuse'}).json()['data']
    assert reused == {'image_id': row['image_id'], 'reused': True, 'updated': False}
    assert not (Path(get_settings().upload_tmp_dir) / second).exists()
    third = raw_upload(local, data)
    copied = local.post(f'/api/v1/images/upload/{third}/complete', json={'resolution': '1m', 'total_parts': 1, 'duplicate_action': 'import'}).json()['data']
    assert copied['image_id'] != row['image_id']
    canceled = raw_upload(local, data)
    assert local.delete(f'/api/v1/images/upload/{canceled}').status_code == 200
    assert not (Path(get_settings().upload_tmp_dir) / canceled).exists()
    other = Project(id=uuid.uuid4(), name=str(uuid.uuid4()))
    db_session.add(other); db_session.commit()
    headers = {'X-Project-Id': str(other.id)}
    separate = raw_upload(local, data, headers=headers)
    assert local.post(f'/api/v1/images/upload/{separate}/complete', json={'resolution': '1m', 'total_parts': 1}, headers=headers).status_code == 200
    assert image.name == 'first'


def sample_upload(client, array=None, resolution='25cm', **fields):
    original = io.BytesIO()
    tifffile.imwrite(original, np.arange(64, dtype=np.uint16).reshape(8, 8) if array is None else array)
    data = {'name': 'sample', 'annotation_id': f'manual:{uuid.uuid4()}', 'image_format': 'image/tiff',
            'width': 8, 'height': 8, 'resolution': resolution, **fields}
    response = client.post('/api/v1/samples/upload', data=data, files={'image': ('sample.tif', original.getvalue(), 'image/tiff')})
    return response, original.getvalue()


def test_standalone_sample_duplicates_include_legacy_and_preserve_metadata(local, db_session):
    array = np.full((8, 8), np.random.default_rng(9).integers(100, 500), dtype=np.uint16)
    response, original = sample_upload(local, array, name='existing', remark='keep me')
    assert response.status_code == 200
    first = response.json()['data']
    record = db_session.get(Sample, uuid.UUID(first['id']))
    record.checksum_sha256 = None
    db_session.commit()
    response, _ = sample_upload(local, array, name='new')
    assert response.status_code == 409
    assert response.json()['detail']['existing']['id'] == first['id']
    response, _ = sample_upload(local, array, name='new', duplicate_action='reuse')
    assert response.json()['data']['remark'] == 'keep me'
    assert response.json()['data']['resolution'] == '25cm'
    response, _ = sample_upload(local, array, duplicate_action='import')
    assert response.status_code == 200 and response.json()['data']['id'] != first['id']
    db_session.refresh(record)
    assert record.checksum_sha256 == hashlib.sha256(original).hexdigest()


def test_echo_duplicates_options_and_project_isolation(local, db_session):
    content = struct.pack('<iiI4H', 1, 2, 7, 32768, 32769, 32770, 32771)
    def upload(**data):
        return local.post('/api/v1/echoes/upload', data=data, files={'file': ('name.dat', content)})
    first = upload(name='first', remark='retained')
    assert first.status_code == 201
    row = first.json()['data']
    assert upload().status_code == 409
    reused = upload(duplicate_action='reuse', name='ignored')
    assert reused.json()['data']['id'] == row['id'] and reused.json()['data']['name'] == 'first'
    assert upload(duplicate_action='import').json()['data']['id'] != row['id']
    other = Project(id=uuid.uuid4(), name=str(uuid.uuid4()))
    db_session.add(other); db_session.commit()
    response = local.post('/api/v1/echoes/upload', headers={'X-Project-Id': str(other.id)}, files={'file': ('name.dat', content)})
    assert response.status_code == 201


@pytest.mark.parametrize('target,size', [(0.5, 4), (1, 2), (2, 1), (3, 1), (5, 1)])
def test_tiff_downsample_dimensions_dtype_and_area_average(local, target, size):
    array = np.arange(64, dtype=np.uint16).reshape(8, 8)
    response, original = sample_upload(local, array, duplicate_action='import')
    sample_id = response.json()['data']['id']
    assert local.get(f'/api/v1/samples/{sample_id}/export').content == original
    result = local.get(f'/api/v1/samples/{sample_id}/export?target_resolution={target}')
    assert result.status_code == 200, result.text
    actual = tifffile.imread(io.BytesIO(result.content))
    assert actual.dtype == np.uint16 and actual.shape == (size, size)
    if target == .5:
        expected = np.rint(array.reshape(4, 2, 4, 2).mean(axis=(1, 3))).astype(np.uint16)
        np.testing.assert_array_equal(actual, expected)
    rendered = local.get(f'/api/v1/samples/{sample_id}/export?format=image/png&target_resolution={target}')
    assert rendered.status_code == 200
    assert PILImage.open(io.BytesIO(rendered.content)).size == (size, size)
    visual_tiff = local.get(f'/api/v1/samples/{sample_id}/export?format=image/tiff&target_resolution={target}')
    assert visual_tiff.status_code == 200
    assert tifffile.imread(io.BytesIO(visual_tiff.content)).shape == (size, size, 3)
    # Export never changes the persisted original.
    assert local.get(f'/api/v1/samples/{sample_id}/export').content == original


@pytest.mark.parametrize('resolution,target', [('1m', 1), ('2m', 1), ('', 2), ('1x2m', 5), ('1', 5), ('1m', 4), ('3m', 3)])
def test_export_rejects_unknown_equal_finer_and_unsupported_targets(local, resolution, target):
    response, _ = sample_upload(local, resolution=resolution, duplicate_action='import')
    sample_id = response.json()['data']['id']
    assert local.get(f'/api/v1/samples/{sample_id}/export?target_resolution={target}').status_code == 422


def test_linked_sample_follows_source_unless_explicit_override(local, db_session):
    project = db_session.query(Project).filter_by(name=get_settings().default_project_name).one()
    image = Image(id=uuid.uuid4(), project_id=project.id, name='source', storage_key='missing', resolution='1m')
    db_session.add(image); db_session.commit()
    response, _ = sample_upload(local, resolution='', image_id=str(image.id))
    sample_id = response.json()['data']['id']
    assert response.json()['data']['resolution'] is None
    assert local.get(f'/api/v1/samples/{sample_id}/export?target_resolution=1').status_code == 422
    image.resolution = '0.5m'; db_session.commit()
    assert local.get(f'/api/v1/samples/{sample_id}/export?target_resolution=1').status_code == 200


def test_legacy_metadata_migration_backs_up_and_is_idempotent(tmp_path):
    path = tmp_path / 'legacy.db'
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE samples(id TEXT PRIMARY KEY, project_id TEXT, name TEXT)')
        connection.exec_driver_sql("INSERT INTO samples VALUES ('saved','project','retained')")
    add_sample_import_metadata(engine)
    backup = Path(str(path) + '.before-sample-import-metadata.bak')
    assert backup.exists()
    before = backup.read_bytes()
    add_sample_import_metadata(engine)
    assert backup.read_bytes() == before
    with engine.connect() as connection:
        assert {'resolution', 'checksum_sha256'} <= {c['name'] for c in inspect(connection).get_columns('samples')}
        assert connection.exec_driver_sql('SELECT name FROM samples').scalar() == 'retained'


def test_portable_original_filenames():
    assert storage_filename('路径/原始影像.TIFF') == '原始影像.TIFF'
    assert storage_filename('CON.tif') == '_CON.tif'
    assert '/' not in storage_filename('../a:b.tif')
    assert len(storage_filename('影像' * 200 + '.tif').encode('utf-8')) <= 104
