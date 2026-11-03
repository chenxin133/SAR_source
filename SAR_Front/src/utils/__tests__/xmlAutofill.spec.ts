import { expect, it } from 'vitest'
import { applyXmlAutofill, clearXmlAutofill } from '../xmlAutofill'
import { sampleName, buildSampleXml } from '../sampleMetadata'
import { entrySatellites, normalizeSatelliteName } from '../../constants/satellites'
import type { SarSample } from '../../types/samples'

it('fills empty/automatic values and retains manual edits when XML is switched or removed', () => {
  const form = { name: 'scene.tif', region: '手填地区', resolution: '' }
  const applied = applyXmlAutofill(form, { name: 'XML 名称', region: '', resolution: '0.5m' }, {}, { name: 'scene.tif' })
  expect(form).toEqual({ name: 'XML 名称', region: '手填地区', resolution: '0.5m' })
  form.resolution = '1m'
  clearXmlAutofill(form, applied, { name: 'next.tif' })
  expect(form).toEqual({ name: 'next.tif', region: '手填地区', resolution: '1m' })
})

it('generates matching four-digit sample names and escaped XML for an exported target', () => {
  const sample = { id: 'sample', name: 'unused', category: '舰船&目标', frequencyBand: 'X', resolution: '50cm', sequenceNo: 7,
    imageId: '', annotationId: '', annotationType: 'rect', remark: '', width: 100, height: 80,
    image: new Blob(), format: 'image/tiff', createdAt: 0, updatedAt: 0 } satisfies SarSample
  expect(sampleName(sample)).toBe('舰船&目标_X_0.5m_0007')
  const filename = sampleName(sample, 2) + '.tif'
  const document = new DOMParser().parseFromString(buildSampleXml(sample, filename, 25, 20, 2), 'application/xml')
  expect(document.querySelector('category')?.textContent).toBe('舰船&目标')
  expect(document.querySelector('resolution')?.textContent).toBe('2')
  expect(document.querySelector('imageSize')?.getAttribute('image')).toBe(filename)
  expect(document.querySelector('sampleNumber')?.textContent).toBe('0007')
})

it('adds the Gaofen entry and normalizes old names without changing entry route IDs', () => {
  expect(entrySatellites.find((satellite) => satellite.id === 'gaofen-3')?.name).toBe('高分三号')
  expect(entrySatellites.find((satellite) => satellite.id === 'luojia-1-01')?.name).toBe('珞珈二号01星')
  expect(normalizeSatelliteName('齐鲁一号')).toBe('齐鲁一号星')
  expect(normalizeSatelliteName('GF-3')).toBe('高分三号')
})

it.each([
  ['GF3', '高分三号'], ['QL1', '齐鲁一号星'], ['TJ04-3', '泰景四号03星'],
  ['HT1-A', '航天宏图一号'], ['LJ2-01', '珞珈二号01星'],
  ['HS-01', '海丝一号'], ['CH-01', '巢湖一号'], ['FC-01', '涪城一号']
])('matches scene code %s to its existing entry', (code, name) => {
  expect(entrySatellites.some(entry => entry.name === name)).toBe(true)
  for (const value of [code, code.toLowerCase(), `  ${code}  `, name]) {
    expect(normalizeSatelliteName(value)).toBe(name)
  }
})

it.each(['TJ04-30', 'HT2-02D', 'QL10', ' Custom-Satellite '])('retains the identity of unrecognized satellite %s', value => {
  expect(normalizeSatelliteName(value)).toBe(value.trim())
})
