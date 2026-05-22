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
      <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px">
        <el-option label="待处理" value="pending" />
        <el-option label="处理中" value="processing" />
        <el-option label="已上传" value="uploaded" />
        <el-option label="已就绪" value="ready" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-input v-model="satelliteFilter" placeholder="筛选卫星源" clearable style="width: 180px" />
    </div>

    <!-- Data Table -->
    <el-table :data="filteredImages" style="width: 100%" border v-loading="store.loading">
      <el-table-column prop="id" label="ID" width="220" />
      <el-table-column prop="name" label="影像名称" min-width="200" />
      <el-table-column v-if="!isBackendMode" prop="satellite" label="卫星源" width="150" />
      <el-table-column prop="acquisitionDate" label="采集时间" width="180" />
      <el-table-column prop="fileSize" label="大小" width="120" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="scope">
          <el-tag :type="getStatusTagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="scope">
          <el-button size="small" type="primary" plain @click="handlePreview(scope.row)">
            <el-icon><Picture /></el-icon> 预览
          </el-button>
          <el-button size="small" type="success" plain @click="handleAnnotate(scope.row)">
            <el-icon><Edit /></el-icon> 标注
          </el-button>
          <el-button size="small" @click="handleView(scope.row)">查看详情</el-button>
          <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <RawImageUploadDialog v-model="uploadVisible" />

    <!-- Details Dialog -->
    <el-dialog v-model="detailsVisible" title="影像详情" width="600px">
        <el-descriptions :column="1" border v-if="selectedImage">
            <el-descriptions-item label="ID">{{ selectedImage.id }}</el-descriptions-item>
            <el-descriptions-item label="名称">{{ selectedImage.name }}</el-descriptions-item>
            <el-descriptions-item label="缩略图">
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
            </el-descriptions-item>
            <el-descriptions-item v-if="!isBackendMode" label="卫星源">{{ selectedImage.satellite }}</el-descriptions-item>
            <el-descriptions-item label="采集时间">{{ selectedImage.acquisitionDate }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ selectedImage.fileSize }}</el-descriptions-item>
            <el-descriptions-item v-if="!isBackendMode" label="分辨率">{{ selectedImage.resolution || '-' }}</el-descriptions-item>
            <el-descriptions-item v-if="!isBackendMode" label="极化方式">{{ selectedImage.polarization || '-' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
                <el-tag size="small">{{ selectedImage.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="selectedImage.originalPersistent === false" label="预览提示">
                <el-alert
                    :title="selectedImage.previewNotice || '原图超过 200MB，仅当前会话可用；系统将优先展示持久化预览图。'"
                    type="warning"
                    :closable="false"
                    show-icon
                />
            </el-descriptions-item>
            <el-descriptions-item v-if="!isBackendMode" label="备注">{{ selectedImage.description || '无' }}</el-descriptions-item>
        </el-descriptions>
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
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRawDataStore } from '../../stores/rawData'
import type { SarImage } from '../../types/sar'
import ImageViewer from '../../components/ImageViewer.vue'
import RawImageUploadDialog from '../../components/raw/RawImageUploadDialog.vue'
import { getStorageMode } from '../../config/storage'
import { exportLocalDataPackage } from '../../utils/migrationExport'

const store = useRawDataStore()
const router = useRouter()
const isBackendMode = computed(() => getStorageMode() === 'backend')
const keyword = ref('')
const statusFilter = ref('')
const satelliteFilter = ref('')

onMounted(() => {
    store.fetchImages()
})

const filteredImages = computed(() => {
    const keywordValue = keyword.value.trim().toLowerCase()
    const statusValue = statusFilter.value.trim().toLowerCase()
    const satelliteValue = satelliteFilter.value.trim().toLowerCase()
    return store.images.filter((img) => {
        const matchKeyword =
            !keywordValue ||
            img.id.toLowerCase().includes(keywordValue) ||
            img.name.toLowerCase().includes(keywordValue)
        const matchStatus = !statusValue || String(img.status || '').toLowerCase() === statusValue
        const matchSatellite = !satelliteValue || String(img.satellite || '').toLowerCase().includes(satelliteValue)
        return matchKeyword && matchStatus && matchSatellite
    })
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

    const lightweightPreview = row.previewUrl || row.thumbnailUrl
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
.progress-bar {
    margin-top: 10px;
}
.thumbnail-preview {
    cursor: pointer;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
}
</style>
