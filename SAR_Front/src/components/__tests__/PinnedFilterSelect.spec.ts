import { afterEach, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PinnedFilterSelect from '../PinnedFilterSelect.vue'

const options = ['A', 'B', 'C'].map(value => ({ value, label: value }))
let wrapper: ReturnType<typeof mount>
afterEach(() => { wrapper?.unmount(); localStorage.clear() })
const create = (key = 'test') => mount(PinnedFilterSelect, { attachTo: document.body,
  props: { modelValue: 'A', options, preferenceKey: key }, attrs: { teleported: false, placeholder: '筛选测试', clearable: true },
  global: { plugins: [ElementPlus] } })
const values = () => wrapper.findAll('.filter-option').map(option => option.attributes('data-value'))

it('pins without selecting, drags pinned items, and restores order after remount', async () => {
  wrapper = create(); await flushPromises()
  await wrapper.find('button[aria-label="置顶C"]').trigger('click')
  await wrapper.find('button[aria-label="置顶B"]').trigger('click')
  expect(values()).toEqual(['C', 'B', 'A'])
  const transfer = { effectAllowed: '', setData: () => {} }
  await wrapper.find('[data-value="B"] .filter-option__drag').trigger('dragstart', { dataTransfer: transfer })
  await wrapper.find('[data-value="C"]').trigger('drop', { dataTransfer: transfer })
  expect(values()).toEqual(['B', 'C', 'A'])
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  wrapper.unmount(); wrapper = create(); await flushPromises()
  expect(values()).toEqual(['B', 'C', 'A'])
  await wrapper.find('button[aria-label="取消置顶B"]').trigger('click')
  expect(values()).toEqual(['C', 'A', 'B'])
})

it('keeps hidden pins through linked filtering and restores them when options return', async () => {
  wrapper = create(); await flushPromises()
  await wrapper.find('button[aria-label="置顶C"]').trigger('click')
  await wrapper.find('button[aria-label="置顶B"]').trigger('click')
  await wrapper.setProps({ options: options.filter(option => option.value !== 'C') })
  expect(values()).toEqual(['B', 'A'])
  await wrapper.setProps({ options })
  expect(values()).toEqual(['C', 'B', 'A'])
  wrapper.unmount(); wrapper = create('separate-filter'); await flushPromises()
  expect(values()).toEqual(['A', 'B', 'C'])
})

it('supports keyboard reordering and forwards normal filter changes', async () => {
  wrapper = create(); await flushPromises()
  await wrapper.find('button[aria-label="置顶C"]').trigger('click')
  await wrapper.find('button[aria-label="置顶B"]').trigger('click')
  await wrapper.find('[data-value="B"] .filter-option__drag').trigger('keydown', { key: 'ArrowUp' })
  expect(values()).toEqual(['B', 'C', 'A'])
  await wrapper.find('[data-value="C"] .filter-option__label').trigger('click')
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['C'])
})
