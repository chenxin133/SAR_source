export class HttpError extends Error {
  status: number
  url: string
  detail?: unknown

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

export const readResponseError = async (resp: Response, url = resp.url): Promise<HttpError> => {
  const trimmed = (await resp.text().catch(() => '')).trim()
  const isHtml = trimmed.startsWith('<') || /<!doctype/i.test(trimmed)
  let detail: unknown
  let message = isHtml ? `HTTP ${resp.status}` : (trimmed || `HTTP ${resp.status}`)
  if (!isHtml && trimmed.startsWith('{')) {
    try {
      const payload = JSON.parse(trimmed)
      detail = payload?.detail
      if (typeof payload?.detail?.message === 'string') message = payload.detail.message
      if (typeof payload?.detail === 'string' && payload.detail.trim()) message = payload.detail
    } catch { /* Keep plain text errors readable. */ }
  }
  const error = new HttpError(message, resp.status, url)
  error.detail = detail
  return error
}

export const requestJson = async <T>(pathOrUrl: string, init?: RequestInit): Promise<T> => {
  const url = buildUrl(pathOrUrl)
  const headers: Record<string, string> = { ...(init?.headers as any) }
  // 仅在 body 为 string（通常为 JSON.stringify）时自动补齐 JSON Content-Type，
  // 避免二进制/Blob/FormData 被误标为 application/json。
  if (typeof init?.body === 'string' && !('Content-Type' in headers)) headers['Content-Type'] = 'application/json'

  const resp = await fetch(url, { ...init, headers })

  if (!resp.ok) throw await readResponseError(resp, url)

  const contentType = resp.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const text = await resp.text().catch(() => '')
    const trimmed = text.trim()
    const isHtml = trimmed.startsWith('<') || /<!doctype/i.test(trimmed)
    const message = isHtml ? '响应不是 JSON（疑似后端未命中接口或被前端页面兜底）' : (trimmed || '响应不是 JSON')
    const error = new HttpError(message, resp.status, url)
    throw error
  }

  return (await resp.json()) as T
}
