export type SatelliteEntry = {
  id: string
  name: string
}

export const entrySatellites: SatelliteEntry[] = [
  { id: 'qilu-1', name: '齐鲁一号' },
  { id: 'taijing-4-03', name: '泰景四号03星' },
  { id: 'hongtu-1', name: '航天宏图一号' },
  { id: 'luojia-1-01', name: '珞珈二号' },
  { id: 'haisi-1', name: '海丝一号' },
  { id: 'chaohu-1', name: '巢湖一号' },
  { id: 'fucheng-1', name: '涪城一号' }
]

export const getSatelliteNameById = (id: string) => {
  return entrySatellites.find((s) => s.id === id)?.name ?? id
}

export const normalizeSatelliteName = (name: string) => name.trim()

export const dedupeSatelliteNames = (names: string[]) => {
  const seen = new Set<string>()
  const result: string[] = []
  for (const n of names) {
    const v = normalizeSatelliteName(n)
    if (!v) continue
    const key = v.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(v)
  }
  return result
}

const STORAGE_KEY = 'sar_custom_satellites'

export const loadCustomSatelliteNames = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return [] as string[]
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return [] as string[]
    return dedupeSatelliteNames(parsed.filter((x) => typeof x === 'string'))
  } catch {
    return [] as string[]
  }
}

export const saveCustomSatelliteNames = (names: string[]) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dedupeSatelliteNames(names)))
  } catch {}
}
