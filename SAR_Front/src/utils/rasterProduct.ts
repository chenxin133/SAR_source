// Read TIFF tags only; never decode or load the full source raster here.
export const validateRasterProduct = async (file: Blob): Promise<void> => {
  const header = new Uint8Array(await file.slice(0, 4).arrayBuffer())
  if (!((header[0] === 73 && header[1] === 73 && [42, 43].includes(header[2]!)) ||
    (header[0] === 77 && header[1] === 77 && [42, 43].includes(header[3]!)))) return
  let singleLook = false
  try {
    const { fromBlob } = await import('geotiff')
    const tiff = await fromBlob(file)
    const image = await tiff.getImage()
    const format = image.getSampleFormat()
    singleLook = format === 5 || format === 6 || (image.getSamplesPerPixel() === 2 && format === 2)
  } catch { return } // Preserve the existing server-side format validation.
  if (singleLook) throw new Error('不支持上传单视产品')
}
