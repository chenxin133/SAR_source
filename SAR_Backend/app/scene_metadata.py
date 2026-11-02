"""Read the supplied sarScene XML and write matching sample sidecars."""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.parsers import expat

from app.sample_resolution import resolution_meters

MAX_XML_BYTES = 2 * 1024 * 1024
SATELLITE_ALIASES = {
    '齐鲁一号': '齐鲁一号星', '齐鲁1号': '齐鲁一号星', 'QL-1': '齐鲁一号星',
    '珞珈二号': '珞珈二号01星', '珞珈一号01星': '珞珈二号01星',
    '高分3号': '高分三号', 'GF3': '高分三号', 'GF-3': '高分三号',
}


def satellite_name(value: str | None) -> str | None:
    text = (value or '').strip()
    return SATELLITE_ALIASES.get(text, text) or None


def parse_scene_xml(content: bytes) -> dict:
    if not content or len(content) > MAX_XML_BYTES:
        raise ValueError('XML 不能为空且不能超过 2 MiB')
    parser = expat.ParserCreate(namespace_separator='}')
    depth, count = 0, 0
    def forbid(*_args):
        raise ValueError('XML 不允许 DTD、实体或外部资源')
    def start(_name, _attrs):
        nonlocal depth, count
        depth += 1
        count += 1
        if depth > 64 or count > 20000:
            raise ValueError('XML 结构过于复杂')
    def end(_name):
        nonlocal depth
        depth -= 1
    parser.StartDoctypeDeclHandler = forbid
    parser.EntityDeclHandler = forbid
    parser.ExternalEntityRefHandler = forbid
    parser.StartElementHandler, parser.EndElementHandler = start, end
    try:
        parser.Parse(content, True)
        root = ET.fromstring(content)
    except (expat.ExpatError, ET.ParseError) as error:
        raise ValueError(f'XML 格式错误：{error}') from error
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'sarScene':
        raise ValueError('请选择 sarScene 格式的配套 XML')
    def text(path):
        return (root.findtext(path) or '').strip()
    resolution = root.find('resolution')
    value = text('resolution')
    unit = resolution.get('unit', '') if resolution is not None else ''
    meters = resolution_meters(value + unit)
    if meters is not None:
        value = f'{meters:g}m'
    elif value and unit:
        value += unit
    else:
        value = ''  # A bare number does not establish a spatial unit.
    reference = text('imagingTime/timeReference')
    start_time = text('imagingTime/start')
    acquisition = ''
    if start_time:
        try:
            parsed = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if parsed.tzinfo is None and reference.upper() == 'UTC':
                parsed = parsed.replace(tzinfo=timezone.utc)
            acquisition = parsed.isoformat().replace('+00:00', 'Z')
        except ValueError:
            pass
    image_size = root.find('imageSize')
    def number(path):
        try:
            result = int(text(path))
            return result if result > 0 else None
        except ValueError:
            return None
    coordinates = {}
    for corner in ('center', 'topLeft', 'topRight', 'bottomLeft', 'bottomRight'):
        lon, lat = text(f'geographicCoordinates/{corner}/longitude'), text(f'geographicCoordinates/{corner}/latitude')
        if lon and lat:
            try:
                longitude, latitude = float(lon), float(lat)
                if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                    coordinates[corner] = {'longitude': longitude, 'latitude': latitude}
            except ValueError:
                pass
    return {
        'schema_version': root.get('schemaVersion', ''), 'scene_id': root.get('id', ''),
        'name': text('dataName'), 'data_source': text('dataSource'), 'satellite': satellite_name(text('satellite')) or '',
        'frequency_band': text('frequencyBand'), 'polarization': text('polarization'),
        'acquisition_at': acquisition, 'imaging_start': start_time, 'imaging_end': text('imagingTime/end'),
        'time_reference': reference, 'resolution': value, 'region': text('region'),
        'category': text('category'), 'sample_number': text('sampleNumber'),
        'image_filename': image_size.get('image', '') if image_size is not None else '',
        'width': number('imageSize/width'), 'height': number('imageSize/height'),
        'coordinates': coordinates,
    }


def decode_scene_xml(encoded: str | None) -> tuple[bytes | None, dict | None]:
    if not encoded:
        return None, None
    if len(encoded) > MAX_XML_BYTES * 4 // 3 + 8:
        raise ValueError('XML 不能超过 2 MiB')
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError('XML 文件编码无效') from error
    return content, parse_scene_xml(content)


def sample_xml(*, sample_id: str, name: str, number: int, category: str, band: str,
               resolution: str, filename: str, width: int, height: int,
               metadata: dict | None = None, source_id: str | None = None, roi: dict | None = None) -> bytes:
    metadata = metadata or {}
    root = ET.Element('sarScene', {'id': sample_id, 'schemaVersion': '2.0', 'dataType': 'sample'})
    def add(parent, key, value):
        if value is not None and str(value).strip():
            ET.SubElement(parent, key).text = str(value)
    add(root, 'dataName', name)
    add(root, 'dataSource', metadata.get('data_source'))
    add(root, 'satellite', satellite_name(metadata.get('satellite')))
    add(root, 'category', category)
    add(root, 'sampleNumber', f'{number:04d}')
    add(root, 'frequencyBand', band)
    add(root, 'polarization', metadata.get('polarization'))
    if metadata.get('imaging_start') or metadata.get('acquisition_at'):
        imaging = ET.SubElement(root, 'imagingTime')
        add(imaging, 'start', metadata.get('imaging_start') or metadata.get('acquisition_at'))
        add(imaging, 'end', metadata.get('imaging_end'))
        add(imaging, 'timeReference', metadata.get('time_reference'))
    meters = resolution_meters(resolution)
    ET.SubElement(root, 'resolution', {'unit': 'm'} if meters is not None else {}).text = f'{meters:g}' if meters is not None else resolution
    size = ET.SubElement(root, 'imageSize', {'image': filename})
    add(size, 'width', width)
    add(size, 'height', height)
    add(root, 'region', metadata.get('region'))
    if source_id:
        source = ET.SubElement(root, 'sourceImage', {'id': source_id})
        add(source, 'dataName', metadata.get('name'))
        # Source coordinates describe the source scene, not the cropped sample.
        if metadata.get('coordinates'):
            corners = ET.SubElement(source, 'geographicCoordinates', {'crs': 'EPSG:4326'})
            for key, point in metadata['coordinates'].items():
                corner = ET.SubElement(corners, key)
                add(corner, 'longitude', point.get('longitude'))
                add(corner, 'latitude', point.get('latitude'))
        if roi:
            geometry = ET.SubElement(source, 'roi')
            for key in ('annotationId', 'annotationType', 'coordinateWidth', 'coordinateHeight'):
                add(geometry, key, roi.get(key))
            if roi.get('polygon'):
                points = ET.SubElement(geometry, 'polygon')
                for point in roi['polygon']:
                    ET.SubElement(points, 'point', {'x': str(point['x']), 'y': str(point['y'])})
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
