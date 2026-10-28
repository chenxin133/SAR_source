<template>
  <p class="hint">双击信息可编辑，Enter 保存，Esc 取消。ID 和缩略图只读。</p>
  <el-descriptions :column="1" border>
    <el-descriptions-item label="ID"><span data-testid="image-id">{{ image.id }}</span></el-descriptions-item>
    <el-descriptions-item label="缩略图"><div data-testid="image-thumbnail"><slot name="thumbnail" /></div></el-descriptions-item>
    <el-descriptions-item v-for="field in fields" :key="field.key" :label="field.label">
      <div v-if="editing === field.key" class="editor" :data-editor="field.key" @keydown.esc.stop.prevent="cancel">
        <el-select v-if="field.key === 'status'" ref="editor" v-model="draft" :disabled="saving" aria-label="状态">
          <el-option v-for="status in ['uploaded', 'processing', 'ready', 'failed']" :key="status" :label="status" :value="status" />
        </el-select>
        <el-input v-else ref="editor" v-model="draft" :disabled="saving" :aria-label="field.label"
          :placeholder="field.key === 'acquisitionDate' ? '例如 2026-10-28 14:30:00；留空清除' : field.key === 'sizeBytes' ? '非负整数字节数' : ''"
          @keydown.enter.stop.prevent="save" />
        <span v-if="field.key === 'sizeBytes'">字节</span>
        <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button size="small" :disabled="saving" @click="cancel">取消</el-button>
      </div>
      <div v-else class="editable-value" :data-field="field.key" title="双击编辑" @dblclick="start(field)">{{ field.display || '无' }}</div>
    </el-descriptions-item>
    <el-descriptions-item v-if="image.originalPersistent === false" label="预览提示">
      <el-alert :title="image.previewNotice || '原图超过 200MB，仅当前会话可用；系统将优先展示持久化预览图。'" type="warning" :closable="false" show-icon />
    </el-descriptions-item>
  </el-descriptions>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ImageMetadataPatch, SarImage } from '../../types/sar'
import { packImageDescription, unpackImageDescription } from '../../utils/imageMetadata'

const props = defineProps<{ image: SarImage; saveMetadata: (patch: ImageMetadataPatch) => Promise<unknown> }>()
type FieldKey = keyof ImageMetadataPatch | 'region' | 'remark'
type Field = { key: FieldKey; label: string; value: string; display?: string }
const editing = ref<FieldKey | ''>('')
const draft = ref('')
const saving = ref(false)
const editor = ref<{ focus?: () => void }>()
const fields = computed<Field[]>(() => {
  const image = props.image
  const description = unpackImageDescription(image.description)
  const sizeMatch = image.fileSize.match(/^([\d.]+)\s*(B|KB|MB|GB|TB)$/i)
  const bytes = image.sizeBytes ?? (sizeMatch ? Math.round(Number(sizeMatch[1]) * 1024 ** ['B', 'KB', 'MB', 'GB', 'TB'].indexOf(sizeMatch[2]!.toUpperCase())) : 0)
  const rows: Field[] = [
    { key: 'name', label: '名称', value: image.name },
    { key: 'satellite', label: '卫星源', value: image.satellite },
    { key: 'region', label: '地区', value: description.region },
    { key: 'acquisitionDate', label: '采集时间', value: image.acquisitionDate },
    { key: 'sizeBytes', label: '文件大小', value: String(bytes), display: image.fileSize },
    { key: 'resolution', label: '分辨率', value: image.resolution || '' },
    { key: 'frequencyBand', label: '数据频段', value: image.frequencyBand || '' },
    { key: 'polarization', label: '极化方式', value: image.polarization || '' },
    { key: 'status', label: '状态', value: image.status.toLowerCase() },
    { key: 'errorMessage', label: '失败原因', value: image.errorMessage || '' },
    { key: 'remark', label: '备注', value: description.remark }
  ]
  return rows.map((field) => ({ ...field, display: field.display ?? field.value }))
})

const start = async (field: Field) => {
  if (saving.value) return
  editing.value = field.key
  draft.value = field.value
  await nextTick()
  // The editor is inside a v-for; Vue collects its template refs into an array.
  const input = Array.isArray(editor.value) ? editor.value[0] : editor.value
  input?.focus?.()
}
const cancel = () => { if (!saving.value) editing.value = '' }
const save = async () => {
  if (!editing.value || saving.value) return
  saving.value = true
  try {
    const key = editing.value
    const value = draft.value.trim()
    let patch: ImageMetadataPatch
    if (key === 'region' || key === 'remark') {
      const current = unpackImageDescription(props.image.description)
      patch = { description: packImageDescription(key === 'region' ? value : current.region, key === 'remark' ? value : current.remark) }
    } else if (key === 'sizeBytes') {
      const bytes = Number(value)
      if (!value || !Number.isSafeInteger(bytes) || bytes < 0) throw new Error('文件大小请输入非负整数字节数')
      patch = { sizeBytes: bytes, fileSize: `${(bytes / 1024 / 1024).toFixed(2)} MB` }
    } else if (key === 'acquisitionDate') {
      const date = new Date(value)
      if (value && !Number.isFinite(date.getTime())) throw new Error('请输入有效的采集时间')
      // Keep the displayed wall-clock value; converting a timezone-less database
      // timestamp to UTC here would silently move the acquisition time by hours.
      patch = { acquisitionDate: value }
    } else {
      if (key === 'name' && !value) throw new Error('名称不能为空')
      patch = { [key]: value }
    }
    await props.saveMetadata(patch)
    editing.value = ''
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败，请重试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint { color: #606266; font-size: 13px; }
.editable-value { cursor: text; min-height: 24px; white-space: pre-wrap; overflow-wrap: anywhere; }
.editable-value:hover { background: #ecf5ff; }
.editor { display: flex; align-items: center; gap: 6px; }
.editor .el-input, .editor .el-select { flex: 1; min-width: 120px; }
.editor .el-button + .el-button { margin-left: 0; }
</style>
