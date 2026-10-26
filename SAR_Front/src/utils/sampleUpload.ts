import type { SarSample } from '../types/samples'

export const SAMPLE_UPLOAD_ACCEPT = '.png,.jpg,.jpeg,.webp,.tif,.tiff'
export const isAllowedSampleFile = (file: File) => /\.(png|jpe?g|webp|tiff?)$/i.test(file.name)

const canvasBlob = (canvas: HTMLCanvasElement) => new Promise<Blob>((resolve, reject) => {
  canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('无法生成样本预览')), 'image/png')
})

export async function buildLocalSampleImage(file: File): Promise<Pick<SarSample, 'image' | 'thumbnail' | 'width' | 'height' | 'format'>> {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建样本画布')
  let width: number
  let height: number
  let image: Blob
  let format: SarSample['format']
  if (/\.tiff?$/i.test(file.name)) {
    const { fromBlob } = await import('geotiff')
    const tiff = await fromBlob(file)
    const first = await tiff.getImage(0)
    width = first.getWidth()
    height = first.getHeight()
    const scale = Math.min(1, 256 / Math.max(width, height))
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const options = { width: canvas.width, height: canvas.height, interleave: true }
    const rgb = first.getFileDirectory().PhotometricInterpretation === 2
    const raster = (rgb ? await first.readRGB(options) : await first.readRasters({ ...options, samples: [0] })) as unknown as ArrayLike<number>
    const pixels = ctx.createImageData(canvas.width, canvas.height)
    // Stretch only the preview; the original TIFF (including precision and tags) is kept byte for byte.
    const values = rgb ? [] : Array.from(raster).filter(Number.isFinite).sort((a, b) => a - b)
    const low = values[Math.floor(values.length * 0.02)] ?? 0
    const high = values[Math.floor(values.length * 0.98)] ?? low
    for (let i = 0; i < canvas.width * canvas.height; i++) {
      const value = raster[i] ?? 0
      const gray = !Number.isFinite(value) ? 0 : high > low ? Math.round(255 * Math.max(0, Math.min(1, (value - low) / (high - low)))) : value === 0 ? 0 : 192
      pixels.data[i * 4] = rgb ? raster[i * 3] ?? 0 : gray
      pixels.data[i * 4 + 1] = rgb ? raster[i * 3 + 1] ?? 0 : gray
      pixels.data[i * 4 + 2] = rgb ? raster[i * 3 + 2] ?? 0 : gray
      pixels.data[i * 4 + 3] = 255
    }
    ctx.putImageData(pixels, 0, 0)
    format = 'image/tiff'
    image = file.slice(0, file.size, format)
  } else {
    const bitmap = await createImageBitmap(file)
    width = bitmap.width
    height = bitmap.height
    canvas.width = width
    canvas.height = height
    try { ctx.drawImage(bitmap, 0, 0) } finally { bitmap.close() }
    format = /\.jpe?g$/i.test(file.name) ? 'image/jpeg' : 'image/png'
    image = format === 'image/jpeg' ? file.slice(0, file.size, format) : await canvasBlob(canvas)
  }
  const thumbnail = document.createElement('canvas')
  const scale = Math.min(1, 256 / Math.max(canvas.width, canvas.height))
  thumbnail.width = Math.max(1, Math.round(canvas.width * scale))
  thumbnail.height = Math.max(1, Math.round(canvas.height * scale))
  const thumbContext = thumbnail.getContext('2d')
  if (!thumbContext) throw new Error('无法创建样本缩略图')
  thumbContext.drawImage(canvas, 0, 0, thumbnail.width, thumbnail.height)
  return { image, thumbnail: await canvasBlob(thumbnail), width, height, format }
}
