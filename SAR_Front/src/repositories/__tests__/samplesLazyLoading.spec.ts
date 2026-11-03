import { beforeEach, expect, it, vi } from 'vitest'
import { samplesRepo } from '../samplesRepo'
import type { SampleSummary } from '../../types/samples'

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), previewImage: vi.fn(), exportBundle: vi.fn() }))
vi.mock('../../config/storage', () => ({ getStorageMode: () => 'backend' }))
vi.mock('../../services/samplesApi', () => ({ samplesApi: api }))
beforeEach(() => { vi.resetAllMocks() })

it('gets one sample directly without enumerating the library', async () => {
  api.get.mockResolvedValue({ id: 'one' })
  expect(await samplesRepo.get('one')).toEqual({ id: 'one' })
  expect(api.get).toHaveBeenCalledExactlyOnceWith('one')
  expect(api.list).not.toHaveBeenCalled()
})

it('loads only the chosen preview', async () => {
  const image = new Blob(['preview'])
  api.previewImage.mockResolvedValue(image)
  expect(await samplesRepo.previewImage({ id: 'one' } as SampleSummary)).toBe(image)
  expect(api.previewImage).toHaveBeenCalledExactlyOnceWith('one')
  expect(api.list).not.toHaveBeenCalled()
})

it('exports selected metadata records without downloading their images in the renderer', async () => {
  const bundle = new Blob(['zip'])
  api.exportBundle.mockResolvedValue(bundle)
  expect(await samplesRepo.exportBundle([{ id: 'one' }, { id: 'two' }] as SampleSummary[], 'source', 3)).toBe(bundle)
  expect(api.exportBundle).toHaveBeenCalledExactlyOnceWith(['one', 'two'], 'source', 3)
  expect(api.get).not.toHaveBeenCalled()
  expect(api.list).not.toHaveBeenCalled()
})
