export type AnnotationType = 'rect' | 'polygon'

export type XY = {
  x: number
  y: number
}

export type RectShape = {
  x: number
  y: number
  w: number
  h: number
}

export type BaseAnnotation = {
  id: string
  type: AnnotationType
  category: string
  remark: string
  createdAt: number
  updatedAt: number
}

export type RectAnnotation = BaseAnnotation & {
  type: 'rect'
  rect: RectShape
  points?: XY[]
}

export type PolygonAnnotation = BaseAnnotation & {
  type: 'polygon'
  points: XY[]
}

export type SarAnnotation = RectAnnotation | PolygonAnnotation

export type AnnotationsFileV1 = {
  version: 1
  imageId: string
  exportedAt: number
  coordinateWidth?: number
  coordinateHeight?: number
  annotations: SarAnnotation[]
}
