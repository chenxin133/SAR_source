import { afterEach, expect, it, vi } from 'vitest'
import { samplesApi } from '../samplesApi'
import type { SarSample } from '../../types/samples'

vi.mock('../http', () => ({ buildUrl: (path: string) => path, requestJson: vi.fn() }))
afterEach(() => vi.unstubAllGlobals())

it('omits an empty source image and maps a null source after saving', async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: {
    id: 'sample-id', image_id: null, name: 'independent', roi: { annotationId: 'manual:one', format: 'image/tiff' },
    image_url: '/sample.tif', created_at: '2026-10-28T00:00:00Z', updated_at: '2026-10-28T00:00:00Z'
  } }) }).mockResolvedValue({ ok: true, blob: async () => new Blob(['original']) })
  vi.stubGlobal('fetch', fetch)
  const sample: SarSample = { id: 'one', name: 'independent', imageId: '', imageName: '', annotationId: 'manual:one',
    annotationType: 'rect', category: '', remark: '', format: 'image/tiff', width: 10, height: 8,
    image: new Blob(['original']), createdAt: 0, updatedAt: 0 }
  const saved = await samplesApi.put(sample)
  const body = fetch.mock.calls[0]![1].body as FormData
  expect(body.has('image_id')).toBe(false)
  expect(body.get('image_format')).toBe('image/tiff')
  expect(saved.imageId).toBe('')
  expect(saved.format).toBe('image/tiff')
})
