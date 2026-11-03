<template>
  <el-select v-bind="$attrs" :model-value="modelValue" @update:model-value="updateValue">
    <el-option v-for="option in ordered" :key="option.value" :value="option.value" :label="option.label">
      <div class="filter-option" :data-value="option.value" @dragover="dragOver($event, option.value)" @drop.stop="drop($event, option.value)">
        <button v-if="pins.includes(option.value)" type="button" class="filter-option__drag" draggable="true"
          :aria-label="`调整${option.label}置顶顺序`" title="拖动排序，也可使用上下方向键"
          @mousedown.stop @click.stop @dragstart.stop="startDrag($event, option.value)" @dragend="dragging = ''"
          @keydown.up.stop.prevent="moveBy(option.value, -1)" @keydown.down.stop.prevent="moveBy(option.value, 1)">⋮⋮</button>
        <span v-else class="filter-option__spacer" />
        <span class="filter-option__label" :title="option.label">{{ option.label }}</span>
        <button type="button" class="filter-option__pin" :aria-pressed="pins.includes(option.value)"
          :aria-label="`${pins.includes(option.value) ? '取消置顶' : '置顶'}${option.label}`"
          :title="pins.includes(option.value) ? '取消置顶' : '置顶'" @mousedown.stop.prevent @click.stop.prevent="toggle(option.value)">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M8 3h8l-1 6 3 3v2H6v-2l3-3-1-6Z" :fill="pins.includes(option.value) ? 'currentColor' : 'none'" />
            <path d="M12 14v7" />
          </svg>
        </button>
      </div>
    </el-option>
    <template #footer><span class="pin-hint">点击图钉置顶，拖动手柄调整顺序</span></template>
  </el-select>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { movePin, orderOptions, readPins, savePins, type FilterOption } from '../utils/pinnedOptions'

defineOptions({ inheritAttrs: false })
const props = defineProps<{ modelValue: string; options: FilterOption[]; preferenceKey: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const pins = ref(readPins(props.preferenceKey))
const dragging = ref('')
const ordered = computed(() => orderOptions(props.options, pins.value))
watch(() => props.preferenceKey, key => { pins.value = readPins(key) })
const updateValue = (value: string | undefined) => emit('update:modelValue', value ?? '')
const store = (values: string[]) => { pins.value = values; savePins(props.preferenceKey, values) }
const toggle = (value: string) => store(pins.value.includes(value) ? pins.value.filter(item => item !== value) : [...pins.value, value])
const startDrag = (event: DragEvent, value: string) => {
  dragging.value = value
  if (event.dataTransfer) { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', value) }
}
const dragOver = (event: DragEvent, value: string) => {
  if (dragging.value && pins.value.includes(value)) event.preventDefault()
}
const drop = (event: DragEvent, value: string) => {
  if (dragging.value && pins.value.includes(value)) { event.preventDefault(); store(movePin(pins.value, dragging.value, value)) }
  dragging.value = ''
}
const moveBy = (value: string, direction: number) => {
  const visible = ordered.value.filter(option => pins.value.includes(option.value)).map(option => option.value)
  const target = visible[visible.indexOf(value) + direction]
  if (target != null) store(movePin(pins.value, value, target))
}
</script>

<style scoped>
.filter-option { display: flex; align-items: center; gap: 6px; width: 100%; height: 100%; }
.filter-option__label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.filter-option__drag, .filter-option__pin { display: inline-flex; align-items: center; justify-content: center; flex: none; padding: 0; border: 0; background: transparent; color: var(--el-text-color-secondary); }
.filter-option__drag, .filter-option__spacer { width: 14px; flex: none; }
.filter-option__drag { cursor: grab; font-size: 14px; }
.filter-option__drag:active { cursor: grabbing; }
.filter-option__pin { width: 20px; height: 24px; cursor: pointer; }
.filter-option__pin[aria-pressed="true"], .filter-option__pin:hover { color: var(--el-color-primary); }
.filter-option__pin svg { stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.pin-hint { color: var(--el-text-color-secondary); font-size: 12px; white-space: normal; line-height: 1.5; }
</style>
