import { createHash } from 'node:crypto'
import { expect, it, vi } from 'vitest'
import { sha256Blob } from '../fileFingerprint'

it('hashes exact bytes in bounded slices without reading the whole file', async () => {
  const data = new Uint8Array(5 * 1024 * 1024 + 17).map((_, i) => i % 251)
  const slice = vi.fn((start: number, end: number) => {
    expect(end - start).toBeLessThanOrEqual(2 * 1024 * 1024)
    return { arrayBuffer: async () => data.slice(start, end).buffer }
  })
  const file = { size: data.length, slice, arrayBuffer: () => { throw Error('whole-file reads forbidden') } } as unknown as Blob
  const progress = vi.fn()
  expect(await sha256Blob(file, progress)).toBe(createHash('sha256').update(data).digest('hex'))
  expect(slice).toHaveBeenCalledTimes(3)
  expect(progress.mock.calls.at(-1)).toEqual([1])
})

it('matches the empty-file SHA256 vector', async () => {
  expect(await sha256Blob({ size: 0 } as Blob)).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
})

it('stops when a local file becomes unreadable', async () => {
  const file = { size: 10, slice: () => ({ arrayBuffer: async () => { throw Error('file disappeared') } }) } as unknown as Blob
  await expect(sha256Blob(file)).rejects.toThrow('file disappeared')
})
