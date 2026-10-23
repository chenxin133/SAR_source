import { buildUrl, requestJson } from './http'
import { unwrapEnvelope, type ApiEnvelope } from '../types/backend'

export type EchoSignal = {
  id: string; name: string; original_filename: string; remark: string
  source: 'imported' | 'simulated'; na: number; nr: number; byte_order: 'little' | 'big'; iq_offset: number
  frequency_band: string | null; center_frequency_ghz: number | null
  gate_min: number; gate_max: number; size_bytes: number; checksum_sha256: string
  simulation: Record<string, unknown> | null; created_at: string; updated_at: string
  preview_url: string; download_url: string
}
export type EchoSimulation = {
  name: string; remark: string; na: number; nr: number; seed: number; noise_std: number; gate_start: number; frequency_band: string
}
export type EchoPulse = {
  pulse: number; igate: number; indices: number[]; i: number[]; q: number[]; magnitude: number[]; phase: number[]
}
export const echoesApi = {
  async list(q: string, source: string, page: number, band: string) {
    const params = new URLSearchParams({ q, limit: '20', offset: String((page - 1) * 20) })
    if (source) params.set('source', source)
    if (band) params.set('frequency_band', band)
    return requestJson<{ data: EchoSignal[]; total: number }>(`/echoes?${params}`)
  },
  async upload(file: File, fields: { name: string; remark: string; byte_order: string; iq_offset: number }) {
    const form = new FormData()
    form.append('file', file)
    Object.entries(fields).forEach(([key, value]) => form.append(key, String(value)))
    return unwrapEnvelope(await requestJson<ApiEnvelope<EchoSignal>>('/echoes/upload', { method: 'POST', body: form }))
  },
  async simulate(payload: EchoSimulation) {
    return unwrapEnvelope(await requestJson<ApiEnvelope<EchoSignal>>('/echoes/simulate', {
      method: 'POST', body: JSON.stringify(payload)
    }))
  },
  async edit(id: string, payload: { name: string; remark: string }) {
    return unwrapEnvelope(await requestJson<ApiEnvelope<EchoSignal>>(`/echoes/${id}`, {
      method: 'PATCH', body: JSON.stringify(payload)
    }))
  },
  async pulse(id: string, pulse: number) {
    return unwrapEnvelope(await requestJson<ApiEnvelope<EchoPulse>>(`/echoes/${id}/pulse?pulse=${pulse}`))
  },
  async remove(id: string) { await requestJson(`/echoes/${id}`, { method: 'DELETE' }) },
  async download(row: EchoSignal) {
    const response = await fetch(buildUrl(`/echoes/${row.id}/download`))
    if (!response.ok) throw new Error(`下载失败：HTTP ${response.status}`)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url; link.download = row.original_filename; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
