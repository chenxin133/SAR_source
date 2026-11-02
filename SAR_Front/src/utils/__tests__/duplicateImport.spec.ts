import { beforeEach, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { HttpError } from '../../services/http'
import { ImportCancelledError, withDuplicateChoice } from '../duplicateImport'

vi.mock('element-plus', () => ({
  ElButton: 'button', ElMessageBox: Object.assign(vi.fn(() => new Promise(() => {})), { close: vi.fn() })
}))
beforeEach(() => vi.clearAllMocks())

const duplicate = () => {
  const error = new HttpError('duplicate', 409, '/upload')
  error.detail = { code: 'duplicate_file', existing: { id: 'existing', name: '原文件.tif' } }
  return error
}

for (const [index, action] of [[0, 'reuse'], [1, 'import'], [2, 'update']] as const) {
  it(`resolves a duplicate with ${action} without redoing the upload`, async () => {
    const operation = vi.fn().mockRejectedValueOnce(duplicate()).mockResolvedValue('saved')
    const pending = withDuplicateChoice(operation)
    await Promise.resolve(); await Promise.resolve()
    const options = vi.mocked(ElMessageBox).mock.calls[0]![0] as any
    options.message.children[2].children[index].props.onClick()
    expect(await pending).toBe('saved')
    expect(operation.mock.calls.map((call) => call[0])).toEqual(['ask', action])
  })
}
it('cancel stops without retrying or surfacing a failed upload', async () => {
  const operation = vi.fn().mockRejectedValue(duplicate())
  const pending = withDuplicateChoice(operation)
  await Promise.resolve(); await Promise.resolve()
  const options = vi.mocked(ElMessageBox).mock.calls[0]![0] as any
  options.message.children[2].children[3].props.onClick()
  await expect(pending).rejects.toBeInstanceOf(ImportCancelledError)
  expect(operation).toHaveBeenCalledTimes(1)
})
it('preserves unrelated server errors', async () => {
  const error = new HttpError('not found', 404, '/upload')
  await expect(withDuplicateChoice(async () => { throw error })).rejects.toBe(error)
  expect(ElMessageBox).not.toHaveBeenCalled()
})
