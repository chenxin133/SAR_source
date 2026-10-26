import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildLocalSampleImage, isAllowedSampleFile, SAMPLE_UPLOAD_ACCEPT } from '../sampleUpload'

const fixtures = [
  ['uint16.tif', 'SUkqABwAAAB4nGNgeMF8gX0Bv4P8//8AGE0EzwkAAAEDAAEAAAADAAAAAQEDAAEAAAACAAAAAgEDAAEAAAAQAAAAAwEDAAEAAAAIAAAABgEDAAEAAAABAAAAEQEEAAEAAAAIAAAAFgEDAAEAAAACAAAAFwEEAAEAAAAUAAAAHAEDAAEAAAABAAAAAAAAAA=='],
  ['float32.TIFF', 'SUkqACYAAAB4nGNgUDjIwMBwgAEMFjgwMHg4MTAcqAcALOYESwAKAAABAwABAAAAAwAAAAEBAwABAAAAAgAAAAIBAwABAAAAIAAAAAMBAwABAAAACAAAAAYBAwABAAAAAQAAABEBBAABAAAACAAAABYBAwABAAAAAgAAABcBBAABAAAAHQAAABwBAwABAAAAAQAAAFMBAwABAAAAAwAAAAAAAAA='],
  ['rgb.tiff', 'SUkqACAAAAB4nPvPwMDwH4S5ROSMbNz+//8PADUeBusKAAABAwABAAAAAwAAAAEBAwABAAAAAgAAAAIBAwADAAAAngAAAAMBAwABAAAACAAAAAYBAwABAAAAAgAAABEBBAABAAAACAAAABUBAwABAAAAAwAAABYBAwABAAAAAgAAABcBBAABAAAAGAAAABwBAwABAAAAAQAAAAAAAAAIAAgACAA=']
]
afterEach(() => vi.restoreAllMocks())

describe('local TIFF sample upload', () => {
  it.each(fixtures)('decodes %s for PNG preview while preserving the exact TIFF', async (name, encoded) => {
    const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0))
    const file = new File([bytes], name, { type: '' })
    const pixels: Uint8ClampedArray[] = []
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
      createImageData: (width: number, height: number) => ({ data: new Uint8ClampedArray(width * height * 4) }),
      putImageData: (image: ImageData) => pixels.push(image.data),
      drawImage: vi.fn()
    }) as any)
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => callback(new Blob(['preview'], { type: 'image/png' })))
    const browserDecoder = vi.fn().mockRejectedValue(new Error('Chromium cannot decode TIFF'))
    vi.stubGlobal('createImageBitmap', browserDecoder)
    try {
      expect(isAllowedSampleFile(file)).toBe(true)
      const result = await buildLocalSampleImage(file)
      expect(result.format).toBe('image/tiff')
      expect([result.width, result.height]).toEqual([3, 2])
      expect(result.thumbnail?.type).toBe('image/png')
      expect(new Uint8Array(await result.image.arrayBuffer())).toEqual(bytes)
      expect(browserDecoder).not.toHaveBeenCalled()
      expect(pixels[0]).toHaveLength(24)
      expect(pixels[0]!.filter((_, i) => i % 4 === 3).every(alpha => alpha === 255)).toBe(true)
      if (name === 'rgb.tiff') expect(Array.from(pixels[0]!.slice(0, 4))).toEqual([255, 0, 0, 255])
    } finally { vi.unstubAllGlobals() }
  })

  it('offers both TIFF suffixes and rejects unsupported files', () => {
    expect(SAMPLE_UPLOAD_ACCEPT.split(',')).toContain('.tif')
    expect(SAMPLE_UPLOAD_ACCEPT.split(',')).toContain('.tiff')
    expect(isAllowedSampleFile(new File(['x'], 'sample.exe'))).toBe(false)
    expect(isAllowedSampleFile(new File(['x'], 'sample.PNG'))).toBe(true)
  })
})
