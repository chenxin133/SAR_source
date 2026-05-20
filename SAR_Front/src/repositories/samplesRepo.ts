import { IdbStore } from './idb'
import type { SarSample } from '../types/samples'

type SampleRecord = {
  id: string
  data: SarSample
  updatedAt: number
}

const store = new IdbStore<SampleRecord>('SarSystemDB', 'samples', 4)

export const samplesRepo = {
  async list(): Promise<SarSample[]> {
    const records = await store.getAll()
    records.sort((a, b) => b.updatedAt - a.updatedAt)
    return records.map((r) => r.data)
  },

  async get(id: string): Promise<SarSample | undefined> {
    const record = await store.get(id)
    return record?.data
  },

  async put(sample: SarSample): Promise<void> {
    const record: SampleRecord = {
      id: sample.id,
      data: sample,
      updatedAt: Date.now()
    }
    await store.put(record)
  },

  async delete(id: string): Promise<void> {
    await store.delete(id)
  },

  async exportAllRecords(): Promise<SampleRecord[]> {
    return await store.getAll()
  }
}
