<template>
  <div class="annotate">
    <div class="header">
      <div class="title">
        <h2>图像标注</h2>
        <div class="hint">点击加点，双击/Enter 完成多边形，Esc 取消绘制，Delete 删除选中，Ctrl+Z 撤销，Ctrl+Y 重做，按住空格拖动画布，选中矩形后可拖动旋转手柄旋转标注框</div>
      </div>

      <div class="toolbar">
        <el-select
          v-model="currentImageId"
          filterable
          placeholder="选择影像"
          style="width: 320px"
          :loading="imagesLoading"
          @change="handleImageChange"
        >
          <el-option
            v-for="img in rawImages"
            :key="img.id"
            :label="`${img.name} (${img.id})`"
            :value="img.id"
          />
        </el-select>

        <el-button-group style="margin-left: 12px">
          <el-button :type="tool === 'select' ? 'primary' : 'default'" @click="setTool('select')">
            <el-icon><Pointer /></el-icon> 选择
          </el-button>
          <el-button :type="tool === 'rect' ? 'primary' : 'default'" @click="setTool('rect')">
            <el-icon><Crop /></el-icon> 矩形
          </el-button>
          <el-button :type="tool === 'polygon' ? 'primary' : 'default'" @click="setTool('polygon')">
            <el-icon><Connection /></el-icon> 多边形
          </el-button>
        </el-button-group>

        <el-button style="margin-left: 12px" @click="fitToScreen">适配</el-button>
      <el-switch v-model="snapEnabled" active-text="吸附" style="margin-left: 12px" />
      <el-slider v-model="snapPx" :min="2" :max="30" :step="1" style="width: 140px" :disabled="!snapEnabled" />
        <el-select v-model="rotationDeg" style="width: 120px; margin-left: 12px" :disabled="!currentImageId">
          <el-option :value="0" label="旋转 0°" />
          <el-option :value="90" label="旋转 90°" />
          <el-option :value="180" label="旋转 180°" />
          <el-option :value="270" label="旋转 270°" />
        </el-select>
        <el-slider v-model="rotationDeg" :min="0" :max="360" :step="1" style="width: 180px" :disabled="!currentImageId" />
        <el-button type="success" style="margin-left: 12px" :disabled="!currentImageId" @click="saveToLocal">保存</el-button>
        <el-checkbox v-model="autoGenerateSamplesOnSave">保存时自动生成样本</el-checkbox>
        <el-button :disabled="!currentImageId" @click="exportJson">导出 JSON</el-button>
        <el-button :disabled="!currentImageId" @click="triggerImport">导入 JSON</el-button>

        <div class="status">当前模式: {{ toolName }}</div>
      </div>
    </div>

    <div class="workspace">
      <div ref="canvasWrapRef" class="canvas-wrap" @contextmenu.prevent>
        <canvas ref="canvasElRef" class="canvas"></canvas>
        <div v-if="canvasLoading" class="loading-mask" v-loading="canvasLoading"></div>
      </div>

      <div class="sidebar">
        <div class="panel">
          <div class="panel-title">标注列表</div>
          <el-table
            :data="annotations"
            height="380"
            style="width: 100%"
            highlight-current-row
            row-key="id"
            :current-row-key="selectedAnnotationId || undefined"
            @row-click="handleRowClick"
          >
            <el-table-column prop="type" label="类型" width="80" />
            <el-table-column prop="category" label="类别" min-width="110" />
            <el-table-column label="时间" width="120">
              <template #default="{ row }">
                {{ formatTime(row.updatedAt || row.createdAt) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button size="small" type="danger" text @click.stop="removeAnnotation(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="panel" style="margin-top: 12px">
          <div class="panel-title">属性</div>
          <div v-if="selectedAnnotation" class="form">
            <el-form label-width="64px" size="default">
              <el-form-item label="类型">
                <el-input :model-value="selectedAnnotation.type" disabled />
              </el-form-item>
              <el-form-item label="类别">
                <el-input v-model="editCategory" placeholder="输入类别" @change="applyMetaEdit" />
              </el-form-item>
              <el-form-item label="备注">
                <el-input v-model="editRemark" type="textarea" :rows="3" placeholder="输入备注" @change="applyMetaEdit" />
              </el-form-item>
              <el-form-item label="样本">
                <el-select v-model="sampleFormat" style="width: 120px">
                  <el-option value="image/png" label="PNG" />
                  <el-option value="image/jpeg" label="JPG" />
                </el-select>
                <el-button type="primary" style="margin-left: 8px" @click="cropSelectedToSample">裁切并保存</el-button>
              </el-form-item>
            </el-form>
          </div>
          <el-empty v-else description="未选中标注" />
        </div>
      </div>
    </div>

    <el-dialog v-model="metaDialogVisible" title="标注信息" width="420px" destroy-on-close>
      <el-form label-width="64px">
        <el-form-item label="类别">
          <el-input v-model="metaDraft.category" placeholder="输入类别" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="metaDraft.remark" type="textarea" :rows="3" placeholder="输入备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelMeta">取消</el-button>
        <el-button type="primary" @click="confirmMeta">确定</el-button>
      </template>
    </el-dialog>

    <input ref="importInputRef" type="file" accept="application/json" style="display: none" @change="handleImportFile" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Canvas, FabricImage, Point, Polygon, Polyline, Rect, util } from 'fabric'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { SarImage } from '../../types/sar'
import type { AnnotationsFileV1, SarAnnotation, XY } from '../../types/annotations'
import { imagesRepo } from '../../repositories/imagesRepo'
import { annotationsRepo } from '../../repositories/annotationsRepo'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarSample } from '../../types/samples'

const route = useRoute()
const router = useRouter()

const canvasElRef = ref<HTMLCanvasElement | null>(null)
const canvasWrapRef = ref<HTMLDivElement | null>(null)
const importInputRef = ref<HTMLInputElement | null>(null)

const rawImages = ref<SarImage[]>([])
const imagesLoading = ref(false)
const currentImageId = ref<string>('')
const currentImage = computed(() => rawImages.value.find((x) => x.id === currentImageId.value))

const tool = ref<'select' | 'rect' | 'polygon'>('select')
const toolName = computed(() => {
  if (tool.value === 'select') return '选择/编辑'
  if (tool.value === 'rect') return '绘制矩形'
  return '绘制多边形'
})

const rotationDeg = ref(0)

const annotations = ref<SarAnnotation[]>([])
const selectedAnnotationId = ref<string | null>(null)
const selectedAnnotation = computed(() => annotations.value.find((a) => a.id === selectedAnnotationId.value) || null)

const editCategory = ref('')
const editRemark = ref('')

const sampleFormat = ref<SarSample['format']>('image/png')
const autoGenerateSamplesOnSave = ref(false)

const metaDialogVisible = ref(false)
const metaDraft = ref<{ category: string; remark: string }>({ category: '', remark: '' })
let pendingObject: Rect | Polygon | null = null
let pendingType: 'rect' | 'polygon' | null = null

const canvasLoading = ref(false)
let canvas: Canvas | null = null
let bgObject: FabricImage | null = null
const objectById = new Map<string, Rect | Polygon>()

const viewZoom = ref(1)
const viewPan = ref<{ x: number; y: number }>({ x: 0, y: 0 })

let resizeObserver: ResizeObserver | null = null

const historyPast = ref<SarAnnotation[][]>([])
const historyFuture = ref<SarAnnotation[][]>([])
let isApplying = false
let persistTimer: number | null = null

const isTiffName = (name?: string) => {
  if (!name) return false
  const n = name.toLowerCase()
  return n.endsWith('.tif') || n.endsWith('.tiff')
}

const cloneAnnotations = (list: SarAnnotation[]): SarAnnotation[] => {
  return JSON.parse(JSON.stringify(list)) as SarAnnotation[]
}

const buildPayload = (): AnnotationsFileV1 => {
  return {
    version: 1,
    imageId: currentImageId.value,
    exportedAt: Date.now(),
    annotations: cloneAnnotations(annotations.value)
  }
}

const schedulePersist = () => {
  if (!currentImageId.value) return
  if (persistTimer) window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(async () => {
    persistTimer = null
    await annotationsRepo.put(buildPayload()).catch(() => undefined)
  }, 300)
}

const pushHistory = () => {
  historyPast.value.push(cloneAnnotations(annotations.value))
  if (historyPast.value.length > 50) historyPast.value.shift()
  historyFuture.value = []
}

const applyAnnotations = (next: SarAnnotation[], recordHistory: boolean) => {
  if (!currentImageId.value) return
  if (recordHistory) pushHistory()
  annotations.value = next
  renderAnnotations()
  schedulePersist()
}

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

const ensureGeoTiff = async () => {
  const w = window as any
  if (w.GeoTIFF?.fromBlob) return w.GeoTIFF
  const mod = await import('geotiff')
  if (typeof (mod as any).fromBlob === 'function') return mod as any
  if (typeof (mod as any).default?.fromBlob === 'function') return (mod as any).default
  throw new Error('geotiff 未导出 fromBlob')
}

const computePercentileRange = (raster: any, len: number) => {
  const sampleCount = Math.min(200000, len)
  const step = Math.max(1, Math.floor(len / sampleCount))
  const values: number[] = []
  for (let i = 0; i < len; i += step) {
    const v = raster[i]
    if (Number.isFinite(v)) values.push(v)
  }
  if (values.length === 0) return { min: 0, max: 1 }
  values.sort((a, b) => a - b)
  const lo = values[Math.floor(values.length * 0.02)] ?? values[0]
  const hi = values[Math.floor(values.length * 0.98)] ?? values[values.length - 1]
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { min: 0, max: 1 }
  if (hi <= lo) return { min: lo, max: lo + 1 }
  return { min: lo, max: hi }
}

const stretchValue = (v: number, min: number, max: number, useLog: boolean) => {
  if (!Number.isFinite(v)) return 0
  let x = (v - min) / (max - min)
  x = Math.max(0, Math.min(1, x))
  if (useLog) x = Math.log1p(9 * x) / Math.log1p(9)
  return Math.max(0, Math.min(255, Math.round(x * 255)))
}

const rasterToCanvas = (raster: any, width: number, height: number, samplesPerPixel: number) => {
  const c = document.createElement('canvas')
  c.width = width
  c.height = height
  const ctx = c.getContext('2d')
  if (!ctx) return c
  const imgData = ctx.createImageData(width, height)
  const data = imgData.data
  const len = width * height
  if (samplesPerPixel >= 3) {
    for (let i = 0; i < len; i++) {
      const r = raster[i * samplesPerPixel + 0] ?? 0
      const g = raster[i * samplesPerPixel + 1] ?? 0
      const b = raster[i * samplesPerPixel + 2] ?? 0
      data[i * 4 + 0] = r & 0xff
      data[i * 4 + 1] = g & 0xff
      data[i * 4 + 2] = b & 0xff
      data[i * 4 + 3] = 255
    }
  } else {
    const { min, max } = computePercentileRange(raster, len)
    const useLog = max > 0 && min >= 0 && max / Math.max(min, 1e-9) > 100
    for (let i = 0; i < len; i++) {
      const v = raster[i] ?? 0
      const cc = stretchValue(v, min, max, useLog)
      data[i * 4 + 0] = cc
      data[i * 4 + 1] = cc
      data[i * 4 + 2] = cc
      data[i * 4 + 3] = 255
    }
  }
  ctx.putImageData(imgData, 0, 0)
  return c
}

const computeTargetSize = (width: number, height: number, maxW: number, maxH: number) => {
  const safeW = Number.isFinite(width) && width > 0 ? width : 1
  const safeH = Number.isFinite(height) && height > 0 ? height : 1
  const maxPreviewPixels = 4_000_000
  const scaleToFit = Math.min(1, Math.min(maxW / safeW, maxH / safeH))
  const scaleToCap = Math.min(1, Math.sqrt(maxPreviewPixels / (safeW * safeH)))
  const scale = Math.max(0.0001, Math.min(scaleToFit, scaleToCap))
  return {
    targetW: Math.max(1, Math.round(safeW * scale)),
    targetH: Math.max(1, Math.round(safeH * scale))
  }
}

const decodeTiffToCanvas = async (blob: Blob, maxW: number, maxH: number) => {
  const GeoTIFF = await ensureGeoTiff()
  const tiff = await GeoTIFF.fromBlob(blob)
  const image0 = await tiff.getImage(0)
  const width0 = image0.getWidth()
  const height0 = image0.getHeight()
  const spp0 = image0.getSamplesPerPixel?.() ?? 1
  const { targetW, targetH } = computeTargetSize(width0, height0, maxW, maxH)
  const samples = spp0 >= 3 ? [0, 1, 2] : [0]

  let raster: any
  let rasterW = targetW
  let rasterH = targetH
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      let result: any
      try {
        result = await tiff.readRGB({ width: rasterW, height: rasterH })
      } catch {
        result = await tiff.readRasters({ width: rasterW, height: rasterH, samples, interleave: true })
      }
      if (result && typeof result === 'object' && 'width' in result && 'height' in result) {
        rasterW = (result as any).width
        rasterH = (result as any).height
        raster = (result as any)[0] ?? (result as any).data ?? result
      } else {
        raster = result
      }
      break
    } catch {
      rasterW = Math.max(1, Math.floor(rasterW / 2))
      rasterH = Math.max(1, Math.floor(rasterH / 2))
    }
  }

  if (!raster) {
    const winSize = 1024
    const winW = Math.min(width0, winSize)
    const winH = Math.min(height0, winSize)
    const result = await image0.readRasters({
      window: [0, 0, winW, winH],
      width: Math.min(512, winW),
      height: Math.min(512, winH),
      samples,
      interleave: true
    })
    rasterW = Math.min(512, winW)
    rasterH = Math.min(512, winH)
    raster = result
  }

  const isRgb = raster && (raster.length === rasterW * rasterH * 3 || raster.length === rasterW * rasterH * 4)
  return rasterToCanvas(raster, rasterW, rasterH, isRgb ? 3 : samples.length)
}

const getViewportPoint = (evt: MouseEvent | WheelEvent) => {
  const anyCanvas = canvas as any
  if (anyCanvas && typeof anyCanvas.getViewportPoint === 'function') {
    const p = anyCanvas.getViewportPoint(evt as any)
    return { x: p.x as number, y: p.y as number }
  }
  const el =
    (anyCanvas?.upperCanvasEl as HTMLCanvasElement | undefined) ||
    (anyCanvas?.lowerCanvasEl as HTMLCanvasElement | undefined) ||
    (canvasWrapRef.value as HTMLElement | null) ||
    (evt.target as HTMLElement | null)
  const rect = el?.getBoundingClientRect?.()
  if (rect) return { x: evt.clientX - rect.left, y: evt.clientY - rect.top }
  return { x: evt.clientX, y: evt.clientY }
}

const getScenePoint = (evt: MouseEvent) => {
  const anyCanvas = canvas as any
  if (anyCanvas && typeof anyCanvas.getScenePoint === 'function') {
    const p = anyCanvas.getScenePoint(evt as any)
    return { x: p.x as number, y: p.y as number }
  }
  const vp = getViewportPoint(evt)
  const m = buildViewMatrix()
  const inv = util.invertTransform(m as any)
  const world = util.transformPoint(new Point(vp.x, vp.y), inv as any)
  return { x: world.x as number, y: world.y as number }
}

const getImageSize = () => {
  const w = (bgObject?.width ?? 0) as number
  const h = (bgObject?.height ?? 0) as number
  return { w: Math.max(1, w), h: Math.max(1, h) }
}

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v))

const ROTATE_CURSOR =
  'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'24\' height=\'24\' viewBox=\'0 0 512 512\'%3E%3Cdefs%3E%3Cfilter id=\'s\' x=\'-50%25\' y=\'-50%25\' width=\'200%25\' height=\'200%25\'%3E%3CfeDropShadow dx=\'0\' dy=\'12\' stdDeviation=\'10\' flood-color=\'%23000000\' flood-opacity=\'0.32\'/%3E%3C/filter%3E%3C/defs%3E%3Cg filter=\'url(%23s)\'%3E%3Cpath fill=\'%23ffffff\' d=\'M512 192H320l71.766-71.765C355.5 83.972 307.285 64 256 64s-99.5 19.972-135.765 56.235C83.972 156.5 64 204.715 64 256s19.972 99.5 56.235 135.766C156.5 428.028 204.715 448 256 448s99.5-19.972 135.764-56.236c3.029-3.027 5.932-6.146 8.729-9.334l48.16 42.143C401.729 478.154 332.82 512 256 512 114.615 512 0 397.385 0 256S114.615 0 256 0c70.693 0 134.684 28.663 181.008 74.992L512 0v192z\'/%3E%3C/g%3E%3C/svg%3E") 10 10, auto'

const tMatrix = (tx: number, ty: number) => [1, 0, 0, 1, tx, ty] as const
const sMatrix = (s: number) => [s, 0, 0, s, 0, 0] as const
const rMatrix = (rad: number) => {
  const c = Math.cos(rad)
  const s = Math.sin(rad)
  return [c, s, -s, c, 0, 0] as const
}

const mul = (a: any, b: any) => util.multiplyTransformMatrices(a, b)

const buildViewMatrixNoPan = (zoom: number, deg: number) => {
  const { w, h } = getImageSize()
  const cx = w / 2
  const cy = h / 2
  const rad = (deg * Math.PI) / 180
  return mul(sMatrix(zoom), mul(tMatrix(cx, cy), mul(rMatrix(rad), tMatrix(-cx, -cy))))
}

const buildViewMatrix = () => {
  const m0 = buildViewMatrixNoPan(viewZoom.value, rotationDeg.value)
  return mul(tMatrix(viewPan.value.x, viewPan.value.y), m0)
}

const applyViewTransform = () => {
  if (!canvas || !bgObject) return
  canvas.setViewportTransform(buildViewMatrix() as any)
  canvas.requestRenderAll()
}

const setTool = (t: 'select' | 'rect' | 'polygon') => {
  tool.value = t
  if (!canvas) return
  canvas.selection = t === 'select'
  canvas.defaultCursor = t === 'select' ? 'default' : 'crosshair'
  canvas.skipTargetFind = t !== 'select'
  if (t !== 'select') canvas.discardActiveObject()
  canvas.requestRenderAll()
}

const fitToScreen = () => {
  if (!canvas || !bgObject || !canvasWrapRef.value) return
  const w = canvasWrapRef.value.clientWidth || 1
  const h = canvasWrapRef.value.clientHeight || 1
  const { w: imgW, h: imgH } = getImageSize()
  const rad = (rotationDeg.value * Math.PI) / 180
  const rotW = Math.abs(imgW * Math.cos(rad)) + Math.abs(imgH * Math.sin(rad))
  const rotH = Math.abs(imgW * Math.sin(rad)) + Math.abs(imgH * Math.cos(rad))
  const z = clamp(Math.min(w / Math.max(1, rotW), h / Math.max(1, rotH)), 0.0001, 20)
  const cx = imgW / 2
  const cy = imgH / 2
  viewZoom.value = z
  viewPan.value = { x: w / 2 - z * cx, y: h / 2 - z * cy }
  applyViewTransform()
}

watch(
  rotationDeg,
  (deg, prev) => {
    if (!canvas || !bgObject) return
    const w = canvas.getWidth() || 1
    const h = canvas.getHeight() || 1
    const sc = { x: w / 2, y: h / 2 }
    const oldM0 = buildViewMatrixNoPan(viewZoom.value, Number.isFinite(prev) ? prev : deg)
    const oldM = mul(tMatrix(viewPan.value.x, viewPan.value.y), oldM0)
    const inv = util.invertTransform(oldM as any)
    const world = util.transformPoint(new Point(sc.x, sc.y), inv as any)
    const newM0 = buildViewMatrixNoPan(viewZoom.value, deg)
    const mapped = util.transformPoint(new Point(world.x, world.y), newM0 as any)
    viewPan.value = { x: sc.x - mapped.x, y: sc.y - mapped.y }
    applyViewTransform()
  },
  { flush: 'post' }
)

const cleanupCanvas = () => {
  if (!canvas) return
  canvas.off()
  canvas.dispose()
  canvas = null
  bgObject = null
  objectById.clear()
}

const initCanvas = async () => {
  if (!canvasElRef.value || !canvasWrapRef.value) return
  cleanupCanvas()
  await nextTick()

  canvas = new Canvas(canvasElRef.value, {
    selection: true,
    preserveObjectStacking: true,
    skipOffscreen: false
  })

  const resize = () => {
    if (!canvas || !canvasWrapRef.value) return
    const oldW = canvas.getWidth() || 1
    const oldH = canvas.getHeight() || 1
    const w = Math.max(1, canvasWrapRef.value.clientWidth)
    const h = Math.max(1, canvasWrapRef.value.clientHeight)
    canvas.setWidth(w)
    canvas.setHeight(h)
    canvas.calcOffset()
    if (bgObject) {
      viewPan.value = { x: viewPan.value.x + (w - oldW) / 2, y: viewPan.value.y + (h - oldH) / 2 }
      applyViewTransform()
    } else {
      canvas.requestRenderAll()
    }
  }

  resizeObserver = new ResizeObserver(() => resize())
  resizeObserver.observe(canvasWrapRef.value)
  resize()
  bindCanvasEvents()
}

const clearObjects = () => {
  if (!canvas) return
  const keep = bgObject ? new Set([bgObject]) : new Set()
  const all = canvas.getObjects()
  for (const obj of all) {
    if (!keep.has(obj as any)) canvas.remove(obj)
  }
  objectById.clear()
  canvas.requestRenderAll()
}

const loadImageToCanvas = async (imageId: string) => {
  if (!canvas || !canvasWrapRef.value) return
  const meta = rawImages.value.find((x) => x.id === imageId)
  if (!meta) return

  canvasLoading.value = true
  try {
    if (String(meta.status || '').toLowerCase() === 'failed' && meta.errorMessage) {
      throw new Error(`影像预处理失败：${meta.errorMessage}`)
    }
    const blob = await imagesRepo.getFile(imageId)
    const sameOriginPreview = `/api/v1/images/${encodeURIComponent(imageId)}/preview`
    const fallbackPreviewUrl = meta.previewUrl || meta.thumbnailUrl || sameOriginPreview
    if (!blob && !fallbackPreviewUrl) {
      throw new Error('无法获取影像文件（可能为超大文件且刷新页面后缓存丢失）')
    }

    let img: FabricImage | null = null
    if (blob && (blob.type === 'image/tiff' || isTiffName(meta.name))) {
      const c = await decodeTiffToCanvas(blob, canvasWrapRef.value.clientWidth || 1024, canvasWrapRef.value.clientHeight || 768)
      img = new FabricImage(c, { selectable: false, evented: false, originX: 'left', originY: 'top', left: 0, top: 0 })
    } else {
      // Use same-origin preview endpoint to avoid canvas taint from cross-origin object URLs.
      const url = blob ? URL.createObjectURL(blob) : fallbackPreviewUrl
      if (!url) throw new Error('无法加载影像')
      img = await FabricImage.fromURL(url, { crossOrigin: 'anonymous' } as any)
      if (blob && url.startsWith('blob:')) URL.revokeObjectURL(url)
      img.set({ selectable: false, evented: false, originX: 'left', originY: 'top', left: 0, top: 0 })
    }

    if (!img) throw new Error('影像加载失败')

    clearObjects()
    selectedAnnotationId.value = null
    bgObject = img
    canvas.add(img)
    canvas.sendObjectToBack(img)
    fitToScreen()
  } finally {
    canvasLoading.value = false
  }
}

const renderAnnotations = () => {
  if (!canvas) return
  isApplying = true
  try {
    clearObjects()
    if (bgObject) {
      canvas.add(bgObject)
      canvas.sendObjectToBack(bgObject)
    }
    for (const a of annotations.value) {
      if (a.type === 'rect') {
        const pts = ((a as any).points as XY[] | undefined) ?? rectToPoints(a.rect)
        const obj = buildPolygonObjectFromAbs(
          pts.map((p) => ({ x: p.x, y: p.y })),
          {
            fill: 'rgba(64,158,255,0.18)',
            stroke: '#409EFF',
            cornerColor: '#409EFF',
            lockRotation: false
          }
        )
        ;(obj as any).annotationId = a.id
        objectById.set(a.id, obj)
        canvas.add(obj)
      } else {
        const pts = a.points.map((p) => ({ x: p.x, y: p.y }))
        const obj = buildPolygonObjectFromAbs(pts)
        ;(obj as any).annotationId = a.id
        objectById.set(a.id, obj)
        canvas.add(obj)
      }
    }
    if (selectedAnnotationId.value) {
      const obj = objectById.get(selectedAnnotationId.value)
      if (obj) canvas.setActiveObject(obj)
    }
    canvas.requestRenderAll()
  } finally {
    isApplying = false
  }
}

const removeAnnotation = (id: string) => {
  const next = annotations.value.filter((a) => a.id !== id)
  applyAnnotations(next, true)
  if (selectedAnnotationId.value === id) selectedAnnotationId.value = null
}

const selectAnnotation = (id: string | null) => {
  selectedAnnotationId.value = id
  setRouteAnnotationId(id)
  if (!canvas) return
  if (!id) {
    canvas.discardActiveObject()
    canvas.requestRenderAll()
    return
  }
  const obj = objectById.get(id)
  if (obj) {
    canvas.setActiveObject(obj)
    canvas.requestRenderAll()
  }
}

const handleRowClick = (row: SarAnnotation) => {
  selectAnnotation(row.id)
}

const setRouteAnnotationId = (id: string | null) => {
  const q: any = { ...(route.query as any) }
  if (!id) delete q.annotationId
  else q.annotationId = id
  router.replace({ query: q })
}

const applyMetaEdit = () => {
  const a = selectedAnnotation.value
  if (!a) return
  const next = annotations.value.map((x) => {
    if (x.id !== a.id) return x
    return { ...x, category: editCategory.value, remark: editRemark.value, updatedAt: Date.now() }
  })
  applyAnnotations(next, true)
}

watch(selectedAnnotation, (a) => {
  if (!a) {
    editCategory.value = ''
    editRemark.value = ''
    return
  }
  editCategory.value = a.category
  editRemark.value = a.remark
})

const newId = () => `ANN_${Date.now()}_${Math.random().toString(16).slice(2)}`

const normalizeAbsPoints = (pts: XY[]) => {
  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  for (const p of pts) {
    if (p.x < minX) minX = p.x
    if (p.y < minY) minY = p.y
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return { left: 0, top: 0, points: [] as XY[] }
  return {
    left: minX,
    top: minY,
    points: pts.map((p) => ({ x: p.x - minX, y: p.y - minY }))
  }
}

const rectToPoints = (rect: { x: number; y: number; w: number; h: number }) => {
  return [
    { x: rect.x, y: rect.y },
    { x: rect.x + rect.w, y: rect.y },
    { x: rect.x + rect.w, y: rect.y + rect.h },
    { x: rect.x, y: rect.y + rect.h }
  ]
}

const applyRotateCursor = <T extends Rect | Polygon>(obj: T) => {
  const rotateControl = (obj.controls as any)?.mtr
  if (rotateControl) {
    rotateControl.cursorStyleHandler = () => ROTATE_CURSOR
  }
  return obj
}

const buildPolygonObjectFromAbs = (
  pts: XY[],
  opts?: Partial<ConstructorParameters<typeof Polygon>[1]>
) => {
  const norm = normalizeAbsPoints(pts)
  return applyRotateCursor(new Polygon(
    norm.points.map((p) => ({ x: p.x, y: p.y })),
    {
      left: norm.left,
      top: norm.top,
      originX: 'left',
      originY: 'top',
      fill: 'rgba(103,194,58,0.15)',
      stroke: '#67C23A',
      strokeWidth: 2,
      transparentCorners: false,
      cornerColor: '#67C23A',
      lockRotation: true,
      objectCaching: false,
      ...(opts || {})
    }
  ))
}

const newSampleId = () => `SMP_${Date.now()}_${Math.random().toString(16).slice(2)}`

const canvasToBlob = (c: HTMLCanvasElement, type: SarSample['format'], quality?: number) => {
  return new Promise<Blob>((resolve) => {
    try {
      c.toBlob((b) => resolve(b ?? new Blob()), type, quality)
    } catch {
      // Cross-origin image without CORS will taint canvas and block export.
      resolve(new Blob())
    }
  })
}

const downscaleCanvas = (src: HTMLCanvasElement, maxSize = 256) => {
  const w = src.width
  const h = src.height
  const scale = Math.min(1, maxSize / Math.max(w, h))
  const tw = Math.max(1, Math.round(w * scale))
  const th = Math.max(1, Math.round(h * scale))
  const c = document.createElement('canvas')
  c.width = tw
  c.height = th
  const ctx = c.getContext('2d')
  if (ctx) ctx.drawImage(src, 0, 0, tw, th)
  return c
}

const getBgElement = () => {
  const anyImg = bgObject as any
  const el = (typeof anyImg?.getElement === 'function' ? anyImg.getElement() : anyImg?._element) as
    | HTMLImageElement
    | HTMLCanvasElement
    | undefined
  return el
}

const getAnnotationCropRegion = (ann: SarAnnotation) => {
  const { w: imgW, h: imgH } = getImageSize()
  let minX = 0
  let minY = 0
  let maxX = 0
  let maxY = 0
  let poly: XY[] | null = null

  if (ann.type === 'rect') {
    const pts = (ann as any).points as XY[] | undefined
    if (pts && pts.length >= 3) {
      poly = pts
      minX = Math.min(...pts.map((p) => p.x))
      minY = Math.min(...pts.map((p) => p.y))
      maxX = Math.max(...pts.map((p) => p.x))
      maxY = Math.max(...pts.map((p) => p.y))
    } else {
      minX = ann.rect.x
      minY = ann.rect.y
      maxX = ann.rect.x + ann.rect.w
      maxY = ann.rect.y + ann.rect.h
    }
  } else {
    poly = ann.points
    minX = Math.min(...poly.map((p) => p.x))
    minY = Math.min(...poly.map((p) => p.y))
    maxX = Math.max(...poly.map((p) => p.x))
    maxY = Math.max(...poly.map((p) => p.y))
  }

  const bx = Math.floor(minX)
  const by = Math.floor(minY)
  const ex = Math.ceil(maxX)
  const ey = Math.ceil(maxY)

  const cx = clamp(bx, 0, imgW - 1)
  const cy = clamp(by, 0, imgH - 1)
  const cex = clamp(ex, cx + 1, imgW)
  const cey = clamp(ey, cy + 1, imgH)
  const cw = Math.max(1, Math.round(cex - cx))
  const ch = Math.max(1, Math.round(cey - cy))
  if (cw < 2 || ch < 2) return null

  return { cx, cy, cw, ch, poly }
}

const buildSampleFromAnnotation = async (
  ann: SarAnnotation,
  src: HTMLImageElement | HTMLCanvasElement,
  name: string,
  existing?: SarSample
): Promise<SarSample | null> => {
  if (!currentImageId.value) return null
  const region = getAnnotationCropRegion(ann)
  if (!region) return null

  const { cx, cy, cw, ch, poly } = region
  const out = document.createElement('canvas')
  out.width = cw
  out.height = ch
  const ctx = out.getContext('2d')
  if (!ctx) return null

  if (sampleFormat.value === 'image/jpeg') {
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, cw, ch)
  }
  ctx.drawImage(src, cx, cy, cw, ch, 0, 0, cw, ch)

  if (poly && poly.length >= 3) {
    ctx.globalCompositeOperation = 'destination-in'
    ctx.beginPath()
    ctx.moveTo(poly[0].x - cx, poly[0].y - cy)
    for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i].x - cx, poly[i].y - cy)
    ctx.closePath()
    ctx.fill()
    ctx.globalCompositeOperation = 'source-over'
  }

  const blob = await canvasToBlob(out, sampleFormat.value, sampleFormat.value === 'image/jpeg' ? 0.92 : undefined)
  if (blob.size <= 0) return null
  const thumbCanvas = downscaleCanvas(out, 256)
  const thumbnail = await canvasToBlob(thumbCanvas, 'image/png')
  const now = Date.now()
  return {
    id: existing?.id || newSampleId(),
    name,
    imageId: currentImageId.value,
    imageName: currentImage.value?.name,
    annotationId: ann.id,
    annotationType: ann.type,
    category: ann.category,
    remark: ann.remark,
    format: sampleFormat.value,
    width: cw,
    height: ch,
    image: blob,
    thumbnail,
    createdAt: existing?.createdAt || now,
    updatedAt: now
  }
}

const cropSelectedToSample = async () => {
  const ann = selectedAnnotation.value
  if (!ann || !bgObject || !currentImageId.value) return
  const src = getBgElement()
  if (!src) {
    ElMessage.error('当前影像未就绪')
    return
  }

  const region = getAnnotationCropRegion(ann)
  if (!region) {
    ElMessage.error('裁切区域过小')
    return
  }

  const defaultName = `${currentImage.value?.name || currentImageId.value}_${ann.category || ann.type}_${ann.id}`
  const name = await ElMessageBox.prompt('样本名称', '裁切并保存为样本', {
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputValue: defaultName,
    inputPlaceholder: '输入样本名称'
  })
    .then((r) => r.value)
    .catch(() => '')
  if (!name) return

  const sample = await buildSampleFromAnnotation(ann, src, name)
  if (!sample) {
    ElMessage.error('生成样本失败')
    return
  }
  try {
    await samplesRepo.put(sample)
  } catch (e: any) {
    ElMessage.error(e?.message ? `保存样本失败：${e.message}` : '保存样本失败')
    return
  }
  ElMessage.success('已裁切并保存为样本')
  ElMessageBox.confirm('是否前往样本管理查看？', '已保存', {
    confirmButtonText: '去查看',
    cancelButtonText: '留在此页',
    type: 'success'
  })
    .then(() => {
      router.push({ name: 'sample-manage', query: { highlight: sample.id } })
    })
    .catch(() => undefined)
}

const autoGenerateSamplesForCurrentImage = async () => {
  if (!bgObject || !currentImageId.value) return 0
  const src = getBgElement()
  if (!src) return 0

  const existing = await samplesRepo.list()
  const existingMap = new Map(
    existing.filter((s) => s.imageId === currentImageId.value).map((s) => [s.annotationId, s] as const)
  )

  let saved = 0
  for (const ann of annotations.value) {
    const baseName = `${currentImage.value?.name || currentImageId.value}_${ann.category || ann.type}_${ann.id}`
    const sample = await buildSampleFromAnnotation(ann, src, baseName, existingMap.get(ann.id))
    if (!sample) continue
    await samplesRepo.put(sample)
    saved += 1
  }
  return saved
}

const openMeta = (obj: Rect | Polygon, type: 'rect' | 'polygon') => {
  pendingObject = obj
  pendingType = type
  metaDraft.value = { category: '', remark: '' }
  metaDialogVisible.value = true
}

const cancelMeta = () => {
  metaDialogVisible.value = false
  if (canvas && pendingObject) {
    canvas.remove(pendingObject)
    canvas.requestRenderAll()
  }
  pendingObject = null
  pendingType = null
  setTool('select')
}

const confirmMeta = async () => {
  if (!pendingObject || !pendingType || !canvas) return
  const now = Date.now()
  const id = newId()

  let ann: SarAnnotation | null = null
  if (pendingType === 'rect') {
    if ((pendingObject as any).type === 'polygon') {
      const p = pendingObject as Polygon
      const pts = extractPolygonAbsPoints(p)
      const obj = buildPolygonObjectFromAbs(pts, {
        fill: 'rgba(64,158,255,0.18)',
        stroke: '#409EFF',
        cornerColor: '#409EFF'
      })
      canvas.remove(p)
      canvas.add(obj)
      pendingObject = obj
      const xs = pts.map((q) => q.x)
      const ys = pts.map((q) => q.y)
      const minX = Math.min(...xs)
      const minY = Math.min(...ys)
      const maxX = Math.max(...xs)
      const maxY = Math.max(...ys)
      ann = {
        id,
        type: 'rect',
        category: metaDraft.value.category,
        remark: metaDraft.value.remark,
        createdAt: now,
        updatedAt: now,
        rect: { x: minX, y: minY, w: maxX - minX, h: maxY - minY },
        points: pts
      }
    } else {
      const r = pendingObject as Rect
      const left = (r.left ?? 0) as number
      const top = (r.top ?? 0) as number
      const w = ((r.width ?? 0) as number) * ((r.scaleX ?? 1) as number)
      const h = ((r.height ?? 0) as number) * ((r.scaleY ?? 1) as number)
      r.set({ width: w, height: h, scaleX: 1, scaleY: 1 })
      r.setCoords()
      ann = {
        id,
        type: 'rect',
        category: metaDraft.value.category,
        remark: metaDraft.value.remark,
        createdAt: now,
        updatedAt: now,
        rect: { x: left, y: top, w, h }
      }
    }
  } else {
    const p = pendingObject as Polygon
    const pts = extractPolygonAbsPoints(p)
    const obj = buildPolygonObjectFromAbs(pts)
    canvas.remove(p)
    canvas.add(obj)
    pendingObject = obj
    ann = {
      id,
      type: 'polygon',
      category: metaDraft.value.category,
      remark: metaDraft.value.remark,
      createdAt: now,
      updatedAt: now,
      points: pts
    }
  }

  ;(pendingObject as any).annotationId = id
  metaDialogVisible.value = false
  pendingObject = null
  pendingType = null
  applyAnnotations([...annotations.value, ann], true)
  setTool('select')
  selectAnnotation(id)
  if (autoGenerateSamplesOnSave.value) {
    await saveToLocal()
  } else {
    ElMessage.success('标注已添加（点击保存后可生成样本）')
  }
}

const extractPolygonAbsPoints = (poly: Polygon): XY[] => {
  const matrix = poly.calcTransformMatrix()
  const pathOffset = (poly as any).pathOffset as { x: number; y: number } | undefined
  const ox = pathOffset?.x ?? 0
  const oy = pathOffset?.y ?? 0
  const points = (poly.points || []) as Array<{ x: number; y: number }>
  return points.map((pt) => {
    const p = util.transformPoint(new Point(pt.x - ox, pt.y - oy), matrix as any)
    return { x: p.x, y: p.y }
  })
}

let isPanning = false
let panLast = { x: 0, y: 0 }
let isSpaceDown = false

let isDrawingRect = false
let rectStartVp = { x: 0, y: 0 }
let rectEndVp = { x: 0, y: 0 }
let drawingRect: Polygon | null = null

let polyPoints: XY[] = []
let drawingLine: Polyline | null = null

const snapEnabled = ref(true)
const snapPx = ref(10)

const sceneToViewport = (p: XY) => {
  const m = buildViewMatrix()
  const vp = util.transformPoint(new Point(p.x, p.y), m as any)
  return { x: vp.x as number, y: vp.y as number }
}

const collectSnapTargets = (): Array<{ p: XY; kind: 'start' | 'vertex' }> => {
  const out: Array<{ p: XY; kind: 'start' | 'vertex' }> = []
  if (polyPoints.length) out.push({ p: polyPoints[0], kind: 'start' })
  for (const p of polyPoints) out.push({ p, kind: 'vertex' })

  for (const a of annotations.value) {
    if (a.type === 'polygon') {
      for (const p of a.points) out.push({ p, kind: 'vertex' })
      continue
    }
    const pts = (a as any).points as XY[] | undefined
    if (pts && pts.length >= 3) {
      for (const p of pts) out.push({ p, kind: 'vertex' })
      continue
    }
    const x = a.rect.x
    const y = a.rect.y
    const w = a.rect.w
    const h = a.rect.h
    out.push({ p: { x, y }, kind: 'vertex' })
    out.push({ p: { x: x + w, y }, kind: 'vertex' })
    out.push({ p: { x: x + w, y: y + h }, kind: 'vertex' })
    out.push({ p: { x, y: y + h }, kind: 'vertex' })
  }
  return out
}

const snapScenePoint = (cursorScene: XY, mouseVp: XY) => {
  if (!snapEnabled.value) return { p: cursorScene, snapped: false, kind: null as null | 'start' | 'vertex' }
  const tol = Math.max(1, snapPx.value)
  let best: { p: XY; kind: 'start' | 'vertex'; d2: number } | null = null
  for (const t of collectSnapTargets()) {
    const tvp = sceneToViewport(t.p)
    const dx = tvp.x - mouseVp.x
    const dy = tvp.y - mouseVp.y
    const d2 = dx * dx + dy * dy
    if (d2 > tol * tol) continue
    if (!best || d2 < best.d2) best = { p: t.p, kind: t.kind, d2 }
  }
  if (!best) return { p: cursorScene, snapped: false, kind: null as null | 'start' | 'vertex' }
  return { p: best.p, snapped: true, kind: best.kind }
}

const setDrawingLinePoints = (cursor?: XY) => {
  if (!canvas || !drawingLine) return
  if (!polyPoints.length) return
  const abs = cursor ? [...polyPoints, cursor] : [...polyPoints]
  const pts = abs.length === 1 ? [abs[0], abs[0]] : abs
  drawingLine.set({ points: pts.map((p) => ({ x: p.x, y: p.y })) as any })
  drawingLine.setBoundingBox(true)
  drawingLine.setCoords()
}

const finishPolygonDrawing = () => {
  if (!canvas || tool.value !== 'polygon' || !drawingLine) return
  const raw = [...polyPoints]
  if (raw.length < 3) return
  canvas.remove(drawingLine)
  drawingLine = null
  polyPoints = []
  const poly = buildPolygonObjectFromAbs(raw)
  canvas.add(poly)
  canvas.requestRenderAll()
  openMeta(poly, 'polygon')
}

const cancelDrawing = () => {
  if (!canvas) return
  if (isDrawingRect && drawingRect) {
    canvas.remove(drawingRect)
    drawingRect = null
    isDrawingRect = false
    canvas.requestRenderAll()
  }
  if (drawingLine) {
    canvas.remove(drawingLine)
    drawingLine = null
    polyPoints = []
    canvas.requestRenderAll()
  }
}

const deleteSelected = () => {
  if (!canvas) return
  const obj = canvas.getActiveObject() as any
  const id = obj?.annotationId as string | undefined
  if (!id) return
  removeAnnotation(id)
  canvas.discardActiveObject()
  canvas.requestRenderAll()
}

const undo = () => {
  if (!historyPast.value.length) return
  historyFuture.value.push(cloneAnnotations(annotations.value))
  const prev = historyPast.value.pop() || []
  applyAnnotations(prev, false)
}

const redo = () => {
  if (!historyFuture.value.length) return
  historyPast.value.push(cloneAnnotations(annotations.value))
  const next = historyFuture.value.pop() || []
  applyAnnotations(next, false)
}

const isTypingTarget = (e: KeyboardEvent) => {
  const el = e.target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea') return true
  if ((el as any).isContentEditable) return true
  return false
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.code === 'Space') isSpaceDown = true
  if (e.key === 'Escape') {
    e.preventDefault()
    if (metaDialogVisible.value) {
      cancelMeta()
      return
    }
    cancelDrawing()
    return
  }
  if (isTypingTarget(e)) return
  if (e.key === 'Enter') {
    if (tool.value === 'polygon' && drawingLine) {
      e.preventDefault()
      finishPolygonDrawing()
      return
    }
  }
  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    deleteSelected()
    return
  }
  const k = e.key.toLowerCase()
  if ((e.ctrlKey || e.metaKey) && k === 'z') {
    e.preventDefault()
    undo()
    return
  }
  if ((e.ctrlKey || e.metaKey) && k === 'y') {
    e.preventDefault()
    redo()
  }
}

const onKeyup = (e: KeyboardEvent) => {
  if (e.code === 'Space') isSpaceDown = false
}

const syncObjectToModel = (obj: Rect | Polygon) => {
  const id = (obj as any).annotationId as string | undefined
  if (!id) return
  const idx = annotations.value.findIndex((a) => a.id === id)
  if (idx < 0) return
  const now = Date.now()

  if (annotations.value[idx]?.type === 'rect' && obj.type === 'rect') {
    const r = obj as Rect
    const left = (r.left ?? 0) as number
    const top = (r.top ?? 0) as number
    const w = ((r.width ?? 0) as number) * ((r.scaleX ?? 1) as number)
    const h = ((r.height ?? 0) as number) * ((r.scaleY ?? 1) as number)
    r.set({ width: w, height: h, scaleX: 1, scaleY: 1 })
    r.setCoords()
    const cur = annotations.value[idx] as any
    const next = cloneAnnotations(annotations.value)
    next[idx] = { ...cur, updatedAt: now, rect: { x: left, y: top, w, h } }
    applyAnnotations(next, true)
    return
  }

  if (annotations.value[idx]?.type === 'rect' && obj.type === 'polygon') {
    const p = obj as Polygon
    const pts = extractPolygonAbsPoints(p)
    const xs = pts.map((q) => q.x)
    const ys = pts.map((q) => q.y)
    const minX = Math.min(...xs)
    const minY = Math.min(...ys)
    const maxX = Math.max(...xs)
    const maxY = Math.max(...ys)
    const next = cloneAnnotations(annotations.value)
    next[idx] = {
      ...(next[idx] as any),
      updatedAt: now,
      rect: { x: minX, y: minY, w: maxX - minX, h: maxY - minY },
      points: pts
    }
    applyAnnotations(next, true)
    return
  }

  if (annotations.value[idx]?.type === 'polygon' && obj.type === 'polygon') {
    const p = obj as Polygon
    const pts = extractPolygonAbsPoints(p)
    const next = cloneAnnotations(annotations.value)
    next[idx] = { ...(next[idx] as any), updatedAt: now, points: pts }
    applyAnnotations(next, true)
  }
}

const bindCanvasEvents = () => {
  if (!canvas) return

  canvas.on('mouse:wheel', (opt) => {
    const e = opt.e as WheelEvent
    if (!canvas || !bgObject) return
    const delta = e.deltaY
    const nextZoom = clamp(viewZoom.value * Math.pow(0.999, delta), 0.05, 20)
    const vp = getViewportPoint(e)
    const oldM = buildViewMatrix()
    const inv = util.invertTransform(oldM as any)
    const world = util.transformPoint(new Point(vp.x, vp.y), inv as any)
    viewZoom.value = nextZoom
    const newM0 = buildViewMatrixNoPan(nextZoom, rotationDeg.value)
    const mapped = util.transformPoint(new Point(world.x, world.y), newM0 as any)
    viewPan.value = { x: vp.x - mapped.x, y: vp.y - mapped.y }
    applyViewTransform()
    e.preventDefault()
    e.stopPropagation()
  })

  canvas.on('mouse:down', (opt) => {
    if (!canvas) return
    const e = opt.e as MouseEvent
    if (e.button === 2 || isSpaceDown) {
      isPanning = true
      panLast = { x: e.clientX, y: e.clientY }
      canvas.defaultCursor = 'grab'
      return
    }
    if (!currentImageId.value || !bgObject) return
    if (tool.value === 'rect') {
      isDrawingRect = true
      rectStartVp = getViewportPoint(e)
      rectEndVp = { ...rectStartVp }
      const inv = util.invertTransform(buildViewMatrix() as any)
      const p0 = util.transformPoint(new Point(rectStartVp.x, rectStartVp.y), inv as any)
      const abs = [
        { x: p0.x, y: p0.y },
        { x: p0.x, y: p0.y },
        { x: p0.x, y: p0.y },
        { x: p0.x, y: p0.y }
      ]
      drawingRect = applyRotateCursor(new Polygon(abs as any, {
        fill: 'rgba(64,158,255,0.18)',
        stroke: '#409EFF',
        strokeWidth: 2,
        transparentCorners: false,
        cornerColor: '#409EFF',
        lockRotation: false,
        objectCaching: false,
        selectable: false,
        evented: false
      }))
      drawingRect.setBoundingBox(true)
      canvas.add(drawingRect)
      canvas.requestRenderAll()
      return
    }
    if (tool.value === 'polygon') {
      const mouseVp = getViewportPoint(e)
      const raw = getScenePoint(e)
      const s = snapScenePoint(raw, mouseVp)
      const p = s.p
      if (drawingLine && e.detail >= 2) {
        finishPolygonDrawing()
        return
      }
      if (drawingLine && s.kind === 'start' && polyPoints.length >= 3) {
        finishPolygonDrawing()
        return
      }
      if (!drawingLine) {
        polyPoints = [{ x: p.x, y: p.y }]
        drawingLine = new Polyline(
          [
            { x: p.x, y: p.y },
            { x: p.x, y: p.y }
          ],
          {
            fill: 'rgba(0,0,0,0)',
            stroke: '#67C23A',
            strokeWidth: 2,
            objectCaching: false,
            selectable: false,
            evented: false
          }
        )
        canvas.add(drawingLine)
      } else {
        const last = polyPoints[polyPoints.length - 1]
        if (!last || last.x !== p.x || last.y !== p.y) polyPoints.push({ x: p.x, y: p.y })
        setDrawingLinePoints(polyPoints[polyPoints.length - 1])
      }
      canvas.requestRenderAll()
    }
  })

  canvas.on('mouse:move', (opt) => {
    if (!canvas) return
    const e = opt.e as MouseEvent
    if (isPanning) {
      viewPan.value = { x: viewPan.value.x + (e.clientX - panLast.x), y: viewPan.value.y + (e.clientY - panLast.y) }
      panLast = { x: e.clientX, y: e.clientY }
      applyViewTransform()
      return
    }
    if (tool.value === 'rect' && isDrawingRect && drawingRect) {
      rectEndVp = getViewportPoint(e)
      const x0 = Math.min(rectStartVp.x, rectEndVp.x)
      const y0 = Math.min(rectStartVp.y, rectEndVp.y)
      const x1 = Math.max(rectStartVp.x, rectEndVp.x)
      const y1 = Math.max(rectStartVp.y, rectEndVp.y)
      const inv = util.invertTransform(buildViewMatrix() as any)
      const p00 = util.transformPoint(new Point(x0, y0), inv as any)
      const p10 = util.transformPoint(new Point(x1, y0), inv as any)
      const p11 = util.transformPoint(new Point(x1, y1), inv as any)
      const p01 = util.transformPoint(new Point(x0, y1), inv as any)
      const abs = [
        { x: p00.x, y: p00.y },
        { x: p10.x, y: p10.y },
        { x: p11.x, y: p11.y },
        { x: p01.x, y: p01.y }
      ]
      drawingRect.set({ points: abs.map((p) => ({ x: p.x, y: p.y })) as any })
      drawingRect.setBoundingBox(true)
      drawingRect.setCoords()
      canvas.requestRenderAll()
      return
    }
    if (tool.value === 'polygon' && drawingLine && polyPoints.length) {
      const mouseVp = getViewportPoint(e)
      const raw = getScenePoint(e)
      const s = snapScenePoint(raw, mouseVp)
      const p = s.p
      setDrawingLinePoints({ x: p.x, y: p.y })
      canvas.requestRenderAll()
    }
  })

  canvas.on('mouse:up', () => {
    if (!canvas) return
    if (isPanning) {
      isPanning = false
      canvas.defaultCursor = tool.value === 'select' ? 'default' : 'crosshair'
      return
    }
    if (tool.value === 'rect' && isDrawingRect && drawingRect) {
      const r = drawingRect
      isDrawingRect = false
      drawingRect = null
      const vw = Math.abs(rectEndVp.x - rectStartVp.x)
      const vh = Math.abs(rectEndVp.y - rectStartVp.y)
      if (vw < 3 || vh < 3) {
        canvas.remove(r)
        canvas.requestRenderAll()
        return
      }
      r.set({ selectable: true, evented: true })
      openMeta(r, 'rect')
    }
  })

  canvas.on('mouse:dblclick', () => {
    finishPolygonDrawing()
  })

  canvas.on('selection:created', (e) => {
    const obj = (e.selected?.[0] as any) || null
    const id = obj?.annotationId as string | undefined
    if (id) selectAnnotation(id)
  })

  canvas.on('selection:updated', (e) => {
    const obj = (e.selected?.[0] as any) || null
    const id = obj?.annotationId as string | undefined
    if (id) selectAnnotation(id)
  })

  canvas.on('selection:cleared', () => {
    if (isApplying) return
    selectedAnnotationId.value = null
  })

  canvas.on('object:modified', (e) => {
    if (isApplying) return
    const obj = e.target as any
    if (!obj) return
    if (obj.type !== 'rect' && obj.type !== 'polygon') return
    syncObjectToModel(obj as Rect | Polygon)
  })
}

const loadImages = async () => {
  imagesLoading.value = true
  try {
    rawImages.value = await imagesRepo.list()
  } finally {
    imagesLoading.value = false
  }
}

const setRouteImageId = (id: string) => {
  router.replace({ name: 'annotate', query: { imageId: id } }).catch(() => undefined)
}

const handleImageChange = async (id: string) => {
  if (!id) return
  setRouteImageId(id)
  await loadForImage(id)
}

const loadForImage = async (id: string) => {
  if (!canvas) await initCanvas()
  if (!canvas) return
  historyPast.value = []
  historyFuture.value = []
  await loadImageToCanvas(id)
  const saved = await annotationsRepo.get(id)
  applyAnnotations(saved?.annotations ? cloneAnnotations(saved.annotations) : [], false)
}

const saveToLocal = async () => {
  if (!currentImageId.value) return
  await annotationsRepo.put(buildPayload())
  if (!autoGenerateSamplesOnSave.value) {
    ElMessage.success('已保存到本地')
    return
  }
  if (!annotations.value.length) {
    ElMessage.success('已保存到本地（当前无标注，未生成样本）')
    return
  }
  if (!bgObject) {
    ElMessage.warning('已保存标注，但当前影像未就绪，未自动生成样本')
    return
  }
  try {
    const n = await autoGenerateSamplesForCurrentImage()
    ElMessage.success(`已保存到本地，并自动生成 ${n} 个样本`)
  } catch (e: any) {
    ElMessage.warning(e?.message ? `标注已保存，但自动生成样本失败：${e.message}` : '标注已保存，但自动生成样本失败')
  }
}

const exportJson = () => {
  if (!currentImageId.value) return
  const payload = buildPayload()
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const name = currentImage.value?.name || currentImageId.value
  a.href = url
  a.download = `${name}.annotations.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出')
}

const triggerImport = () => {
  importInputRef.value?.click()
}

const handleImportFile = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const text = await file.text()
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch {
    ElMessage.error('JSON 解析失败')
    return
  }
  if (!parsed || parsed.version !== 1 || typeof parsed.imageId !== 'string' || !Array.isArray(parsed.annotations)) {
    ElMessage.error('不支持的标注文件格式')
    return
  }
  const payload = parsed as AnnotationsFileV1
  if (!currentImageId.value || payload.imageId !== currentImageId.value) {
    const ok = await ElMessageBox.confirm(`导入文件影像ID为 ${payload.imageId}，是否切换影像并导入？`, '导入确认', {
      confirmButtonText: '切换并导入',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => true).catch(() => false)
    if (!ok) return
    currentImageId.value = payload.imageId
    setRouteImageId(payload.imageId)
    await loadForImage(payload.imageId)
  }
  applyAnnotations(cloneAnnotations(payload.annotations), true)
  await annotationsRepo.put({ ...payload, exportedAt: Date.now(), annotations: cloneAnnotations(payload.annotations) })
  ElMessage.success('已导入并保存到本地')
}

onMounted(async () => {
  await initCanvas()
  await loadImages()
  const q = route.query.imageId
  const initial = typeof q === 'string' ? q : ''
  if (initial) currentImageId.value = initial
  if (currentImageId.value) await loadForImage(currentImageId.value)
  applyRouteAnnotation()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
})

onUnmounted(() => {
  if (resizeObserver && canvasWrapRef.value) resizeObserver.unobserve(canvasWrapRef.value)
  resizeObserver = null
  if (persistTimer) window.clearTimeout(persistTimer)
  persistTimer = null
  cleanupCanvas()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
})

watch(
  () => route.query.imageId,
  async (v) => {
    const id = typeof v === 'string' ? v : ''
    if (!id || id === currentImageId.value) return
    currentImageId.value = id
    await loadForImage(id)
  }
)

const applyRouteAnnotation = () => {
  const q = route.query.annotationId
  const id = typeof q === 'string' ? q : ''
  if (!id) return
  if (!annotations.value.some((a) => a.id === id)) return
  selectAnnotation(id)
}

watch(
  () => route.query.annotationId,
  () => {
    applyRouteAnnotation()
  }
)
</script>

<style scoped>
.annotate {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
}

.title h2 {
  margin: 0;
  font-size: 18px;
}

.hint {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.status {
  margin-left: 8px;
  color: #606266;
  font-size: 14px;
}

.workspace {
  flex: 1;
  display: flex;
  overflow: hidden;
  gap: 12px;
  padding-top: 12px;
}

.canvas-wrap {
  flex: 1;
  position: relative;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  overflow: hidden;
  min-height: 520px;
}

.canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.loading-mask {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.55);
}

.sidebar {
  width: 360px;
  display: flex;
  flex-direction: column;
}

.panel {
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 10px;
}

.panel-title {
  font-weight: 600;
  margin-bottom: 10px;
}
</style>
