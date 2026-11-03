import { sha256Blob } from '../utils/fileFingerprint'

self.onmessage = async (event: MessageEvent<Blob>) => {
  try {
    const digest = await sha256Blob(event.data, progress => self.postMessage({ progress }))
    self.postMessage({ digest })
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : '读取文件失败' })
  }
}
