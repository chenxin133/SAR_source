import type { XY } from '../types/annotations'

export const constrainSquareEnd = (start: XY, end: XY, square: boolean): XY => {
  if (!square) return { ...end }
  const dx = end.x - start.x, dy = end.y - start.y
  const side = Math.max(Math.abs(dx), Math.abs(dy))
  return { x: start.x + (dx < 0 ? -side : side), y: start.y + (dy < 0 ? -side : side) }
}

export function placeDimensionLabel(bounds: { left: number; top: number; right: number; bottom: number },
  viewport: { width: number; height: number }, handle: XY, height = 34, width = 180) {
  const gap = 14
  const clamp = (value: number, limit: number) => Math.max(4, Math.min(value, Math.max(4, limit - 4)))
  const left = clamp(bounds.left, viewport.width - width)
  const candidates = [
    { left, top: bounds.bottom + gap },
    { left: bounds.right + gap, top: bounds.top },
    { left, top: bounds.top - height - 60 },
    { left: bounds.left - width - gap, top: bounds.top }
  ]
  const avoidsHandle = (point: { left: number; top: number }) =>
    handle.x + 22 < point.left || handle.x - 22 > point.left + width ||
    handle.y + 22 < point.top || handle.y - 22 > point.top + height
  const fits = (point: { left: number; top: number }) => point.left >= 4 && point.top >= 4 &&
    point.left + width <= viewport.width - 4 && point.top + height <= viewport.height - 4
  const direct = candidates.find(point => fits(point) && avoidsHandle(point))
  if (direct) return direct
  const corners = [
    { left: 4, top: 4 }, { left: clamp(viewport.width, viewport.width - width), top: 4 },
    { left: 4, top: clamp(viewport.height, viewport.height - height) }
  ]
  return corners.find(avoidsHandle) || corners[0]
}
