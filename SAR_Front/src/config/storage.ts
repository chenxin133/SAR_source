export type StorageMode = 'local' | 'backend'

const normalizeMode = (raw: unknown): StorageMode => {
  const v = String(raw ?? '')
    .trim()
    .toLowerCase()
  if (v === 'backend' || v === 'api' || v === 'server') return 'backend'
  if (v === 'local' || v === 'idb' || v === 'indexeddb' || v === 'browser') return 'local'
  return 'local'
}

export const getStorageMode = (): StorageMode => {
  return normalizeMode(import.meta.env.VITE_STORAGE_MODE)
}

