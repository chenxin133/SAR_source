<template>
  <div class="tiff-thumbnail" :style="{ width: maxSize + 'px', height: maxSize + 'px' }">
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>Processing...</span>
    </div>
    
    <div v-else-if="error" class="error-state">
      <el-icon><Warning /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

    <img 
      v-else-if="imgSrc" 
      :src="imgSrc" 
      :alt="file?.name"
      class="thumbnail-img"
    />
    
    <img 
      v-else 
      :src="fallbackSrc" 
      class="fallback-img"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { generateTiffThumbnail } from '../utils/tiffProcessor';
import { Loading, Warning } from '@element-plus/icons-vue';

const props = defineProps({
  file: {
    type: Object as () => File,
    required: true
  },
  maxSize: {
    type: Number,
    default: 256
  },
  fallbackSrc: {
    type: String,
    default: '/vite.svg' // Using vite logo as default fallback for now
  }
});

const loading = ref(false);
const error = ref(false);
const errorMsg = ref('');
const imgSrc = ref('');

let currentUrl: string | null = null;

const generate = async () => {
  if (!props.file) return;
  
  // Reset state
  loading.value = true;
  error.value = false;
  
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl);
    currentUrl = null;
  }

  try {
    const url = await generateTiffThumbnail(props.file, props.maxSize);
    imgSrc.value = url;
    currentUrl = url;
  } catch (err: any) {
    console.error('Thumbnail generation failed:', err);
    error.value = true;
    errorMsg.value = 'Preview Failed';
  } finally {
    loading.value = false;
  }
};

watch(() => props.file, () => {
  generate();
}, { immediate: true });

onUnmounted(() => {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl);
  }
});
</script>

<style scoped>
.tiff-thumbnail {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.thumbnail-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #909399;
  font-size: 12px;
  gap: 8px;
}

.error-state {
  color: #f56c6c;
}
</style>
