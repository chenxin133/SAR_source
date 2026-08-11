from __future__ import annotations


def test_chunk_upload_flow(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.images.put_file", lambda **_kwargs: None, raising=False)

    init = client.post("/api/v1/images/upload/init", json={"filename": "a.tif", "total_size": 10})
    assert init.status_code == 200
    upload_id = init.json()["data"]["upload_id"]

    part1 = client.put(f"/api/v1/images/upload/{upload_id}/part/1", data=b"12345")
    assert part1.status_code == 200
    part2 = client.put(f"/api/v1/images/upload/{upload_id}/part/2", data=b"67890")
    assert part2.status_code == 200

    done = client.post(
        f"/api/v1/images/upload/{upload_id}/complete",
        json={"total_parts": 2, "name": "a.tif", "mime_type": "image/tiff", "frequency_band": "X"},
    )
    assert done.status_code == 200
    image_id = done.json()["data"]["image_id"]
    assert image_id

    lst = client.get("/api/v1/images")
    assert lst.status_code == 200
    uploaded = next(x for x in lst.json()["data"] if str(x["id"]) == image_id)
    assert uploaded["frequency_band"] == "X"
