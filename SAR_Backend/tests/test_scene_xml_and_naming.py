import base64
import io
import json
from pathlib import Path
import struct
import uuid
import zipfile
import sqlite3
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import tifffile
from PIL import Image as PILImage, ImageDraw

from app.config import get_settings
from app.models import Annotation, Image, Project, Sample, Thumbnail
from app.scene_metadata import parse_scene_xml
from app.sample_resolution import downsample
from app.schema_updates import add_scene_xml_metadata
from sqlalchemy import create_engine, text

XML = '''<?xml version="1.0" encoding="utf-8"?>
<sarScene id="fixture" schemaVersion="2.0">
 <dataName>测试影像</dataName><dataSource>航天宏图</dataSource><satellite>HT2-02D</satellite>
 <frequencyBand>X</frequencyBand><polarization>HH</polarization>
 <imagingTime><start>2026-07-02T00:11:31.831368</start><end>2026-07-02T00:11:32.663178</end><timeReference>UTC</timeReference></imagingTime>
 <resolution unit="m">0.5</resolution><imageSize image="scene.tif"><width>8</width><height>8</height></imageSize>
 <geographicCoordinates><center><longitude>120.5</longitude><latitude>30.5</latitude></center></geographicCoordinates>
</sarScene>'''.encode()


@pytest.fixture
def scene_client(client, db_session, tmp_path):
    settings = get_settings()
    settings.storage_backend = 'local'
    settings.local_storage_dir = str(tmp_path / 'storage')
    settings.rate_limit_requests = 0
    project = Project(id=uuid.uuid4(), name=str(uuid.uuid4()))
    db_session.add(project); db_session.commit()
    client.headers['X-Project-Id'] = str(project.id)
    return client


def raster():
    output = io.BytesIO()
    tifffile.imwrite(output, np.arange(64, dtype=np.uint16).reshape(8, 8))
    return output.getvalue()


def upload_raw(client, **fields):
    content = raster()
    upload = client.post('/api/v1/images/upload/init', json={'filename': 'scene.tif', 'total_size': len(content)}).json()['data']['upload_id']
    assert client.put(f'/api/v1/images/upload/{upload}/part/1', content=content).status_code == 200
    return client.post(f'/api/v1/images/upload/{upload}/complete', json={'total_parts': 1, **fields})


def test_supplied_schema_reads_fields_time_units_and_missing_region(scene_client):
    response = scene_client.post('/api/v1/images/metadata/parse-xml', files={'file': ('scene.xml', XML)})
    assert response.status_code == 200
    metadata = response.json()['data']
    assert metadata['satellite'] == 'HT2-02D' and metadata['data_source'] == '航天宏图'
    assert metadata['frequency_band'] == 'X' and metadata['polarization'] == 'HH'
    assert metadata['resolution'] == '0.5m' and metadata['region'] == ''
    assert metadata['acquisition_at'] == '2026-07-02T00:11:31.831368Z'
    assert metadata['width'] == 8 and metadata['coordinates']['center']['longitude'] == 120.5
    namespaces = XML.replace(b'<sarScene ', b'<sarScene xmlns="urn:example" ')
    assert parse_scene_xml(namespaces)['name'] == '测试影像'
    assert parse_scene_xml(XML.replace(b'unit="m">0.5', b'unit="cm">50'))['resolution'] == '0.5m'


@pytest.mark.parametrize('content', [
    b'<broken>', b'<wrong/>', b'<!DOCTYPE sarScene [<!ENTITY e "boom">]><sarScene>&e;</sarScene>',
    b'<!DOCTYPE sarScene SYSTEM "file:///secret"><sarScene/>',
    '<!DOCTYPE sarScene [<!ENTITY e SYSTEM "file:///secret">]><sarScene>&e;</sarScene>'.encode('utf-16'),
    b'<sarScene>' + b'<x>' * 70 + b'</x>' * 70 + b'</sarScene>', b'x' * (2 * 1024 * 1024 + 1),
], ids=['broken', 'wrong-root', 'entity', 'external-dtd', 'utf16-entity', 'depth', 'size'])
def test_xml_rejects_invalid_complex_and_external_entities(scene_client, content):
    assert scene_client.post('/api/v1/images/metadata/parse-xml', files={'file': ('scene.xml', content)}).status_code == 422


def test_xml_archived_exactly_manual_overrides_and_required_resolution(scene_client, db_session):
    before = db_session.query(Image).count()
    assert upload_raw(scene_client).status_code == 422
    assert db_session.query(Image).count() == before
    response = upload_raw(scene_client, metadata_xml_base64=base64.b64encode(XML).decode(), metadata_xml_filename='原配套.xml',
                          name='人工名称', description='地区：青岛', resolution='1m')
    assert response.status_code == 200, response.text
    image_id = response.json()['data']['image_id']
    detail = scene_client.get(f'/api/v1/images/{image_id}').json()['data']
    assert detail['name'] == '人工名称' and detail['resolution'] == '1m'
    assert detail['satellite'] == 'HT2-02D' and detail['metadata_xml_filename'] == '原配套.xml'
    assert scene_client.get(detail['metadata_xml_url']).content == XML
    image = db_session.get(Image, uuid.UUID(image_id))
    stored = Path(get_settings().local_storage_dir) / 'sar' / image.storage_key
    assert stored.name == 'scene.tif' and stored.read_bytes() == raster()
    assert Path(image.metadata_xml_key).name == 'scene.xml'


def test_duplicate_update_preserves_image_identity_files_annotations_and_previews(scene_client, db_session):
    first = upload_raw(scene_client, resolution='0.5m', name='first').json()['data']['image_id']
    image = db_session.get(Image, uuid.UUID(first))
    db_session.add(Annotation(project_id=image.project_id, image_id=image.id, type='saved', payload={'saved': True}))
    db_session.add(Thumbnail(project_id=image.project_id, image_id=image.id, purpose='preview', level=64, format='png', storage_key='thumbnails/unchanged.png'))
    db_session.commit()
    old_key, old_checksum = image.storage_key, image.checksum_sha256
    response = upload_raw(scene_client, duplicate_action='update', name='new', resolution='2m', satellite='GF-3', metadata_xml_base64=base64.b64encode(XML).decode())
    assert response.status_code == 200 and response.json()['data']['image_id'] == first
    assert response.json()['data']['updated']
    db_session.refresh(image)
    assert image.name == 'new' and image.satellite == '高分三号' and image.resolution == '2m'
    assert (image.storage_key, image.checksum_sha256) == (old_key, old_checksum)
    assert db_session.query(Annotation).filter_by(image_id=image.id).one().payload == {'saved': True}
    assert db_session.query(Thumbnail).filter_by(image_id=image.id).one().storage_key == 'thumbnails/unchanged.png'


def upload_sample(client, **fields):
    return client.post('/api/v1/samples/upload', data={'name': 'ignored custom name', 'category': '舰船', 'frequency_band': 'X', 'resolution': '0.5m',
        'annotation_id': f'manual:{uuid.uuid4()}', 'image_format': 'image/tiff', 'width': 999, 'height': 999, **fields},
        files={'image': ('input.tif', raster(), 'image/tiff')})


def test_sample_names_xml_update_copy_and_four_digit_sequence(scene_client, db_session):
    first = upload_sample(scene_client).json()['data']
    assert first['name'] == '舰船_X_0.5m_0001' and first['sequence_no'] == 1
    assert Path(first['crop_storage_key']).name == '舰船_X_0.5m_0001.tif'
    assert first['roi']['width'] == first['roi']['height'] == 8
    xml = ET.fromstring(scene_client.get(first['metadata_xml_url']).content)
    assert xml.findtext('sampleNumber') == '0001' and xml.find('imageSize').get('image') == '舰船_X_0.5m_0001.tif'
    assert xml.findtext('imageSize/width') == '8'
    assert upload_sample(scene_client).status_code == 409
    updated = upload_sample(scene_client, duplicate_action='update', category='车辆').json()['data']
    assert updated['id'] == first['id'] and updated['name'] == '车辆_X_0.5m_0001'
    assert scene_client.get(first['image_url']).status_code == 404
    copied = upload_sample(scene_client, duplicate_action='import').json()['data']
    assert copied['id'] != first['id'] and copied['name'] == '舰船_X_0.5m_0002'


def test_export_bundle_uses_actual_target_resolution_name_and_xml(scene_client):
    sample = upload_sample(scene_client).json()['data']
    response = scene_client.get(f"/api/v1/samples/{sample['id']}/export?bundle=true&target_resolution=2")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ['舰船_X_2m_0001.tif', '舰船_X_2m_0001.xml']
        pixels = tifffile.imread(io.BytesIO(archive.read(archive.namelist()[0])))
        xml = ET.fromstring(archive.read(archive.namelist()[1]))
        assert pixels.shape == (2, 2) and pixels.dtype == np.uint16
        assert xml.findtext('resolution') == '2' and xml.findtext('imageSize/width') == '2'
    invalid = scene_client.post('/api/v1/samples/export', json={'sample_ids': [sample['id']], 'target_resolution': 0.5})
    assert invalid.status_code == 422


def test_echo_named_files_and_update_keep_id(scene_client):
    content = struct.pack('<iiI4H', 1, 2, 7, 32768, 32769, 32770, 32771)
    def upload(**fields):
        return scene_client.post('/api/v1/echoes/upload', data={'name': '回波一', **fields}, files={'file': ('incoming.dat', content)})
    first = upload().json()['data']
    assert unquote(first['download_url']).endswith('/回波一.dat')
    assert unquote(first['preview_url']).endswith('/回波一_amplitude.png')
    updated = upload(duplicate_action='update', name='更新回波').json()['data']
    assert updated['id'] == first['id'] and unquote(updated['download_url']).endswith('/更新回波.dat')
    assert scene_client.get(updated['download_url']).content == content
    renamed = scene_client.patch(f"/api/v1/echoes/{first['id']}", json={'name': '新名', 'remark': 'kept'}).json()['data']
    assert unquote(renamed['download_url']).endswith('/新名.dat') and scene_client.get(renamed['download_url']).content == content


def test_crop_names_sidecars_update_and_live_source_time(scene_client):
    image_id = upload_raw(scene_client, metadata_xml_base64=base64.b64encode(XML).decode()).json()['data']['image_id']
    payload = {'image_id': image_id, 'annotation_id': 'rect1', 'annotation_type': 'rect', 'category': '舰船',
               'coordinate_width': 8, 'coordinate_height': 8, 'output_format': 'source',
               'polygon': [{'x': 1, 'y': 1}, {'x': 5, 'y': 1}, {'x': 5, 'y': 5}, {'x': 1, 'y': 5}]}
    response = scene_client.post('/api/v1/samples/crop', json=payload)
    assert response.status_code == 200, response.text
    sample = response.json()['data']
    assert sample['name'] == '舰船_X_0.5m_0001'
    assert Path(sample['crop_storage_key']).name == sample['name'] + '.tif'
    xml = ET.fromstring(scene_client.get(sample['metadata_xml_url']).content)
    assert xml.findtext('imageSize/width') == '4'
    assert xml.find('sourceImage').get('id') == image_id
    assert xml.find('geographicCoordinates') is None
    assert xml.find('sourceImage/geographicCoordinates/center') is not None
    assert scene_client.patch(f'/api/v1/images/{image_id}', json={'acquisition_at': '2026-07-03T12:34:56'}).status_code == 200
    updated = scene_client.post('/api/v1/samples/crop', json={**payload, 'category': '码头'}).json()['data']
    assert updated['id'] == sample['id'] and updated['name'] == '码头_X_0.5m_0001'
    xml = ET.fromstring(scene_client.get(updated['metadata_xml_url']).content)
    assert xml.findtext('imagingTime/start') == '2026-07-03T12:34:56'
    assert xml.find('imagingTime/end') is None


def test_encoded_storage_urls_and_project_isolated_batch_export(scene_client, db_session):
    sample = upload_sample(scene_client, category='舰船#1% &泊位').json()['data']
    assert '%23' in sample['image_url'] and '%25' in sample['image_url']
    assert scene_client.get(sample['image_url']).content == raster()
    assert scene_client.get(sample['metadata_xml_url']).status_code == 200
    project = Project(id=uuid.uuid4(), name=str(uuid.uuid4()))
    db_session.add(project); db_session.commit()
    scene_client.headers['X-Project-Id'] = str(project.id)
    assert scene_client.post('/api/v1/samples/export', json={'sample_ids': [sample['id']]}).status_code == 404


@pytest.mark.parametrize('separate', [False, True])
def test_two_channel_tiff_downsample_retains_spatial_axes_and_xml_dimensions(separate):
    pixels = np.stack([np.arange(64, dtype=np.uint16).reshape(8, 8), np.full((8, 8), 65000, dtype=np.uint16)], axis=-1)
    source = io.BytesIO()
    tifffile.imwrite(source, np.moveaxis(pixels, -1, 0) if separate else pixels, photometric='minisblack',
                     planarconfig='separate' if separate else 'contig', extrasamples=['unspecified'])
    output, mime = downsample(source.getvalue(), 'image/tiff', 0.5, 'source', 1)
    with tifffile.TiffFile(io.BytesIO(output)) as opened:
        assert opened.series[0].axes == 'YXS'
        assert opened.series[0].shape == (4, 4, 2)
        assert (opened.pages[0].imagewidth, opened.pages[0].imagelength) == (4, 4)
        assert np.all(opened.asarray()[..., 1] == 65000)


def test_scene_upgrade_preserves_existing_rows_and_backup_and_is_idempotent(tmp_path):
    database = tmp_path / 'existing.db'
    engine = create_engine(f'sqlite:///{database}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE images (id TEXT PRIMARY KEY, name TEXT)')
        connection.exec_driver_sql('CREATE TABLE samples (id TEXT PRIMARY KEY, project_id TEXT, name TEXT, image_id TEXT)')
        connection.exec_driver_sql("INSERT INTO images VALUES ('image1', 'old image')")
        connection.exec_driver_sql("INSERT INTO samples VALUES ('sample1', 'project1', 'old sample', 'image1')")
    add_scene_xml_metadata(engine)
    backup = Path(str(database) + '.before-scene-xml-metadata.bak')
    original_backup = backup.read_bytes()
    add_scene_xml_metadata(engine)
    assert backup.read_bytes() == original_backup
    with engine.connect() as connection:
        assert connection.execute(text('SELECT id,name FROM images')).one() == ('image1', 'old image')
        assert connection.execute(text('SELECT name,image_id,sequence_no FROM samples')).one() == ('old sample', 'image1', None)
        assert 'ux_samples_project_sequence' in [row[1] for row in connection.exec_driver_sql('PRAGMA index_list(samples)')]
    with sqlite3.connect(backup) as old:
        assert 'scene_metadata' not in [row[1] for row in old.execute('PRAGMA table_info(images)')]
        assert old.execute('SELECT id FROM images').fetchone() == ('image1',)
    engine.dispose()


@pytest.mark.parametrize('output_format', ['image/png', 'image/tiff', 'source'])
def test_polygon_crop_thumbnail_and_exports_keep_the_outline(scene_client, output_format):
    image_id = upload_raw(scene_client, resolution='0.5m', frequency_band='X').json()['data']['image_id']
    response = scene_client.post('/api/v1/samples/crop', json={'image_id': image_id, 'annotation_id': 'triangle',
        'annotation_type': 'polygon', 'category': '舰船', 'coordinate_width': 8, 'coordinate_height': 8,
        'output_format': output_format, 'polygon': [{'x': 1, 'y': 1}, {'x': 7, 'y': 1}, {'x': 1, 'y': 7}]})
    assert response.status_code == 200, response.text
    sample = response.json()['data']
    with PILImage.open(io.BytesIO(scene_client.get(sample['thumbnail_url']).content)) as thumbnail:
        assert thumbnail.getpixel((5, 5)) == (0, 0, 0, 0)
        assert thumbnail.getpixel((1, 1))[3] == 255
    with PILImage.open(io.BytesIO(scene_client.get(sample['image_url']).content)) as image:
        if output_format == 'source':
            assert np.asarray(image).dtype == np.uint16 and image.getpixel((5, 5)) == 0
        else:
            assert image.mode == 'RGBA' and image.getpixel((5, 5)) == (0, 0, 0, 0)
    if output_format == 'image/png':
        for extension in ['image/png', 'image/tiff']:
            exported = scene_client.get(f"/api/v1/samples/{sample['id']}/export", params={'format': extension})
            with PILImage.open(io.BytesIO(exported.content)) as image:
                assert image.getpixel((5, 5)) == (0, 0, 0, 0)


@pytest.mark.parametrize('output_format', ['PNG', 'TIFF', 'JPEG'])
def test_legacy_transparent_png_never_reveals_hidden_source_rgb_on_conversion(tmp_path, output_format):
    from app.api.routes.samples import _save_crop
    old = PILImage.new('RGBA', (32, 32), (180, 90, 40, 255))
    mask = PILImage.new('L', old.size, 0); ImageDraw.Draw(mask).polygon([(0, 0), (31, 0), (0, 31)], fill=255)
    old.putalpha(mask)
    assert old.getpixel((31, 31)) == (180, 90, 40, 0)
    path = tmp_path / ('export.' + output_format.lower())
    _save_crop(old, str(path), output_format)
    with PILImage.open(path) as image:
        if output_format == 'JPEG':
            assert max(image.getpixel((31, 31))) < 15
        else:
            assert image.getpixel((31, 31)) == (0, 0, 0, 0)
