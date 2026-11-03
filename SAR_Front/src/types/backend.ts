export type ApiEnvelope<T> = T | { data: T }

export const unwrapEnvelope = <T>(value: ApiEnvelope<T>): T => {
  if (value && typeof value === 'object' && 'data' in (value as any)) {
    return (value as any).data as T
  }
  return value as T
}

export type ApiImageOut = {
  metadata_xml_url?: string | null
  metadata_xml_filename?: string | null
  scene_metadata?: import('./metadata').SceneMetadata | null
  id: string
  name: string
  size_bytes: number
  mime_type?: string | null
  satellite?: string | null
  acquisition_at?: string | null
  resolution?: string | null
  frequency_band?: string | null
  polarization?: string | null
  description?: string | null
  width?: number | null
  height?: number | null
  status: string
  error_message?: string | null
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
  upload_id?: string | null
  part_size?: number | null
  image_id?: string | null
  reused?: boolean
  updated?: boolean
  duplicate_action?: import('../utils/duplicateImport').DuplicateAction
}

export type ApiUploadCompleteResponse = {
  reused?: boolean
  updated?: boolean
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
