<template>
  <div class="sample-data">
    <div class="header-actions">
      <h2>样本数据管理</h2>
      <el-button type="primary" @click="reload">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
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
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="scope">
          <el-button size="small" type="primary" plain @click="openPreview(scope.row)">预览</el-button>
          <el-button size="small" type="success" plain @click="openAnnotate(scope.row)">标注</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { imagesRepo } from '../../repositories/imagesRepo'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarImage } from '../../types/sar'
import type { SarSample } from '../../types/samples'
import { unpackImageDescription } from '../../utils/imageMetadata'

const router = useRouter()

type Row = {
  id: string
  name: string
  category: string
  source: string
  region: string
  polarization: string
  annotation: string
  size: string
  time: string
  raw: SarSample
}

const samples = ref<SarSample[]>([])
const images = ref<SarImage[]>([])
const keyword = ref('')
const categoryFilter = ref('')
const annotationFilter = ref('')
const sourceFilter = ref('')
const regionFilter = ref('')
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
      source: s.imageName || s.imageId,
      region: parsed.region || '',
      polarization: String(imageMeta?.polarization || ''),
      annotation: `${s.annotationType} / ${s.annotationId}`,
      size: `${s.width}×${s.height}`,
      time: formatTime(s.updatedAt || s.createdAt),
      raw: s
    }
  })
})

const categoryOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.category)))
const sourceOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.source)))
const regionOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.region)))
const polarizationOptions = computed(() => buildUniqueOptions(tableData.value.map((row) => row.polarization)))

const filteredTableData = computed<Row[]>(() => {
  const keywordValue = normalizeFilterValue(keyword.value)
  const categoryValue = normalizeFilterValue(categoryFilter.value)
  const annotationValue = normalizeFilterValue(annotationFilter.value)
  const sourceValue = normalizeFilterValue(sourceFilter.value)
  const regionValue = normalizeFilterValue(regionFilter.value)
  const polarizationValue = normalizeFilterValue(polarizationFilter.value)
  return tableData.value.filter((row) => {
    const matchKeyword =
      !keywordValue ||
      row.id.toLowerCase().includes(keywordValue) ||
      row.name.toLowerCase().includes(keywordValue) ||
      row.source.toLowerCase().includes(keywordValue) ||
      row.region.toLowerCase().includes(keywordValue) ||
      row.polarization.toLowerCase().includes(keywordValue)
    const matchCategory = !categoryValue || row.category.toLowerCase() === categoryValue
    const matchAnnotation = !annotationValue || row.raw.annotationType.toLowerCase() === annotationValue
    const matchSource = !sourceValue || row.source.toLowerCase() === sourceValue
    const matchRegion = !regionValue || row.region.toLowerCase() === regionValue
    const matchPolarization = !polarizationValue || row.polarization.toLowerCase() === polarizationValue
    return matchKeyword && matchCategory && matchAnnotation && matchSource && matchRegion && matchPolarization
  })
})

const hasActiveFilters = computed(() => {
  return [keyword.value, categoryFilter.value, annotationFilter.value, sourceFilter.value, regionFilter.value, polarizationFilter.value].some(
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
    const [sampleList, imageList] = await Promise.all([samplesRepo.list(), imagesRepo.list().catch(() => [])])
    samples.value = sampleList
    images.value = imageList
  } catch (e: any) {
    samples.value = []
    images.value = []
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
</style>
