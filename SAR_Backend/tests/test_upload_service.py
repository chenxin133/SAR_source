from __future__ import annotations

import uuid

from app import config as app_config
from app.upload_service import assemble, cleanup, write_part


def test_assemble_and_cleanup(tmp_path, monkeypatch):
    app_config._settings = None
    s = app_config.get_settings()
    s.upload_tmp_dir = str(tmp_path)

    upload_id = uuid.uuid4()
    write_part(upload_id=upload_id, part_no=1, data=b"abc")
    write_part(upload_id=upload_id, part_no=2, data=b"def")

    out_path, sha256, size_bytes = assemble(upload_id=upload_id, total_parts=2)
    assert size_bytes == 6
    assert sha256
    assert tmp_path.joinpath(str(upload_id), "assembled.bin").exists()

    cleanup(upload_id)
    assert not tmp_path.joinpath(str(upload_id)).exists()

