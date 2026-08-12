import { requestJson } from './http'
import { unwrapEnvelope, type ApiEnvelope } from '../types/backend'
import type { AnnotationsFileV1 } from '../types/annotations'

type ApiAnnotation = {
  id: string
  image_id?: string | null
  type: string
  payload: AnnotationsFileV1
}

export const annotationsApi = {
  async get(imageId: string): Promise<AnnotationsFileV1 | undefined> {
    const params = new URLSearchParams({ image_id: imageId, limit: '200' })
    const res = await requestJson<ApiEnvelope<ApiAnnotation[]>>(`/annotations?${params}`, { method: 'GET' })
    const rows = unwrapEnvelope(res)
    return rows.find((row) => row.type === 'annotations_v1')?.payload
  },

  async put(payload: AnnotationsFileV1): Promise<void> {
    await requestJson<ApiEnvelope<ApiAnnotation>>(`/annotations/image/${encodeURIComponent(payload.imageId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
  }
}
