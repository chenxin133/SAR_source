<template>
  <div class="sample-data">
    <div class="header-actions">
      <h2>样本数据管理</h2>
      <el-button type="primary" @click="reload">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <el-table :data="tableData" style="width: 100%" border>
      <el-table-column prop="id" label="样本ID" width="120" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="category" label="类别" width="140" />
      <el-table-column prop="source" label="来源影像" min-width="180" />
      <el-table-column prop="annotation" label="标注" width="220" />
      <el-table-column prop="size" label="尺寸" width="110" />
      <el-table-column prop="time" label="时间" width="160" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="scope">
          <el-button size="small" type="primary" plain @click="openPreview(scope.row)">预览</el-button>
          <el-button size="small" type="success" plain @click="openAnnotate(scope.row)">标注</el-button>
          <el-button size="small" type="danger" plain @click="deleteSample(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="tableData.length === 0" description="暂无样本数据" style="margin-top: 18px" />

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarSample } from '../../types/samples'

const router = useRouter()

type Row = {
  id: string
  name: string
  category: string
  source: string
  annotation: string
  size: string
  time: string
  raw: SarSample
}

const samples = ref<SarSample[]>([])

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

const tableData = computed<Row[]>(() => {
  return samples.value.map((s) => ({
    id: s.id,
    name: s.name,
    category: s.category || '未分类',
    source: s.imageName || s.imageId,
    annotation: `${s.annotationType} / ${s.annotationId}`,
    size: `${s.width}×${s.height}`,
    time: formatTime(s.updatedAt || s.createdAt),
    raw: s
  }))
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
  previewUrl.value = URL.createObjectURL(row.raw.image)
  previewVisible.value = true
}

const openAnnotate = (row: Row) => {
  router.push({
    name: 'annotate',
    query: { imageId: row.raw.imageId, annotationId: row.raw.annotationId }
  })
}

const reload = async () => {
  try {
    samples.value = await samplesRepo.list()
  } catch (e: any) {
    samples.value = []
    ElMessage.error(e?.message ? `样本加载失败：${e.message}` : '样本加载失败')
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
  await reload()
})
</script>

<style scoped>
.header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.preview-meta {
    margin-top: 10px;
    color: #606266;
    font-size: 13px;
    line-height: 22px;
}
</style>
