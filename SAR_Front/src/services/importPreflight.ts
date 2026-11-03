import { fingerprintFile } from '../utils/fingerprintFile'
import { chooseDuplicate, type DuplicateAction } from '../utils/duplicateImport'
import { requestJson } from './http'
import { unwrapEnvelope, type ApiEnvelope } from '../types/backend'

export const importPreflight = async (resource: 'samples' | 'echoes', file: Blob): Promise<{
  action: DuplicateAction; existing?: { id: string; name: string } | null
}> => {
  const checksum_sha256 = await fingerprintFile(file)
  const result = unwrapEnvelope(await requestJson<ApiEnvelope<{ existing: { id: string; name: string } | null }>>('/imports/check', {
    method: 'POST', body: JSON.stringify({ resource, checksum_sha256 })
  }))
  return { existing: result.existing, action: result.existing ? await chooseDuplicate(result.existing) : 'ask' }
}
