"""Keep recognizable original names within portable filesystem limits."""
import re
from pathlib import PureWindowsPath


def storage_filename(original: str) -> str:
    name = PureWindowsPath(original).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().rstrip('. ')
    suffix = PureWindowsPath(name).suffix
    if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
        suffix = '.bin'
        stem = name
    else:
        stem = name[:-len(suffix)]
    if stem.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        stem = '_' + stem
    # At most 100 UTF-8 bytes also leaves room for installation/storage paths.
    stem = stem.encode('utf-8')[:100].decode('utf-8', errors='ignore').rstrip('. ') or 'source'
    return stem + suffix
