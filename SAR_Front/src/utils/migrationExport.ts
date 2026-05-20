import JSZip from 'jszip'
import { rawImagesRepo } from '../repositories/rawImagesRepo'
import { samplesRepo } from '../repositories/samplesRepo'
import { annotationsRepo } from '../repositories/annotationsRepo'

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5_000)
}

export const exportLocalDataPackage = async () => {
  const zip = new JSZip()
  const exportedAt = new Date().toISOString()

  const rawRecords = await rawImagesRepo.exportAllRecords()
  const sampleRecords = await samplesRepo.exportAllRecords()
  const annotationRecords = await annotationsRepo.exportAllRecords()

  const manifest: any = {
    version: 1,
    exported_at: exportedAt,
    raw_images: rawRecords.map((r) => ({ id: r.id, createdAt: r.createdAt })),
    samples: sampleRecords.map((r) => ({ id: r.id, updatedAt: r.updatedAt })),
    annotations: annotationRecords.map((r) => ({ id: r.id, updatedAt: r.updatedAt }))
  }

  zip.file('manifest.json', JSON.stringify(manifest, null, 2))

  for (const r of rawRecords) {
    const base = `raw_images/${r.id}`
    zip.file(`${base}/metadata.json`, JSON.stringify(r.metadata ?? {}, null, 2))
    if (r.file) zip.file(`${base}/file.bin`, r.file)
    if (r.preview) zip.file(`${base}/preview.bin`, r.preview)
    if (r.thumbnail) zip.file(`${base}/thumbnail.bin`, r.thumbnail)
  }

  for (const rec of sampleRecords) {
    const s = rec.data as any
    const base = `samples/${rec.id}`
    const payload = { ...s, image: s?.image ? `${base}/image.bin` : null, thumbnail: s?.thumbnail ? `${base}/thumbnail.bin` : null }
    zip.file(`${base}/sample.json`, JSON.stringify(payload, null, 2))
    if (s?.image) zip.file(`${base}/image.bin`, s.image)
    if (s?.thumbnail) zip.file(`${base}/thumbnail.bin`, s.thumbnail)
  }

  for (const rec of annotationRecords) {
    const base = `annotations/${rec.id}`
    zip.file(`${base}/annotation.json`, JSON.stringify(rec.data ?? {}, null, 2))
  }

  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } })
  downloadBlob(blob, `sar_local_export_${exportedAt.replace(/[:.]/g, '-')}.zip`)
}

