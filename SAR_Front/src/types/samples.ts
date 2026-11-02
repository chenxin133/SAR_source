import type { AnnotationType } from './annotations'

export type SarSample = {
  id: string
  name: string
  imageId: string
  imageName?: string
  annotationId: string
  annotationType: AnnotationType
  category: string
  frequencyBand?: string
  sequenceNo?: number
  metadataXmlUrl?: string
  metadataXmlFile?: File
  sceneMetadata?: import('./metadata').SceneMetadata
  resolution?: string
  remark: string
  format: 'image/png' | 'image/jpeg' | 'image/tiff'
  width: number
  height: number
  image: Blob
  thumbnail?: Blob
  createdAt: number
  updatedAt: number
}
