import { afterEach, expect, it, vi } from 'vitest'
import { fingerprintFile } from '../fingerprintFile'

const state = vi.hoisted(() => ({ workers: 0, terminated: 0 }))
vi.mock('../../workers/fileHash.worker.ts?worker', () => ({ default: class {
  onmessage?: (event: { data: object }) => void
  constructor() { state.workers++ }
  postMessage() { this.onmessage?.({ data: { progress: 1 } }); this.onmessage?.({ data: { digest: 'worker-digest' } }) }
  terminate() { state.terminated++ }
} }))
afterEach(() => { vi.unstubAllGlobals(); state.workers = state.terminated = 0 })

it('prefers the native streaming hash for files selected on the desktop', async () => {
  const native = vi.fn().mockResolvedValue('native-digest')
  vi.stubGlobal('window', { sarDesktop: { fingerprintFile: native } })
  const file = new Blob(['abc']), progress = vi.fn()
  expect(await fingerprintFile(file, progress)).toBe('native-digest')
  expect(native).toHaveBeenCalledWith(file, progress); expect(state.workers).toBe(0)
})
it('preserves native read/change errors without hashing a changed file again', async () => {
  vi.stubGlobal('window', { sarDesktop: { fingerprintFile: vi.fn().mockRejectedValue(new Error('file changed')) } })
  await expect(fingerprintFile(new Blob(['abc']))).rejects.toThrow('file changed')
  expect(state.workers).toBe(0)
})
it('uses a worker for browser and generated blobs', async () => {
  vi.stubGlobal('window', { sarDesktop: { fingerprintFile: vi.fn().mockResolvedValue(null) } })
  const progress = vi.fn()
  expect(await fingerprintFile(new Blob(['abc']), progress)).toBe('worker-digest')
  expect(progress).toHaveBeenCalledWith(1); expect(state.workers).toBe(1); expect(state.terminated).toBe(1)
})
