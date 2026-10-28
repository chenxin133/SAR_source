import type { SarImage, UploadPayload } from '../types/sar'
import { IdbStore } from './idb'

type RawImageRecord = {
  id: string
  metadata: Omit<SarImage, 'previewUrl' | 'thumbnailUrl'>
  file?: Blob
  preview?: Blob
  thumbnail?: Blob
  createdAt: number
}

const store = new IdbStore<RawImageRecord>('SarSystemDB', 'raw_images', 4)
const sessionBigFileCache = new Map<string, File>()
const MAX_STORE_BYTES = 200 * 1024 * 1024
const PREVIEW_SIZE = 1536

const isTiffName = (name?: string) => {
  if (!name) return false
  const n = name.toLowerCase()
  return n.endsWith('.tif') || n.endsWith('.tiff')
}

const isRasterPreviewable = (file: File) => file.type.startsWith('image/') || isTiffName(file.name)

const canvasToBlob = (canvas: HTMLCanvasElement, type = 'image/png', quality?: number) => {
  return new Promise<Blob>((resolve) => {
    canvas.toBlob((b) => resolve(b ?? new Blob()), type, quality)
  })
}

const downscaleCanvas = (src: HTMLCanvasElement, maxSize = 256) => {
  const w = src.width
  const h = src.height
  const scale = Math.min(1, maxSize / Math.max(w, h))
  const tw = Math.max(1, Math.round(w * scale))
  const th = Math.max(1, Math.round(h * scale))
  const canvas = document.createElement('canvas')
  canvas.width = tw
  canvas.height = th
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.drawImage(src, 0, 0, tw, th)
  return canvas
}

const readFileToArrayBuffer = async (file: File): Promise<ArrayBuffer> => {
  try {
    return await file.arrayBuffer()
  } catch (e: any) {
    return await new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = () => reject(reader.error ?? e)
      reader.onload = () => resolve(reader.result as ArrayBuffer)
      reader.readAsArrayBuffer(file)
    })
  }
}

const ensureGeoTiff = async () => {
  const w = window as any
  if (w.GeoTIFF?.fromBlob) return w.GeoTIFF
  try {
    const mod = await import('geotiff')
    if (typeof (mod as any).fromBlob === 'function') return mod as any
    if (typeof (mod as any).default?.fromBlob === 'function') return (mod as any).default
    throw new Error('geotiff 未导出 fromBlob')
  } catch {
    throw new Error('GeoTIFF 依赖未安装：请先执行 npm install 安装 geotiff/ol 相关依赖')
  }
}

const computePercentileRange = (raster: any, len: number, noData?: number) => {
  const sampleCount = Math.min(200000, len)
  const step = Math.max(1, Math.floor(len / sampleCount))
  const values: number[] = []
  for (let i = 0; i < len; i += step) {
    const v = raster[i]
    if (noData != null && Number.isFinite(noData) && v === noData) continue
    if (Number.isFinite(v)) values.push(v)
  }
  if (values.length === 0) return { min: 0, max: 1 }
  values.sort((a, b) => a - b)
  const lo = values[Math.floor(values.length * 0.02)] ?? values[0]
  const hi = values[Math.floor(values.length * 0.98)] ?? values[values.length - 1]
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { min: 0, max: 1 }
  if (hi <= lo) return { min: lo, max: lo + 1 }
  return { min: lo, max: hi }
}

const stretchValue = (v: number, min: number, max: number, useLog: boolean) => {
  if (!Number.isFinite(v)) return 0
  let x = (v - min) / (max - min)
  x = Math.max(0, Math.min(1, x))
  if (useLog) x = Math.log1p(9 * x) / Math.log1p(9)
  return Math.max(0, Math.min(255, Math.round(x * 255)))
}

const rasterToCanvas = (
  raster: any,
  width: number,
  height: number,
  samplesPerPixel: number,
  opts?: { noData?: number; forceLog?: boolean }
) => {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas

  const imgData = ctx.createImageData(width, height)
  const data = imgData.data

  const len = width * height
  if (samplesPerPixel >= 3) {
    for (let i = 0; i < len; i++) {
      const r = raster[i * samplesPerPixel + 0] ?? 0
      const g = raster[i * samplesPerPixel + 1] ?? 0
      const b = raster[i * samplesPerPixel + 2] ?? 0
      data[i * 4 + 0] = r & 0xff
      data[i * 4 + 1] = g & 0xff
      data[i * 4 + 2] = b & 0xff
      data[i * 4 + 3] = 255
    }
  } else {
    const noData = opts?.noData
    const { min, max } = computePercentileRange(raster, len, noData)
    const useLog = !!opts?.forceLog || (max > 0 && min >= 0 && max / Math.max(min, 1e-9) > 100)
    for (let i = 0; i < len; i++) {
      const v = raster[i] ?? 0
      if (!Number.isFinite(v) || (noData != null && Number.isFinite(noData) && v === noData)) {
        data[i * 4 + 0] = 0
        data[i * 4 + 1] = 0
        data[i * 4 + 2] = 0
        data[i * 4 + 3] = 0
        continue
      }
      const c = stretchValue(v, min, max, useLog)
      data[i * 4 + 0] = c
      data[i * 4 + 1] = c
      data[i * 4 + 2] = c
      data[i * 4 + 3] = 255
    }
  }

  ctx.putImageData(imgData, 0, 0)
  return canvas
}

const buildTiffPreviewCanvasWithGeoTiff = async (file: File, maxSize = PREVIEW_SIZE): Promise<HTMLCanvasElement> => {
  const GeoTIFF = await ensureGeoTiff()
  const tiff = await GeoTIFF.fromBlob(file)
  const image0 = await tiff.getImage(0)
  const width0 = image0.getWidth()
  const height0 = image0.getHeight()
  const spp0 = image0.getSamplesPerPixel?.() ?? 1
  const noDataRaw = image0.getGDALNoData?.()
  const noData = Number.isFinite(Number(noDataRaw)) ? Number(noDataRaw) : undefined
  const scale = Math.min(1, maxSize / Math.max(width0, height0))
  const tw = Math.max(1, Math.round(width0 * scale))
  const th = Math.max(1, Math.round(height0 * scale))
  const samples = spp0 >= 3 ? [0, 1, 2] : [0]

  let result: any
  try {
    result = await tiff.readRGB({ width: tw, height: th })
  } catch {
    try {
      result = await tiff.readRasters({ width: tw, height: th, samples, interleave: true })
    } catch {
      const fw = Math.max(1, Math.min(512, width0))
      const fh = Math.max(1, Math.min(512, height0))
      result = await image0.readRasters({ width: fw, height: fh, samples, interleave: true })
      const raster = (result && typeof result === 'object' && 0 in result) ? (result as any)[0] : result
      return rasterToCanvas(raster, fw, fh, samples.length, { noData, forceLog: true })
    }
  }

  const raster = (result && typeof result === 'object' && 0 in result) ? (result as any)[0] : result
  const isRgb = raster && (raster.length === tw * th * 3 || raster.length === tw * th * 4)
  return rasterToCanvas(raster, tw, th, isRgb ? 3 : samples.length, { noData, forceLog: spp0 < 3 })
}

const buildTiffPreviewAndThumbnail = async (file: File): Promise<{ preview?: Blob; thumbnail?: Blob }> => {
  const previewCanvas = await buildTiffPreviewCanvasWithGeoTiff(file, PREVIEW_SIZE)
  const preview = await canvasToBlob(previewCanvas, 'image/webp', 0.86)
  const thumbnailCanvas = downscaleCanvas(previewCanvas, 256)
  const thumbnail = await canvasToBlob(thumbnailCanvas, 'image/webp', 0.82)
  return { preview, thumbnail }
}

const buildPreviewAndThumbnail = async (file: File): Promise<{ preview?: Blob; thumbnail?: Blob } | undefined> => {
  if (!isRasterPreviewable(file)) return undefined
  if (isTiffName(file.name)) {
    return await buildTiffPreviewAndThumbnail(file)
  }

  const bmp = await createImageBitmap(file)
  const canvas = document.createElement('canvas')
  const scalePreview = Math.min(1, PREVIEW_SIZE / Math.max(bmp.width, bmp.height))
  canvas.width = Math.max(1, Math.round(bmp.width * scalePreview))
  canvas.height = Math.max(1, Math.round(bmp.height * scalePreview))
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height)
  bmp.close()
  const preview = await canvasToBlob(canvas, 'image/webp', 0.86)
  const thumbnailCanvas = downscaleCanvas(canvas, 256)
  const thumbnail = await canvasToBlob(thumbnailCanvas, 'image/webp', 0.82)
  return { preview, thumbnail }
}

export const rawImagesRepo = {
  async update(id: string, patch: import('../types/sar').ImageMetadataPatch) {
    const record = await store.get(id)
    if (!record) throw new Error('影像不存在')
    record.metadata = { ...record.metadata, ...patch }
    await store.put(record)
    return patch
  },
  async list(): Promise<SarImage[]> {
    const records = await store.getAll()
    records.sort((a, b) => b.createdAt - a.createdAt)

    return records.map((r) => {
      const img: SarImage = { ...(r.metadata as any) }
      if (r.thumbnail) img.thumbnailUrl = URL.createObjectURL(r.thumbnail)
      if (r.preview) {
        img.previewUrl = URL.createObjectURL(r.preview)
      } else if (r.file && r.file.type.startsWith('image/') && !isTiffName(r.metadata.name)) {
        img.previewUrl = URL.createObjectURL(r.file)
      }
      return img
    })
  },

  async create(payload: UploadPayload, onProgress?: (percent: number) => void): Promise<SarImage> {
    const now = Date.now()
    const id = `IMG_${now}`
    const file = payload.file
    const metadata: Omit<SarImage, 'previewUrl' | 'thumbnailUrl'> = {
      id,
      name: payload.name || file.name,
      satellite: payload.satellite,
      acquisitionDate: payload.acquisitionAt || '',
      fileSize: (file.size / (1024 * 1024)).toFixed(2) + ' MB',
      sizeBytes: file.size,
      resolution: payload.resolution || '',
      frequencyBand: payload.frequencyBand || '',
      polarization: payload.polarization || '',
      status: 'Ready',
      description: payload.description || ''
    }

    if (onProgress) onProgress(10)
    const previewPair = await buildPreviewAndThumbnail(file).catch(() => undefined)
    const preview = previewPair?.preview
    const thumbnail = previewPair?.thumbnail
    if (onProgress) onProgress(80)

    let storedFile: Blob | undefined = file
    let originalPersistent = true
    let previewPersistent = !!preview
    let previewNotice = ''
    if (file.size > MAX_STORE_BYTES) {
      storedFile = undefined
      sessionBigFileCache.set(id, file)
      originalPersistent = false
      previewPersistent = !!preview
      previewNotice = preview
        ? '原图超过 200MB，仅当前会话可用；已持久化中等质量预览图。'
        : '原图超过 200MB，仅当前会话可用；当前未生成持久化预览图。'
    } else if (isTiffName(file.name)) {
      try {
        const buf = await readFileToArrayBuffer(file)
        storedFile = new Blob([buf], { type: 'image/tiff' })
      } catch (e: any) {
        const name = e?.name || ''
        if (name === 'NotReadableError') {
          throw new Error('无法读取该 TIFF 文件（可能被其他程序占用或权限不足），请关闭占用程序或复制到本地后重试')
        }
        throw e
      }
    }
    metadata.originalPersistent = originalPersistent
    metadata.previewPersistent = previewPersistent
    metadata.previewNotice = previewNotice || undefined

    const record: RawImageRecord = {
      id,
      metadata,
      file: storedFile,
      preview,
      thumbnail,
      createdAt: now
    }
    await store.put(record)
    if (onProgress) onProgress(100)

    const result: SarImage = { ...(metadata as any) }
    if (thumbnail) result.thumbnailUrl = URL.createObjectURL(thumbnail)
    if (preview) {
      result.previewUrl = URL.createObjectURL(preview)
    } else if (file.type.startsWith('image/') && !isTiffName(file.name)) {
      result.previewUrl = URL.createObjectURL(file)
    }
    return result
  },

  async delete(id: string): Promise<void> {
    sessionBigFileCache.delete(id)
    await store.delete(id)
  },

  async getFile(id: string): Promise<Blob | undefined> {
    const record = await store.get(id)
    return record?.file ?? sessionBigFileCache.get(id)
  },

  async getThumbnail(id: string): Promise<Blob | undefined> {
    const record = await store.get(id)
    return record?.thumbnail
  },

  async exportAllRecords(): Promise<RawImageRecord[]> {
    return await store.getAll()
  }
}
