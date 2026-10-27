import type { SarImage, UploadPayload } from '../types/sar'
import { getStorageMode } from '../config/storage'
import { rawImagesRepo } from './rawImagesRepo'
import { imagesApi } from '../services/imagesApi'
import { tasksApi, type TaskStreamMessage } from '../services/tasksApi'
import type { ApiImageOut, ApiThumbnailOut } from '../types/backend'

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const
  let idx = 0
  let n = bytes
  while (n >= 1024 && idx < units.length - 1) {
    n /= 1024
    idx++
  }
  const fixed = idx >= 2 ? 2 : 0
  return `${n.toFixed(fixed)} ${units[idx]}`
}

const pickPreviewUrls = (thumbs: ApiThumbnailOut[]) => {
  const preview = thumbs.filter((t) => (t.purpose || '').toLowerCase() === 'preview' && !!t.url)
  preview.sort((a, b) => (b.level ?? 0) - (a.level ?? 0))
  const previewUrl = preview[0]?.url ?? undefined
  const thumbnailUrl = preview[preview.length - 1]?.url ?? preview[0]?.url ?? undefined
  return { previewUrl, thumbnailUrl }
}

const mapApiImageToSarImage = (img: ApiImageOut, thumbs?: ApiThumbnailOut[]): SarImage => {
  const { previewUrl, thumbnailUrl } = thumbs ? pickPreviewUrls(thumbs) : { previewUrl: undefined, thumbnailUrl: undefined }
  const statusValue = String(img.status || '').toLowerCase()
  const sameOriginPreviewUrl =
    statusValue === 'ready' ? `/api/v1/images/${encodeURIComponent(String(img.id))}/preview` : undefined
  return {
    id: String(img.id),
    name: img.name,
    satellite: String(img.satellite ?? ''),
    acquisitionDate: String(img.acquisition_at ?? ''),
    fileSize: formatBytes(Number(img.size_bytes ?? 0)),
    resolution: String(img.resolution ?? ''),
    frequencyBand: String(img.frequency_band ?? ''),
    polarization: String(img.polarization ?? ''),
    width: Number(img.width ?? 0) || undefined,
    height: Number(img.height ?? 0) || undefined,
    status: img.status,
    description: String(img.description ?? ''),
    previewUrl: previewUrl ?? sameOriginPreviewUrl,
    thumbnailUrl: thumbnailUrl ?? previewUrl ?? sameOriginPreviewUrl,
    originalPersistent: true,
    previewPersistent: !!(previewUrl ?? sameOriginPreviewUrl),
    previewNotice: undefined,
    errorMessage: String(img.error_message ?? '')
  }
}

const isFinalTaskStatus = (status: string) => {
  const s = String(status || '').toLowerCase()
  return s === 'succeeded' || s === 'failed' || s === 'canceled'
}

const waitTask = async (
  taskId: string,
  opts: { timeoutMs: number; preferSse: boolean; onProgress?: (progress01: number) => void }
): Promise<TaskStreamMessage> => {
  const startedAt = Date.now()
  const timeoutAt = startedAt + Math.max(1_000, opts.timeoutMs)
  const clamp01 = (v: number) => Math.max(0, Math.min(1, v))

  const poll = async (): Promise<TaskStreamMessage> => {
    // 1s 轮询，直到结束或超时
    while (Date.now() < timeoutAt) {
      const t = await tasksApi.get(taskId)
      const msg: TaskStreamMessage = {
        status: t.status,
        progress: Number(t.progress ?? 0),
        error: (t as any).error_message ?? null,
        result: (t as any).result ?? null
      }
      opts.onProgress?.(clamp01(Number(msg.progress ?? 0) / 100))
      if (isFinalTaskStatus(msg.status)) return msg
      await new Promise((r) => setTimeout(r, 1_000))
    }
    throw new Error('任务处理超时，请稍后刷新列表或重试')
  }

  if (!opts.preferSse || typeof EventSource === 'undefined') {
    return await poll()
  }

  // SSE：若无法建立连接/频繁报错，则自动降级到轮询
  return await new Promise<TaskStreamMessage>((resolve, reject) => {
    let settled = false
    let gotAny = false
    let fallbacking = false
    let lastMessageAt = 0
    const timer = window.setInterval(() => {
      if (Date.now() >= timeoutAt && !settled) {
        settled = true
        try {
          sub.close()
        } catch {}
        window.clearInterval(timer)
        reject(new Error('任务处理超时，请稍后刷新列表或重试'))
        return
      }

      // 某些环境会出现 SSE 收到首条消息后长时间不再更新（前端进度停在 70% 左右）。
      // 这里做“静默超时”探测，超过阈值自动降级轮询。
      if (gotAny && !fallbacking && !settled && Date.now() - lastMessageAt > 6_000) {
        void fallbackToPoll()
      }
    }, 500)

    const fallbackToPoll = async () => {
      if (settled || fallbacking) return
      fallbacking = true
      try {
        sub.close()
      } catch {}
      window.clearInterval(timer)
      try {
        const msg = await poll()
        if (!settled) {
          settled = true
          resolve(msg)
        }
      } catch (e) {
        if (!settled) {
          settled = true
          reject(e)
        }
      }
    }

    const sub = tasksApi.stream(taskId, {
      onMessage: (msg) => {
        gotAny = true
        lastMessageAt = Date.now()
        opts.onProgress?.(clamp01(Number(msg.progress ?? 0) / 100))
        if (!isFinalTaskStatus(msg.status)) return
        if (settled) return
        settled = true
        sub.close()
        window.clearInterval(timer)
        resolve(msg)
      },
      onOpen: () => {
        // 某些代理/网络环境下 SSE 会“连上但不下发数据”，导致进度卡死在 70%。
        // 若短时间内未收到任何消息，自动降级到轮询。
        window.setTimeout(() => {
          if (!gotAny) void fallbackToPoll()
        }, 2_000)
      },
      onError: async () => {
        if (settled) return
        // 若尚未收到任何进度，倾向降级到轮询；否则允许短暂抖动（继续等待）
        if (!gotAny) {
          await fallbackToPoll()
        }
      }
    })
  })
}

export const imagesRepo = {
  async list(): Promise<SarImage[]> {
    const mode = getStorageMode()
    if (mode === 'local') return await rawImagesRepo.list()

    const rows = await imagesApi.list({ limit: 200, offset: 0 })
    // 首屏列表只返回基础元数据，避免首次进入页面时被 N 次缩略图请求拖慢交互。
    // 已就绪影像会优先使用同源 preview URL，详情/预览再按需获取更多缩略图信息。
    return rows.map((img) => mapApiImageToSarImage(img))
  },

  async create(
    payload: UploadPayload,
    onProgress?: (percent: number) => void,
    onStage?: (stage: string) => void
  ): Promise<SarImage> {
    const mode = getStorageMode()
    if (mode === 'local') {
      onStage?.('正在导入影像并生成预览')
      return await rawImagesRepo.create(payload, onProgress)
    }

    onStage?.('正在传输原始影像')
    const file = payload.file
    const init = await imagesApi.uploadInit({ filename: file.name, total_size: file.size })
    const partSize = Math.max(1, Number(init.part_size))
    const totalParts = Math.max(1, Math.ceil(file.size / partSize))

    const uploadWeight = 0.7
    const processWeight = 0.3
    const setP = (p01: number) => onProgress?.(Math.round(Math.max(0, Math.min(1, p01)) * 100))

    // 上传分片（0% ~ 70%）
    let uploaded = 0
    for (let partNo = 1; partNo <= totalParts; partNo++) {
      const start = (partNo - 1) * partSize
      const end = Math.min(file.size, partNo * partSize)
      const chunk = file.slice(start, end)
      await imagesApi.uploadPart(init.upload_id, partNo, chunk)
      uploaded += chunk.size
      const p01 = (uploaded / Math.max(1, file.size)) * uploadWeight
      setP(p01)
    }

    onStage?.('正在校验并保存原始影像')
    const completed = await imagesApi.uploadComplete({
      upload_id: init.upload_id,
      total_parts: totalParts,
      name: payload.name || file.name,
      mime_type: file.type || undefined,
      satellite: payload.satellite || undefined,
      acquisition_at: payload.acquisitionAt || undefined,
      resolution: payload.resolution || undefined,
      frequency_band: payload.frequencyBand || undefined,
      polarization: payload.polarization || undefined,
      description: payload.description || undefined
    })

    // 触发后端处理任务（70% ~ 100%）
    onStage?.('正在生成影像预览')
    const { task_id } = await imagesApi.process(completed.image_id)
    const msg = await waitTask(task_id, {
      timeoutMs: 5 * 60_000,
      preferSse: true,
      onProgress: (progress01) => {
        setP(uploadWeight + progress01 * processWeight)
      }
    })

    if (String(msg.status).toLowerCase() !== 'succeeded') {
      const err = msg.error ? String(msg.error) : '后端处理失败'
      throw new Error(err)
    }

    // 刷新缩略图 URL（成功后一定会有至少 1 个 preview_*）
    let thumbs: ApiThumbnailOut[] | undefined
    try {
      thumbs = await imagesApi.getThumbnails(completed.image_id)
    } catch {
      thumbs = undefined
    }

    // 用 detail 再补齐 status/时间等（可选）
    const detail = await imagesApi.getDetail(completed.image_id).catch(() => null)
    const image = detail?.image ?? ({
      id: completed.image_id,
      name: payload.name || file.name,
      size_bytes: file.size,
      mime_type: file.type || null,
      status: 'ready',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    } as ApiImageOut)

    setP(1)
    return mapApiImageToSarImage(image, thumbs ?? detail?.thumbnails)
  },

  async delete(id: string): Promise<void> {
    const mode = getStorageMode()
    if (mode === 'local') return await rawImagesRepo.delete(id)
    await imagesApi.delete(id)
  },

  async getFile(id: string): Promise<Blob | undefined> {
    const mode = getStorageMode()
    if (mode === 'local') return await rawImagesRepo.getFile(id)
    // 后端模式：前端默认只展示缩略图/预览 URL，不拉取原始大文件
    return undefined
  },

  async ensureHighResolutionPreview(id: string, minLevel = 8192): Promise<SarImage | undefined> {
    if (getStorageMode() !== 'backend') return undefined
    let thumbs = await imagesApi.getThumbnails(id).catch(() => [])
    const currentMax = Math.max(0, ...thumbs.map((thumbnail) => Number(thumbnail.level || 0)))
    if (currentMax < minLevel) {
      const { task_id } = await imagesApi.process(id)
      const result = await waitTask(task_id, { timeoutMs: 5 * 60_000, preferSse: true })
      if (String(result.status).toLowerCase() !== 'succeeded') {
        throw new Error(result.error ? String(result.error) : '高清预览生成失败')
      }
      thumbs = await imagesApi.getThumbnails(id)
    }
    const detail = await imagesApi.getDetail(id)
    const mapped = mapApiImageToSarImage(detail.image, thumbs.length ? thumbs : detail.thumbnails)
    const cacheBust = (url?: string) => {
      if (!url) return url
      return `${url}${url.includes('?') ? '&' : '?'}v=${Date.now()}`
    }
    mapped.previewUrl = cacheBust(mapped.previewUrl)
    return mapped
  }
}
