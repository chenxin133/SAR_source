import { expect, it } from 'vitest'
import { buildResolutionOptions, coarserResolutions, resolutionKey, resolutionMeters, UNKNOWN_RESOLUTION } from '../resolution'

it('combines equivalent units and retains unknown, paired and unitless resolutions', () => {
  expect(['1m', '1 m', '100cm', '1000mm', '0.001千米'].map(resolutionKey)).toEqual(Array(5).fill('1 m'))
  expect(resolutionKey('')).toBe(UNKNOWN_RESOLUTION)
  expect(resolutionKey('1')).not.toBe(resolutionKey('1m'))
  expect(resolutionMeters('1x2m')).toBeUndefined()
  expect(resolutionMeters('0m')).toBeUndefined()
  expect(buildResolutionOptions(['1m', '100 cm', '', '未知'])).toHaveLength(2)
})

it('offers only coarser targets that apply to every sample in a batch', () => {
  expect(coarserResolutions(['25cm'])).toEqual([0.5, 1, 2, 3, 5])
  expect(coarserResolutions(['0.5m'])).toEqual([1, 2, 3, 5])
  expect(coarserResolutions(['1m', '2m'])).toEqual([3, 5])
  expect(coarserResolutions(['3m'])).toEqual([5])
  expect(coarserResolutions(['5m'])).toEqual([])
  expect(coarserResolutions(['1m', ''])).toEqual([])
  expect(coarserResolutions(['1×2m'])).toEqual([])
})
