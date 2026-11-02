import { requestJson } from './http'
import { unwrapEnvelope, type ApiEnvelope } from '../types/backend'
import type { SceneMetadata } from '../types/metadata'

export const metadataApi = {
  async parseXml(file: File): Promise<SceneMetadata> {
    const form = new FormData()
    form.append('file', file)
    return unwrapEnvelope(await requestJson<ApiEnvelope<SceneMetadata>>('/images/metadata/parse-xml', { method: 'POST', body: form }))
  }
}
