import type { SarImage, UploadPayload } from '../types/sar'
import { buildUrl, requestJson } from './http'

type ApiEnvelope<T> = T | { data: T }

const unwrap = <T>(value: ApiEnvelope<T>): T => {
  if (value && typeof value === 'object' && 'data' in (value as any)) {
    return (value as any).data as T
  }
  return value as T
}

export const listRawImages = async (): Promise<SarImage[]> => {
  const res = await requestJson<ApiEnvelope<SarImage[]>>('/raw-images', { method: 'GET' })
  return unwrap(res)
}

export const deleteRawImage = async (id: string): Promise<void> => {
  const url = `/raw-images/${encodeURIComponent(id)}`
  await requestJson<ApiEnvelope<unknown>>(url, { method: 'DELETE' })
}

export const uploadRawImage = (payload: UploadPayload, onProgress?: (percent: number) => void): Promise<SarImage> => {
  const url = buildUrl('/raw-images')
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.responseType = 'text'

    xhr.upload.onprogress = (evt) => {
      if (!onProgress) return
      if (!evt.lengthComputable) return
      const percent = Math.round((evt.loaded / evt.total) * 100)
      onProgress(Math.max(0, Math.min(100, percent)))
    }

    xhr.onload = () => {
      try {
        const text = xhr.responseText || ''

        if (xhr.status < 200 || xhr.status >= 300) {
          let message: string = xhr.statusText || `HTTP ${xhr.status}`
          try {
            const parsed = text ? JSON.parse(text) : null
            message =
              (parsed && typeof parsed === 'object' && (parsed as any).message) ||
              (parsed && typeof parsed === 'object' && (parsed as any).detail) ||
              message
          } catch {}
          if (!message && text) message = text
          reject(new Error(String(message)))
          return
        }

        const raw = (text ? (JSON.parse(text) as ApiEnvelope<SarImage>) : ({} as ApiEnvelope<SarImage>))
        resolve(unwrap(raw))
      } catch (e) {
        reject(e)
      }
    }

    xhr.onerror = () => reject(new Error('网络错误'))

    const form = new FormData()
    form.append('file', payload.file)
    form.append('name', payload.name)
    form.append('satellite', payload.satellite)
    if (payload.resolution) form.append('resolution', payload.resolution)
    if (payload.frequencyBand) form.append('frequency_band', payload.frequencyBand)
    if (payload.polarization) form.append('polarization', payload.polarization)
    if (payload.description) form.append('description', payload.description)

    xhr.send(form)
  })
}

export const getRawImageFileUrl = (id: string) => buildUrl(`/raw-images/${encodeURIComponent(id)}/file`)
