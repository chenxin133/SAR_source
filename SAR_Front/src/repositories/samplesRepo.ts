import JSZip from 'jszip'
import { sampleName, buildSampleXml } from '../utils/sampleMetadata'
import type { SarImage } from '../types/sar'
import { resolutionMeters, EXPORT_RESOLUTIONS } from '../utils/resolution'
import { IdbStore } from './idb'
import type { SarSample } from '../types/samples'
import { getStorageMode } from '../config/storage'
import { samplesApi } from '../services/samplesApi'

type SampleRecord = {
  id: string
  data: SarSample
  updatedAt: number
}

const store = new IdbStore<SampleRecord>('SarSystemDB', 'samples', 4)
const SAMPLES_CHANGED_EVENT = 'sar-samples-changed'

const emitSamplesChanged = () => {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(SAMPLES_CHANGED_EVENT))
}

export const samplesRepo = {
  changedEventName: SAMPLES_CHANGED_EVENT,

  async list(): Promise<SarSample[]> {
    if (getStorageMode() === 'backend') return await samplesApi.list()
    const records = await store.getAll()
    records.sort((a, b) => b.updatedAt - a.updatedAt)
    return records.map((r) => r.data)
  },

  async get(id: string): Promise<SarSample | undefined> {
    if (getStorageMode() === 'backend') return (await samplesApi.list()).find((sample) => sample.id === id)
    const record = await store.get(id)
    return record?.data
  },

  async put(sample: SarSample): Promise<SarSample> {
    if (getStorageMode() === 'backend') {
      const saved = await samplesApi.put(sample)
      emitSamplesChanged()
      return saved
    }
    if (!sample.sequenceNo) {
      const records = await store.getAll()
      sample.sequenceNo = Math.max(0, ...records.map((record) => record.data.sequenceNo || 0)) + 1
    }
    sample.name = sampleName(sample)
    const record: SampleRecord = {
      id: sample.id,
      data: sample,
      updatedAt: Date.now()
    }
    await store.put(record)
    emitSamplesChanged()
    return sample
  },

  async delete(id: string): Promise<void> {
    if (getStorageMode() === 'backend') {
      await samplesApi.delete(id)
      emitSamplesChanged()
      return
    }
    await store.delete(id)
    emitSamplesChanged()
  },

  async exportAllRecords(): Promise<SampleRecord[]> {
    return await store.getAll()
  },

  async deleteByAnnotation(imageId: string, annotationId: string): Promise<void> {
    const matches = (await samplesRepo.list()).filter(
      (sample) => sample.imageId === imageId && sample.annotationId === annotationId
    )
    await Promise.all(matches.map((sample) => samplesRepo.delete(sample.id)))
  },

  async cropFromSource(payload: Parameters<typeof samplesApi.cropFromSource>[0]): Promise<SarSample> {
    if (getStorageMode() !== 'backend') throw new Error('源文件裁切仅适用于后端存储模式')
    const saved = await samplesApi.cropFromSource(payload)
    emitSamplesChanged()
    return saved
  },

  async exportBundle(samples: SarSample[], format: 'source' | 'image/png' | 'image/jpeg' | 'image/tiff', target?: number, sources?: Map<string, SarImage>): Promise<Blob> {
    if (getStorageMode() === 'backend') return samplesApi.exportBundle(samples.map((sample) => sample.id), format, target)
    const archive = new JSZip()
    for (const original of samples) {
      const source = sources?.get(original.imageId)
      const sample = { ...original, resolution: original.resolution || source?.resolution,
        frequencyBand: original.frequencyBand || source?.frequencyBand, sceneMetadata: original.sceneMetadata || source?.sceneMetadata }
      if (!sample.sequenceNo) await samplesRepo.put(sample)
      let image = await samplesRepo.exportBlob(sample, format, target, source?.resolution)
      const output = format === 'source' ? sample.format : format
      if (image.type !== output) {
        if (output === 'image/tiff' || image.type === 'image/tiff') throw new Error('TIFF 转换请使用桌面存储模式')
        const bitmap = await createImageBitmap(image)
        const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height
        const context = canvas.getContext('2d')
        if (!context) throw new Error('无法创建导出画布')
        context.drawImage(bitmap, 0, 0); bitmap.close()
        image = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error('导出失败')), output))
      }
      const extension = output === 'image/tiff' ? '.tif' : output === 'image/jpeg' ? '.jpg' : '.png'
      const filename = sampleName(sample, target) + extension
      const ratio = target != null ? resolutionMeters(sample.resolution)! / target : 1
      archive.file(filename, image)
      archive.file(sampleName(sample, target) + '.xml', buildSampleXml(sample, filename, Math.max(1, Math.round(sample.width * ratio)), Math.max(1, Math.round(sample.height * ratio)), target))
    }
    return archive.generateAsync({ type: 'blob' })
  },

  async exportBlob(sample: SarSample, format: 'source' | 'image/png' | 'image/jpeg' | 'image/tiff', targetResolution?: number, sourceResolution?: string): Promise<Blob> {
    if (getStorageMode() === 'backend' && /^[0-9a-f-]{36}$/i.test(sample.id)) {
      return await samplesApi.exportBlob(sample.id, format, targetResolution)
    }
    if (targetResolution != null) {
      const current = resolutionMeters(sample.resolution || sourceResolution)
      if (!current || !EXPORT_RESOLUTIONS.includes(targetResolution) || targetResolution <= current) throw new Error('目标分辨率必须比已知的样本空间分辨率更粗')
      if (sample.format === 'image/tiff' || format === 'image/tiff') throw new Error('TIFF 降采样请使用桌面后端模式，以保留像素数值')
      const bitmap = await createImageBitmap(sample.image)
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(bitmap.width * current / targetResolution))
      canvas.height = Math.max(1, Math.round(bitmap.height * current / targetResolution))
      const context = canvas.getContext('2d')
      if (!context) throw new Error('无法创建降采样画布')
      context.imageSmoothingEnabled = true
      context.imageSmoothingQuality = 'high'
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      bitmap.close()
      const outputType = format === 'source' ? sample.format : format
      return await new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('降采样失败')), outputType))
    }
    return sample.image
  }
}
