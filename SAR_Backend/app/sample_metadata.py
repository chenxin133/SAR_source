"""Stable sample numbers, filenames and XML sidecars."""
from pathlib import Path
from datetime import datetime
import re
import tempfile

from sqlalchemy import func, select

from app.config import get_settings
from app.models import Image, Project, Sample
from app.sample_resolution import resolution_meters
from app.scene_metadata import sample_xml
from app.storage import put_file
from app.upload_filenames import storage_filename


def sample_name(category: str | None, band: str | None, resolution: str | None, number: int) -> str:
    def component(value, fallback, limit):
        text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value or '').strip()) or fallback
        return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')
    meters = resolution_meters(resolution)
    label = f'{meters:g}m' if meters is not None else re.sub(r'\s+', '', resolution or '')
    return f'{component(category, "未分类", 48)}_{component(band, "未知频段", 16)}_{component(label, "未知分辨率", 16)}_{number:04d}'


def ensure_sample_number(db, sample: Sample) -> int:
    if sample.sequence_no is None:
        db.scalar(select(Project).where(Project.id == sample.project_id).with_for_update())
        sample.sequence_no = int(db.scalar(select(func.max(Sample.sequence_no)).where(Sample.project_id == sample.project_id)) or 0) + 1
        db.flush()
    return sample.sequence_no


def effective_metadata(db, sample: Sample) -> tuple[str, str, dict]:
    source = db.get(Image, sample.image_id) if sample.image_id else None
    resolution = sample.resolution or (source.resolution if source else '') or ''
    band = sample.frequency_band or (source.frequency_band if source else '') or ''
    metadata = dict((source.scene_metadata if source else None) or sample.scene_metadata or {})
    if source:
        metadata.update(name=source.name, satellite=source.satellite, polarization=source.polarization)
        if source.acquisition_at:
            current = source.acquisition_at.isoformat()
            metadata['acquisition_at'] = current
            original = metadata.get('imaging_start')
            try:
                unchanged = datetime.fromisoformat(original.replace('Z', '+00:00')).replace(tzinfo=None) == source.acquisition_at.replace(tzinfo=None) if original else False
            except ValueError:
                unchanged = False
            if not unchanged:
                metadata['imaging_start'] = current
                metadata.pop('imaging_end', None)
                metadata.pop('time_reference', None)
        for line in (source.description or '').splitlines():
            if line.startswith('地区：'):
                metadata['region'] = line[3:].strip()
    return resolution, band, metadata


def sample_paths(db, sample: Sample, extension: str) -> tuple[str, str]:
    number = ensure_sample_number(db, sample)
    resolution, band, _ = effective_metadata(db, sample)
    sample.name = sample_name(sample.category, band, resolution, number)
    leaf = storage_filename(sample.name + extension)
    folder = f'samples/{sample.image_id or "local"}/{sample.id}'
    return f'{folder}/{leaf}', f'{folder}/{Path(leaf).stem}_thumbnail.png'


def make_sample_xml(db, sample: Sample, *, filename: str | None = None, resolution: str | None = None,
                    width: int | None = None, height: int | None = None) -> tuple[str, bytes]:
    number = ensure_sample_number(db, sample)
    current_resolution, band, metadata = effective_metadata(db, sample)
    resolution = resolution if resolution is not None else current_resolution
    name = sample_name(sample.category, band, resolution, number)
    filename = filename or Path(sample.crop_storage_key).name
    roi = sample.roi or {}
    return name, sample_xml(sample_id=str(sample.id), name=name, number=number, category=sample.category or '',
                            band=band, resolution=resolution, filename=filename,
                            width=width if width is not None else int(roi.get('width') or 0),
                            height=height if height is not None else int(roi.get('height') or 0),
                            metadata=metadata, source_id=str(sample.image_id) if sample.image_id else None, roi=roi)


def persist_sample_xml(db, sample: Sample) -> None:
    _, content = make_sample_xml(db, sample)
    key = str(Path(sample.crop_storage_key).with_suffix('.xml')).replace('\\', '/')
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'metadata.xml'
        path.write_bytes(content)
        put_file(bucket=get_settings().s3_bucket, key=key, file_path=str(path), content_type='application/xml')
    sample.metadata_xml_key = key
