import { afterEach, expect, it, vi } from 'vitest'
import { samplesApi } from '../samplesApi'
vi.mock('../importPreflight', () => ({ importPreflight: async () => ({ action: 'ask', existing: null }) }))
import type { SarSample } from '../../types/samples'
import { requestJson } from '../http'

vi.mock('../http', () => ({ buildUrl: (path: string) => path, requestJson: vi.fn() }))
afterEach(() => { vi.unstubAllGlobals(); vi.mocked(requestJson).mockReset() })

it('omits an empty source image and maps a null source after saving', async () => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: {
    id: 'sample-id', image_id: null, name: 'independent', roi: { annotationId: 'manual:one', format: 'image/tiff' },
    image_url: '/sample.tif', created_at: '2026-10-28T00:00:00Z', updated_at: '2026-10-28T00:00:00Z'
  } })
  const fetch = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['original']) })
  vi.stubGlobal('fetch', fetch)
  const sample: SarSample = { id: 'one', name: 'independent', imageId: '', imageName: '', annotationId: 'manual:one',
    annotationType: 'rect', category: '', remark: '', format: 'image/tiff', width: 10, height: 8,
    image: new Blob(['original']), createdAt: 0, updatedAt: 0 }
  const saved = await samplesApi.put(sample)
  const body = vi.mocked(requestJson).mock.calls[0]![1]!.body as FormData
  expect(body.has('image_id')).toBe(false)
  expect(body.get('image_format')).toBe('image/tiff')
  expect(saved.imageId).toBe('')
  expect(saved.format).toBe('image/tiff')
})

const apiRow = (id: string, format = 'image/tiff') => ({ id, image_id: null, name: id, category: 'AIRCRAFT', resolution: '0.5m',
  roi: { format, width: 512, height: 512 }, image_url: `/original/${id}`, thumbnail_url: `/thumbnail/${id}`,
  created_at: '2026-11-03T00:00:00Z', updated_at: '2026-11-03T00:00:00Z' })

it('lists 188 samples using metadata only, including records with missing files', async () => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: [...Array.from({ length: 187 }, (_, i) => apiRow(String(i))), { ...apiRow('missing'), image_url: null }] })
  const fetch = vi.fn().mockRejectedValue(new Error('List must not download sample images'))
  vi.stubGlobal('fetch', fetch)
  const rows = await samplesApi.list()
  expect(rows).toHaveLength(188)
  expect(rows[0]).toMatchObject({ id: '0', imageUrl: '/original/0', thumbnailUrl: '/thumbnail/0', width: 512 })
  expect(rows[0]).not.toHaveProperty('image')
  expect(fetch).not.toHaveBeenCalled()
  expect(requestJson).toHaveBeenCalledExactlyOnceWith('/samples?limit=200&offset=0', { method: 'GET' })
})

it('retrieves all metadata pages without requesting original images or thumbnails', async () => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: Array.from({ length: 200 }, (_, i) => apiRow(String(i))) }).mockResolvedValueOnce({ data: [apiRow('last')] })
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  expect(await samplesApi.list()).toHaveLength(201)
  expect(vi.mocked(requestJson).mock.calls.map(call => call[0])).toEqual(['/samples?limit=200&offset=0', '/samples?limit=200&offset=200'])
  expect(fetch).not.toHaveBeenCalled()
})

it('gets only the requested sample rather than loading the entire library', async () => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: apiRow('chosen') })
  const fetch = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['pixels']) }); vi.stubGlobal('fetch', fetch)
  expect((await samplesApi.get('chosen'))?.image.size).toBe(6)
  expect(requestJson).toHaveBeenCalledExactlyOnceWith('/samples/chosen')
  expect(fetch.mock.calls.map(call => call[0])).toEqual(['/original/chosen', '/thumbnail/chosen'])
})

it.each(['image/tiff', 'image/jpeg', 'image/png'])('downloads only the selected %s preview and keeps PNG polygon transparency', async format => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: apiRow('chosen', format) })
  const fetch = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['preview']) }); vi.stubGlobal('fetch', fetch)
  await samplesApi.previewImage('chosen')
  expect(requestJson).toHaveBeenCalledExactlyOnceWith('/samples/chosen')
  expect(fetch).toHaveBeenCalledExactlyOnceWith(format === 'image/png' ? '/original/chosen' : '/thumbnail/chosen')
})

it('reports a missing preview only when that sample is opened', async () => {
  vi.mocked(requestJson).mockResolvedValueOnce({ data: apiRow('broken') })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
  await expect(samplesApi.previewImage('broken')).rejects.toThrow('样本图片读取失败：HTTP 404')
})

it('returns undefined for a deleted sample and preserves other server failures', async () => {
  vi.mocked(requestJson).mockRejectedValueOnce({ status: 404 }).mockRejectedValueOnce(new Error('backend unavailable'))
  expect(await samplesApi.get('deleted')).toBeUndefined()
  await expect(samplesApi.get('failed')).rejects.toThrow('backend unavailable')
})
