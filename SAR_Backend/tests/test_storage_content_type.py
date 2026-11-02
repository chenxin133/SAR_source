from pathlib import Path

import pytest

from app.storage import guess_content_type


@pytest.mark.parametrize('name', ['scene.xml', '舰船_C_1m_0001.XML', Path('中文目录/样本.xml')])
def test_xml_content_type_does_not_depend_on_windows_mime_registry(monkeypatch, name):
    def unavailable_registry(*args, **kwargs):
        raise RuntimeError('System MIME registry is unavailable in the frozen runtime')
    monkeypatch.setattr('app.storage.mimetypes.guess_type', unavailable_registry)
    assert guess_content_type(name) == 'application/xml'
