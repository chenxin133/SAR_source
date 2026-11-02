import { expect, it } from 'vitest'
import { placeDimensionLabel } from '../annotationGeometry'

it.each([
  [{ left: 200, top: 200, right: 312, bottom: 312 }, { x: 256, y: 160 }],
  [{ left: 200, top: 200, right: 312, bottom: 312 }, { x: 256, y: 352 }],
  [{ left: 200, top: 200, right: 312, bottom: 312 }, { x: 352, y: 256 }],
  [{ left: 200, top: 620, right: 312, bottom: 770 }, { x: 256, y: 580 }]
])('keeps the dimension badge outside rotation hit targets: %j', (bounds, handle) => {
  const point = placeDimensionLabel(bounds, { width: 1000, height: 800 }, handle)
  const overlaps = handle.x + 22 >= point.left && handle.x - 22 <= point.left + 180 &&
    handle.y + 22 >= point.top && handle.y - 22 <= point.top + 34
  expect(overlaps).toBe(false)
  expect(point.left).toBeGreaterThanOrEqual(4); expect(point.top).toBeGreaterThanOrEqual(4)
  expect(point.top + 34).toBeLessThanOrEqual(796)
})
