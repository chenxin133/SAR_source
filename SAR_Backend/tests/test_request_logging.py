import io
import json
from pathlib import Path

from app.config import get_settings


class LegacyWindowsConsole(io.StringIO):
    def write(self, value):
        value.encode('cp1252')
        return super().write(value)


def test_unicode_storage_request_succeeds_with_legacy_windows_console(client, monkeypatch, tmp_path):
    settings = get_settings()
    settings.storage_backend = 'local'
    settings.local_storage_dir = str(tmp_path / 'storage')
    xml = Path(settings.local_storage_dir) / settings.s3_bucket / '样本.xml'
    xml.parent.mkdir(parents=True)
    xml.write_bytes(b'<sarScene/>')
    console = LegacyWindowsConsole()
    with monkeypatch.context() as context:
        context.setattr('sys.stdout', console)
        response = client.get(f'/api/v1/storage/{settings.s3_bucket}/样本.xml')
    assert response.status_code == 200
    assert response.content == b'<sarScene/>'
    entry = json.loads(console.getvalue())
    assert entry['path'].endswith('/样本.xml')
    assert entry['status_code'] == 200
