import { IdbStore } from './idb'
import type { AnnotationsFileV1 } from '../types/annotations'

type AnnotationRecord = {
  id: string
  data: AnnotationsFileV1
  updatedAt: number
}

const store = new IdbStore<AnnotationRecord>('SarSystemDB', 'annotations', 4)

export const annotationsRepo = {
  async get(imageId: string): Promise<AnnotationsFileV1 | undefined> {
    const record = await store.get(imageId)
    return record?.data
  },

  async put(payload: AnnotationsFileV1): Promise<void> {
    const record: AnnotationRecord = {
      id: payload.imageId,
      data: payload,
      updatedAt: Date.now()
    }
    await store.put(record)
  },

  async delete(imageId: string): Promise<void> {
    await store.delete(imageId)
  },

  async exportAllRecords(): Promise<AnnotationRecord[]> {
    return await store.getAll()
  }
}
