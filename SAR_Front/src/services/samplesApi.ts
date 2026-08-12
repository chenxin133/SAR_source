import { buildUrl, requestJson } from './http'
import { unwrapEnvelope, type ApiEnvelope } from '../types/backend'
import type { SarSample } from '../types/samples'

type ApiSample = {
  id: string
  image_id: string
  name?: string | null
  category?: string | null
  remark?: string | null
  roi?: Record<string, unknown> | null
  image_url?: string | null
  thumbnail_url?: string | null
  created_at: string
  updated_at: string
}

const fetchBlob = async (url?: string | null) => {
  if (!url) return undefined
  const resp = await fetch(url.startsWith('/') ? url : buildUrl(url))
  if (!resp.ok) throw new Error(`样本图片读取失败：HTTP ${resp.status}`)
  return await resp.blob()
}

const mapSample = async (row: ApiSample): Promise<SarSample> => {
  const roi = row.roi ?? {}
  const image = await fetchBlob(row.image_url)
  if (!image) throw new Error(`样本 ${row.id} 缺少图片文件`)
  const thumbnail = await fetchBlob(row.thumbnail_url).catch(() => undefined)
  return {
    id: row.id,
    name: row.name || row.id,
    imageId: row.image_id,
    imageName: String(roi.imageName ?? ''),
    annotationId: String(roi.annotationId ?? ''),
    annotationType: roi.annotationType === 'polygon' ? 'polygon' : 'rect',
    category: row.category || '',
    remark: row.remark || '',
    format: roi.format === 'image/jpeg' ? 'image/jpeg' : 'image/png',
    width: Number(roi.width ?? 0),
    height: Number(roi.height ?? 0),
    image,
    thumbnail,
    createdAt: new Date(row.created_at).getTime(),
    updatedAt: new Date(row.updated_at).getTime()
  }
}

export const samplesApi = {
  async list(): Promise<SarSample[]> {
    const res = await requestJson<ApiEnvelope<ApiSample[]>>('/samples?limit=200', { method: 'GET' })
    return await Promise.all(unwrapEnvelope(res).map(mapSample))
  },

  async put(sample: SarSample): Promise<SarSample> {
    const form = new FormData()
    form.append('image_id', sample.imageId)
    form.append('name', sample.name)
    form.append('category', sample.category)
    form.append('remark', sample.remark)
    form.append('annotation_id', sample.annotationId)
    form.append('annotation_type', sample.annotationType)
    form.append('image_name', sample.imageName || '')
    form.append('image_format', sample.format)
    form.append('width', String(sample.width))
    form.append('height', String(sample.height))
    if (/^[0-9a-f-]{36}$/i.test(sample.id)) form.append('sample_id', sample.id)
    form.append('image', sample.image, sample.format === 'image/jpeg' ? 'image.jpg' : 'image.png')
    if (sample.thumbnail) form.append('thumbnail', sample.thumbnail, 'thumbnail.png')

    const resp = await fetch(buildUrl('/samples/upload'), { method: 'POST', body: form })
    if (!resp.ok) throw new Error((await resp.text().catch(() => '')) || `HTTP ${resp.status}`)
    const row = unwrapEnvelope((await resp.json()) as ApiEnvelope<ApiSample>)
    return await mapSample(row)
  },

  async delete(id: string): Promise<void> {
    await requestJson<ApiEnvelope<unknown>>(`/samples/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }
}
