import base64
import hashlib
import struct
import uuid
from pathlib import Path

import numpy as np
import pytest
import tifffile

from app.config import get_settings
from app.models import Image, Project, Sample
from app.raster_product import UnsupportedSingleLookError, validate_raster_product
from app.workers import tasks
from test_duplicate_resolution_export import local, raw_upload, sample_upload
from test_scene_xml_and_naming import XML


def test_raw_preflight_prompts_and_resolves_before_any_transfer(local, db_session, monkeypatch):
    content = b'preflight-' + uuid.uuid4().bytes
    first = raw_upload(local, content)
    original = local.post(f'/api/v1/images/upload/{first}/complete', json={'total_parts': 1, 'name': 'existing', 'resolution': '1m'}).json()['data']['image_id']
    image = db_session.get(Image, uuid.UUID(original))
    key = image.storage_key
    payload = {'filename': 'renamed.tif', 'total_size': len(content), 'checksum_sha256': hashlib.sha256(content).hexdigest(), 'name': 'updated', 'resolution': '2m'}
    folders = set(Path(get_settings().upload_tmp_dir).iterdir())
    prompt = local.post('/api/v1/images/upload/init', json=payload)
    assert prompt.status_code == 409 and prompt.json()['detail']['existing']['id'] == original
    with monkeypatch.context() as patch:
        patch.setattr('app.api.routes.images.init_upload', lambda **_kwargs: pytest.fail('duplicate reuse/update must not create an upload'))
        reused = local.post('/api/v1/images/upload/init', json={**payload, 'duplicate_action': 'reuse'}).json()['data']
        assert reused['image_id'] == original and reused['upload_id'] is None
        db_session.refresh(image)
        assert image.name == 'existing'
        updated = local.post('/api/v1/images/upload/init', json={**payload, 'duplicate_action': 'update', 'metadata_xml_base64': base64.b64encode(XML).decode()}).json()['data']
        assert updated['image_id'] == original and updated['updated'] and updated['upload_id'] is None
    db_session.refresh(image)
    assert image.name == 'updated' and image.resolution == '2m' and image.storage_key == key
    assert image.metadata_xml_key and image.original_filename != 'renamed.tif'
    assert (Path(get_settings().local_storage_dir) / get_settings().s3_bucket / key).read_bytes() == content
    assert set(Path(get_settings().upload_tmp_dir).iterdir()) == folders
    copied = local.post('/api/v1/images/upload/init', json={**payload, 'duplicate_action': 'import'}).json()['data']
    assert copied['upload_id'] and not copied['image_id']
    local.put(f'/api/v1/images/upload/{copied["upload_id"]}/part/1', content=content)
    result = local.post(f'/api/v1/images/upload/{copied["upload_id"]}/complete', json={'total_parts': 1, 'resolution': '1m', 'duplicate_action': 'import'})
    assert result.status_code == 200 and result.json()['data']['image_id'] != original
    # Same filename and size never substitute for an exact content match.
    assert local.post('/api/v1/images/upload/init', json={**payload, 'checksum_sha256': '0' * 64}).json()['data']['upload_id']
    other = Project(id=uuid.uuid4(), name=str(uuid.uuid4())); db_session.add(other); db_session.commit()
    assert local.post('/api/v1/images/upload/init', json=payload, headers={'X-Project-Id': str(other.id)}).json()['data']['upload_id']
    assert local.post('/api/v1/images/upload/init', json={**payload, 'checksum_sha256': 'not-a-hash'}).status_code == 422


def test_sample_and_echo_preflight_finds_legacy_without_uploading_content(local, db_session):
    response, content = sample_upload(local, np.arange(64, dtype=np.uint16).reshape(8, 8) + 9421, name='preflight sample')
    assert response.status_code == 200
    sample = response.json()['data']; row = db_session.get(Sample, uuid.UUID(sample['id']))
    row.checksum_sha256 = None; db_session.commit()
    payload = {'resource': 'samples', 'checksum_sha256': hashlib.sha256(content).hexdigest()}
    assert local.post('/api/v1/imports/check', json=payload).json()['data']['existing']['id'] == sample['id']
    assert local.get(f'/api/v1/samples/{sample["id"]}').json()['data']['name'] == sample['name']
    db_session.refresh(row); assert row.checksum_sha256 == payload['checksum_sha256']
    echo_bytes = struct.pack('<iiI4H', 1, 2, 33226123, 32768, 32769, 32770, 32771)
    echo = local.post('/api/v1/echoes/upload', files={'file': ('signal.dat', echo_bytes)}).json()['data']
    echo_payload = {'resource': 'echoes', 'checksum_sha256': hashlib.sha256(echo_bytes).hexdigest()}
    assert local.post('/api/v1/imports/check', json=echo_payload).json()['data']['existing']['id'] == echo['id']
    other = Project(id=uuid.uuid4(), name=str(uuid.uuid4())); db_session.add(other); db_session.commit()
    headers = {'X-Project-Id': str(other.id)}
    for body in (payload, echo_payload):
        assert local.post('/api/v1/imports/check', json=body, headers=headers).json()['data']['existing'] is None
    assert local.get(f'/api/v1/samples/{sample["id"]}', headers=headers).status_code == 404


@pytest.mark.parametrize('planar', ['contig', 'separate'])
def test_single_look_rejected_with_clear_message_before_preview_or_storage(local, tmp_path, monkeypatch, planar):
    data = np.arange(40 * 64, dtype=np.int16).reshape(40, 64)
    array = np.stack([data, data], axis=-1 if planar == 'contig' else 0)
    path = tmp_path / 'single-look.tif'
    tifffile.imwrite(path, array, photometric='minisblack', planarconfig=planar, extrasamples=['unspecified'], compression='lzw')
    with pytest.raises(UnsupportedSingleLookError, match='不支持上传单视产品'):
        validate_raster_product(str(path))
    monkeypatch.setattr(tasks, '_read_preview_with_gdal', lambda *_args, **_kwargs: pytest.fail('single-look must be rejected before decoding'))
    with pytest.raises(UnsupportedSingleLookError) as error:
        tasks._build_preview_rgb(str(path), 8192)
    assert tasks._describe_preview_error(error.value, str(path)) == '不支持上传单视产品'
    upload = raw_upload(local, path.read_bytes())
    result = local.post(f'/api/v1/images/upload/{upload}/complete', json={'total_parts': 1, 'resolution': '1m'})
    assert result.status_code == 422 and result.json()['detail'] == '不支持上传单视产品'
    assert not (Path(get_settings().upload_tmp_dir) / upload).exists()


@pytest.mark.parametrize('planar', ['contig', 'separate'])
def test_compressed_preview_reads_segments_only(tmp_path, monkeypatch, planar):
    array = np.arange(600 * 900, dtype=np.uint16).reshape(600, 900)
    raster = np.stack([array, np.zeros_like(array)], axis=-1 if planar == 'contig' else 0)
    path = tmp_path / 'tiled.tif'
    tifffile.imwrite(path, raster, tile=(128, 128), compression='lzw', photometric='minisblack',
                     planarconfig=planar, extrasamples=['unspecified'])
    for owner in (tifffile.TiffPage, tifffile.TiffFile, tifffile.TiffPageSeries):
        monkeypatch.setattr(owner, 'asarray', lambda *_args, **_kwargs: pytest.fail('must not decode the entire raster'))
    preview = tasks._read_preview_with_tifffile(str(path), 90)
    assert preview.shape == (60, 90)
    np.testing.assert_array_equal(preview, array[::10, ::10])
