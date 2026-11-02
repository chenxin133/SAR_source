export type SceneMetadata = {
  name: string
  data_source: string
  satellite: string
  frequency_band: string
  polarization: string
  acquisition_at: string
  imaging_start: string
  imaging_end: string
  time_reference: string
  resolution: string
  region: string
  category: string
  image_filename: string
  width: number | null
  height: number | null
  coordinates: Record<string, { longitude: number; latitude: number }>
  [key: string]: unknown
}

export type XmlAttachment = { file: File; base64: string; metadata: SceneMetadata }
