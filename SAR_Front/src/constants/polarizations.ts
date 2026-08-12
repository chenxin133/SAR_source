export const POLARIZATION_OPTIONS = [
  'HH',
  'HV',
  'VH',
  'VV',
  'HH+HV',
  'VV+VH',
  'HH+VV',
  'HH+HV+VH+VV'
] as const

export const buildPolarizationOptions = (values: Array<string | undefined | null> = []) => {
  const existing = values.map((value) => String(value ?? '').trim()).filter(Boolean)
  return Array.from(new Set([...POLARIZATION_OPTIONS, ...existing]))
}
