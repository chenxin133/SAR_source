/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * API Base，例如：
   * - /api/v1（默认）
   * - http://localhost:8000/api/v1（本地联调）
   */
  readonly VITE_API_BASE?: string

  /**
   * 存储模式：
   * - local / idb / indexeddb：浏览器 IndexedDB（原纯前端模式）
   * - backend / api：后端模式（方案A）
   */
  readonly VITE_STORAGE_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface SarDesktopBridge {
  getRuntimeInfo(): Promise<unknown>
  pingBackend(): Promise<{ ok: boolean }>
  openExternal(url: string): Promise<{ ok: true }>
}

interface Window {
  sarDesktop?: SarDesktopBridge
}
