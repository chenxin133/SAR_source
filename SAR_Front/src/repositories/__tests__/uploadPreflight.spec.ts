import { beforeEach, expect, it, vi } from 'vitest'
import { imagesRepo } from '../imagesRepo'
import { ImportCancelledError } from '../../utils/duplicateImport'

const state = vi.hoisted(() => ({ hash: vi.fn(), validate: vi.fn(), init: vi.fn(), part: vi.fn(), complete: vi.fn(), detail: vi.fn(), process: vi.fn(), task: vi.fn(), thumbnails: vi.fn(), cancel: vi.fn() }))
vi.mock('../../config/storage', () => ({ getStorageMode: () => 'backend' }))
vi.mock('../rawImagesRepo', () => ({ rawImagesRepo: {} }))
vi.mock('../../utils/fingerprintFile', () => ({ fingerprintFile: state.hash }))
vi.mock('../../utils/rasterProduct', () => ({ validateRasterProduct: state.validate }))
vi.mock('../../services/imagesApi', () => ({ imagesApi: { uploadInit: state.init, uploadPart: state.part, uploadComplete: state.complete,
  getDetail: state.detail, process: state.process, getThumbnails: state.thumbnails, cancelUpload: state.cancel } }))
vi.mock('../../services/tasksApi', () => ({ tasksApi: { get: state.task } }))
const payload = { file: { size: 10, name: 'renamed.tif', slice: (start: number, end: number) => ({ size: Math.min(10, end) - start }) } as File,
  name: 'updated', resolution: '1m', metadataXmlBase64: 'xml-content', metadataXmlFilename: 'same.xml' }
beforeEach(() => {
  vi.resetAllMocks(); vi.stubGlobal('EventSource', undefined)
  state.hash.mockResolvedValue('a'.repeat(64)); state.detail.mockResolvedValue({ image: { id: 'same-id', name: 'saved', size_bytes: 10, status: 'ready' }, thumbnails: [] })
})
for (const updated of [false, true]) it(`uses existing content without transfer for preflight ${updated ? 'update' : 'reuse'}`, async () => {
  state.init.mockResolvedValue({ image_id: 'same-id', reused: true, updated })
  expect((await imagesRepo.create(payload)).id).toBe('same-id')
  expect(state.init).toHaveBeenCalledWith(expect.objectContaining({ checksum_sha256: 'a'.repeat(64), total_size: 10, metadata_xml_base64: 'xml-content' }))
  expect(state.part).not.toHaveBeenCalled(); expect(state.complete).not.toHaveBeenCalled(); expect(state.process).not.toHaveBeenCalled()
})
it('cancels at the preflight prompt without creating or transmitting an upload', async () => {
  state.init.mockRejectedValue(new ImportCancelledError())
  await expect(imagesRepo.create(payload)).rejects.toBeInstanceOf(ImportCancelledError)
  expect(state.part).not.toHaveBeenCalled(); expect(state.cancel).not.toHaveBeenCalled()
})
it('carries the copy choice to completion without a second duplicate prompt', async () => {
  state.init.mockResolvedValue({ upload_id: 'upload', part_size: 4, duplicate_action: 'import' })
  state.complete.mockResolvedValue({ image_id: 'same-id' }); state.process.mockResolvedValue({ task_id: 'task' })
  state.task.mockResolvedValue({ status: 'succeeded' }); state.thumbnails.mockResolvedValue([])
  await imagesRepo.create(payload)
  expect(state.part).toHaveBeenCalledTimes(3)
  expect(state.complete).toHaveBeenCalledWith(expect.objectContaining({ upload_id: 'upload', duplicate_action: 'import', metadata_xml_base64: 'xml-content' }))
})
it('rejects single-look products before hashing or any request', async () => {
  state.validate.mockRejectedValue(new Error('不支持上传单视产品'))
  await expect(imagesRepo.create(payload)).rejects.toThrow('不支持上传单视产品')
  expect(state.hash).not.toHaveBeenCalled(); expect(state.init).not.toHaveBeenCalled()
})
