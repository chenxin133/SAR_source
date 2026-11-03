"""Reject complex single-look rasters before previewing them as amplitude images."""
import tifffile


class UnsupportedSingleLookError(ValueError):
    pass


def validate_raster_product(path: str) -> None:
    try:
        with tifffile.TiffFile(path) as tif:
            if not tif.pages:
                return
            page = tif.pages[0]
            single_look = page.dtype.kind == 'c' or (page.samplesperpixel == 2 and page.dtype.kind == 'i')
    except (OSError, ValueError):
        return  # Other readers handle non-TIFF files and malformed TIFFs.
    if single_look:
        raise UnsupportedSingleLookError('不支持上传单视产品')
