export const REGION_PREFIX = '地区：'
export const REMARK_PREFIX = '备注：'

export const packImageDescription = (region?: string, remark?: string) => {
  const regionText = String(region ?? '').trim()
  const remarkText = String(remark ?? '').trim()
  if (!regionText && !remarkText) return ''
  if (!regionText) return remarkText
  if (!remarkText) return `${REGION_PREFIX}${regionText}`
  return `${REGION_PREFIX}${regionText}\n${REMARK_PREFIX}${remarkText}`
}

export const unpackImageDescription = (description?: string | null) => {
  const raw = String(description ?? '').trim()
  if (!raw) return { region: '', remark: '' }

  const lines = raw
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  let region = ''
  const remarkLines: string[] = []

  for (const line of lines) {
    if (line.startsWith(REGION_PREFIX)) {
      region = line.slice(REGION_PREFIX.length).trim()
      continue
    }
    if (line.startsWith(REMARK_PREFIX)) {
      const remark = line.slice(REMARK_PREFIX.length).trim()
      if (remark) remarkLines.push(remark)
      continue
    }
    remarkLines.push(line)
  }

  return {
    region,
    remark: remarkLines.join('\n').trim()
  }
}
