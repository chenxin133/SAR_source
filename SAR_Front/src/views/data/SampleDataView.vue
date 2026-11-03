<template>
  <div class="sample-data">
    <div class="header-actions">
      <h2>样本数据管理</h2>
      <div class="header-buttons">
        <el-button type="primary" plain @click="uploadVisible = true">本地上传样本</el-button>
        <el-select v-model="exportResolution" aria-label="批量导出分辨率" style="width: 180px" placeholder="导出分辨率">
          <el-option label="原分辨率" value="" />
          <el-option v-for="value in batchResolutionOptions" :key="value" :label="`${value} m`" :value="value" />
        </el-select>
        <el-dropdown trigger="click" :disabled="!batchRows.length || isBatchExporting" @command="handleBatchExport">
          <el-button :loading="isBatchExporting" :disabled="!batchRows.length">
            {{ exportScope === 'selected' ? '导出选中' : '导出筛选结果' }}（{{ batchRows.length }}）<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="origin">原格式</el-dropdown-item>
              <el-dropdown-item command="image/tiff">可视化 TIFF</el-dropdown-item>
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
      <PinnedFilterSelect v-model="categoryFilter" placeholder="全部类别" clearable style="width: 180px" preference-key="samples-categoryFilter" :options="categoryOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="annotationFilter" placeholder="全部标注类型" clearable style="width: 160px" preference-key="samples-annotationFilter" :options="annotationOptions.map(value => ({ value, label: value === 'polygon' ? '多边形' : '矩形' }))" />
      <PinnedFilterSelect v-model="sourceFilter" placeholder="全部来源影像" clearable style="width: 220px" preference-key="samples-sourceFilter" :options="sourceOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="regionFilter" placeholder="全部地区" clearable style="width: 180px" preference-key="samples-regionFilter" :options="regionOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="frequencyBandFilter" placeholder="全部数据频段" clearable style="width: 180px" preference-key="samples-frequencyBandFilter" :options="frequencyBandOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="polarizationFilter" placeholder="全部极化方式" clearable style="width: 180px" preference-key="samples-polarizationFilter" :options="polarizationOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="resolutionFilter" placeholder="全部分辨率" clearable filterable style="width: 180px" preference-key="samples-resolutionFilter" :options="resolutionOptions" />
    </div>

    <div class="batch-scope">
      <el-radio-group v-model="exportScope" aria-label="批量导出范围">
        <el-radio-button value="selected">勾选样本（{{ selectedRows.length }}）</el-radio-button>
        <el-radio-button value="filtered">全部筛选结果（{{ filteredTableData.length }}）</el-radio-button>
      </el-radio-group>
      <span>勾选表格左侧复选框；导出包含影像和配套 XML。</span>
    </div>

    <el-table v-if="filteredTableData.length" :data="filteredTableData" row-key="id" style="width: 100%" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="id" label="样本ID" width="120" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="category" label="类别" width="140" />
      <el-table-column prop="source" label="来源影像" min-width="180" />
      <el-table-column prop="annotation" label="标注" width="220" />
      <el-table-column label="分辨率" width="140">
        <template #default="{ row }">{{ resolutionLabel(row.resolution) }}</template>
      </el-table-column>
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
                <el-dropdown-item command="image/tiff">可视化 TIFF</el-dropdown-item>
                <el-dropdown-item command="image/png">PNG</el-dropdown-item>
                <el-dropdown-item command="image/jpeg">JPEG</el-dropdown-item>
              <el-dropdown-item v-for="target in coarserResolutions([effectiveResolution(scope.row.raw)])" :key="target" :command="`downsample:${target}`" divided>
                降采样 {{ target }} m（原格式）
              </el-dropdown-item>
              <el-dropdown-item v-if="!coarserResolutions([effectiveResolution(scope.row.raw)]).length" disabled divided>
                无可用的更粗分辨率
              </el-dropdown-item>
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
      <el-image v-if="previewUrl" class="sample-preview-image" :src="previewUrl" fit="contain" style="width: 100%; height: 420px" />
      <div v-if="previewSample" class="preview-meta">
        <div>名称：{{ previewSample.name }}</div>
        <div>类别：{{ previewSample.category || '未分类' }}</div>
        <div>来源：{{ previewSample.imageName || previewSample.imageId || '本地上传（未关联）' }}</div>
        <div>标注：{{ previewSample.annotationType }} / {{ previewSample.annotationId }}</div>
        <div>尺寸：{{ previewSample.width }} × {{ previewSample.height }}</div>
      </div>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="本地上传样本" width="520px" destroy-on-close @closed="resetUploadForm">
      <el-form ref="uploadFormRef" :model="uploadForm" :rules="uploadRules" label-width="90px">
        <el-alert title="按 类别_频段_分辨率_编号 自动命名，并生成同名 XML；编号从 0001 开始。" type="info" :closable="false" />
        <el-form-item label="来源影像" prop="imageId">
          <el-select v-model="uploadForm.imageId" filterable clearable placeholder="来源影像（可选）" style="width: 100%">
            <el-option v-for="image in images" :key="image.id" :label="`${image.name} (${image.id})`" :value="image.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="分辨率" required>
          <el-input v-model="uploadForm.resolution" :placeholder="uploadForm.imageId ? '留空跟随来源影像，例如 1m' : '必填，例如 1m'" />
        </el-form-item>
        <el-form-item label="频段" required>
          <el-select v-model="uploadForm.frequencyBand" clearable filterable allow-create placeholder="可从来源影像或 XML 读取" style="width:100%">
            <el-option v-for="band in frequencyBandOptions" :key="band" :value="band" :label="band" />
          </el-select>
        </el-form-item>
        <el-form-item label="配套 XML">
          <XmlMetadataPicker ref="sampleXmlPicker" :image-file="uploadForm.file" :image-filename="uploadForm.file?.name" :disabled="uploading"
            @parsed="applySampleXml" @cleared="clearSampleXml" @parsing="sampleXmlParsing = $event" />
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
            :accept="SAMPLE_UPLOAD_ACCEPT"
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
              <div class="el-upload__tip">支持 .png / .jpg / .jpeg / .webp / .tif / .tiff</div>
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
          <el-button type="primary" :loading="uploading" :disabled="sampleXmlParsing" @click="submitLocalUpload">
            {{ uploading ? '上传中...' : '确定上传' }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import PinnedFilterSelect from '../../components/PinnedFilterSelect.vue'
import XmlMetadataPicker from '../../components/XmlMetadataPicker.vue'
import type { XmlAttachment } from '../../types/metadata'
import { applyXmlAutofill, clearXmlAutofill } from '../../utils/xmlAutofill'
import { ImportCancelledError } from '../../utils/duplicateImport'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile, type UploadFiles, type UploadInstance, type UploadUserFile } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { imagesRepo } from '../../repositories/imagesRepo'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarImage } from '../../types/sar'
import type { SarSample } from '../../types/samples'
import { unpackImageDescription } from '../../utils/imageMetadata'
import { buildResolutionOptions, resolutionKey, resolutionLabel, coarserResolutions } from '../../utils/resolution'
import { buildLocalSampleImage, isAllowedSampleFile, SAMPLE_UPLOAD_ACCEPT } from '../../utils/sampleUpload'

const exportResolution = ref<number | ''>('')
const effectiveResolution = (sample: SarSample) => sample.resolution || imageMetaById.value.get(sample.imageId)?.resolution || ''
const batchResolutionOptions = computed(() => coarserResolutions(batchRows.value.map((row) => row.resolution)))
const router = useRouter()
const route = useRoute()

type SampleUploadForm = {
  name: string
  imageId: string
  resolution: string
  frequencyBand: string
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
  resolution: string
  frequencyBand: string
  polarization: string
  annotation: string
  size: string
  time: string
  raw: SarSample
}

const samples = ref<SarSample[]>([])
const isBatchExporting = ref(false)
const exportScope = ref<'selected' | 'filtered'>('selected')
const selectedIds = ref<string[]>([])
const selectedRows = computed(() => filteredTableData.value.filter(row => selectedIds.value.includes(row.id)))
const batchRows = computed(() => exportScope.value === 'selected' ? selectedRows.value : filteredTableData.value)
const handleSelectionChange = (rows: Row[]) => { selectedIds.value = rows.map(row => row.id) }
const images = ref<SarImage[]>([])
const keyword = ref('')
const categoryFilter = ref('')
const annotationFilter = ref('')
const sourceFilter = ref('')
const regionFilter = ref('')
const frequencyBandFilter = ref('')
const polarizationFilter = ref('')
const resolutionFilter = ref('')

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

const isLocalSample = (sample: SarSample) => !sample.imageId || sample.imageId.startsWith('local-upload:')
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
      resolution: s.resolution || imageMeta?.resolution || '',
      frequencyBand: s.frequencyBand || String(imageMeta?.frequencyBand || ''),
      polarization: String(imageMeta?.polarization || ''),
      annotation: isLocalSample(s) ? '本地上传 / 无关联标注' : `${s.annotationType} / ${s.annotationId}`,
      size: `${s.width}×${s.height}`,
      time: formatTime(s.updatedAt || s.createdAt),
      raw: s
    }
  })
})

type SampleFilter = 'resolution' | 'category' | 'annotation' | 'source' | 'region' | 'frequencyBand' | 'polarization'
const resolutionOptions = computed(() => buildResolutionOptions(filterRows('resolution').map(row => row.resolution)))
const categoryOptions = computed(() => buildUniqueOptions(filterRows('category').map(row => row.category)))
const annotationOptions = computed(() => [...new Set(filterRows('annotation').map(row => row.raw.annotationType))])
const sourceOptions = computed(() => buildUniqueOptions(filterRows('source').map(row => row.source)))
const regionOptions = computed(() => buildUniqueOptions(filterRows('region').map(row => row.region)))
const frequencyBandOptions = computed(() => buildUniqueOptions(filterRows('frequencyBand').map(row => row.frequencyBand)))
const polarizationOptions = computed(() => buildUniqueOptions(filterRows('polarization').map(row => row.polarization)))

const filterRows = (omit?: SampleFilter): Row[] => {
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
    const matchCategory = omit === 'category' || !categoryValue || row.category.toLowerCase() === categoryValue
    const matchAnnotation = omit === 'annotation' || !annotationValue || row.raw.annotationType.toLowerCase() === annotationValue
    const matchSource = omit === 'source' || !sourceValue || row.source.toLowerCase() === sourceValue
    const matchRegion = omit === 'region' || !regionValue || row.region.toLowerCase() === regionValue
    const matchFrequencyBand = omit === 'frequencyBand' || !frequencyBandValue || row.frequencyBand.toLowerCase() === frequencyBandValue
    const matchPolarization = omit === 'polarization' || !polarizationValue || row.polarization.toLowerCase() === polarizationValue
    return (omit === 'resolution' || !resolutionFilter.value || resolutionKey(row.resolution) === resolutionFilter.value) && matchKeyword && matchCategory && matchAnnotation && matchSource && matchRegion && matchFrequencyBand && matchPolarization
  })
}
const filteredTableData = computed(() => filterRows())

const hasActiveFilters = computed(() => {
  return [resolutionFilter.value, keyword.value, categoryFilter.value, annotationFilter.value, sourceFilter.value, regionFilter.value, frequencyBandFilter.value, polarizationFilter.value].some(
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
  // Legacy PNG thumbnails discarded alpha; the full sample retains its mask.
  previewUrl.value = URL.createObjectURL(row.raw.format === 'image/png' ? row.raw.image : row.raw.thumbnail || row.raw.image)
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

type ExportCommand = 'origin' | 'image/tiff' | 'image/png' | 'image/jpeg'
const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1500)
}
const exportOne = async (sample: SarSample, command: ExportCommand, targetResolution?: number) => {
  const bundle = await samplesRepo.exportBundle([sample], command === 'origin' ? 'source' : command, targetResolution, imageMetaById.value)
  triggerDownload(bundle, `${sample.name}.zip`)
}
const handleExportOne = async (sample: SarSample, command: unknown) => {
  try {
    const value = String(command)
    const target = value.startsWith('downsample:') ? Number(value.split(':')[1]) : undefined
    await exportOne(sample, target != null ? 'origin' : command as ExportCommand, target)
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}
const handleBatchExport = async (command: unknown) => {
  if (!batchRows.value.length || isBatchExporting.value) return
  const rows = [...batchRows.value]
  const target = exportResolution.value === '' ? undefined : exportResolution.value
  if (target != null && !batchResolutionOptions.value.includes(target)) {
    ElMessage.warning('本次导出的样本中有未知分辨率或不满足降采样条件的样本，请重新选择导出分辨率')
    return
  }
  isBatchExporting.value = true
  try {
    const format = command === 'origin' ? 'source' : command as SarSample['format']
    const bundle = await samplesRepo.exportBundle(rows.map((row) => row.raw), format, target, imageMetaById.value)
    triggerDownload(bundle, 'samples.zip')
    ElMessage.success(`已开始导出 ${rows.length} 个样本`)
  } catch (error: any) {
    ElMessage.error(error?.message || '批量导出失败')
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

const sampleXmlPicker = ref<InstanceType<typeof XmlMetadataPicker>>()
const sampleXml = ref<XmlAttachment | null>(null)
const sampleXmlParsing = ref(false)
let sampleXmlAuto: Record<string, string> = {}
const clearSampleXml = () => {
  clearXmlAutofill(uploadForm, sampleXmlAuto)
  sampleXmlAuto = {}; sampleXml.value = null
}
const applySampleXml = (value: XmlAttachment) => {
  sampleXmlAuto = applyXmlAutofill(uploadForm, { resolution: value.metadata.resolution, frequencyBand: value.metadata.frequency_band, category: value.metadata.category }, sampleXmlAuto)
  sampleXml.value = value
}
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()
const uploadFileList = ref<UploadUserFile[]>([])
const uploadForm = reactive<SampleUploadForm>({
  name: '',
  imageId: '',
  resolution: '',
  frequencyBand: '',
  annotationType: 'rect',
  category: '',
  remark: '',
  file: null
})

const uploadRules = {
  annotationType: [{ required: true, message: '请选择标注类型', trigger: 'change' }],
  category: [{ required: true, message: '请输入类别', trigger: 'blur' }]
} as const

const resetUploadForm = () => {
  uploadForm.name = ''
  uploadForm.imageId = ''
  sampleXmlPicker.value?.clear()
  uploadForm.resolution = ''
  uploadForm.frequencyBand = ''
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

const handleUploadFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  uploadFileList.value = uploadFiles as UploadUserFile[]
  const raw = uploadFile.raw ?? null
  if (!raw) {
    uploadForm.file = null
    return
  }
  if (!isAllowedSampleFile(raw)) {
    ElMessage.error('仅支持 PNG/JPG/JPEG/WEBP/TIF/TIFF 图片样本')
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

const buildLocalSamplePayload = async (file: File) => {
  const payload = await buildLocalSampleImage(file)
  const now = Date.now()
  const id = `sample-${now}-${Math.random().toString(36).slice(2, 8)}`
  const sourceImage = imageMetaById.value.get(uploadForm.imageId)
  return {
    id,
    name: uploadForm.name.trim(),
    imageId: uploadForm.imageId,
    resolution: uploadForm.resolution.trim(),
    frequencyBand: uploadForm.frequencyBand.trim(),
    metadataXmlFile: sampleXml.value?.file,
    sceneMetadata: sampleXml.value?.metadata,
    imageName: sourceImage?.name || uploadForm.imageId,
    annotationId: `manual:${id}`,
    annotationType: uploadForm.annotationType,
    category: uploadForm.category.trim(),
    remark: uploadForm.remark.trim(),
    ...payload,
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
  const source = imageMetaById.value.get(uploadForm.imageId)
  if (!(uploadForm.resolution.trim() || source?.resolution)) return void ElMessage.warning('请填写分辨率或选择有分辨率的来源影像')
  if (!(uploadForm.frequencyBand.trim() || source?.frequencyBand)) return void ElMessage.warning('请填写频段或选择有频段的来源影像')
  uploading.value = true
  try {
    const sample = await buildLocalSamplePayload(uploadForm.file)
    await samplesRepo.put(sample)
    await reload()
    uploadVisible.value = false
    ElMessage.success('样本已导入或使用已有记录')
    resetUploadForm()
  } catch (e: any) {
    if (e instanceof ImportCancelledError) return
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
.batch-scope { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.batch-scope > span { color: #909399; font-size: 12px; }
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

.sample-preview-image {
    background: repeating-conic-gradient(#e7e7e7 0% 25%, #fff 0% 50%) 0 / 20px 20px;
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
