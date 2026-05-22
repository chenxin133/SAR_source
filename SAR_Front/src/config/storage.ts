export type StorageMode = 'local' | 'backend'

const normalizeMode = (raw: unknown): StorageMode | null => {
  const v = String(raw ?? '')
    .trim()
    .toLowerCase()
  if (v === 'backend' || v === 'api' || v === 'server') return 'backend'
  if (v === 'local' || v === 'idb' || v === 'indexeddb' || v === 'browser') return 'local'
  return null
}

const isDesktopBackendRuntime = (): boolean => {
  if (typeof window === 'undefined') return false
  return typeof window.sarDesktop?.getRuntimeInfo === 'function'
}

export const getStorageMode = (): StorageMode => {
  const configured = normalizeMode(import.meta.env.VITE_STORAGE_MODE)
  if (configured) return configured
  if (isDesktopBackendRuntime()) return 'backend'
  return 'local'
}
