export class HttpError extends Error {
  status: number
  url: string

  constructor(message: string, status: number, url: string) {
    super(message)
    this.status = status
    this.url = url
  }
}

const getApiBase = () => {
  const envBase = (import.meta as any)?.env?.VITE_API_BASE as string | undefined
  // 默认对齐后端 FastAPI 的 api_prefix（当前后端为 /api/v1）
  return (envBase ?? '/api/v1').replace(/\/$/, '')
}

export const buildUrl = (pathOrUrl: string) => {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl
  const base = getApiBase()
  const path = pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`
  return `${base}${path}`
}

export const requestJson = async <T>(pathOrUrl: string, init?: RequestInit): Promise<T> => {
  const url = buildUrl(pathOrUrl)
  const headers: Record<string, string> = { ...(init?.headers as any) }
  // 仅在 body 为 string（通常为 JSON.stringify）时自动补齐 JSON Content-Type，
  // 避免二进制/Blob/FormData 被误标为 application/json。
  if (typeof init?.body === 'string' && !('Content-Type' in headers)) headers['Content-Type'] = 'application/json'

  const resp = await fetch(url, { ...init, headers })

  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    const trimmed = text.trim()
    const isHtml = trimmed.startsWith('<') || /<!doctype/i.test(trimmed)
    const message = isHtml ? `HTTP ${resp.status}` : (trimmed || `HTTP ${resp.status}`)
    throw new HttpError(message, resp.status, url)
  }

  const contentType = resp.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const text = await resp.text().catch(() => '')
    const trimmed = text.trim()
    const isHtml = trimmed.startsWith('<') || /<!doctype/i.test(trimmed)
    const message = isHtml ? '响应不是 JSON（疑似后端未命中接口或被前端页面兜底）' : (trimmed || '响应不是 JSON')
    throw new HttpError(message, resp.status, url)
  }

  return (await resp.json()) as T
}
