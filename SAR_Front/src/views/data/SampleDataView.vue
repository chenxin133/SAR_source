<template>
  <div class="sample-data">
    <div class="header-actions">
      <h2>样本数据管理</h2>
      <div class="header-buttons">
        <el-button type="primary" plain @click="uploadVisible = true">本地上传样本</el-button>
        <el-dropdown @command="handleBatchExport">
          <el-button :loading="isBatchExporting">
            批量导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="origin">原格式</el-dropdown-item>
              <el-dropdown-item command="image/png">PNG</el-dropdown-item>
              <el-dropdown-item command="image/jpeg">JPEG</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="reload">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-input v-model="keyword" placeholder="筛选名称 / 样本ID" clearable style="width: 240px" />
      <el-select v-model="categoryFilter" placeholder="全部类别" clearable style="width: 180px">
        <el-option v-for="item in categoryOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="annotationFilter" placeholder="全部标注类型" clearable style="width: 160px">
        <el-option label="矩形" value="rect" />
        <el-option label="多边形" value="polygon" />
      </el-select>
      <el-select v-model="sourceFilter" placeholder="全部来源影像" clearable style="width: 220px">
        <el-option v-for="item in sourceOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="regionFilter" placeholder="全部地区" clearable style="width: 180px">
        <el-option v-for="item in regionOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="frequencyBandFilter" placeholder="全部数据频段" clearable style="width: 180px">
        <el-option v-for="item in frequencyBandOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="polarizationFilter" placeholder="全部极化方式" clearable style="width: 180px">
        <el-option v-for="item in polarizationOptions" :key="item" :label="item" :value="item" />
      </el-select>
    </div>

    <el-table v-if="filteredTableData.length" :data="filteredTableData" style="width: 100%" border>
      <el-table-column prop="id" label="样本ID" width="120" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="category" label="类别" width="140" />
      <el-table-column prop="source" label="来源影像" min-width="180" />
      <el-table-column prop="annotation" label="标注" width="220" />
      <el-table-column prop="size" label="尺寸" width="110" />
      <el-table-column prop="time" label="时间" width="160" />
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="scope">
          <el-button size="small" type="primary" plain @click="openPreview(scope.row)">预览</el-button>
          <el-button size="small" type="success" plain :disabled="!canOpenAnnotate(scope.row.raw)" @click="openAnnotate(scope.row)">标注</el-button>
          <el-dropdown trigger="click" @command="(cmd: unknown) => handleExportOne(scope.row.raw, cmd)">
            <el-button size="small" plain>导出<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="origin">原格式</el-dropdown-item>
                <el-dropdown-item command="image/png">PNG</el-dropdown-item>
                <el-dropdown-item command="image/jpeg">JPEG</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" type="danger" plain @click="deleteSample(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-else class="empty-state">
      <el-empty :description="tableEmptyText" />
    </div>

    <el-dialog v-model="previewVisible" title="样本预览" width="760px" destroy-on-close @closed="clearPreview">
      <el-image v-if="previewUrl" :src="previewUrl" fit="contain" style="width: 100%; height: 420px; background: #111" />
      <div v-if="previewSample" class="preview-meta">
        <div>名称：{{ previewSample.name }}</div>
        <div>类别：{{ previewSample.category || '未分类' }}</div>
        <div>来源：{{ previewSample.imageName || previewSample.imageId }}</div>
        <div>标注：{{ previewSample.annotationType }} / {{ previewSample.annotationId }}</div>
        <div>尺寸：{{ previewSample.width }} × {{ previewSample.height }}</div>
      </div>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="本地上传样本" width="520px" destroy-on-close @closed="resetUploadForm">
      <el-form ref="uploadFormRef" :model="uploadForm" :rules="uploadRules" label-width="90px">
        <el-form-item label="样本名称" prop="name">
          <el-input v-model="uploadForm.name" placeholder="请输入样本名称" />
        </el-form-item>
        <el-form-item label="来源影像" prop="imageId">
          <el-select v-model="uploadForm.imageId" filterable placeholder="选择来源影像" style="width: 100%">
            <el-option v-for="image in images" :key="image.id" :label="`${image.name} (${image.id})`" :value="image.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标注类型" prop="annotationType">
          <el-select v-model="uploadForm.annotationType" style="width: 100%">
            <el-option label="矩形" value="rect" />
            <el-option label="多边形" value="polygon" />
          </el-select>
        </el-form-item>
        <el-form-item label="类别" prop="category">
          <el-input v-model="uploadForm.category" placeholder="请输入类别" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.remark" type="textarea" :rows="3" placeholder="输入备注" />
        </el-form-item>
        <el-form-item label="文件" required>
          <el-upload
            ref="uploadRef"
            action="#"
            :auto-upload="false"
            :limit="1"
            :show-file-list="false"
            :file-list="uploadFileList"
            :on-change="handleUploadFileChange"
            :on-remove="handleUploadFileRemove"
            :on-exceed="handleUploadFileExceed"
          >
            <el-button type="primary">选择图片</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 .png / .jpg / .jpeg / .webp</div>
            </template>
          </el-upload>
          <div v-if="uploadFileList.length" class="selected-file">
            <span class="selected-file__name" :title="uploadFileList[0].name">{{ uploadFileList[0].name }}</span>
            <el-button class="selected-file__remove" link @click="clearUploadFile">移除</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="uploadVisible = false" :disabled="uploading">取消</el-button>
          <el-button type="primary" :loading="uploading" @click="submitLocalUpload">
            {{ uploading ? '上传中...' : '确定上传' }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile, type UploadFiles, type UploadInstance, type UploadUserFile } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { imagesRepo } from '../../repositories/imagesRepo'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarImage } from '../../types/sar'
import type { SarSample } from '../../types/samples'
import { unpackImageDescription } from '../../utils/imageMetadata'
import { buildPolarizationOptions } from '../../constants/polarizations'

const router = useRouter()
const route = useRoute()

type SampleUploadForm = {
  name: string
  imageId: string
  annotationType: 'rect' | 'polygon'
  category: string
  remark: string
  file: File | null
}

type Row = {
  id: string
  name: string
  category: string
  source: string
  region: string
  frequencyBand: string
  polarization: string
  annotation: string
  size: string
  time: string
  raw: SarSample
}

const samples = ref<SarSample[]>([])
const isBatchExporting = ref(false)
const images = ref<SarImage[]>([])
const keyword = ref('')
const categoryFilter = ref('')
const annotationFilter = ref('')
const sourceFilter = ref('')
const regionFilter = ref('')
const frequencyBandFilter = ref('')
const polarizationFilter = ref('')

const normalizeFilterValue = (value: unknown) => String(value ?? '').trim().toLowerCase()

const buildUniqueOptions = (values: Array<string | undefined | null>) => {
  return Array.from(
    new Set(
      values
        .map((value) => String(value ?? '').trim())
        .filter((value) => value.length > 0)
    )
  ).sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

const imageMetaById = computed(() => {
  const map = new Map<string, SarImage>()
  for (const img of images.value) map.set(img.id, img)
  return map
})

const isLocalSample = (sample: SarSample) => sample.imageId.startsWith('local-upload:')
const canOpenAnnotate = (sample: SarSample) => !isLocalSample(sample) && imageMetaById.value.has(sample.imageId)

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

const tableData = computed<Row[]>(() => {
  return samples.value.map((s) => {
    const imageMeta = imageMetaById.value.get(s.imageId)
    const parsed = unpackImageDescription(imageMeta?.description)
    return {
      id: s.id,
      name: s.name,
      category: s.category || '未分类',
      source: isLocalSample(s) ? '本地上传' : s.imageName || s.imageId,
      region: parsed.region || '',
      frequencyBand: String(imageMeta?.frequencyBand || ''),
      polarization: String(imageMeta?.polarization || ''),
      annotation: isLocalSample(s) ? '本地上传 / 无关联标注' : `${s.annotationType} / ${s.annotationId}`,
      size: `${s.width}×${s.height}`,
      time: formatTime(s.updatedAt || s.createdAt),
      raw: s
    }
  })
})

const categoryOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.category)))
const sourceOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.source)))
const regionOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.region)))
const frequencyBandOptions = ['Ka', 'Ku', 'X', 'C']
const polarizationOptions = computed(() => buildPolarizationOptions(tableData.value.map((row) => row.polarization)))

const filteredTableData = computed<Row[]>(() => {
  const keywordValue = normalizeFilterValue(keyword.value)
  const categoryValue = normalizeFilterValue(categoryFilter.value)
  const annotationValue = normalizeFilterValue(annotationFilter.value)
  const sourceValue = normalizeFilterValue(sourceFilter.value)
  const regionValue = normalizeFilterValue(regionFilter.value)
  const frequencyBandValue = normalizeFilterValue(frequencyBandFilter.value)
  const polarizationValue = normalizeFilterValue(polarizationFilter.value)
  return tableData.value.filter((row) => {
    const matchKeyword =
      !keywordValue ||
      row.id.toLowerCase().includes(keywordValue) ||
      row.name.toLowerCase().includes(keywordValue) ||
      row.source.toLowerCase().includes(keywordValue) ||
      row.region.toLowerCase().includes(keywordValue) ||
      row.frequencyBand.toLowerCase().includes(keywordValue) ||
      row.polarization.toLowerCase().includes(keywordValue)
    const matchCategory = !categoryValue || row.category.toLowerCase() === categoryValue
    const matchAnnotation = !annotationValue || row.raw.annotationType.toLowerCase() === annotationValue
    const matchSource = !sourceValue || row.source.toLowerCase() === sourceValue
    const matchRegion = !regionValue || row.region.toLowerCase() === regionValue
    const matchFrequencyBand = !frequencyBandValue || row.frequencyBand.toLowerCase() === frequencyBandValue
    const matchPolarization = !polarizationValue || row.polarization.toLowerCase() === polarizationValue
    return matchKeyword && matchCategory && matchAnnotation && matchSource && matchRegion && matchFrequencyBand && matchPolarization
  })
})

const hasActiveFilters = computed(() => {
  return [keyword.value, categoryFilter.value, annotationFilter.value, sourceFilter.value, regionFilter.value, frequencyBandFilter.value, polarizationFilter.value].some(
    (value) => String(value || '').trim().length > 0
  )
})

const tableEmptyText = computed(() => {
  return hasActiveFilters.value ? '没有匹配的样本数据' : '暂无样本数据'
})

const previewVisible = ref(false)
const previewSample = ref<SarSample | null>(null)
const previewUrl = ref<string>('')

const clearPreview = () => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewSample.value = null
}

const openPreview = (row: Row) => {
  clearPreview()
  previewSample.value = row.raw
  previewUrl.value = URL.createObjectURL(row.raw.thumbnail || row.raw.image)
  previewVisible.value = true
}

const openAnnotate = (row: Row) => {
  if (!canOpenAnnotate(row.raw)) {
    ElMessage.info('本地上传样本未关联原始影像，暂不支持跳转标注页')
    return
  }
  const query: Record<string, string> = { imageId: row.raw.imageId }
  if (row.raw.annotationId && !row.raw.annotationId.startsWith('manual:')) query.annotationId = row.raw.annotationId
  router.push({ name: 'annotate', query })
}

type ExportCommand = 'origin' | 'image/png' | 'image/jpeg'
const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'sample'
const extFromType = (type: SarSample['format']) => (type === 'image/tiff' ? 'tif' : type === 'image/png' ? 'png' : 'jpg')
const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1500)
}
const transcodeImageBlob = async (blob: Blob, target: SarSample['format']) => {
  if (blob.type === target) return blob
  const bmp = await createImageBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = bmp.width
  canvas.height = bmp.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建导出画布')
  if (target === 'image/jpeg') {
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  ctx.drawImage(bmp, 0, 0)
  bmp.close()
  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((out) => (out ? resolve(out) : reject(new Error('导出失败'))), target, target === 'image/jpeg' ? 0.92 : undefined)
  })
}
const exportOne = async (sample: SarSample, command: ExportCommand) => {
  const blob =
    command === 'origin'
      ? await samplesRepo.exportBlob(sample, 'source')
      : sample.format === 'image/tiff'
        ? await samplesRepo.exportBlob(sample, command)
        : await transcodeImageBlob(sample.image, command)
  const type: SarSample['format'] =
    command === 'origin'
      ? blob.type === 'image/tiff'
        ? 'image/tiff'
        : blob.type === 'image/jpeg'
          ? 'image/jpeg'
          : 'image/png'
      : command
  triggerDownload(blob, `${sanitizeFileName(sample.name)}_${sample.id}.${extFromType(type)}`)
}
const handleExportOne = async (sample: SarSample, command: unknown) => {
  try {
    await exportOne(sample, command as ExportCommand)
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}
const handleBatchExport = async (command: unknown) => {
  if (!filteredTableData.value.length || isBatchExporting.value) return
  isBatchExporting.value = true
  try {
    for (const row of filteredTableData.value) {
      await exportOne(row.raw, command as ExportCommand)
      await new Promise((resolve) => setTimeout(resolve, 80))
    }
    ElMessage.success(`已开始导出 ${filteredTableData.value.length} 个样本`)
  } finally {
    isBatchExporting.value = false
  }
}

const reload = async () => {
  try {
    const [sampleList, imageList] = await Promise.all([samplesRepo.list(), imagesRepo.list().catch(() => [])])
    samples.value = sampleList
    images.value = imageList
    const highlightId = typeof route.query.highlight === 'string' ? route.query.highlight : ''
    if (highlightId) {
      const sample = sampleList.find((item) => item.id === highlightId)
      if (sample) openPreview({ raw: sample } as Row)
      const query = { ...route.query }
      delete query.highlight
      void router.replace({ query })
    }
  } catch (e: any) {
    samples.value = []
    images.value = []
    ElMessage.error(e?.message ? `样本加载失败：${e.message}` : '样本加载失败')
  }
}

const handleSamplesChanged = () => {
  void reload()
}

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()
const uploadFileList = ref<UploadUserFile[]>([])
const uploadForm = reactive<SampleUploadForm>({
  name: '',
  imageId: '',
  annotationType: 'rect',
  category: '',
  remark: '',
  file: null
})

const uploadRules = {
  name: [{ required: true, message: '请输入样本名称', trigger: 'blur' }],
  imageId: [{ required: true, message: '请选择来源影像', trigger: 'change' }],
  annotationType: [{ required: true, message: '请选择标注类型', trigger: 'change' }],
  category: [{ required: true, message: '请输入类别', trigger: 'blur' }]
} as const

const allowedUploadExts = new Set(['png', 'jpg', 'jpeg', 'webp'])

const resetUploadForm = () => {
  uploadForm.name = ''
  uploadForm.imageId = ''
  uploadForm.annotationType = 'rect'
  uploadForm.category = ''
  uploadForm.remark = ''
  uploadForm.file = null
  uploadFileList.value = []
  uploadRef.value?.clearFiles()
  uploadFormRef.value?.clearValidate()
  uploading.value = false
}

const clearUploadFile = () => {
  uploadRef.value?.clearFiles()
  uploadFileList.value = []
  uploadForm.file = null
}

const isAllowedUploadFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return allowedUploadExts.has(ext)
}

const handleUploadFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  uploadFileList.value = uploadFiles as UploadUserFile[]
  const raw = uploadFile.raw ?? null
  if (!raw) {
    uploadForm.file = null
    return
  }
  if (!isAllowedUploadFile(raw)) {
    ElMessage.error('仅支持 PNG/JPG/JPEG/WEBP 图片样本')
    clearUploadFile()
    return
  }
  uploadForm.file = raw
  if (!uploadForm.name) {
    uploadForm.name = raw.name.replace(/\.[^.]+$/, '')
  }
}

const handleUploadFileRemove = () => {
  uploadForm.file = null
  uploadFileList.value = []
}

const handleUploadFileExceed = () => {
  ElMessage.warning('一次只能选择 1 个样本文件')
}

const canvasToBlob = (canvas: HTMLCanvasElement, type: SarSample['format'], quality?: number) => {
  return new Promise<Blob>((resolve) => {
    canvas.toBlob((blob) => resolve(blob ?? new Blob()), type, quality)
  })
}

const downscaleCanvas = (src: HTMLCanvasElement, maxSize = 256) => {
  const scale = Math.min(1, maxSize / Math.max(src.width, src.height))
  const out = document.createElement('canvas')
  out.width = Math.max(1, Math.round(src.width * scale))
  out.height = Math.max(1, Math.round(src.height * scale))
  const ctx = out.getContext('2d')
  if (ctx) ctx.drawImage(src, 0, 0, out.width, out.height)
  return out
}

const buildLocalSamplePayload = async (file: File) => {
  const bitmap = await createImageBitmap(file)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close()
    throw new Error('无法创建样本画布')
  }
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()

  const format: SarSample['format'] = file.type === 'image/jpeg' ? 'image/jpeg' : 'image/png'
  const imageBlob = format === 'image/jpeg' ? file : await canvasToBlob(canvas, 'image/png')
  const thumbnail = await canvasToBlob(downscaleCanvas(canvas, 256), 'image/png')
  const now = Date.now()
  const id = `sample-${now}-${Math.random().toString(36).slice(2, 8)}`
  const sourceImage = imageMetaById.value.get(uploadForm.imageId)
  return {
    id,
    name: uploadForm.name.trim(),
    imageId: uploadForm.imageId,
    imageName: sourceImage?.name || uploadForm.imageId,
    annotationId: `manual:${id}`,
    annotationType: uploadForm.annotationType,
    category: uploadForm.category.trim(),
    remark: uploadForm.remark.trim(),
    format,
    width: canvas.width,
    height: canvas.height,
    image: imageBlob,
    thumbnail,
    createdAt: now,
    updatedAt: now
  } satisfies SarSample
}

const submitLocalUpload = async () => {
  await uploadFormRef.value?.validate()
  if (!uploadForm.file) {
    ElMessage.warning('请选择样本文件')
    return
  }
  uploading.value = true
  try {
    const sample = await buildLocalSamplePayload(uploadForm.file)
    await samplesRepo.put(sample)
    await reload()
    uploadVisible.value = false
    ElMessage.success('本地样本上传成功')
    resetUploadForm()
  } catch (e: any) {
    ElMessage.error(e?.message ? `样本上传失败：${e.message}` : '样本上传失败')
  } finally {
    uploading.value = false
  }
}

const deleteSample = (row: Row) => {
  ElMessageBox.confirm('确定要删除该样本吗？', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
    .then(async () => {
      await samplesRepo.delete(row.id)
      await reload()
      ElMessage.success('删除成功')
    })
    .catch(() => undefined)
}

onMounted(async () => {
  window.addEventListener(samplesRepo.changedEventName, handleSamplesChanged)
  window.addEventListener('focus', handleSamplesChanged)
  await reload()
})

onUnmounted(() => {
  window.removeEventListener(samplesRepo.changedEventName, handleSamplesChanged)
  window.removeEventListener('focus', handleSamplesChanged)
})
</script>

<style scoped>
.header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.header-buttons {
    display: flex;
    gap: 12px;
}

.filter-bar {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}

.empty-state {
    width: 100%;
    min-height: 240px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #fff;
    border: 1px solid #ebeef5;
    border-radius: 4px;
}

.preview-meta {
    margin-top: 10px;
    color: #606266;
    font-size: 13px;
    line-height: 22px;
}

.selected-file {
    margin-top: 10px;
    width: 100%;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    background: #f5f7fa;
}

.selected-file__name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #606266;
}

.selected-file__remove {
    flex-shrink: 0;
}
</style>
