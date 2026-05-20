<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="80%"
    top="5vh"
    append-to-body
    destroy-on-close
    custom-class="image-viewer-dialog"
  >
    <div 
      class="image-container" 
      @wheel.prevent="handleWheel" 
      @mousedown="startDrag" 
      v-loading="loading"
      ref="containerRef"
    >
      <div v-if="error" class="error-message">
        <el-empty :description="error" />
      </div>
      <div v-else-if="!hasContent" class="no-image">
        <el-empty description="暂无预览图像" />
      </div>
      
      <!-- Canvas Container for TIFF -->
      <div 
        v-show="isTiff && !error"
        ref="canvasContainerRef"
        class="canvas-wrapper"
        :style="imageStyle"
      ></div>

      <!-- Img for normal images -->
      <img
        v-if="!isTiff && displaySrc && !error"
        ref="imgRef"
        :src="displaySrc"
        class="preview-image"
        :style="imageStyle"
        @load="resetImage"
      />
    </div>
    <template #footer>
        <div class="viewer-controls">
            <el-button-group>
                <el-button @click="zoomIn"><el-icon><ZoomIn /></el-icon></el-button>
                <el-button @click="zoomOut"><el-icon><ZoomOut /></el-icon></el-button>
                <el-button @click="resetImage"><el-icon><Refresh /></el-icon> 重置</el-button>
            </el-button-group>
            <el-switch
              v-if="isTiff"
              v-model="singleBandLog"
              active-text="单波段Log增强"
              style="margin-left: 12px;"
            />
            <el-button @click="visible = false" style="margin-left: 20px;">关闭</el-button>
        </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const ensureGeoTiff = async () => {
  const w = window as any
  if (w.GeoTIFF?.fromBlob && w.GeoTIFF?.fromUrl) {
    return { fromBlob: w.GeoTIFF.fromBlob as (b: Blob) => Promise<any>, fromUrl: w.GeoTIFF.fromUrl as (u: string) => Promise<any> }
  }

  try {
    const mod = await import('geotiff')
    const fromBlob = (mod as any).fromBlob
    const fromUrl = (mod as any).fromUrl
    if (typeof fromBlob !== 'function' || typeof fromUrl !== 'function') {
      throw new Error('geotiff 未导出 fromBlob/fromUrl')
    }
    return { fromBlob: fromBlob as (b: Blob) => Promise<any>, fromUrl: fromUrl as (u: string) => Promise<any> }
  } catch {
    throw new Error('GeoTIFF 依赖未安装：请先执行 npm install 安装 geotiff/ol 相关依赖')
  }
}

const props = defineProps<{
  modelValue: boolean
  src?: string
  blob?: Blob
  title?: string
}>()

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const displaySrc = ref('')
const loading = ref(false)
const error = ref('')
const isTiff = ref(false)
const singleBandLog = ref(true)
const hasContent = ref(false)
const canvasContainerRef = ref<HTMLDivElement | null>(null)
const objectUrl = ref<string | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

const computePercentileRange = (raster: any, len: number, noData?: number) => {
  const sampleCount = Math.min(200000, len)
  const step = Math.max(1, Math.floor(len / sampleCount))
  const values: number[] = []
  for (let i = 0; i < len; i += step) {
    const v = raster[i]
    if (noData != null && Number.isFinite(noData) && v === noData) continue
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

const rasterToCanvas = (
  raster: any,
  width: number,
  height: number,
  samplesPerPixel: number,
  opts?: { noData?: number; useLog?: boolean }
) => {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas

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
    const noData = opts?.noData
    const { min, max } = computePercentileRange(raster, len, noData)
    const useLog = opts?.useLog ?? false
    for (let i = 0; i < len; i++) {
      const v = raster[i] ?? 0
      if (!Number.isFinite(v) || (noData != null && Number.isFinite(noData) && v === noData)) {
        data[i * 4 + 0] = 0
        data[i * 4 + 1] = 0
        data[i * 4 + 2] = 0
        data[i * 4 + 3] = 0
        continue
      }
      const c = stretchValue(v, min, max, useLog)
      data[i * 4 + 0] = c
      data[i * 4 + 1] = c
      data[i * 4 + 2] = c
      data[i * 4 + 3] = 255
    }
  }

  ctx.putImageData(imgData, 0, 0)
  return canvas
}

// Image manipulation state
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const isDragging = ref(false)
const startX = ref(0)
const startY = ref(0)

const imageStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
  transition: isDragging.value ? 'none' : 'transform 0.1s ease-out',
  transformOrigin: 'center center'
}))

const resetImage = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

const zoomIn = () => {
  scale.value = Math.min(scale.value * 1.2, 10)
}

const zoomOut = () => {
  scale.value = Math.max(scale.value / 1.2, 0.1)
}

const handleWheel = (e: WheelEvent) => {
  if (e.deltaY < 0) {
    zoomIn()
  } else {
    zoomOut()
  }
}

const onVisibilityChange = () => {
  if (document.hidden) stopDrag()
}

const startDrag = (e: MouseEvent) => {
  // Only allow drag if left button is pressed
  if (e.button !== 0) return
  
  e.preventDefault()
  isDragging.value = true
  startX.value = e.clientX - translateX.value
  startY.value = e.clientY - translateY.value
  
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
  window.addEventListener('blur', stopDrag)
  document.addEventListener('mouseleave', stopDrag)
  document.addEventListener('visibilitychange', onVisibilityChange)
}

const onDrag = (e: MouseEvent) => {
  if (!isDragging.value) return
  translateX.value = e.clientX - startX.value
  translateY.value = e.clientY - startY.value
}

const stopDrag = () => {
  isDragging.value = false
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
  window.removeEventListener('blur', stopDrag)
  document.removeEventListener('mouseleave', stopDrag)
  document.removeEventListener('visibilitychange', onVisibilityChange)
}

// Cleanup canvas
const cleanupCanvas = () => {
  if (canvasContainerRef.value) {
    canvasContainerRef.value.innerHTML = ''
  }
}

const cleanupObjectUrl = () => {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = null
  }
}

const computeTargetSize = (width: number, height: number, maxW: number, maxH: number) => {
  const safeW = Number.isFinite(width) && width > 0 ? width : 1
  const safeH = Number.isFinite(height) && height > 0 ? height : 1

  const maxPreviewPixels = 250_000
  const scaleToFit = Math.min(1, Math.min(maxW / safeW, maxH / safeH))
  const scaleToCap = Math.min(1, Math.sqrt(maxPreviewPixels / (safeW * safeH)))
  const scale = Math.max(0.0001, Math.min(scaleToFit, scaleToCap))

  return {
    targetW: Math.max(1, Math.round(safeW * scale)),
    targetH: Math.max(1, Math.round(safeH * scale))
  }
}

const mountCanvas = async (canvas: HTMLCanvasElement) => {
  cleanupCanvas()
  canvas.style.display = 'block'
  canvas.style.maxWidth = '100%'
  canvas.style.maxHeight = '100%'
  if (canvasContainerRef.value) {
    ;(canvasContainerRef.value as unknown as HTMLDivElement).appendChild(canvas)
    return
  }
  await nextTick()
  if (canvasContainerRef.value) {
    ;(canvasContainerRef.value as unknown as HTMLDivElement).appendChild(canvas)
  }
}

let loadSeq = 0

const loadContent = async () => {
  const seq = ++loadSeq
  error.value = ''
  cleanupCanvas()
  cleanupObjectUrl()
  resetImage()
  
  if (!props.src && !props.blob) {
    displaySrc.value = ''
    hasContent.value = false
    isTiff.value = false
    return
  }

  hasContent.value = true
  
  const srcLower = (props.src || '').toLowerCase()
  const blobType = (props.blob?.type || '').toLowerCase()
  const isTiffFile =
    srcLower.endsWith('.tiff') ||
    srcLower.endsWith('.tif') ||
    blobType.includes('tiff') ||
    blobType.includes('geotiff')

  isTiff.value = isTiffFile

  if (isTiffFile) {
    loading.value = true
    try {
      const { fromBlob, fromUrl } = await ensureGeoTiff()
      const tiff = props.blob ? await fromBlob(props.blob) : await fromUrl(props.src as string)
      if (seq !== loadSeq) return

      const image0 = await tiff.getImage(0)
      if (seq !== loadSeq) return
      const width0 = image0.getWidth()
      const height0 = image0.getHeight()
      const spp0 = image0.getSamplesPerPixel?.() ?? 1
      const noDataRaw = image0.getGDALNoData?.()
      const noData = Number.isFinite(Number(noDataRaw)) ? Number(noDataRaw) : undefined

      const cw = containerRef.value?.clientWidth || 1024
      const ch = containerRef.value?.clientHeight || 600
      const { targetW, targetH } = computeTargetSize(width0, height0, Math.max(1024, cw), Math.max(768, ch))
      const samples = spp0 >= 3 ? [0, 1, 2] : [0]
      const decodeToCanvas = async (w: number, h: number) => {
        let result: any
        try {
          result = await tiff.readRGB({ width: w, height: h })
        } catch {
          result = await tiff.readRasters({ width: w, height: h, samples, interleave: true })
        }
        const raster = (result && typeof result === 'object' && 0 in result) ? (result as any)[0] : result
        const isRgb = raster && (raster.length === w * h * 3 || raster.length === w * h * 4)
        return rasterToCanvas(raster, w, h, isRgb ? 3 : samples.length, {
          noData,
          useLog: spp0 < 3 && singleBandLog.value
        })
      }

      const lowMax = 512
      const lowScale = Math.min(1, lowMax / Math.max(width0, height0))
      const lowW = Math.max(1, Math.round(width0 * lowScale))
      const lowH = Math.max(1, Math.round(height0 * lowScale))
      const baseCanvas = await decodeToCanvas(lowW, lowH).catch(async () => {
        const winW = Math.min(width0, 1024)
        const winH = Math.min(height0, 1024)
        const result = await image0.readRasters({
          window: [0, 0, winW, winH],
          width: Math.min(512, winW),
          height: Math.min(512, winH),
          samples,
          interleave: true
        })
        const rw = Math.min(512, winW)
        const rh = Math.min(512, winH)
        return rasterToCanvas(result, rw, rh, samples.length, {
          noData,
          useLog: true
        })
      })
      if (seq !== loadSeq) return
      await mountCanvas(baseCanvas)

      const progressiveSizes = [1024, 1536, Math.max(targetW, targetH)]
      for (const maxEdge of progressiveSizes) {
        const scale = Math.min(1, maxEdge / Math.max(width0, height0))
        const w = Math.max(1, Math.round(width0 * scale))
        const h = Math.max(1, Math.round(height0 * scale))
        if (w <= lowW && h <= lowH) continue
        try {
          const better = await decodeToCanvas(w, h)
          if (seq !== loadSeq) return
          await mountCanvas(better)
        } catch {
          continue
        }
      }
    } catch (e: any) {
      console.error('Failed to load TIFF', e)
      const msg = String(e?.message || '未知错误')
      if (msg.toLowerCase().includes('allocation') || msg.toLowerCase().includes('memory')) {
        error.value = '无法加载 TIFF 影像: 内存不足。该文件需要内置概览（overviews）或转换为 COG 才能在浏览器稳定预览。'
      } else {
        error.value = '无法加载 TIFF 影像: ' + msg
      }
      if (props.src) {
        displaySrc.value = props.src
        isTiff.value = false
      }
    } finally {
      loading.value = false
    }
  } else {
    if (props.blob) {
      objectUrl.value = URL.createObjectURL(props.blob)
      displaySrc.value = objectUrl.value
    } else {
      displaySrc.value = props.src as string
    }
    loading.value = false
  }
}

watch(() => [props.src, props.blob, props.title], loadContent, { immediate: true })
watch(singleBandLog, () => {
  if (visible.value && isTiff.value) loadContent()
})
watch(visible, (v) => {
  if (!v) stopDrag()
})

// Ensure cleanup on unmount
onUnmounted(() => {
    cleanupCanvas()
    cleanupObjectUrl()
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
})
</script>

<style scoped>
.image-container {
  height: 60vh;
  width: 100%;
  overflow: hidden;
  background-color: #f0f2f5;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: grab;
  position: relative;
  border: 1px solid #dcdfe6;
}

.image-container:active {
  cursor: grabbing;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  user-select: none;
  pointer-events: none; /* Prevent native drag */
  display: block;
}

.canvas-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    max-width: 100%;
    max-height: 100%;
    pointer-events: none; /* Allow drag on container */
}

/* Deep selector to target the canvas appended dynamically */
.canvas-wrapper :deep(canvas) {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
}

.viewer-controls {
    display: flex;
    justify-content: center;
    align-items: center;
}

.no-image, .error-message {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
    width: 100%;
}
</style>
