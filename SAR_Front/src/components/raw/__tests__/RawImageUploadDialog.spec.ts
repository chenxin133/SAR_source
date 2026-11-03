import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElButton, ElForm, ElUpload } from 'element-plus'
import RawImageUploadDialog from '../RawImageUploadDialog.vue'
import XmlMetadataPicker from '../../XmlMetadataPicker.vue'
import { entrySatellites } from '../../../constants/satellites'
import type { XmlAttachment } from '../../../types/metadata'

const state = vi.hoisted(() => ({ uploadImage: vi.fn().mockResolvedValue(true) }))
vi.mock('../../../stores/rawData', () => ({ useRawDataStore: () => ({ images: [], isUploading: false, uploadImage: state.uploadImage }) }))
let wrapper: ReturnType<typeof mount>
const setup = (props = {}) => {
  wrapper = mount(RawImageUploadDialog, { props: { modelValue: true, ...props }, global: {
    plugins: [ElementPlus], stubs: { ElDialog: { template: '<div><slot/><slot name="footer"/></div>' } }
  } })
  return wrapper.findComponent(ElForm).props('model')!
}
const attachment = (overrides = {}): XmlAttachment => ({ file: new File(['<sarScene/>'], 'scene.xml'), base64: 'b3JpZ2luYWw=', metadata: {
  name: 'XML 场景', data_source: '航天宏图', satellite: 'HT2-02D', frequency_band: 'X', polarization: 'HH',
  acquisition_at: '2026-07-02T00:11:31.831368Z', imaging_start: '2026-07-02T00:11:31.831368', imaging_end: '',
  time_reference: 'UTC', resolution: '0.5m', region: '', category: '', image_filename: 'scene.tif', width: 8, height: 8,
  coordinates: {}, ...overrides
} })
const parse = async (value = attachment()) => { wrapper.findComponent(XmlMetadataPicker).vm.$emit('parsed', value); await flushPromises() }
afterEach(() => { wrapper?.unmount(); state.uploadImage.mockClear() })

it('autofills XML, requires missing region and preserves original UTC precision on upload', async () => {
  const form = setup()
  const file = new File(['pixels'], 'scene.tif')
  const onChange = wrapper.findComponent(ElUpload).props('onChange')!
  const selected = { name: file.name, raw: file, status: 'ready', uid: 1 } as any
  onChange(selected, [selected])
  await flushPromises()
  await parse()
  expect(form.name).toBe('XML 场景')
  expect(form.resolution).toBe('0.5m')
  expect(form.acquisitionAt).toBe('2026-07-02T00:11:31')
  const submit = () => wrapper.findAllComponents(ElButton).find(button => button.text() === '确定上传')!.trigger('click')
  await submit(); await flushPromises()
  expect(state.uploadImage).not.toHaveBeenCalled()
  form.region = '夏威夷'
  await submit(); await flushPromises()
  expect(state.uploadImage).toHaveBeenCalledWith(expect.objectContaining({ file, resolution: '0.5m',
    acquisitionAt: '2026-07-02T00:11:31.831368Z', metadataXmlFilename: 'scene.xml', metadataXmlBase64: 'b3JpZ2luYWw=' }))
})

it('retains manual fields through XML replacement and removal and enforces resolution', async () => {
  const form = setup()
  form.name = '人工名称'; form.region = '青岛'; form.resolution = '2m'
  await parse()
  expect(form.name).toBe('人工名称'); expect(form.region).toBe('青岛'); expect(form.resolution).toBe('2m')
  await parse(attachment({ resolution: '1m', frequency_band: 'C' }))
  expect(form.frequencyBand).toBe('C'); expect(form.resolution).toBe('2m')
  wrapper.findComponent(XmlMetadataPicker).vm.$emit('cleared'); await flushPromises()
  expect(form.satellite).toBe(''); expect(form.resolution).toBe('2m'); expect(form.name).toBe('人工名称')
  form.resolution = ''
  await wrapper.findAllComponents(ElButton).find(button => button.text() === '确定上传')!.trigger('click'); await flushPromises(); expect(state.uploadImage).not.toHaveBeenCalled()
})

it('adds GF3 entry, accepts its XML alias and blocks XML from a different satellite entry', async () => {
  expect(entrySatellites).toContainEqual({ id: 'gaofen-3', name: '高分三号' })
  const form = setup({ satellitePreset: '高分三号', satelliteReadonly: true })
  await parse(attachment({ satellite: 'GF-3' }))
  const submit = () => wrapper.findAllComponents(ElButton).find(button => button.text() === '确定上传')!
  expect(submit().props('disabled')).toBe(false)
  await parse()
  expect(form.satellite).toBe('高分三号')
  expect(submit().props('disabled')).toBe(true)
  expect(wrapper.text()).toContain('与当前入口不同')
})

it.each([
  ['GF3', '高分三号'], ['QL1', '齐鲁一号星'], ['TJ04-3', '泰景四号03星'],
  ['HT1-A', '航天宏图一号'], ['LJ2-01', '珞珈二号01星'],
  ['HS-01', '海丝一号'], ['CH-01', '巢湖一号'], ['FC-01', '涪城一号']
])('accepts XML code %s only in its matching satellite entry', async (code, name) => {
  const form = setup({ satellitePreset: name, satelliteReadonly: true })
  const submit = () => wrapper.findAllComponents(ElButton).find(button => button.text() === '确定上传')!
  await parse(attachment({ satellite: code }))
  expect(form.satellite).toBe(name)
  expect(submit().props('disabled')).toBe(false)
  expect(wrapper.text()).not.toContain('与当前入口不同')
  await parse(attachment({ satellite: code === 'TJ04-3' ? 'GF3' : 'TJ04-3' }))
  expect(submit().props('disabled')).toBe(true)
  expect(form.satellite).toBe(name)
  expect(wrapper.text()).toContain('与当前入口不同')
})
