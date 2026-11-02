import type { SarSample } from '../types/samples'
import { resolutionMeters } from './resolution'

const component = (value: string | undefined, fallback: string, limit: number) => {
  const text = (value?.trim() || fallback).replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
  let result = '', bytes = 0
  for (const char of text) {
    const size = new TextEncoder().encode(char).length
    if (bytes + size > limit) break
    result += char; bytes += size
  }
  return result
}
export const sampleName = (sample: Pick<SarSample, 'category' | 'frequencyBand' | 'resolution' | 'sequenceNo'>, target?: number) => {
  const meters = target ?? resolutionMeters(sample.resolution)
  const resolution = meters != null ? `${meters}m` : sample.resolution?.replace(/\s+/g, '')
  return `${component(sample.category, '未分类', 48)}_${component(sample.frequencyBand, '未知频段', 16)}_${component(resolution, '未知分辨率', 16)}_${String(sample.sequenceNo || 1).padStart(4, '0')}`
}

export const buildSampleXml = (sample: SarSample, filename: string, width: number, height: number, target?: number): string => {
  const xml = document.implementation.createDocument('', 'sarScene')
  const root = xml.documentElement
  root.setAttribute('id', sample.id); root.setAttribute('schemaVersion', '2.0'); root.setAttribute('dataType', 'sample')
  const add = (parent: Element, name: string, value: unknown) => {
    if (value == null || value === '') return
    const element = xml.createElement(name); element.textContent = String(value); parent.appendChild(element)
  }
  add(root, 'dataName', sampleName(sample, target)); add(root, 'category', sample.category)
  add(root, 'sampleNumber', String(sample.sequenceNo || 1).padStart(4, '0'))
  add(root, 'frequencyBand', sample.frequencyBand)
  for (const [tag, key] of [['satellite', 'satellite'], ['dataSource', 'data_source'], ['polarization', 'polarization'], ['region', 'region']] as const) {
    add(root, tag, sample.sceneMetadata?.[key])
  }
  const meters = target ?? resolutionMeters(sample.resolution)
  const resolution = xml.createElement('resolution')
  if (meters != null) resolution.setAttribute('unit', 'm')
  resolution.textContent = meters != null ? String(meters) : sample.resolution || ''
  root.appendChild(resolution)
  const size = xml.createElement('imageSize'); size.setAttribute('image', filename); root.appendChild(size)
  add(size, 'width', width); add(size, 'height', height)
  if (sample.sceneMetadata?.imaging_start || sample.sceneMetadata?.acquisition_at) {
    const time = xml.createElement('imagingTime'); root.appendChild(time)
    add(time, 'start', sample.sceneMetadata.imaging_start || sample.sceneMetadata.acquisition_at)
    add(time, 'end', sample.sceneMetadata.imaging_end); add(time, 'timeReference', sample.sceneMetadata.time_reference)
  }
  if (sample.imageId) { const source = xml.createElement('sourceImage'); source.setAttribute('id', sample.imageId); root.appendChild(source); add(source, 'dataName', sample.imageName) }
  return '<?xml version="1.0" encoding="utf-8"?>\n' + new XMLSerializer().serializeToString(xml)
}
