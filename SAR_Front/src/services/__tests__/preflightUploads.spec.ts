import { beforeEach, expect, it, vi } from 'vitest'
import { echoesApi } from '../echoesApi'
import { samplesApi } from '../samplesApi'
import type { SarSample } from '../../types/samples'

const state = vi.hoisted(() => ({ preflight: vi.fn(), request: vi.fn() }))
vi.mock('../importPreflight', () => ({ importPreflight: state.preflight }))
vi.mock('../http', () => ({ requestJson: state.request, buildUrl: (url: string) => url, readResponseError: vi.fn() }))
beforeEach(() => { vi.resetAllMocks() })
it('reuses an echo before sending its multipart body', async () => {
  state.preflight.mockResolvedValue({ existing: { id: 'echo-id' }, action: 'reuse' })
  state.request.mockResolvedValue({ data: { id: 'echo-id' } })
  const result = await echoesApi.upload(new File(['abc'], 'signal.dat'), { name: '', remark: '', byte_order: 'little', iq_offset: 32768 })
  expect(result.id).toBe('echo-id'); expect(state.request.mock.calls).toEqual([['/echoes/echo-id']])
})
it('reuses a standalone sample before sending its multipart body', async () => {
  state.preflight.mockResolvedValue({ existing: { id: 'sample-id' }, action: 'reuse' })
  state.request.mockResolvedValue({ data: { id: 'sample-id', image_url: '/sample.tif', created_at: '2026-11-03', updated_at: '2026-11-03' } })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['existing']) }))
  const result = await samplesApi.put({ id: 'new-local', imageId: '', image: new Blob(['abc']) } as SarSample)
  expect(result.id).toBe('sample-id'); expect(state.request.mock.calls).toEqual([['/samples/sample-id']])
  vi.unstubAllGlobals()
})
it('stops an echo upload when the early prompt is cancelled', async () => {
  state.preflight.mockRejectedValue(new Error('cancelled'))
  await expect(echoesApi.upload(new File(['abc'], 'signal.dat'), { name: '', remark: '', byte_order: 'little', iq_offset: 32768 })).rejects.toThrow('cancelled')
  expect(state.request).not.toHaveBeenCalled()
})
