import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import RawImageDetails from '../RawImageDetails.vue'
import type { SarImage } from '../../../types/sar'

const image: SarImage = { id: 'fixed-id', name: 'before.tif', satellite: 'SAR', acquisitionDate: '',
  fileSize: '1 MB', sizeBytes: 1048576, status: 'ready', description: '地区：北京\n备注：原备注',
  thumbnailUrl: '/fixed.webp' }
const wrappers: ReturnType<typeof mount>[] = []
const setup = (saveMetadata = vi.fn().mockResolvedValue(undefined)) => {
  const wrapper = mount(RawImageDetails, { props: { image: { ...image }, saveMetadata },
    slots: { thumbnail: '<img src="/fixed.webp" />' }, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper)
  return { wrapper, saveMetadata }
}
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

describe('raw image detail editing', () => {
  it('keeps ID and thumbnail read-only on double click', async () => {
    const { wrapper, saveMetadata } = setup()
    await wrapper.get('[data-testid="image-id"]').trigger('dblclick')
    await wrapper.get('[data-testid="image-thumbnail"] img').trigger('dblclick')
    expect(wrapper.find('[data-editor]').exists()).toBe(false)
    expect(saveMetadata).not.toHaveBeenCalled()
    expect(wrapper.get('img').attributes('src')).toBe('/fixed.webp')
  })
  it('saves a double-clicked field and supports cancelling without a request', async () => {
    const { wrapper, saveMetadata } = setup()
    await wrapper.get('[data-field="name"]').trigger('dblclick')
    await wrapper.get('input').setValue('after.tif')
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(saveMetadata).toHaveBeenCalledWith({ name: 'after.tif' })
    expect(wrapper.find('[data-editor]').exists()).toBe(false)
    await wrapper.get('[data-field="name"]').trigger('dblclick')
    await wrapper.get('input').setValue('cancelled')
    await wrapper.get('input').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[data-editor]').exists()).toBe(false)
    expect(saveMetadata).toHaveBeenCalledTimes(1)
  })
  it('retains the draft when saving fails and preserves remark when changing region', async () => {
    const saveMetadata = vi.fn().mockRejectedValueOnce(new Error('测试保存失败')).mockResolvedValue(undefined)
    const { wrapper } = setup(saveMetadata)
    await wrapper.get('[data-field="region"]').trigger('dblclick')
    await wrapper.get('input').setValue('上海')
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('上海')
    expect(wrapper.find('[data-editor="region"]').exists()).toBe(true)
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(saveMetadata).toHaveBeenLastCalledWith({ description: '地区：上海\n备注：原备注' })
  })
  it('preserves the entered acquisition time without a timezone shift', async () => {
    const { wrapper, saveMetadata } = setup()
    await wrapper.get('[data-field="acquisitionDate"]').trigger('dblclick')
    await wrapper.get('input').setValue('2026-10-28 14:30:00')
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(saveMetadata).toHaveBeenCalledWith({ acquisitionDate: '2026-10-28 14:30:00' })
  })
})
