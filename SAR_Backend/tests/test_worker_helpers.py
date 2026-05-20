from __future__ import annotations

import numpy as np

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
