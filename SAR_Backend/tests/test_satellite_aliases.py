import pytest

from app.scene_metadata import parse_scene_xml, sample_xml, satellite_name


@pytest.mark.parametrize('code,name', [
    ('GF3', '高分三号'), ('QL1', '齐鲁一号星'), ('TJ04-3', '泰景四号03星'),
    ('HT1-A', '航天宏图一号'), ('LJ2-01', '珞珈二号01星'),
    ('HS-01', '海丝一号'), ('CH-01', '巢湖一号'), ('FC-01', '涪城一号'),
])
def test_scene_codes_match_entry_names_and_sample_xml(code, name):
    for value in (code, code.lower(), f'  {code}  ', name):
        assert satellite_name(value) == name
        xml = f'<sarScene><satellite>{value}</satellite></sarScene>'.encode('utf-8')
        assert parse_scene_xml(xml)['satellite'] == name
    xml = sample_xml(sample_id='sample', name='sample', number=1, category='AIRCRAFT',
                     band='X', resolution='1m', filename='sample.tif', width=8, height=8,
                     metadata={'satellite': code})
    assert parse_scene_xml(xml)['satellite'] == name


@pytest.mark.parametrize('value', ['TJ04-30', 'HT2-02D', 'QL10', ' Custom-Satellite '])
def test_unknown_satellites_keep_their_identity(value):
    assert satellite_name(value) == value.strip()
