import { afterEach, describe, expect, it, vi } from 'vitest'
import { HttpError, requestJson } from '../http'

afterEach(() => vi.unstubAllGlobals())

describe('API error messages', () => {
  it('shows the missing original explanation from the backend', async () => {
    const detail = '原始影像文件缺失：source.tif。请恢复该影像的原文件后重试。'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), {
      status: 409, headers: { 'Content-Type': 'application/json' }
    })))
    try {
      await requestJson('/samples/crop')
      expect.fail('expected an HTTP error')
    } catch (error) {
      expect(error).toBeInstanceOf(HttpError)
      expect((error as HttpError).message).toBe(detail)
      expect((error as HttpError).status).toBe(409)
    }
  })

  it.each([
    ['Internal Server Error', 'Internal Server Error'],
    ['<html>proxy error</html>', 'HTTP 502'],
    [JSON.stringify({ detail: [{ msg: 'Field required' }] }), JSON.stringify({ detail: [{ msg: 'Field required' }] })]
  ])('keeps other error responses readable: %s', async (body, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 502 })))
    await expect(requestJson('/samples/crop')).rejects.toThrow(message)
  })
})
