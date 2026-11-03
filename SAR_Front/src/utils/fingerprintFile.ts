import FileHashWorker from '../workers/fileHash.worker.ts?worker'

export const fingerprintFile = async (file: Blob, onProgress?: (fraction: number) => void): Promise<string> => {
  const native = await window.sarDesktop?.fingerprintFile?.(file, onProgress)
  if (native) return native
  return new Promise((resolve, reject) => {
    const worker = new FileHashWorker()
    worker.onmessage = ({ data }) => {
      if (data.progress != null) onProgress?.(data.progress)
      if (data.digest || data.error) {
        worker.terminate()
        if (data.error) reject(new Error(data.error))
        else resolve(data.digest)
      }
    }
    worker.onerror = () => { worker.terminate(); reject(new Error('本机文件校验失败，请重新选择文件')) }
    worker.postMessage(file)
  })
}
