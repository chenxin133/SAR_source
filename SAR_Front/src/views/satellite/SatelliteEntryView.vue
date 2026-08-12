<template>
  <div class="satellite-entry">
    <h2>特定卫星录入（录入该卫星 SAR 影像）: {{ satelliteName }}</h2>

    <el-alert
      class="entry-tip"
      type="info"
      :closable="false"
      show-icon
      title="本模块用于将当前卫星的 SAR 原始影像上传入库；卫星源字段会自动带入。"
    />

    <div class="entry-content">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>原始影像（{{ satelliteName }}）</span>
              <el-button class="button" type="primary" @click="openUpload">
                上传影像
              </el-button>
            </div>
          </template>

          <el-table :data="satelliteImages" style="width: 100%" border v-loading="store.loading" table-layout="fixed">
            <el-table-column prop="id" label="ID" width="230" show-overflow-tooltip />
            <el-table-column prop="name" label="影像名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="acquisitionDate" label="采集时间" width="180">
              <template #default="scope">{{ scope.row.acquisitionDate || '-' }}</template>
            </el-table-column>
            <el-table-column prop="frequencyBand" label="频段" width="90" />
            <el-table-column prop="polarization" label="极化" width="90" />
            <el-table-column prop="resolution" label="分辨率" width="100" />
            <el-table-column prop="fileSize" label="大小" width="110" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.status === 'Ready' ? 'success' : 'info'">{{ scope.row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="scope">
                <el-button size="small" type="primary" plain @click="handlePreview(scope.row)">预览</el-button>
                <el-button size="small" @click="handleView(scope.row)">详情</el-button>
                <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <RawImageUploadDialog
          v-model="uploadVisible"
          :satellite-preset="satelliteName"
          :satellite-readonly="true"
        />

        <el-dialog v-model="detailsVisible" title="影像详情" width="600px">
          <el-descriptions :column="1" border v-if="selectedImage">
            <el-descriptions-item label="ID">{{ selectedImage.id }}</el-descriptions-item>
            <el-descriptions-item label="名称">{{ selectedImage.name }}</el-descriptions-item>
            <el-descriptions-item label="卫星源">{{ selectedImage.satellite }}</el-descriptions-item>
            <el-descriptions-item label="采集时间">{{ selectedImage.acquisitionDate }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ selectedImage.fileSize }}</el-descriptions-item>
            <el-descriptions-item label="分辨率">{{ selectedImage.resolution || '-' }}</el-descriptions-item>
            <el-descriptions-item label="数据频段">{{ selectedImage.frequencyBand || '-' }}</el-descriptions-item>
            <el-descriptions-item label="极化方式">{{ selectedImage.polarization || '-' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag size="small">{{ selectedImage.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="备注">{{ selectedImage.description || '无' }}</el-descriptions-item>
          </el-descriptions>
          <template #footer>
            <el-button type="primary" plain @click="handlePreview(selectedImage!)" v-if="selectedImage">
              预览
            </el-button>
            <el-button @click="detailsVisible = false">关闭</el-button>
          </template>
        </el-dialog>

        <ImageViewer
          v-model="previewVisible"
          :src="previewUrl"
          :blob="previewBlob"
          :title="previewTitle"
        />
    </div>
    
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSatelliteNameById } from '../../constants/satellites'
import { useRawDataStore } from '../../stores/rawData'
import type { SarImage } from '../../types/sar'
import ImageViewer from '../../components/ImageViewer.vue'
import RawImageUploadDialog from '../../components/raw/RawImageUploadDialog.vue'

const route = useRoute()
const satelliteId = computed(() => route.params.id as string)

const satelliteName = computed(() => getSatelliteNameById(satelliteId.value))

// --- Raw images ---
const store = useRawDataStore()

onMounted(() => {
  store.fetchImages()
})

const satelliteImages = computed(() =>
  store.images.filter((img) => img.satellite === satelliteName.value)
)

const uploadVisible = ref(false)
const openUpload = () => {
  if (!satelliteName.value) {
    ElMessage.warning('未识别到卫星名称，无法自动带入卫星源')
    return
  }
  uploadVisible.value = true
}

const detailsVisible = ref(false)
const selectedImage = ref<SarImage | null>(null)

const handleView = (row: SarImage) => {
  selectedImage.value = row
  detailsVisible.value = true
}

const isTiffFile = (name?: string) => {
  if (!name) return false
  const n = name.toLowerCase()
  return n.endsWith('.tif') || n.endsWith('.tiff')
}

const previewVisible = ref(false)
const previewUrl = ref('')
const previewTitle = ref('')
const previewBlob = ref<Blob | undefined>(undefined)

const handlePreview = async (row: SarImage) => {
  previewTitle.value = row.name
  previewBlob.value = undefined
  previewUrl.value = ''

  if (!isTiffFile(row.name) && row.previewUrl) {
    previewUrl.value = row.previewUrl
    previewVisible.value = true
    return
  }

  const blob = await store.getFileBlob(row.id)
  if (blob) {
    previewBlob.value = blob
    previewVisible.value = true
    return
  }

  if (row.previewUrl) {
    previewUrl.value = row.previewUrl
    previewVisible.value = true
    return
  }

  ElMessage.info('该影像暂无可预览文件')
}

const handleDelete = (row: SarImage) => {
  ElMessageBox.confirm(`确定要删除影像 "${row.name}" 吗?`, '删除确认', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  })
    .then(async () => {
      await store.deleteImage(row.id)
    })
    .catch(() => {
      // ignore cancel
    })
}

</script>

<style scoped>
.box-card {
    width: 100%;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.entry-tip {
  width: 100%;
  margin-bottom: 12px;
}
.entry-content {
  width: 100%;
  min-width: 0;
}
</style>
