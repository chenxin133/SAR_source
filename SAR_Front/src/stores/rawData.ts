import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SarImage, UploadPayload } from '../types/sar'
import { ElMessage } from 'element-plus'
import { imagesRepo } from '../repositories/imagesRepo'
import { getStorageMode } from '../config/storage'

export const useRawDataStore = defineStore('rawData', () => {
  const images = ref<SarImage[]>([])
  const loading = ref(false)
  const uploadProgress = ref(0)
  const uploadStage = ref('')
  const isUploading = ref(false)

  const fetchImages = async () => {
    loading.value = true
    try {
      images.value = await imagesRepo.list()
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : '加载影像列表失败'
      ElMessage.error(message)
      console.error(error)
    } finally {
      loading.value = false
    }
  }

  const uploadImage = async (payload: UploadPayload) => {
    isUploading.value = true
    uploadProgress.value = 0
    try {
      const newImage = await imagesRepo.create(
        payload,
        (percent) => { uploadProgress.value = percent },
        (stage) => { uploadStage.value = stage }
      )

      images.value.unshift(newImage)
      ElMessage.success('上传成功')
      if (getStorageMode() === 'local' && payload.file.size > 200 * 1024 * 1024) {
        ElMessage.warning(
          newImage.previewNotice ||
            '该文件超过 200MB：原图仅本次会话可用，已保存可预览中间产物（刷新后仍可查看预览）。'
        )
      }
      return true
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : '上传失败'
      ElMessage.error(message)
      console.error(error)
      return false
    } finally {
      isUploading.value = false
      uploadProgress.value = 0
      uploadStage.value = ''
    }
  }

  const deleteImage = async (id: string) => {
    try {
      await imagesRepo.delete(id)
      images.value = images.value.filter((img) => img.id !== id)
      ElMessage.success('删除成功')
    } catch (error) {
      ElMessage.error('删除失败')
      console.error(error)
    }
  }

  const getFileBlob = async (id: string) => {
    return await imagesRepo.getFile(id)
  }

  return {
    images,
    loading,
    uploadProgress,
    uploadStage,
    isUploading,
    fetchImages,
    uploadImage,
    deleteImage,
    getFileBlob
  }
})
