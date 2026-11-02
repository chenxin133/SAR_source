<template>
  <el-dialog
    v-model="visibleProxy"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="!store.isUploading"
    :close-on-press-escape="!store.isUploading"
    :show-close="!store.isUploading"
    @closed="handleClosed"
  >
    <el-form ref="formRef" :model="form" label-width="100px" :rules="rules">
      <el-form-item label="影像名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入影像名称" />
      </el-form-item>

      <el-form-item label="卫星源" prop="satellite">
        <el-input v-if="satelliteReadonly" v-model="form.satellite" disabled />
        <el-select
          v-else
          v-model="form.satellite"
          placeholder="选择或输入卫星"
          style="width: 100%"
          filterable
          allow-create
          default-first-option
        >
          <el-option v-for="s in satelliteOptions" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>

      <el-form-item label="采集时间" prop="acquisitionAt">
        <el-date-picker
          v-model="form.acquisitionAt"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          placeholder="选择影像实际采集时间"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="分辨率" prop="resolution">
        <el-input v-model="form.resolution" placeholder="例如: 1m" />
      </el-form-item>

      <el-form-item label="数据频段" prop="frequencyBand">
        <el-select v-model="form.frequencyBand" placeholder="选择数据频段" style="width: 100%">
          <el-option label="Ka" value="Ka" />
          <el-option label="Ku" value="Ku" />
          <el-option label="X" value="X" />
          <el-option label="C" value="C" />
        </el-select>
      </el-form-item>

      <el-form-item label="地区" prop="region">
        <el-input v-model="form.region" placeholder="例如: 海南 / 青岛 / 南海" />
      </el-form-item>

      <el-form-item label="极化方式" prop="polarization">
        <el-select v-model="form.polarization" placeholder="选择极化方式" style="width: 100%">
          <el-option v-for="item in polarizationOptions" :key="item" :label="item" :value="item" />
        </el-select>
      </el-form-item>

      <el-form-item label="文件" required>
        <el-upload
          ref="uploadRef"
          action="#"
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :on-exceed="handleExceed"
          :file-list="fileList"
          :show-file-list="false"
        >
          <el-button type="primary">选择文件</el-button>
          <template #tip>
            <div class="el-upload__tip">
              支持 .sar / .tif / .tiff / .dat / .jpg / .jpeg / .png
            </div>
          </template>
        </el-upload>
        <div v-if="fileList.length" class="selected-file">
          <span class="selected-file__name" :title="fileList[0].name">{{ fileList[0].name }}</span>
          <el-button class="selected-file__remove" link @click="clearSelectedFile">移除</el-button>
        </div>
      </el-form-item>

      <el-form-item label="配套 XML">
        <XmlMetadataPicker ref="xmlPicker" :image-file="form.file" :image-filename="form.file?.name" :disabled="store.isUploading"
          @parsed="applyXml" @cleared="clearXml" @parsing="xmlParsing = $event" />
      </el-form-item>
      <el-alert v-if="xmlSatelliteMismatch" type="error" :closable="false"
        :title="`XML 卫星为 ${xmlAttachment?.metadata.satellite}，与当前入口不同。请使用对应卫星入口或原始影像管理录入。`" />
      <el-form-item label="备注">
        <el-input v-model="form.description" type="textarea" />
      </el-form-item>

      <div v-if="store.isUploading" class="progress-bar">
        <div class="upload-stage" role="status">{{ store.uploadStage }}</div>
        <el-progress :percentage="store.uploadProgress" />
      </div>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visibleProxy = false" :disabled="store.isUploading">取消</el-button>
        <el-button type="primary" @click="submitUpload" :loading="store.isUploading" :disabled="xmlParsing || xmlSatelliteMismatch">
          {{ store.isUploading ? '上传中...' : '确定上传' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import XmlMetadataPicker from '../XmlMetadataPicker.vue'
import type { XmlAttachment } from '../../types/metadata'
import { applyXmlAutofill, clearXmlAutofill } from '../../utils/xmlAutofill'
import { computed, reactive, ref, watch } from 'vue'
import {
  ElMessage,
  type FormInstance,
  type UploadFile,
  type UploadFiles,
  type UploadInstance,
  type UploadUserFile
} from 'element-plus'
import { useRawDataStore } from '../../stores/rawData'
import {
  dedupeSatelliteNames,
  entrySatellites,
  loadCustomSatelliteNames,
  normalizeSatelliteName,
  saveCustomSatelliteNames
} from '../../constants/satellites'
import { buildPolarizationOptions } from '../../constants/polarizations'
import { packImageDescription, unpackImageDescription } from '../../utils/imageMetadata'

type RawImageUploadForm = {
  name: string
  satellite: string
  acquisitionAt: string
  region: string
  resolution: string
  frequencyBand: string
  polarization: string
  description: string
  file: File | null
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    satellitePreset?: string
    satelliteReadonly?: boolean
  }>(),
  {
    satellitePreset: undefined,
    satelliteReadonly: false
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'uploaded'): void
}>()

const store = useRawDataStore()

const visibleProxy = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const satelliteReadonly = computed(() => !!props.satelliteReadonly)
const dialogTitle = computed(() => (props.satellitePreset ? `上传原始影像（${props.satellitePreset}）` : '上传原始影像'))

const formRef = ref<FormInstance>()
const xmlPicker = ref<InstanceType<typeof XmlMetadataPicker>>()
const xmlAttachment = ref<XmlAttachment | null>(null)
const xmlParsing = ref(false)
const xmlSatelliteMismatch = computed(() => !!(props.satelliteReadonly && props.satellitePreset &&
  xmlAttachment.value?.metadata.satellite &&
  normalizeSatelliteName(xmlAttachment.value.metadata.satellite) !== normalizeSatelliteName(props.satellitePreset)))
let xmlAuto: Record<string, string> = {}
let xmlTimeDisplay = ''
const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadUserFile[]>([])

const form = reactive<RawImageUploadForm>({
  name: '',
  satellite: props.satellitePreset ?? '',
  acquisitionAt: '',
  region: '',
  resolution: '',
  frequencyBand: '',
  polarization: '',
  description: '',
  file: null
})

const rules = {
  resolution: [{ required: true, message: '请从 XML 读取或手动填写分辨率', trigger: 'blur' }],
  name: [{ required: true, message: '请输入影像名称', trigger: 'blur' }],
  satellite: [{ required: true, message: '请选择卫星源', trigger: 'change' }],
  region: [{ required: true, message: '请输入地区', trigger: 'blur' }],
  frequencyBand: [{ required: true, message: '请选择数据频段', trigger: 'change' }],
  polarization: [{ required: true, message: '请选择极化方式', trigger: 'change' }]
} as const

const builtinSatelliteNames = computed(() => entrySatellites.map((s) => s.name))
const customSatelliteNames = ref<string[]>(loadCustomSatelliteNames())

const satelliteOptions = computed(() => {
  const fromImages = store.images.map((img) => img.satellite)
  return dedupeSatelliteNames([...builtinSatelliteNames.value, ...customSatelliteNames.value, ...fromImages])
})
const polarizationOptions = computed(() => buildPolarizationOptions(store.images.map((img) => img.polarization)))

watch(
  () => visibleProxy.value,
  (v) => {
    if (!v) return
    customSatelliteNames.value = loadCustomSatelliteNames()
    resetForm(true)
  }
)

watch(
  () => props.satellitePreset,
  (preset) => {
    if (!preset) return
    form.satellite = preset
  }
)

watch(
  () => form.satellite,
  (v) => {
    if (satelliteReadonly.value) return
    const name = normalizeSatelliteName(v)
    if (!name) return
    if (builtinSatelliteNames.value.includes(name)) return
    if (customSatelliteNames.value.includes(name)) return
    customSatelliteNames.value = dedupeSatelliteNames([name, ...customSatelliteNames.value])
    saveCustomSatelliteNames(customSatelliteNames.value)
  }
)

const allowedExts = new Set(['sar', 'tif', 'tiff', 'dat', 'jpg', 'jpeg', 'png'])
const isAllowedFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return allowedExts.has(ext)
}

const clearSelectedFile = () => {
  uploadRef.value?.clearFiles()
  fileList.value = []
  form.file = null
}

const resetForm = (keepSatellitePreset: boolean) => {
  xmlPicker.value?.clear()
  xmlAttachment.value = null
  xmlAuto = {}
  form.name = ''
  form.acquisitionAt = ''
  form.region = ''
  form.resolution = ''
  form.frequencyBand = ''
  form.polarization = ''
  form.description = ''
  form.file = null
  fileList.value = []
  uploadRef.value?.clearFiles()
  if (keepSatellitePreset && props.satellitePreset) {
    form.satellite = props.satellitePreset
  } else if (!satelliteReadonly.value) {
    form.satellite = ''
  }
  formRef.value?.clearValidate()
}

const handleFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  // 受控 file-list：必须同步回写，否则部分桌面环境下看起来“无法选择文件”
  fileList.value = uploadFiles as UploadUserFile[]
  const raw = uploadFile.raw ?? null
  if (!raw) {
    form.file = null
    return
  }
  if (!isAllowedFile(raw)) {
    ElMessage.error('文件类型不支持，请选择 SAR/TIFF/DAT/JPG/PNG 文件')
    clearSelectedFile()
    return
  }
  form.file = raw
  if (!form.name) form.name = uploadFile.name
  const parsed = unpackImageDescription(form.description)
  if (!form.region && parsed.region) form.region = parsed.region
  if (!form.description && parsed.remark) form.description = parsed.remark
}

const handleFileRemove = () => {
  form.file = null
  fileList.value = []
}

const handleExceed = () => {
  ElMessage.warning('最多只能选择 1 个文件，请先移除已选文件')
}

const clearXml = () => {
  clearXmlAutofill(form, xmlAuto, { name: form.file?.name || '', satellite: props.satellitePreset || '' })
  xmlAuto = {}; xmlAttachment.value = null; xmlTimeDisplay = ''
}
const applyXml = (attachment: XmlAttachment) => {
  const metadata = attachment.metadata
  xmlTimeDisplay = metadata.acquisition_at.replace(/[Zz]$/, '').replace(/[+-]\d{2}:\d{2}$/, '').replace(/\.\d+$/, '')
  xmlAuto = applyXmlAutofill(form, {
    name: metadata.name, satellite: props.satelliteReadonly ? props.satellitePreset || '' : normalizeSatelliteName(metadata.satellite), acquisitionAt: xmlTimeDisplay,
    resolution: metadata.resolution, frequencyBand: metadata.frequency_band,
    polarization: metadata.polarization, region: metadata.region
  }, xmlAuto, { name: form.file?.name || '', satellite: props.satellitePreset || '' })
  xmlAttachment.value = attachment
  formRef.value?.clearValidate()
}

const submitUpload = async () => {
  if (xmlSatelliteMismatch.value || xmlParsing.value) return
  if (!formRef.value) return
  const missing = Object.entries({ 影像名称: form.name, 卫星源: form.satellite, 分辨率: form.resolution,
    地区: form.region, 数据频段: form.frequencyBand, 极化方式: form.polarization }).find(([, value]) => !value.trim())
  if (missing) { ElMessage.warning(`请填写${missing[0]}`); return }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  if (!form.file) {
    ElMessage.warning('请选择文件')
    return
  }

  const satellite = normalizeSatelliteName(form.satellite)
  if (!satellite) {
    ElMessage.warning('卫星源不能为空')
    return
  }

  const success = await store.uploadImage({
    name: form.name,
    satellite,
    file: form.file,
    acquisitionAt: xmlAttachment.value && form.acquisitionAt === xmlTimeDisplay ? xmlAttachment.value.metadata.acquisition_at || undefined : form.acquisitionAt || undefined,
    metadataXmlBase64: xmlAttachment.value?.base64,
    metadataXmlFilename: xmlAttachment.value?.file.name,
    description: packImageDescription(form.region, form.description),
    resolution: form.resolution,
    frequencyBand: form.frequencyBand,
    polarization: form.polarization
  })

  if (success) {
    visibleProxy.value = false
    emit('uploaded')
  }
}

const handleClosed = () => {
  // 关闭后清理：避免下次打开仍残留已选文件（桌面端更容易误判为“无法上传”）
  resetForm(true)
}
</script>

<style scoped>
.progress-bar {
  margin-top: 10px;
}

.upload-stage {
  margin-bottom: 8px;
  color: #606266;
  font-size: 13px;
}

.selected-file {
  width: 100%;
  margin-top: 12px;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  gap: 12px;
  box-sizing: border-box;
  min-width: 0;
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

:deep(.el-upload) {
  max-width: 100%;
}
</style>
