<template>
  <div class="sample-manage">
    <h2>样本管理</h2>

    <div class="filter-container">
      <el-input v-model="searchQuery" placeholder="搜索样本名称/备注/来源影像" style="width: 240px; margin-right: 10px" clearable />
      <el-select v-model="selectedCategory" placeholder="类别" clearable style="width: 160px; margin-right: 10px">
        <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
      </el-select>
      <el-button type="primary" @click="reload">
        <el-icon><Search /></el-icon> 刷新
      </el-button>
      <el-dropdown style="margin-left: 10px" @command="handleBatchExport">
        <el-button type="success" plain>
          批量导出
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="origin">导出原格式</el-dropdown-item>
            <el-dropdown-item command="image/png">导出为 PNG</el-dropdown-item>
            <el-dropdown-item command="image/jpeg">导出为 JPEG</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-row :gutter="20">
      <el-col :span="6" v-for="sample in filteredSamples" :key="sample.id" style="margin-bottom: 20px">
        <el-card :body-style="{ padding: '0px' }">
          <el-image
            v-if="sample.thumbUrl"
            :src="sample.thumbUrl"
            fit="cover"
            class="thumb"
            :preview-src-list="[]"
            @click="openPreview(sample)"
          />
          <div v-else class="image-placeholder">
            <span>无预览</span>
          </div>
          <div style="padding: 14px">
            <div class="name">{{ sample.name }}</div>
            <div class="bottom">
              <time class="time">{{ formatTime(sample.createdAt) }}</time>
              <el-tag size="small">{{ sample.category || '未分类' }}</el-tag>
            </div>
            <div class="sub">{{ sample.imageName || sample.imageId }}</div>
            <div class="actions">
              <el-button text class="button" @click="openPreview(sample)">预览</el-button>
              <el-button text class="button" type="primary" @click="openAnnotate(sample)">标注</el-button>
              <el-dropdown @command="handleExportOneFromCommand">
                <el-button text class="button" type="success">导出</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item :command="{ sample, format: 'origin' }">原格式</el-dropdown-item>
                    <el-dropdown-item :command="{ sample, format: 'image/png' }">PNG</el-dropdown-item>
                    <el-dropdown-item :command="{ sample, format: 'image/jpeg' }">JPEG</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button text class="button" type="danger" @click="deleteSample(sample)">删除</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-empty v-if="filteredSamples.length === 0" description="未找到匹配的样本" />

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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { samplesRepo } from '../../repositories/samplesRepo'
import type { SarSample } from '../../types/samples'

const route = useRoute()
const router = useRouter()

const searchQuery = ref('')
const selectedCategory = ref('')
const isBatchExporting = ref(false)

type SampleVM = SarSample & { thumbUrl?: string }
const samples = ref<SampleVM[]>([])
const thumbUrlById = new Map<string, string>()

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

const rebuildThumbUrls = (list: SarSample[]) => {
  for (const url of thumbUrlById.values()) URL.revokeObjectURL(url)
  thumbUrlById.clear()
  samples.value = list.map((s) => {
    const thumbBlob = s.thumbnail || s.image
    const url = URL.createObjectURL(thumbBlob)
    thumbUrlById.set(s.id, url)
    return { ...(s as any), thumbUrl: url }
  })
}

const clearHighlightQuery = () => {
  if (!route.query.highlight) return
  const q: any = { ...(route.query as any) }
  delete q.highlight
  router.replace({ query: q })
}

const reload = async (opts?: { openHighlight?: boolean }) => {
  const openHighlight = !!opts?.openHighlight
  try {
    const list = await samplesRepo.list()
    rebuildThumbUrls(list)
    if (openHighlight) {
      const hl = route.query.highlight
      const targetId = typeof hl === 'string' ? hl : ''
      if (targetId) {
        const hit = list.find((x) => x.id === targetId)
        if (hit) openPreview(hit)
        clearHighlightQuery()
      }
    }
  } catch (e: any) {
    rebuildThumbUrls([])
    ElMessage.error(e?.message ? `样本加载失败：${e.message}` : '样本加载失败')
  }
}

const categoryOptions = computed(() => {
  const set = new Set<string>()
  for (const s of samples.value) if (s.category) set.add(s.category)
  return Array.from(set)
})

const filteredSamples = computed(() => {
  const q = searchQuery.value.trim()
  const selected = typeof selectedCategory.value === 'string' ? selectedCategory.value : ''
  return samples.value.filter((sample) => {
    const matchQuery =
      !q ||
      sample.name.includes(q) ||
      (sample.remark || '').includes(q) ||
      (sample.imageName || '').includes(q) ||
      sample.imageId.includes(q)
    const matchCategory = !selected || sample.category === selected
    return matchQuery && matchCategory
  })
})

const previewVisible = ref(false)
const previewSample = ref<SarSample | null>(null)
const previewUrl = ref<string>('')

const clearPreview = () => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewSample.value = null
}

const openPreview = (sample: SarSample) => {
  clearPreview()
  previewSample.value = sample
  previewUrl.value = URL.createObjectURL(sample.image)
  previewVisible.value = true
}

const openAnnotate = (sample: SarSample) => {
  router.push({
    name: 'annotate',
    query: { imageId: sample.imageId, annotationId: sample.annotationId }
  })
}

type ExportCommand = 'origin' | 'image/png' | 'image/jpeg'

const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'sample'

const extFromType = (type: 'image/png' | 'image/jpeg') => (type === 'image/png' ? 'png' : 'jpg')

const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.setTimeout(() => URL.revokeObjectURL(url), 1500)
}

const transcodeImageBlob = async (blob: Blob, target: 'image/png' | 'image/jpeg') => {
  if (blob.type === target) return blob
  const bmp = await createImageBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = bmp.width
  canvas.height = bmp.height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bmp.close()
    throw new Error('无法创建导出画布')
  }
  if (target === 'image/jpeg') {
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  ctx.drawImage(bmp, 0, 0)
  bmp.close()
  const out = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((b) => resolve(b), target, target === 'image/jpeg' ? 0.92 : undefined)
  })
  if (!out) throw new Error('导出失败')
  return out
}

const resolveExportBlob = async (sample: SarSample, command: ExportCommand) => {
  if (command === 'origin') return { blob: sample.image, type: sample.format }
  const blob = await transcodeImageBlob(sample.image, command)
  return { blob, type: command }
}

const exportOne = async (sample: SarSample, command: ExportCommand) => {
  const { blob, type } = await resolveExportBlob(sample, command)
  const filename = `${sanitizeFileName(sample.name)}_${sample.id}.${extFromType(type)}`
  triggerDownload(blob, filename)
}

const handleExportOne = async (sample: SarSample, cmd: string | number | object) => {
  const command = cmd as ExportCommand
  try {
    await exportOne(sample, command)
    ElMessage.success('样本导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message ? `样本导出失败：${e.message}` : '样本导出失败')
  }
}

const handleExportOneFromCommand = async (cmd: unknown) => {
  const payload = cmd as { sample?: SarSample; format?: ExportCommand }
  if (!payload.sample || !payload.format) return
  await handleExportOne(payload.sample, payload.format)
}

const handleBatchExport = async (cmd: string | number | object) => {
  const command = cmd as ExportCommand
  if (!samples.value.length) {
    ElMessage.info('暂无可导出的样本')
    return
  }
  if (isBatchExporting.value) return
  isBatchExporting.value = true
  try {
    for (const sample of samples.value) {
      await exportOne(sample, command)
      await new Promise((resolve) => setTimeout(resolve, 60))
    }
    ElMessage.success(`已开始导出 ${samples.value.length} 个样本`)
  } catch (e: any) {
    ElMessage.error(e?.message ? `批量导出失败：${e.message}` : '批量导出失败')
  } finally {
    isBatchExporting.value = false
  }
}

const deleteSample = (sample: SarSample) => {
  ElMessageBox.confirm('确定要删除该样本吗？', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
    .then(async () => {
      await samplesRepo.delete(sample.id)
      await reload()
      ElMessage.success('删除成功')
    })
    .catch(() => undefined)
}

onMounted(async () => {
  await reload({ openHighlight: true })
})

watch(
  () => route.query.highlight,
  async (v) => {
    const id = typeof v === 'string' ? v : ''
    if (!id) return
    if (!samples.value.some((x) => x.id === id)) await reload({ openHighlight: true })
    else {
      const hit = samples.value.find((x) => x.id === id)
      if (hit) openPreview(hit)
      clearHighlightQuery()
    }
  }
)

onUnmounted(() => {
  clearPreview()
  for (const url of thumbUrlById.values()) URL.revokeObjectURL(url)
  thumbUrlById.clear()
})
</script>

<style scoped>
.filter-container {
    margin-bottom: 20px;
    background-color: #fff;
    padding: 15px;
    border-radius: 4px;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.thumb {
    width: 100%;
    height: 150px;
    cursor: pointer;
}

.image-placeholder {
    width: 100%;
    height: 150px;
    background-color: #e9e9eb;
    display: flex;
    justify-content: center;
    align-items: center;
    color: #909399;
}

.time {
    font-size: 12px;
    color: #999;
}

.bottom {
    margin-top: 13px;
    line-height: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.actions {
    margin-top: 10px;
    display: flex;
    justify-content: flex-end;
}

.button {
    padding: 0;
    min-height: auto;
}

.name {
    font-weight: 600;
}

.sub {
    margin-top: 6px;
    font-size: 12px;
    color: #909399;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.preview-meta {
    margin-top: 10px;
    color: #606266;
    font-size: 13px;
    line-height: 22px;
}
</style>
