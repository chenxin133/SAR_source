import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import XmlMetadataPicker from '../XmlMetadataPicker.vue'
import { metadataApi } from '../../services/metadataApi'

vi.mock('../../services/metadataApi', () => ({ metadataApi: { parseXml: vi.fn() } }))
const metadata = { name: 'scene', resolution: '0.5m', frequency_band: 'X', satellite: 'HT2-02D',
  coordinates: {}, image_filename: 'scene.tif' } as any
let wrapper: ReturnType<typeof mount>
const setup = (find: NonNullable<SarDesktopBridge['findCompanionXml']>) => {
  window.sarDesktop = { findCompanionXml: find } as SarDesktopBridge
  vi.mocked(metadataApi.parseXml).mockResolvedValue(metadata)
  wrapper = mount(XmlMetadataPicker, { global: { stubs: {
    'el-button': { template: '<button><slot/></button>' },
    'el-alert': { props: ['title'], template: '<div>{{title}}</div>' }
  } } })
}
const found = (filename = 'scene.xml') => ({ status: 'found', filename, base64: btoa('<sarScene/>'), match: 'same-name' } as const)
afterEach(() => { wrapper?.unmount(); delete window.sarDesktop; vi.clearAllMocks() })

it('automatically parses the sibling XML after selecting an image without selecting XML', async () => {
  const find = vi.fn().mockResolvedValue(found())
  setup(find)
  const image = new File(['pixels'], 'scene.tif')
  await wrapper.setProps({ imageFile: image, imageFilename: image.name }); await flushPromises()
  expect(find).toHaveBeenCalledWith(image)
  expect(metadataApi.parseXml).toHaveBeenCalledOnce()
  const parsed = wrapper.emitted('parsed')![0][0] as any
  expect(parsed.file.name).toBe('scene.xml'); expect(parsed.base64).toBe(btoa('<sarScene/>'))
  expect(parsed.metadata.resolution).toBe('0.5m')
  expect(wrapper.text()).toContain('已自动读取同目录配套 XML')
  expect(wrapper.emitted('parsing')!.at(-1)).toEqual([false])
})

it.each(['not-found', 'ambiguous', 'unavailable'] as const)('supports manual entry when lookup is %s', async status => {
  setup(vi.fn().mockResolvedValue({ status, filenames: ['a.xml', 'b.xml'] }))
  await wrapper.setProps({ imageFile: new File(['pixels'], 'scene.tif') }); await flushPromises()
  expect(metadataApi.parseXml).not.toHaveBeenCalled()
  expect(wrapper.emitted('parsed')).toBeUndefined()
  expect(wrapper.text()).toContain('手动')
  expect(wrapper.emitted('parsing')!.at(-1)).toEqual([false])
})

it('discards a late lookup when a different same-named image is selected or removed', async () => {
  let resolveFirst!: (value: ReturnType<typeof found>) => void
  const find = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    .mockResolvedValueOnce(found('second.xml'))
  setup(find)
  await wrapper.setProps({ imageFile: new File(['a'], 'scene.tif') }); await flushPromises()
  await wrapper.setProps({ imageFile: new File(['b'], 'scene.tif') }); await flushPromises()
  resolveFirst(found('first.xml')); await flushPromises()
  expect(wrapper.text()).toContain('second.xml'); expect(wrapper.text()).not.toContain('first.xml')
  expect(wrapper.emitted('parsed')).toHaveLength(1)
  await wrapper.setProps({ imageFile: null }); await flushPromises()
  expect(wrapper.text()).not.toContain('second.xml')
})

it('shows read/parse errors and allows manually replacing the automatic XML', async () => {
  setup(vi.fn().mockResolvedValue(found()))
  vi.mocked(metadataApi.parseXml).mockRejectedValueOnce(new Error('XML 格式错误'))
  await wrapper.setProps({ imageFile: new File(['pixels'], 'scene.tif') }); await flushPromises()
  expect(wrapper.text()).toContain('XML 格式错误')
  expect(wrapper.emitted('parsed')).toBeUndefined()
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['<sarScene/>'], 'manual.xml')] })
  await input.trigger('change'); await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 30)); await flushPromises()
  expect((wrapper.emitted('parsed')![0][0] as any).file.name).toBe('manual.xml')
  expect(wrapper.text()).not.toContain('XML 格式错误')
})
