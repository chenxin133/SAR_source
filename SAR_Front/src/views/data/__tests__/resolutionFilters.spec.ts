import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import ElementPlus, { ElSelect, ElTable } from 'element-plus'
import RawDataView from '../RawDataView.vue'
import SampleDataView from '../SampleDataView.vue'
import { UNKNOWN_RESOLUTION } from '../../../utils/resolution'

const state = vi.hoisted(() => ({ images: [] as any[], samples: [] as any[], exportBundle: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('../../../config/storage', () => ({ getStorageMode: () => 'backend' }))
vi.mock('../../../stores/rawData', () => ({ useRawDataStore: () => reactive({ images: state.images, fetchImages: vi.fn(), loading: false }) }))
vi.mock('../../../repositories/imagesRepo', () => ({ imagesRepo: { list: async () => state.images } }))
vi.mock('../../../repositories/samplesRepo', () => ({ samplesRepo: { list: async () => state.samples, exportBundle: state.exportBundle, changedEventName: 'test-samples-changed' } }))
let wrapper: ReturnType<typeof mount>
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); state.exportBundle.mockReset() })

const setFilter = async (placeholder: string, value: string) => {
  const select = wrapper.findAllComponents(ElSelect).find((select) => select.props('placeholder') === placeholder)!
  select.vm.$emit('update:modelValue', value)
  await nextTick()
}
const rowIds = () => (wrapper.findComponent(ElTable).props('data') as any[]).map((row) => row.id)

it('filters original images by normalized resolution together with other filters and clears it', async () => {
  state.images = [
    { id: 'a', name: 'a', resolution: '100cm', frequencyBand: 'X', status: 'ready' },
    { id: 'b', name: 'b', resolution: '1 m', frequencyBand: 'C', status: 'ready' },
    { id: 'c', name: 'c', resolution: '', frequencyBand: 'X', status: 'ready' }
  ]
  wrapper = mount(RawDataView, { global: { plugins: [ElementPlus], stubs: { RawImageUploadDialog: true, ImageViewer: true, Upload: true, Picture: true, Edit: true } } })
  await flushPromises()
  await setFilter('全部分辨率', '1 m')
  expect(rowIds()).toEqual(['a', 'b'])
  await setFilter('全部数据频段', 'X')
  expect(rowIds()).toEqual(['a'])
  await setFilter('全部分辨率', UNKNOWN_RESOLUTION)
  expect(rowIds()).toEqual(['c'])
  await setFilter('全部分辨率', '')
  expect(rowIds()).toEqual(['a', 'c'])
})

it('filters standalone and old linked samples and follows source resolution changes', async () => {
  state.images = [{ id: 'source', name: 'source', resolution: '1m' }]
  const base = { name: 'sample', category: '', remark: '', annotationType: 'rect', annotationId: 'manual:x', width: 8, height: 8, image: new Blob(), createdAt: 0 }
  state.samples = [
    { ...base, id: 'linked', imageId: 'source' },
    { ...base, id: 'independent', imageId: '', resolution: '100cm' },
    { ...base, id: 'unknown', imageId: '' }
  ]
  wrapper = mount(SampleDataView, { global: { plugins: [ElementPlus], stubs: { ArrowDown: true, Refresh: true } } })
  await flushPromises()
  await setFilter('全部分辨率', '1 m')
  expect(rowIds()).toEqual(['linked', 'independent'])
  const exportSelect = wrapper.findAllComponents(ElSelect).find((select) => select.props('placeholder') === '导出分辨率')!
  expect(exportSelect.exists()).toBe(true)
  state.images = [{ id: 'source', name: 'source', resolution: '2m' }]
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(rowIds()).toEqual(['independent'])
  await setFilter('全部分辨率', UNKNOWN_RESOLUTION)
  expect(rowIds()).toEqual(['unknown'])
})

it('previews the original polygon PNG instead of an old thumbnail that lost transparency', async () => {
  const image = new Blob(['masked PNG'], { type: 'image/png' })
  const thumbnail = new Blob(['old opaque RGB thumbnail'], { type: 'image/png' })
  state.images = []
  state.samples = [{ id: 'polygon', name: 'polygon', category: '舰船', remark: '', annotationType: 'polygon',
    annotationId: 'ann1', imageId: '', format: 'image/png', width: 8, height: 8, image, thumbnail, createdAt: 0 }]
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:polygon-preview')
  wrapper = mount(SampleDataView, { global: { plugins: [ElementPlus], stubs: { ArrowDown: true, Refresh: true } } })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '预览')!.trigger('click')
  expect(create).toHaveBeenCalledWith(image)
})

it('links raw image facets and keeps alternatives within the current facet available', async () => {
  state.images = [
    { id: 'a', name: 'a', satellite: '高分三号', resolution: '1m', frequencyBand: 'C', polarization: 'HH', status: 'ready', description: '地区：北京' },
    { id: 'b', name: 'b', satellite: '高分三号', resolution: '3m', frequencyBand: 'C', polarization: 'VV', status: 'ready', description: '地区：上海' },
    { id: 'c', name: 'c', satellite: '齐鲁一号星', resolution: '0.5m', frequencyBand: 'Ku', polarization: 'HH', status: 'failed', description: '地区：北京' }
  ]
  wrapper = mount(RawDataView, { global: { plugins: [ElementPlus], stubs: { RawImageUploadDialog: true, ImageViewer: true, Upload: true, Picture: true, Edit: true } } })
  await flushPromises()
  const vm = (wrapper.vm as any).$.setupState
  await setFilter('全部卫星源', '高分三号')
  expect(vm.frequencyBandOptions).toEqual(['C'])
  expect(vm.resolutionOptions.map((option: any) => option.value)).toEqual(['1 m', '3 m'])
  expect(vm.statusOptions.map((option: any) => option.value)).toEqual(['ready'])
  await setFilter('全部地区', '北京')
  expect(rowIds()).toEqual(['a'])
  expect(vm.regionOptions).toEqual(['北京', '上海'])
  expect(vm.satelliteOptions).toEqual(['高分三号', '齐鲁一号星'])
  expect(vm.polarizationOptions).toEqual(['HH'])
  await setFilter('全部卫星源', '')
  expect(vm.frequencyBandOptions).toEqual(['C', 'Ku'])
})

it('exports only checked visible samples with their common coarser resolutions including 3m, or an explicit filtered scope', async () => {
  state.images = []
  const base = { name: 'sample', category: '舰船', remark: '', annotationType: 'rect', annotationId: 'manual:x', imageId: '', width: 8, height: 8, image: new Blob(), createdAt: 0 }
  state.samples = [{ ...base, id: 'a', resolution: '1m', frequencyBand: 'C' },
    { ...base, id: 'b', resolution: '2m', frequencyBand: 'C' },
    { ...base, id: 'c', category: '车辆', resolution: '5m', frequencyBand: 'X' }]
  state.exportBundle.mockResolvedValue(new Blob(['zip']))
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  wrapper = mount(SampleDataView, { global: { plugins: [ElementPlus], stubs: { ArrowDown: true, Refresh: true } } })
  await flushPromises()
  const vm = (wrapper.vm as any).$.setupState
  expect(vm.exportScope).toBe('selected')
  expect(vm.batchRows).toHaveLength(0)
  const table = wrapper.findComponent(ElTable).vm as any
  table.toggleRowSelection(vm.filteredTableData[0], true)
  table.toggleRowSelection(vm.filteredTableData[1], true)
  await nextTick()
  expect(vm.batchResolutionOptions).toEqual([3, 5])
  vm.exportResolution = 3
  await vm.handleBatchExport('origin')
  expect(state.exportBundle.mock.calls[0][0].map((s: any) => s.id)).toEqual(['a', 'b'])
  expect(state.exportBundle.mock.calls[0].slice(1, 3)).toEqual(['source', 3])
  await setFilter('全部数据频段', 'X')
  expect(vm.batchRows).toHaveLength(0)
  expect(vm.categoryOptions).toEqual(['车辆'])
  expect(vm.resolutionOptions.map((option: any) => option.value)).toEqual(['5 m'])
  vm.exportScope = 'filtered'; vm.exportResolution = ''
  await vm.handleBatchExport('image/png')
  expect(state.exportBundle.mock.calls[1][0].map((s: any) => s.id)).toEqual(['c'])
  await setFilter('全部数据频段', '')
  expect(vm.categoryOptions).toEqual(['车辆', '舰船'].sort((a,b) => a.localeCompare(b, 'zh-CN')))
})
