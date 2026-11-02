export const EXPORT_RESOLUTIONS = [0.5, 1, 2, 3, 5]
export const resolutionMeters = (value?: string | null): number | undefined => {
  const key = resolutionKey(value)
  if (!/^\d+(?:\.\d+)? m$/.test(key)) return undefined
  return Number.parseFloat(key)
}
export const coarserResolutions = (values: Array<string | null | undefined>) => {
  if (!values.length) return []
  const meters = values.map(resolutionMeters)
  return EXPORT_RESOLUTIONS.filter((target) => meters.every((current) => current != null && target > current))
}

export const UNKNOWN_RESOLUTION = '__unknown_resolution__'

export const resolutionKey = (value?: string | null): string => {
  const text = String(value ?? '').trim().toLowerCase().replace(/\s+/g, '')
  if (!text || ['未知', 'unknown', 'n/a', '-'].includes(text)) return UNKNOWN_RESOLUTION
  const scalar = text.match(/^(\d+(?:\.\d+)?|\.\d+)(km|cm|mm|m|千米|厘米|毫米|米)$/)
  if (scalar) {
    const factor: Record<string, number> = { km: 1000, 千米: 1000, cm: 0.01, 厘米: 0.01, mm: 0.001, 毫米: 0.001, m: 1, 米: 1 }
    const meters = Number(scalar[1]) * factor[scalar[2]]!
    if (Number.isFinite(meters) && meters > 0) return `${Number(meters.toPrecision(12))} m`
  }
  // Keep paired resolutions and values with no unit distinct from scalar meters.
  return text.replace(/[x×*]/g, '×')
}

export const resolutionLabel = (value?: string | null) => {
  const key = resolutionKey(value)
  return key === UNKNOWN_RESOLUTION ? '未知' : key
}

export const buildResolutionOptions = (values: Array<string | null | undefined>) =>
  [...new Set(values.map(resolutionKey))].sort((a, b) => a.localeCompare(b, 'zh-CN', { numeric: true }))
    .map((value) => ({ value, label: value === UNKNOWN_RESOLUTION ? '未知' : value }))
