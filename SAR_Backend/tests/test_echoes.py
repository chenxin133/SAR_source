from __future__ import annotations

import hashlib
import math
import struct
import uuid
import pytest

from app.config import get_settings
from app.echo_service import create_preview, pulse_preview, read_header, simulate_echo
from app.models import EchoSignal, Project


def fixture_dat(endian="<"):
    return (struct.pack(endian + "ii", 2, 2)
            + struct.pack(endian + "I4H", 4294967295, 32771, 32772, 0, 65535)
            + struct.pack(endian + "I4H", 7, 32768, 32768, 32769, 32768))


@pytest.fixture()
def echo_client(client, tmp_path):
    settings = get_settings()
    settings.storage_backend = "local"
    settings.local_storage_dir = str(tmp_path / "storage")
    settings.rate_limit_requests = 0
    return client


@pytest.mark.parametrize("endian,order", [("<", "little"), (">", "big")])
def test_exact_binary_values_and_unsigned_gate(tmp_path, endian, order):
    path = tmp_path / "echo.dat"
    path.write_bytes(fixture_dat(endian))
    assert read_header(path, order) == (2, 2)
    metadata = create_preview(path, tmp_path / "preview.png", order, 32768)
    assert metadata["gate_max"] == 4294967295
    assert metadata["gate_min"] == 7
    pulse = pulse_preview(path, order, 32768, 0)
    assert pulse["i"] == [32771, 0]
    assert pulse["q"] == [32772, 65535]
    assert pulse["magnitude"][0] == 5
    assert pulse["phase"][0] == pytest.approx(math.atan2(4, 3))
    assert (tmp_path / "preview.png").read_bytes().startswith(b"\x89PNG")
    assert pulse_preview(path, order, 0, 1)["magnitude"][0] == pytest.approx(math.hypot(32768, 32768))


@pytest.mark.parametrize("data", [b"", b"1234567", struct.pack("<ii", 0, 1), struct.pack("<ii", -1, 5),
                                  struct.pack("<ii", 2147483647, 2147483647), fixture_dat()[:-1],
                                  fixture_dat() + b"extra", fixture_dat(">")])
def test_reject_malformed_binary_without_partial_records(echo_client, db_session, tmp_path, data):
    before = db_session.query(EchoSignal).count()
    response = echo_client.post("/api/v1/echoes/upload", files={"file": ("bad.dat", data)})
    assert response.status_code == 400, response.text
    assert db_session.query(EchoSignal).count() == before
    assert not list((tmp_path / "storage").rglob("*.dat"))


def test_simulation_is_reproducible_and_bounded(tmp_path):
    parameters = dict(na=12, nr=32, seed=42, noise_std=300, gate_start=1234)
    first, second = tmp_path / "first.dat", tmp_path / "second.dat"
    simulate_echo(first, **parameters)
    simulate_echo(second, **parameters)
    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_size == 8 + 12 * (4 + 32 * 4)
    assert pulse_preview(first, "little", 32768, 11)["igate"] == 1234
    simulate_echo(second, **{**parameters, "seed": 43})
    assert first.read_bytes() != second.read_bytes()


def test_management_lifecycle_and_project_isolation(echo_client, db_session):
    response = echo_client.post("/api/v1/echoes/simulate", json={
        "name": "生命周期回波", "na": 8, "nr": 16, "seed": 42, "gate_start": 4294967295})
    assert response.status_code == 201, response.text
    row = response.json()["data"]
    echo_id = row["id"]
    assert row["source"] == "simulated" and row["iq_offset"] == 32768
    assert row["simulation"]["seed"] == 42
    assert row["size_bytes"] == 8 + 8 * (4 + 16 * 4)
    listing = echo_client.get("/api/v1/echoes", params={"q": "生命周期", "source": "simulated"}).json()
    assert any(item["id"] == echo_id for item in listing["data"])
    assert echo_client.get(row["preview_url"]).headers["content-type"].startswith("image/png")
    binary = echo_client.get(f"/api/v1/echoes/{echo_id}/download").content
    assert hashlib.sha256(binary).hexdigest() == row["checksum_sha256"]
    assert echo_client.get(f"/api/v1/echoes/{echo_id}/pulse?pulse=7").json()["data"]["igate"] == 4294967295
    assert echo_client.get(f"/api/v1/echoes/{echo_id}/pulse?pulse=8").status_code == 400
    assert echo_client.get(f"/api/v1/echoes/{echo_id}/pulse?pulse=-1").status_code == 422
    assert echo_client.patch(f"/api/v1/echoes/{echo_id}", json={"name": "   "}).status_code == 422
    changed = echo_client.patch(f"/api/v1/echoes/{echo_id}", json={"name": "已编辑回波", "remark": "持久化备注"})
    assert changed.status_code == 200
    db_session.expire_all()
    assert echo_client.get(f"/api/v1/echoes/{echo_id}").json()["data"]["remark"] == "持久化备注"
    other = Project(id=uuid.uuid4(), name=f"echo-test-{uuid.uuid4()}")
    db_session.add(other)
    db_session.commit()
    headers = {"X-Project-Id": str(other.id)}
    for method, suffix in (("GET", ""), ("GET", "/pulse"), ("GET", "/download"), ("DELETE", "")):
        assert echo_client.request(method, f"/api/v1/echoes/{echo_id}{suffix}", headers=headers).status_code == 404
    assert echo_client.get("/api/v1/echoes", headers=headers).json()["total"] == 0
    assert echo_client.delete(f"/api/v1/echoes/{echo_id}").status_code == 200
    assert echo_client.get(f"/api/v1/echoes/{echo_id}").status_code == 404
    assert echo_client.get(row["download_url"]).status_code == 404
    assert echo_client.get(row["preview_url"]).status_code == 404


@pytest.mark.parametrize("endian,order,offset", [("<", "little", 32768), (">", "big", 0)])
def test_upload_preserves_original_binary(echo_client, endian, order, offset):
    data = fixture_dat(endian)
    result = echo_client.post("/api/v1/echoes/upload", files={"file": ("example.dat", data)},
                              data={"byte_order": order, "iq_offset": str(offset), "name": "导入示例"})
    assert result.status_code == 201, result.text
    row = result.json()["data"]
    assert row["source"] == "imported" and row["iq_offset"] == offset
    assert echo_client.get(row["download_url"]).content == data


def test_invalid_options_and_limits(echo_client, monkeypatch):
    from app.api.routes import echoes
    monkeypatch.setattr(echoes, "MAX_ECHO_BYTES", 16)
    assert echo_client.post("/api/v1/echoes/upload", files={"file": ("big.dat", fixture_dat())}).status_code == 413
    assert echo_client.post("/api/v1/echoes/upload", files={"file": ("bad.txt", b"x")}).status_code == 400
    assert echo_client.post("/api/v1/echoes/upload", files={"file": ("x.dat", b"x")},
                            data={"iq_offset": "7"}).status_code == 422
    for payload in ({"na": 0}, {"nr": -1}, {"na": 4096, "nr": 8192}, {"seed": -1}, {"gate_start": 4294967296}):
        assert echo_client.post("/api/v1/echoes/simulate", json=payload).status_code == 422
    assert echo_client.post("/api/v1/echoes/simulate", json={"frequency_band": "invalid"}).status_code == 422


def test_four_bands_change_binary_and_can_be_filtered(echo_client):
    checksums = set()
    for band, frequency in (("C", 5.3), ("X", 9.6), ("Ku", 15.0), ("Ka", 35.0)):
        response = echo_client.post("/api/v1/echoes/simulate", json={
            "name": f"四频段测试-{band}", "frequency_band": band, "na": 16, "nr": 64, "seed": 42})
        assert response.status_code == 201, response.text
        row = response.json()["data"]
        assert row["frequency_band"] == band and row["center_frequency_ghz"] == frequency
        assert row["simulation"]["sample_rate_hz"] > row["simulation"]["bandwidth_hz"]
        checksums.add(row["checksum_sha256"])
        listing = echo_client.get("/api/v1/echoes", params={"frequency_band": band, "q": "四频段测试"}).json()
        assert listing["total"] == 1 and listing["data"][0]["id"] == row["id"]
    assert len(checksums) == 4


def test_reject_oversized_header_before_mapping(tmp_path):
    path = tmp_path / "oversized.dat"
    with path.open("wb") as stream:
        stream.write(struct.pack("<ii", 1, 1))
        stream.truncate(64 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="64 MiB"):
        read_header(path)


def test_echo_route_can_be_refreshed_without_masking_api_404(echo_client, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text('<html><div id="app"></div></html>', encoding="utf-8")
    get_settings().frontend_dist_dir = str(frontend)
    app = create_app()
    browser = TestClient(app)
    assert browser.get("/data/echo").status_code == 200
    assert 'id="app"' in browser.get("/data/echo").text
    assert browser.get("/api/v1/echoes/not-a-route").status_code in (404, 422)
    assert browser.get("/assets/missing.js").status_code == 404
    get_settings().frontend_dist_dir = ""
