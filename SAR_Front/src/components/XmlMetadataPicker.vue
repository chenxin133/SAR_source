<template>
  <div class="xml-picker">
    <input ref="input" type="file" accept=".xml,application/xml,text/xml" hidden @change="select" />
    <el-button :loading="parsing" :disabled="disabled" @click="input?.click()">手动选择 XML</el-button>
    <el-button v-if="filename" link :disabled="disabled" @click="clear">移除</el-button>
    <div v-if="filename" class="filename">{{ filename }}</div>
    <div class="tip">选择影像后自动查找同目录配套 XML；缺少的信息请手动补充。</div>
    <div v-if="autoHint" class="auto-hint" role="status">{{ autoHint }}</div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="mismatch" title="XML 中的影像文件名与当前文件不同，请核对是否为配套文件。" type="warning" :closable="false" />
    <div v-if="metadata" class="xml-summary">
      <span v-if="metadata.data_source">数据源：{{ metadata.data_source }}；</span>
      <span v-if="metadata.width && metadata.height">XML 尺寸：{{ metadata.width }} × {{ metadata.height }} px；</span>
      <span v-if="metadata.time_reference">时间基准：{{ metadata.time_reference }}；</span>
      <span v-if="metadata.coordinates.center">中心：{{ metadata.coordinates.center.longitude }}, {{ metadata.coordinates.center.latitude }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { metadataApi } from '../services/metadataApi'
import type { SceneMetadata, XmlAttachment } from '../types/metadata'

const props = defineProps<{ imageFile?: File | null; imageFilename?: string; disabled?: boolean }>()
const emit = defineEmits<{ parsed: [value: XmlAttachment]; cleared: []; parsing: [value: boolean] }>()
const input = ref<HTMLInputElement>()
const parsing = ref(false)
const filename = ref('')
const error = ref('')
const autoHint = ref('')
const metadata = ref<SceneMetadata | null>(null)
let origin: 'auto' | 'manual' | '' = ''
let request = 0
const mismatch = computed(() => !!(props.imageFilename && metadata.value?.image_filename &&
  props.imageFilename.toLowerCase() !== metadata.value.image_filename.replace(/\\/g, '/').split('/').pop()?.toLowerCase()))
const clear = () => {
  request++
  filename.value = ''; error.value = ''; autoHint.value = ''; metadata.value = null; parsing.value = false; origin = ''
  if (input.value) input.value.value = ''
  emit('parsing', false); emit('cleared')
}
const readAttachment = async (file: File, id: number, encoded?: string) => {
  if (!file.name.toLowerCase().endsWith('.xml') || file.size > 2 * 1024 * 1024 || !file.size) {
    error.value = '请选择不超过 2 MiB 的 XML 文件'; return
  }
  filename.value = file.name
  const parsed = await metadataApi.parseXml(file)
  if (id !== request) return
  const base64 = encoded ?? await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('XML 文件读取失败'))
    reader.readAsDataURL(file)
  })
  if (id !== request) return
  metadata.value = parsed
  emit('parsed', { file, base64, metadata: parsed })
}
const start = () => { const id = ++request; parsing.value = true; emit('parsing', true); return id }
const finish = (id: number) => { if (id === request) { parsing.value = false; emit('parsing', false) } }
const select = async (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  clear()
  if (!file) return
  origin = 'manual'
  const id = start()
  try {
    await readAttachment(file, id)
  } catch (value) {
    if (id === request) error.value = value instanceof Error ? value.message : 'XML 解析失败'
  } finally { finish(id) }
}
watch([() => props.imageFile, () => props.imageFilename], async ([file, name], [oldFile, oldName]) => {
  // An XML explicitly selected before the first image remains the user's choice.
  if (file && !oldFile && !oldName && origin === 'manual' && metadata.value) return
  if (file === oldFile && name === oldName) return
  clear()
  if (!file) return
  const find = window.sarDesktop?.findCompanionXml
  if (!find) { autoHint.value = '当前环境无法自动查找同目录文件，请手动选择 XML。'; return }
  const id = start()
  try {
    const result = await find(file)
    if (id !== request) return
    if (result.status === 'not-found') { autoHint.value = '同目录未找到 XML，可手动选择或直接填写信息。'; return }
    if (result.status === 'ambiguous') { autoHint.value = '同目录有多份 XML，无法确定配套文件，请手动选择。'; return }
    if (result.status === 'unavailable') { autoHint.value = '无法取得所选文件的目录，请手动选择 XML。'; return }
    const bytes = Uint8Array.from(atob(result.base64), char => char.charCodeAt(0))
    origin = 'auto'
    await readAttachment(new File([bytes], result.filename, { type: 'application/xml' }), id, result.base64)
    if (id === request && metadata.value) autoHint.value = result.match === 'only-xml'
      ? '已自动读取同目录唯一的 XML，请核对配套信息。' : '已自动读取同目录配套 XML。'
  } catch (value) {
    if (id === request) error.value = `自动读取 XML 失败：${value instanceof Error ? value.message : '请手动选择或填写信息'}`
  } finally { finish(id) }
})
onBeforeUnmount(() => { request++ })
defineExpose({ clear })
</script>

<style scoped>
.xml-picker { width: 100%; }
.filename { overflow-wrap: anywhere; margin-top: 6px; }
.tip, .xml-summary { color: #606266; font-size: 12px; line-height: 1.7; margin-top: 6px; }
.auto-hint { font-size: 12px; line-height: 1.7; margin-top: 6px; color: #409eff; }
</style>
