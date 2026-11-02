import { afterEach, expect, it, vi } from 'vitest'
import { imagesRepo } from '../imagesRepo'

const state = vi.hoisted(() => ({ process: vi.fn(), get: vi.fn(), detail: vi.fn(), thumbnails: vi.fn() }))
vi.mock('../../config/storage', () => ({ getStorageMode: () => 'backend' }))
vi.mock('../rawImagesRepo', () => ({ rawImagesRepo: {} }))
vi.mock('../../services/imagesApi', () => ({ imagesApi: {
  process: state.process, getDetail: state.detail, getThumbnails: state.thumbnails
} }))
vi.mock('../../services/tasksApi', () => ({ tasksApi: { get: state.get } }))
afterEach(() => { vi.unstubAllGlobals(); vi.resetAllMocks() })

it('forces reprocessing of the existing record even when an 8192 preview is already cached', async () => {
  vi.stubGlobal('EventSource', undefined)
  state.thumbnails.mockResolvedValue([{ level: 8192, url: '/old.webp', purpose: 'preview' }])
  state.process.mockResolvedValue({ task_id: 'retry-task' })
  state.get.mockResolvedValue({ status: 'succeeded', progress: 100 })
  state.detail.mockResolvedValue({ image: { id: 'same-id', name: 'huge.tif', width: 24444, height: 24303, status: 'ready', error_message: '' }, thumbnails: [] })
  const saved = await imagesRepo.ensureHighResolutionPreview('same-id', 8192, true)
  expect(state.process).toHaveBeenCalledExactlyOnceWith('same-id')
  expect(saved).toMatchObject({ id: 'same-id', status: 'ready', width: 24444, height: 24303, errorMessage: '' })
  expect(saved!.previewUrl).toContain('v=')
})

it('surfaces the retry failure without replacing the image record', async () => {
  vi.stubGlobal('EventSource', undefined)
  state.thumbnails.mockResolvedValue([])
  state.process.mockResolvedValue({ task_id: 'retry-task' })
  state.get.mockResolvedValue({ status: 'failed', progress: 100, error_message: '原始影像文件缺失' })
  await expect(imagesRepo.ensureHighResolutionPreview('same-id', 8192, true)).rejects.toThrow('原始影像文件缺失')
  expect(state.detail).not.toHaveBeenCalled()
})
