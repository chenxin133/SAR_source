import { beforeEach, expect, it, vi } from 'vitest'
import { validateRasterProduct } from '../rasterProduct'

const state = vi.hoisted(() => ({ samples: 2, format: 2 }))
vi.mock('geotiff', () => ({ fromBlob: async () => ({ getImage: async () => ({
  getSampleFormat: () => state.format, getSamplesPerPixel: () => state.samples
}) }) }))
const file = { slice: () => ({ arrayBuffer: async () => new Uint8Array([73, 73, 42, 0]).buffer }) } as unknown as Blob
beforeEach(() => { state.samples = 2; state.format = 2 })
it('rejects signed I/Q single-look tags before decoding or hashing', async () => {
  await expect(validateRasterProduct(file)).rejects.toThrow('不支持上传单视产品')
})
it('rejects complex single-look tags', async () => {
  state.samples = 1; state.format = 6
  await expect(validateRasterProduct(file)).rejects.toThrow('不支持上传单视产品')
})
it('allows unsigned multiband and signed single-band amplitude products', async () => {
  state.format = 1
  await expect(validateRasterProduct(file)).resolves.toBeUndefined()
  state.samples = 1; state.format = 2
  await expect(validateRasterProduct(file)).resolves.toBeUndefined()
})
