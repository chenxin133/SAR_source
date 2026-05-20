export type ApiEnvelope<T> = T | { data: T }

export const unwrapEnvelope = <T>(value: ApiEnvelope<T>): T => {
  if (value && typeof value === 'object' && 'data' in (value as any)) {
    return (value as any).data as T
  }
  return value as T
}

export type ApiImageOut = {
  id: string
  name: string
  size_bytes: number
  mime_type?: string | null
  satellite?: string | null
  acquisition_at?: string | null
  resolution?: string | null
  polarization?: string | null
  description?: string | null
  width?: number | null
  height?: number | null
  status: string
  created_at: string
  updated_at: string
}

export type ApiThumbnailOut = {
  id: string
  purpose: string
  level: number
  format: string
  quality?: number | null
  width?: number | null
  height?: number | null
  size_bytes?: number | null
  url?: string | null
}

export type ApiUploadInitResponse = {
  upload_id: string
  part_size: number
}

export type ApiUploadCompleteResponse = {
  image_id: string
}

export type ApiTaskOut = {
  id: string
  type: string
  status: string
  progress: number
  error_message?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  result?: Record<string, unknown> | null
}
