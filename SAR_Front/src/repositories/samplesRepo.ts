import { IdbStore } from './idb'
import type { SarSample } from '../types/samples'

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
    emitSamplesChanged()
  },

  async delete(id: string): Promise<void> {
    await store.delete(id)
    emitSamplesChanged()
  },

  async exportAllRecords(): Promise<SampleRecord[]> {
    return await store.getAll()
  }
}
