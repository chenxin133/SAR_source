"""Spatial resolution validation and area-averaged sample downsampling."""
import io
import re

import numpy as np
import tifffile
from PIL import Image

EXPORT_RESOLUTIONS = (0.5, 1.0, 2.0, 3.0, 5.0)


def resolution_meters(value: str | None) -> float | None:
    text = re.sub(r"\s+", "", value or "").lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?|\.\d+)(km|cm|mm|m|千米|厘米|毫米|米)", text)
    if not match:
        return None
    factors = {"m": 1, "米": 1, "km": 1000, "千米": 1000, "cm": .01, "厘米": .01, "mm": .001, "毫米": .001}
    meters = float(match[1]) * factors[match[2]]
    return meters if np.isfinite(meters) and meters > 0 else None


def downsample(content: bytes, media_type: str, ratio: float, target_format: str, target_resolution: float) -> tuple[bytes, str]:
    """Average source values before rendering; retain native TIFF dtype/channels."""
    if media_type == "image/tiff":
        with tifffile.TiffFile(io.BytesIO(content)) as tiff:
            if len(tiff.series) != 1:
                raise ValueError("多组 TIFF 暂不支持降采样，请导出原分辨率")
            series = tiff.series[0]
            array = series.asarray()
            axes = series.axes
        if array.ndim == 3 and axes.startswith('S') and axes.endswith('YX'):
            array = np.moveaxis(array, 0, -1)
        elif not (array.ndim == 2 or (array.ndim == 3 and axes.startswith('YX') and axes[-1] in 'SC')):
            raise ValueError("该 TIFF 的维度无法确定为二维样本，请导出原分辨率")
    else:
        with Image.open(io.BytesIO(content)) as image:
            array = np.asarray(image.convert('RGBA') if image.mode in ('P', 'LA') else image).copy()
    height, width = array.shape[:2]
    size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    def average_axis(values, length, axis):
        values = np.moveaxis(values, axis, 0)
        edges = np.linspace(0, values.shape[0], length + 1)
        indices = np.floor(edges).astype(int)
        fractions = (edges - indices).reshape((-1,) + (1,) * (values.ndim - 1))
        integral = np.concatenate([np.zeros_like(values[:1]), np.cumsum(values, axis=0)], axis=0)
        at_edges = integral[indices] + fractions * values[np.minimum(indices, len(values) - 1)]
        return np.moveaxis(np.diff(at_edges, axis=0) / (values.shape[0] / length), 0, axis)
    values = array.astype(np.complex128 if np.iscomplexobj(array) else np.float64)
    resized = average_axis(average_axis(values, size[0], 1), size[1], 0)
    if np.issubdtype(array.dtype, np.integer):
        bounds = np.iinfo(array.dtype)
        resized = np.clip(np.rint(resized), bounds.min, bounds.max)
    resized = resized.astype(array.dtype)
    output = io.BytesIO()
    output_type = media_type if target_format == 'source' else target_format
    if output_type == 'image/tiff' and target_format == 'source':
        photometric = 'rgb' if resized.ndim == 3 and resized.shape[-1] in (3, 4) else 'minisblack'
        options = {}
        if resized.ndim == 3:
            options['planarconfig'] = 'contig'
            if photometric == 'minisblack':
                options['extrasamples'] = ['unspecified'] * (resized.shape[-1] - 1)
        tifffile.imwrite(output, resized, photometric=photometric, metadata={"resolution_m": target_resolution}, **options)
    else:
        # Use the existing display stretch only after averaging native values.
        from app.api.routes.samples import _display_image
        if np.iscomplexobj(resized):
            resized = np.abs(resized).astype(np.float32)
        if resized.ndim == 3:
            if resized.shape[-1] in (3, 4):
                bands = [_display_image(Image.fromarray(resized[..., c])).convert('L') for c in range(resized.shape[-1])]
                rendered = Image.merge('RGB' if len(bands) == 3 else 'RGBA', bands)
            else:
                rendered = _display_image(Image.fromarray(resized[..., 0]))
        else:
            rendered = _display_image(Image.fromarray(resized))
        if output_type == 'image/tiff':
            rendered.convert('RGB').save(output, format='TIFF', compression='tiff_deflate')
        elif output_type == 'image/jpeg':
            rendered.convert('RGB').save(output, format='JPEG', quality=95)
        else:
            rendered.save(output, format='PNG')
            output_type = 'image/png'
    return output.getvalue(), output_type
