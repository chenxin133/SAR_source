<template>
  <div class="raw-data">
    <div class="header-actions">
      <h2>原始影像管理</h2>
      <div>
        <el-button v-if="!isBackendMode" @click="handleExportClick">导出本地数据包</el-button>
        <el-button type="primary" @click="handleUploadClick">
          <el-icon><Upload /></el-icon> 上传影像
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-input v-model="keyword" placeholder="筛选名称 / ID" clearable style="width: 240px" />
      <PinnedFilterSelect v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px" preference-key="raw-statusFilter" :options="statusOptions" />
      <PinnedFilterSelect v-model="satelliteFilter" placeholder="全部卫星源" clearable style="width: 180px" preference-key="raw-satelliteFilter" :options="satelliteOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="regionFilter" placeholder="全部地区" clearable style="width: 180px" preference-key="raw-regionFilter" :options="regionOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="frequencyBandFilter" placeholder="全部数据频段" clearable style="width: 180px" preference-key="raw-frequencyBandFilter" :options="frequencyBandOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="polarizationFilter" placeholder="全部极化方式" clearable style="width: 180px" preference-key="raw-polarizationFilter" :options="polarizationOptions.map(value => ({ value, label: value }))" />
      <PinnedFilterSelect v-model="resolutionFilter" placeholder="全部分辨率" clearable filterable style="width: 180px" preference-key="raw-resolutionFilter" :options="resolutionOptions" />
    </div>

    <!-- Data Table -->
    <el-table
      v-if="filteredImages.length"
      :data="filteredImages"
      style="width: 100%"
      border
      v-loading="store.loading"
    >
      <el-table-column prop="id" label="ID" width="220" />
      <el-table-column prop="name" label="影像名称" min-width="200" />
      <el-table-column v-if="!isBackendMode" prop="satellite" label="卫星源" width="150" />
      <el-table-column prop="acquisitionDate" label="采集时间" width="180" />
      <el-table-column label="分辨率" width="140">
        <template #default="{ row }">{{ resolutionLabel(row.resolution) }}</template>
      </el-table-column>
      <el-table-column prop="fileSize" label="大小" width="120" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="scope">
          <el-tag :type="getStatusTagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="220">
        <template #default="scope">
          <span v-if="scope.row.errorMessage">{{ scope.row.errorMessage }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="scope">
          <div class="table-actions">
            <el-button class="table-actions__button" size="small" type="primary" plain @click="handlePreview(scope.row)">
              <el-icon><Picture /></el-icon> 预览
            </el-button>
            <el-button class="table-actions__button" size="small" type="success" plain @click="handleAnnotate(scope.row)">
              <el-icon><Edit /></el-icon> 标注
            </el-button>
            <el-button class="table-actions__button" size="small" @click="handleView(scope.row)">查看详情</el-button>
            <el-button v-if="isBackendMode && scope.row.status === 'failed'" class="table-actions__button" size="small" type="warning" plain
              :loading="regeneratingId === scope.row.id" :disabled="!!regeneratingId" @click="handleRegeneratePreview(scope.row)">重新生成预览</el-button>
            <el-button class="table-actions__button" size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div v-else class="empty-state" v-loading="store.loading">
      <el-empty :description="tableEmptyText" />
    </div>

    <RawImageUploadDialog v-model="uploadVisible" />

    <!-- Details Dialog -->
    <el-dialog v-model="detailsVisible" title="影像详情" width="600px" destroy-on-close>
        <RawImageDetails v-if="selectedImage" :key="selectedImage.id" :image="selectedImage"
          :save-metadata="(patch) => store.updateImage(selectedImage!.id, patch)">
          <template #thumbnail>
                <el-image 
                    v-if="(selectedImage.thumbnailUrl || selectedImage.previewUrl) && !isTiffFile(selectedImage.name)"
                    style="width: 100px; height: 100px" 
                    :src="selectedImage.thumbnailUrl || selectedImage.previewUrl" 
                    fit="cover"
                    @click="handlePreview(selectedImage)"
                    class="thumbnail-preview"
                />
                <el-image
                    v-else-if="selectedImage.thumbnailUrl && isTiffFile(selectedImage.name)"
                    style="width: 100px; height: 100px"
                    :src="selectedImage.thumbnailUrl"
                    fit="cover"
                    @click="handlePreview(selectedImage)"
                    class="thumbnail-preview"
                />
                <el-button v-else-if="isTiffFile(selectedImage.name)" type="primary" link @click="handlePreview(selectedImage)">
                    点击预览TIFF
                </el-button>
                <span v-else>无预览图</span>
          </template>
        </RawImageDetails>
        <template #footer>
            <el-button type="primary" plain @click="handlePreview(selectedImage!)" v-if="selectedImage?.previewUrl || selectedImage?.thumbnailUrl">
                全屏预览
            </el-button>
            <el-button @click="detailsVisible = false">关闭</el-button>
        </template>
    </el-dialog>

    <!-- Image Previewer -->
    <ImageViewer
        v-model="previewVisible"
        :src="previewUrl"
        :blob="previewBlob"
        :title="previewTitle"
    />
  </div>
</template>

<script setup lang="ts">
import PinnedFilterSelect from '../../components/PinnedFilterSelect.vue'
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRawDataStore } from '../../stores/rawData'
import { imagesRepo } from '../../repositories/imagesRepo'
import type { SarImage } from '../../types/sar'
import ImageViewer from '../../components/ImageViewer.vue'
import RawImageUploadDialog from '../../components/raw/RawImageUploadDialog.vue'
import RawImageDetails from '../../components/raw/RawImageDetails.vue'
import { getStorageMode } from '../../config/storage'
import { exportLocalDataPackage } from '../../utils/migrationExport'
import { unpackImageDescription } from '../../utils/imageMetadata'
import { buildResolutionOptions, resolutionKey, resolutionLabel } from '../../utils/resolution'

const store = useRawDataStore()
const router = useRouter()
const isBackendMode = computed(() => getStorageMode() === 'backend')
const regeneratingId = ref('')
const handleRegeneratePreview = async (row: SarImage) => {
    if (regeneratingId.value) return
    regeneratingId.value = row.id
    try {
        const saved = await imagesRepo.ensureHighResolutionPreview(row.id, 8192, true)
        if (saved) Object.assign(row, saved)
        ElMessage.success('预览已重新生成，无需重新上传')
    } catch (error) {
        ElMessage.error(error instanceof Error ? error.message : '预览重新生成失败')
        await store.fetchImages()
    } finally {
        regeneratingId.value = ''
    }
}
const keyword = ref('')
const statusFilter = ref('')
const satelliteFilter = ref('')
const regionFilter = ref('')
const frequencyBandFilter = ref('')
const polarizationFilter = ref('')
const resolutionFilter = ref('')

const normalizeFilterValue = (value: unknown) => String(value ?? '').trim().toLowerCase()

const buildUniqueOptions = (values: Array<string | undefined | null>) => {
    return Array.from(
        new Set(
            values
                .map((value) => String(value || '').trim())
                .filter((value) => value.length > 0)
        )
    ).sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

type ImageFilter = 'status' | 'satellite' | 'region' | 'resolution' | 'frequencyBand' | 'polarization'
const statusOptions = computed(() => {
    const available = new Set(filterImages('status').map(img => img.status))
    return [{ value: 'pending', label: '待处理' }, { value: 'processing', label: '处理中' },
        { value: 'uploaded', label: '已上传' }, { value: 'ready', label: '已就绪' }, { value: 'failed', label: '失败' }].filter(item => available.has(item.value as SarImage['status']))
})
const satelliteOptions = computed(() => buildUniqueOptions(filterImages('satellite').map(img => img.satellite)))
const regionOptions = computed(() => buildUniqueOptions(filterImages('region').map(img => unpackImageDescription(img.description).region)))
const resolutionOptions = computed(() => buildResolutionOptions(filterImages('resolution').map(img => img.resolution)))
const frequencyBandOptions = computed(() => buildUniqueOptions(filterImages('frequencyBand').map(img => img.frequencyBand)))
const polarizationOptions = computed(() => buildUniqueOptions(filterImages('polarization').map(img => img.polarization)))

const getImageRegion = (img?: SarImage | null) => unpackImageDescription(img?.description).region
const getImageRemark = (img?: SarImage | null) => unpackImageDescription(img?.description).remark

onMounted(() => {
    store.fetchImages()
})

const filterImages = (omit?: ImageFilter) => {
    const keywordValue = normalizeFilterValue(keyword.value)
    const statusValue = normalizeFilterValue(statusFilter.value)
    const satelliteValue = normalizeFilterValue(satelliteFilter.value)
    const regionValue = normalizeFilterValue(regionFilter.value)
    const frequencyBandValue = normalizeFilterValue(frequencyBandFilter.value)
    const polarizationValue = normalizeFilterValue(polarizationFilter.value)

    return store.images.filter((img) => {
        const nameValue = String(img.name || '').toLowerCase()
        const descriptionValue = getImageRemark(img).toLowerCase()
        const regionText = getImageRegion(img).toLowerCase()
        const satelliteText = String(img.satellite || '').toLowerCase()
        const frequencyBandText = String(img.frequencyBand || '').toLowerCase()
        const polarizationText = String(img.polarization || '').toLowerCase()
        const matchKeyword =
            !keywordValue ||
            img.id.toLowerCase().includes(keywordValue) ||
            nameValue.includes(keywordValue) ||
            descriptionValue.includes(keywordValue) ||
            regionText.includes(keywordValue)
        const matchStatus = omit === 'status' || !statusValue || String(img.status || '').toLowerCase() === statusValue
        const matchSatellite = omit === 'satellite' || !satelliteValue || satelliteText === satelliteValue
        const matchRegion = omit === 'region' || !regionValue || regionText === regionValue
        const matchFrequencyBand = omit === 'frequencyBand' || !frequencyBandValue || frequencyBandText === frequencyBandValue
        const matchPolarization = omit === 'polarization' || !polarizationValue || polarizationText === polarizationValue
        return (omit === 'resolution' || !resolutionFilter.value || resolutionKey(img.resolution) === resolutionFilter.value) && matchKeyword && matchStatus && matchSatellite && matchRegion && matchFrequencyBand && matchPolarization
    })
}
const filteredImages = computed(() => filterImages())
const hasActiveFilters = computed(() => {
    return [
        keyword.value,
        resolutionFilter.value,
        statusFilter.value,
        satelliteFilter.value,
        regionFilter.value,
        frequencyBandFilter.value,
        polarizationFilter.value,
    ].some((value) => String(value || '').trim().length > 0)
})

const tableEmptyText = computed(() => {
    return hasActiveFilters.value ? '没有匹配的原始影像' : '暂无原始影像'
})

const isTiffFile = (name?: string) => {
    if (!name) return false
    const n = name.toLowerCase()
    return n.endsWith('.tif') || n.endsWith('.tiff')
}

const getStatusTagType = (status: string) => {
    const s = String(status || '').toLowerCase()
    if (s === 'ready' || s === 'uploaded' || s === 'succeeded') return 'success'
    if (s === 'failed' || s === 'error') return 'danger'
    if (s === 'processing' || s === 'pending') return 'warning'
    return 'info'
}

// --- Upload Logic ---
const uploadVisible = ref(false)

const handleUploadClick = () => {
    uploadVisible.value = true
}

const handleExportClick = async () => {
    await exportLocalDataPackage()
}

// --- View Details Logic ---
const detailsVisible = ref(false)
const selectedImage = ref<SarImage | null>(null)

const handleView = (row: SarImage) => {
    selectedImage.value = row
    detailsVisible.value = true
}

// --- Preview Logic ---
const previewVisible = ref(false)
const previewUrl = ref('')
const previewTitle = ref('')
const previewBlob = ref<Blob | undefined>(undefined)

const handlePreview = async (row: SarImage) => {
    previewTitle.value = row.name
    previewBlob.value = undefined
    previewUrl.value = ''
    const sameOriginPreview = `/api/v1/images/${encodeURIComponent(row.id)}/preview`

    const lightweightPreview = row.previewUrl || row.thumbnailUrl || (isBackendMode.value ? sameOriginPreview : '')
    if (lightweightPreview) {
        previewUrl.value = lightweightPreview
        previewVisible.value = true
        if (row.originalPersistent === false) {
            ElMessage.warning(row.previewNotice || '该大文件原图仅本次会话可用，当前展示的是持久化预览图。')
        }
        return
    }

    const blob = await store.getFileBlob(row.id)
    if (blob) {
        previewBlob.value = blob
        previewVisible.value = true
        return
    }

    if (row.originalPersistent === false) {
        ElMessage.warning(row.previewNotice || '原图超过 200MB，仅当前会话可用，刷新后若无持久化预览将无法打开。')
        return
    }
    if (row.errorMessage) {
        ElMessage.error(`当前影像预览生成失败：${row.errorMessage}`)
        return
    }
    ElMessage.info('该影像暂无可预览文件，可重新上传或生成预览后再试。')
}

const handleAnnotate = (row: SarImage) => {
    router.push({ name: 'annotate', query: { imageId: row.id } })
}

// --- Delete Logic ---
const handleDelete = (row: SarImage) => {
    ElMessageBox.confirm(
        `确定要删除影像 "${row.name}" 吗?`,
        '删除确认',
        {
            confirmButtonText: '确定删除',
            cancelButtonText: '取消',
            type: 'warning',
        }
    )
    .then(async () => {
        await store.deleteImage(row.id)
    })
    .catch(() => {
        // catch cancel
    })
}
</script>

<style scoped>
.header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
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
.progress-bar {
    margin-top: 10px;
}
.thumbnail-preview {
    cursor: pointer;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
}
.error-text {
    color: #f56c6c;
    white-space: pre-wrap;
    word-break: break-word;
}

.table-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.table-actions__button {
    width: calc(50% - 4px);
    margin: 0;
    justify-content: center;
}
</style>
