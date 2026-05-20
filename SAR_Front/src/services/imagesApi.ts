import { buildUrl, requestJson } from './http'
import type {
  ApiEnvelope,
  ApiImageOut,
  ApiThumbnailOut,
  ApiUploadCompleteResponse,
  ApiUploadInitResponse
} from '../types/backend'
import { unwrapEnvelope } from '../types/backend'

export const imagesApi = {
  async list(params?: { limit?: number; offset?: number }): Promise<ApiImageOut[]> {
    const q = new URLSearchParams()
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.offset != null) q.set('offset', String(params.offset))
    const suffix = q.toString() ? `?${q.toString()}` : ''
    const res = await requestJson<ApiEnvelope<ApiImageOut[]>>(`/images${suffix}`, { method: 'GET' })
    return unwrapEnvelope(res)
  },

  async getDetail(imageId: string): Promise<{ image: ApiImageOut; thumbnails: ApiThumbnailOut[] }> {
    const res = await requestJson<ApiEnvelope<any>>(`/images/${encodeURIComponent(imageId)}`, { method: 'GET' })
    const data = unwrapEnvelope(res) as any
    return { image: data as ApiImageOut, thumbnails: (data?.thumbnails ?? []) as ApiThumbnailOut[] }
  },

  async getThumbnails(imageId: string): Promise<ApiThumbnailOut[]> {
    const res = await requestJson<ApiEnvelope<ApiThumbnailOut[]>>(`/images/${encodeURIComponent(imageId)}/thumbnails`, {
      method: 'GET'
    })
    return unwrapEnvelope(res)
  },

  async delete(imageId: string): Promise<void> {
    await requestJson<ApiEnvelope<unknown>>(`/images/${encodeURIComponent(imageId)}`, { method: 'DELETE' })
  },

  async uploadInit(payload: { filename: string; total_size: number }): Promise<ApiUploadInitResponse> {
    const res = await requestJson<ApiEnvelope<ApiUploadInitResponse>>('/images/upload/init', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    return unwrapEnvelope(res)
  },

  async uploadPart(uploadId: string, partNo: number, chunk: Blob): Promise<{ stored_bytes: number }> {
    const res = await requestJson<ApiEnvelope<{ stored_bytes: number }>>(
      `/images/upload/${encodeURIComponent(uploadId)}/part/${encodeURIComponent(String(partNo))}`,
      {
        method: 'PUT',
        body: chunk
      }
    )
    return unwrapEnvelope(res)
  },

  async uploadComplete(payload: {
    upload_id: string
    total_parts: number
    name?: string
    mime_type?: string
    satellite?: string
    acquisition_at?: string
    resolution?: string
    polarization?: string
    description?: string
  }): Promise<ApiUploadCompleteResponse> {
    const res = await requestJson<ApiEnvelope<ApiUploadCompleteResponse>>(
      `/images/upload/${encodeURIComponent(payload.upload_id)}/complete`,
      {
        method: 'POST',
        body: JSON.stringify({
          total_parts: payload.total_parts,
          name: payload.name,
          mime_type: payload.mime_type,
          satellite: payload.satellite,
          acquisition_at: payload.acquisition_at,
          resolution: payload.resolution,
          polarization: payload.polarization,
          description: payload.description
        })
      }
    )
    return unwrapEnvelope(res)
  },

  async process(imageId: string): Promise<{ task_id: string }> {
    const res = await requestJson<ApiEnvelope<{ task_id: string }>>(`/images/${encodeURIComponent(imageId)}/process`, {
      method: 'POST'
    })
    return unwrapEnvelope(res)
  },

  buildTaskStreamUrl(taskId: string): string {
    return buildUrl(`/tasks/stream/${encodeURIComponent(taskId)}`)
  }
}
