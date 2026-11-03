import { sha256 } from '@noble/hashes/sha2'

export const sha256Blob = async (file: Blob, onProgress?: (fraction: number) => void): Promise<string> => {
  const digest = sha256.create()
  const chunkSize = 2 * 1024 * 1024
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    digest.update(new Uint8Array(await file.slice(offset, offset + chunkSize).arrayBuffer()))
    onProgress?.(Math.min(1, (offset + chunkSize) / file.size))
  }
  return Array.from(digest.digest(), byte => byte.toString(16).padStart(2, '0')).join('')
}
