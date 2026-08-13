import type { AnnotationType } from './annotations'

export type SarSample = {
  id: string
  name: string
  imageId: string
  imageName?: string
  annotationId: string
  annotationType: AnnotationType
  category: string
  remark: string
  format: 'image/png' | 'image/jpeg' | 'image/tiff'
  width: number
  height: number
  image: Blob
  thumbnail?: Blob
  createdAt: number
  updatedAt: number
}
