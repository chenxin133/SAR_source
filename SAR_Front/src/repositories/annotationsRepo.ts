import { IdbStore } from './idb'
import type { AnnotationsFileV1 } from '../types/annotations'
import { getStorageMode } from '../config/storage'
import { annotationsApi } from '../services/annotationsApi'

type AnnotationRecord = {
  id: string
  data: AnnotationsFileV1
  updatedAt: number
}

const store = new IdbStore<AnnotationRecord>('SarSystemDB', 'annotations', 4)

export const annotationsRepo = {
  async get(imageId: string): Promise<AnnotationsFileV1 | undefined> {
    if (getStorageMode() === 'backend') return await annotationsApi.get(imageId)
    const record = await store.get(imageId)
    return record?.data
  },

  async put(payload: AnnotationsFileV1): Promise<void> {
    if (getStorageMode() === 'backend') return await annotationsApi.put(payload)
    const record: AnnotationRecord = {
      id: payload.imageId,
      data: payload,
      updatedAt: Date.now()
    }
    await store.put(record)
  },

  async delete(imageId: string): Promise<void> {
    if (getStorageMode() === 'backend') {
      await annotationsApi.put({ version: 1, imageId, exportedAt: Date.now(), annotations: [] })
      return
    }
    await store.delete(imageId)
  },

  async exportAllRecords(): Promise<AnnotationRecord[]> {
    return await store.getAll()
  }
}
