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

  async exportBlob(sample: SarSample, format: 'source' | 'image/png' | 'image/jpeg' | 'image/tiff'): Promise<Blob> {
    if (getStorageMode() === 'backend' && /^[0-9a-f-]{36}$/i.test(sample.id)) {
      return await samplesApi.exportBlob(sample.id, format)
    }
    return sample.image
  }
}
