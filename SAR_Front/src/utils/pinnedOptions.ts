export type FilterOption = { value: string; label: string }
const storageKey = (scope: string) => `sar.filter-pins.v1.${scope}`

export const readPins = (scope: string): string[] => {
  try {
    const values: unknown = JSON.parse(localStorage.getItem(storageKey(scope)) || '[]')
    return Array.isArray(values) ? [...new Set(values.filter((value): value is string => typeof value === 'string'))] : []
  } catch { return [] }
}

export const savePins = (scope: string, values: string[]) => {
  try { localStorage.setItem(storageKey(scope), JSON.stringify(values)) } catch { /* Keep this session's ordering. */ }
}

export const orderOptions = (options: FilterOption[], pins: string[]): FilterOption[] => {
  const available = new Map(options.map(option => [option.value, option]))
  return [...pins.flatMap(value => available.has(value) ? [available.get(value)!] : []),
    ...options.filter(option => !pins.includes(option.value))]
}

export const movePin = (pins: string[], from: string, to: string): string[] => {
  const source = pins.indexOf(from), target = pins.indexOf(to)
  if (source < 0 || target < 0 || source === target) return pins
  const updated = [...pins]
  updated.splice(source, 1)
  updated.splice(target, 0, from)
  return updated
}
