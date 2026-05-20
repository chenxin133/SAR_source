import { buildUrl, requestJson } from './http'
import type { ApiEnvelope, ApiTaskOut } from '../types/backend'
import { unwrapEnvelope } from '../types/backend'

export type TaskStreamMessage = {
  status: string
  progress: number
  error?: string | null
  result?: Record<string, unknown> | null
}

export const tasksApi = {
  async get(taskId: string): Promise<ApiTaskOut> {
    const res = await requestJson<ApiEnvelope<ApiTaskOut>>(`/tasks/${encodeURIComponent(taskId)}`, { method: 'GET' })
    return unwrapEnvelope(res)
  },

  /**
   * SSE 订阅任务进度。返回一个 close() 用于取消订阅。
   * 注意：EventSource 无法自定义 header；若后端鉴权依赖 Authorization header，请改用轮询。
   */
  stream(
    taskId: string,
    handlers: {
      onMessage: (msg: TaskStreamMessage) => void
      onError?: (e: Event) => void
      onOpen?: () => void
    }
  ): { close: () => void; source: EventSource } {
    const url = buildUrl(`/tasks/stream/${encodeURIComponent(taskId)}`)
    const es = new EventSource(url)

    es.onopen = () => handlers.onOpen?.()
    es.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data) as TaskStreamMessage
        handlers.onMessage(parsed)
      } catch {
        // ignore invalid payload
      }
    }
    es.onerror = (e) => handlers.onError?.(e)

    return {
      source: es,
      close: () => es.close()
    }
  }
}
