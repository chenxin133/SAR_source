<template>
  <el-dialog
    v-model="visibleProxy"
    :title="dialogTitle"
    width="520px"
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

      <el-form-item label="分辨率" prop="resolution">
        <el-input v-model="form.resolution" placeholder="例如: 1m" />
      </el-form-item>

      <el-form-item label="地区" prop="region">
        <el-input v-model="form.region" placeholder="例如: 海南 / 青岛 / 南海" />
      </el-form-item>

      <el-form-item label="极化方式" prop="polarization">
        <el-select v-model="form.polarization" placeholder="选择极化方式" style="width: 100%">
          <el-option label="HH" value="HH" />
          <el-option label="HV" value="HV" />
          <el-option label="VH" value="VH" />
          <el-option label="VV" value="VV" />
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

      <el-form-item label="备注">
        <el-input v-model="form.description" type="textarea" />
      </el-form-item>

      <div v-if="store.isUploading" class="progress-bar">
        <el-progress :percentage="store.uploadProgress" />
      </div>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visibleProxy = false" :disabled="store.isUploading">取消</el-button>
        <el-button type="primary" @click="submitUpload" :loading="store.isUploading">
          {{ store.isUploading ? '上传中...' : '确定上传' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
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
import { packImageDescription, unpackImageDescription } from '../../utils/imageMetadata'

type RawImageUploadForm = {
  name: string
  satellite: string
  region: string
  resolution: string
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
const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadUserFile[]>([])

const form = reactive<RawImageUploadForm>({
  name: '',
  satellite: props.satellitePreset ?? '',
  region: '',
  resolution: '',
  polarization: '',
  description: '',
  file: null
})

const rules = {
  name: [{ required: true, message: '请输入影像名称', trigger: 'blur' }],
  satellite: [{ required: true, message: '请选择卫星源', trigger: 'change' }],
  region: [{ required: true, message: '请输入地区', trigger: 'blur' }],
  polarization: [{ required: true, message: '请选择极化方式', trigger: 'change' }]
} as const

const builtinSatelliteNames = computed(() => entrySatellites.map((s) => s.name))
const customSatelliteNames = ref<string[]>(loadCustomSatelliteNames())

const satelliteOptions = computed(() => {
  const fromImages = store.images.map((img) => img.satellite)
  return dedupeSatelliteNames([...builtinSatelliteNames.value, ...customSatelliteNames.value, ...fromImages])
})

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
  form.name = ''
  form.region = ''
  form.resolution = ''
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

const submitUpload = async () => {
  if (!formRef.value) return

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
    description: packImageDescription(form.region, form.description),
    resolution: form.resolution,
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
