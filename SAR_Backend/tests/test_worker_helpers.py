from __future__ import annotations

import numpy as np
import pytest
import uuid

from app import config as app_config
from app.models import Image, Project, Task
from app.workers import client as worker_client
from app.workers import tasks


def test_levels_parsing(monkeypatch):
    monkeypatch.setattr(
        "app.workers.tasks.get_settings",
        lambda: type("S", (), {"thumbnail_levels": "2048,1024,512,256"})(),
    )
    assert tasks._levels() == [2048, 1024, 512, 256]


def test_to_uint8_gray_handles_nan():
    x = np.array([[0.0, 1.0], [np.nan, 10.0]], dtype=np.float32)
    y = tasks._to_uint8_gray(x)
    assert y.dtype == np.uint8
    assert y.shape == x.shape


def test_to_uint8_rgb_from_single_band():
    x = np.ones((10, 10), dtype=np.float32)
    rgb = tasks._to_uint8_rgb(x)
    assert rgb.shape == (10, 10, 3)
    assert rgb.dtype == np.uint8


def test_to_uint8_rgb_from_three_bands():
    x = np.stack(
        [
            np.zeros((4, 4), dtype=np.float32),
            np.ones((4, 4), dtype=np.float32),
            np.full((4, 4), 2.0, dtype=np.float32),
        ]
    )
    rgb = tasks._to_uint8_rgb(x)
    assert rgb.shape == (4, 4, 3)
    assert rgb.dtype == np.uint8


@pytest.mark.parametrize("planarconfig", ["contig", "separate"])
@pytest.mark.parametrize("compressed", [False, True])
def test_two_sample_tiff_preview_without_gdal(tmp_path, monkeypatch, planarconfig, compressed):
    import tifffile

    first = np.arange(9 * 13, dtype=np.uint16).reshape(9, 13)
    second = np.full_like(first, 65535)
    axis = -1 if planarconfig == "contig" else 0
    raster = np.stack([first, second], axis=axis)
    path = tmp_path / "two-sample.tif"
    tifffile.imwrite(path, raster, photometric="minisblack", planarconfig=planarconfig,
                     extrasamples=["unspecified"], compression="deflate" if compressed else None)
    original = path.read_bytes()
    def no_gdal(*_args, **_kwargs):
        raise RuntimeError("GDAL not available")
    monkeypatch.setattr(tasks, "_read_preview_with_gdal", no_gdal)
    rgb = tasks._build_preview_rgb(str(path), max_size=20)
    assert rgb.shape == (9, 13, 3)
    for channel in range(3):
        np.testing.assert_array_equal(rgb[:, :, channel], tasks._to_uint8_gray(first))
    small = tasks._build_preview_rgb(str(path), max_size=5)
    assert max(small.shape[:2]) <= 5
    assert tasks._read_source_dimensions(str(path)) == (13, 9)
    assert path.read_bytes() == original


def test_build_preview_rgb_falls_back_without_gdal(monkeypatch):
    def _raise_gdal(*_args, **_kwargs):
        raise RuntimeError("GDAL not available")

    monkeypatch.setattr(tasks, "_read_preview_with_gdal", _raise_gdal)
    monkeypatch.setattr(
        tasks,
        "_read_preview_with_tifffile",
        lambda *_args, **_kwargs: np.ones((8, 8), dtype=np.float32),
    )

    rgb = tasks._build_preview_rgb("dummy.tif", max_size=4)
    assert rgb.shape == (4, 4, 3)
    assert rgb.dtype == np.uint8


def test_build_preview_rgb_falls_back_to_pillow(monkeypatch):
    monkeypatch.setattr(tasks, "_read_preview_with_gdal", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no gdal")))
    monkeypatch.setattr(tasks, "_read_preview_with_tifffile", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no tifffile")))
    monkeypatch.setattr(tasks, "_read_preview_with_pillow", lambda *_args, **_kwargs: np.ones((6, 6, 3), dtype=np.uint8))

    rgb = tasks._build_preview_rgb("dummy.tif", max_size=4)
    assert rgb.shape == (4, 4, 3)
    assert rgb.dtype == np.uint8


@pytest.mark.parametrize('dtype', [np.float32, np.uint16, np.int32])
def test_lzw_numeric_tiff_pillow_fallback_stretches_before_uint8_conversion(tmp_path, monkeypatch, dtype):
    from PIL import Image as PILImage
    import tifffile
    values = (np.arange(80 * 120).reshape(80, 120) + 1000).astype(dtype)
    path = tmp_path / 'numeric-lzw.tif'
    PILImage.fromarray(values).save(path, compression='tiff_lzw')
    with tifffile.TiffFile(path) as opened:
        assert int(opened.pages[0].compression) == 5
    original = path.read_bytes()
    monkeypatch.setattr(tasks, '_read_preview_with_gdal', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('no gdal')))
    monkeypatch.setattr(tasks, '_read_preview_with_tifffile', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('requires imagecodecs')))
    decoded = tasks._read_preview_with_pillow(str(path), max_size=60)
    assert np.percentile(decoded, 50) > 255
    rgb = tasks._build_preview_rgb(str(path), max_size=60)
    assert rgb.shape == (40, 60, 3)
    assert len(np.unique(rgb[..., 0])) > 100
    assert 80 < np.median(rgb[..., 0]) < 180
    assert np.mean(rgb[..., 0] >= 250) < .1
    assert path.read_bytes() == original


def test_sample_raster_for_preview_downsamples_2d():
    arr = np.arange(100, dtype=np.float32).reshape(10, 10)
    sampled = tasks._sample_raster_for_preview(arr, max_size=4)
    assert sampled.shape == (4, 4)


@pytest.mark.parametrize('suffix', ['.tif', ''])
def test_pillow_preview_accepts_large_tiff_without_changing_generic_image_limits(tmp_path, monkeypatch, suffix):
    from PIL import Image as PILImage
    values = (np.arange(80 * 120).reshape(80, 120) + 1000).astype(np.float32)
    path = tmp_path / ('source' + suffix)
    PILImage.fromarray(values).save(path, format='TIFF', compression='tiff_lzw')
    png = tmp_path / 'ordinary.tif'
    PILImage.fromarray(np.zeros((80, 120), dtype=np.uint8)).save(png, format='PNG')
    monkeypatch.setattr(PILImage, 'MAX_IMAGE_PIXELS', 100)
    with pytest.raises(PILImage.DecompressionBombError):
        PILImage.open(path)
    monkeypatch.setattr(tasks, '_read_preview_with_gdal', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('no gdal')))
    monkeypatch.setattr(tasks, '_read_preview_with_tifffile', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('requires imagecodecs')))
    rgb = tasks._build_preview_rgb(str(path), max_size=60)
    assert rgb.shape == (40, 60, 3) and len(np.unique(rgb[..., 0])) > 100
    assert PILImage.MAX_IMAGE_PIXELS == 100
    with pytest.raises(PILImage.DecompressionBombError):
        tasks._read_preview_with_pillow(str(png), max_size=60)


def test_pillow_dimension_fallback_accepts_large_tiff(tmp_path, monkeypatch):
    from PIL import Image as PILImage
    import sys
    import tifffile
    path = tmp_path / 'source'
    PILImage.fromarray(np.zeros((80, 120), dtype=np.uint8)).save(path, format='TIFF')
    monkeypatch.setattr(PILImage, 'MAX_IMAGE_PIXELS', 100)
    monkeypatch.setitem(sys.modules, 'osgeo', None)
    monkeypatch.setattr(tifffile, 'TiffFile', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('reader unavailable')))
    assert tasks._read_source_dimensions(str(path)) == (120, 80)
    assert PILImage.MAX_IMAGE_PIXELS == 100


def test_sample_raster_for_preview_handles_channel_last():
    arr = np.zeros((10, 10, 3), dtype=np.float32)
    sampled = tasks._sample_raster_for_preview(arr, max_size=4)
    assert sampled.shape == (3, 4, 4)


def test_enqueue_process_image_inline_uses_background_thread(db_session, monkeypatch):
    app_config._settings = None
    settings = app_config.get_settings()
    settings.task_execution_mode = "inline"

    project = db_session.query(Project).first()
    if project is None:
        project = Project(id=uuid.uuid4(), name="default", description="default")
        db_session.add(project)
        db_session.commit()
    image_id = uuid.uuid4()
    db_session.add(
        Image(
            id=image_id,
            project_id=project.id,
            name="inline.tif",
            original_filename="inline.tif",
            mime_type="image/tiff",
            size_bytes=1,
            storage_key=f"raw/{image_id}/inline.tif",
            status="uploaded",
        )
    )
    db_session.commit()

    seen: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, kwargs, daemon, name):
            seen["target"] = target
            seen["kwargs"] = kwargs
            seen["daemon"] = daemon
            seen["name"] = name

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(worker_client.threading, "Thread", FakeThread)

    task_id = worker_client.enqueue_process_image(db=db_session, project_id=project.id, image_id=image_id)

    task = db_session.get(Task, task_id)
    assert task is not None
    assert task.status == "processing"
    assert seen["started"] is True
    assert seen["target"] is worker_client._run_process_image_inline_async
    assert seen["kwargs"] == {"task_id": task_id, "project_id": project.id, "image_id": image_id}
    assert seen["daemon"] is True
