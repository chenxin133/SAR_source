export type SatelliteEntry = {
  id: string
  name: string
}

export const entrySatellites: SatelliteEntry[] = [
  { id: 'gaofen-3', name: '高分三号' },
  { id: 'qilu-1', name: '齐鲁一号星' },
  { id: 'taijing-4-03', name: '泰景四号03星' },
  { id: 'hongtu-1', name: '航天宏图一号' },
  { id: 'luojia-1-01', name: '珞珈二号01星' },
  { id: 'haisi-1', name: '海丝一号' },
  { id: 'chaohu-1', name: '巢湖一号' },
  { id: 'fucheng-1', name: '涪城一号' }
]

export const getSatelliteNameById = (id: string) => {
  return entrySatellites.find((s) => s.id === id)?.name ?? id
}

const satelliteAliases: Record<string, string> = {
  '齐鲁一号': '齐鲁一号星', '齐鲁1号': '齐鲁一号星', 'QL-1': '齐鲁一号星', 'QL1': '齐鲁一号星',
  '珞珈二号': '珞珈二号01星', '珞珈一号01星': '珞珈二号01星', 'LJ2-01': '珞珈二号01星',
  '高分3号': '高分三号', 'GF3': '高分三号', 'GF-3': '高分三号',
  'TJ04-3': '泰景四号03星', 'HT1-A': '航天宏图一号',
  'HS-01': '海丝一号', 'CH-01': '巢湖一号', 'FC-01': '涪城一号'
}
export const normalizeSatelliteName = (name: string) => satelliteAliases[name.trim().toUpperCase()] || name.trim()

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
