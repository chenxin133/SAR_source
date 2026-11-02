import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { Point, Rect, util } from 'fabric'
import AnnotateView from '../AnnotateView.vue'
import type { AnnotationsFileV1 } from '../../../types/annotations'

const state = vi.hoisted(() => ({
  canvas: null as any,
  saved: undefined as AnnotationsFileV1 | undefined,
  put: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { imageId: 'rotation-test' } }),
  useRouter: () => ({ replace: vi.fn().mockResolvedValue(undefined) })
}))
vi.mock('../../../config/storage', () => ({ getStorageMode: () => 'local' }))
vi.mock('../../../repositories/imagesRepo', () => ({
  imagesRepo: {
    list: async () => [{ id: 'rotation-test', name: 'test.png', width: 2000, height: 1600, previewUrl: '/test.png' }],
    getFile: async () => undefined
  }
}))
vi.mock('../../../repositories/annotationsRepo', () => ({
  annotationsRepo: {
    get: async () => state.saved,
    put: async (payload: AnnotationsFileV1) => {
      state.saved = JSON.parse(JSON.stringify(payload))
      state.put(payload)
    }
  }
}))
vi.mock('../../../repositories/samplesRepo', () => ({ samplesRepo: {} }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: {}
}))
vi.mock('fabric', async (importOriginal) => {
  const real = await importOriginal<typeof import('fabric')>()
  class TestCanvas {
    objects: any[] = []
    handlers = new Map<string, (event: any) => void>()
    viewportTransform = [1, 0, 0, 1, 0, 0]
    width = 1000
    height = 800
    active: any = null
    constructor() { state.canvas = this }
    on(name: string, handler: (event: any) => void) { this.handlers.set(name, handler) }
    off() { this.handlers.clear() }
    dispose() {}
    setWidth(width: number) { this.width = width }
    setHeight(height: number) { this.height = height }
    getWidth() { return this.width }
    getHeight() { return this.height }
    calcOffset() {}
    setViewportTransform(matrix: number[]) { this.viewportTransform = matrix }
    requestRenderAll() { this.handlers.get('after:render')?.({}) }
    getObjects() { return [...this.objects] }
    add(object: any) {
      if (!this.objects.includes(object)) this.objects.push(object)
      object.setCoords()
    }
    remove(object: any) { this.objects = this.objects.filter((item) => item !== object) }
    sendObjectToBack() {}
    setActiveObject(object: any) { this.active = object }
    discardActiveObject() { this.active = null }
    getActiveObject() { return this.active }
    getViewportPoint(event: MouseEvent) { return new real.Point(event.clientX, event.clientY) }
    getScenePoint(event: MouseEvent) {
      return real.util.transformPoint(this.getViewportPoint(event), real.util.invertTransform(this.viewportTransform as any))
    }
  }
  return {
    ...real,
    Canvas: TestCanvas,
    FabricImage: {
      fromURL: async () => ({
        width: 2000, height: 1600,
        set(options: object) { Object.assign(this, options) },
        setCoords() {}
      })
    }
  }
})

let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => {
  state.saved = undefined
  state.put.mockClear()
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1000)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(800)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
})

async function openView(rotation: number) {
  wrapper = mount(AnnotateView, {
    global: {
      stubs: Object.fromEntries([
        'el-select', 'el-option', 'el-button-group', 'el-button', 'el-icon', 'el-switch', 'el-slider',
        'el-checkbox', 'el-table', 'el-table-column', 'el-form', 'el-form-item', 'el-input', 'el-empty',
        'el-input-number', 'el-dialog', 'Pointer', 'Crop', 'Connection'
      ].map((name) => [name, true])),
      directives: { loading: () => {} }
    }
  })
  await flushPromises()
  const vm = (wrapper.vm as any).$.setupState
  vm.rotationDeg = rotation
  await nextTick()
  return vm
}

const emitPointer = (name: string, x: number, y: number) => {
  state.canvas.handlers.get(name)({ e: new MouseEvent(name, { clientX: x, clientY: y, button: 0 }) })
}
const drawingRectangle = () => state.canvas.getObjects().find((object: any) => object instanceof Rect) as Rect
const screenCorners = (rect: Rect) => rect.getCoords().map((p) => util.transformPoint(p, state.canvas.viewportTransform))
function expectHorizontalRectangle(rect: Rect, start: Point, end: Point) {
  const [tl, tr, br, bl] = screenCorners(rect)
  expect(tl.y).toBeCloseTo(tr.y, 8)
  expect(tr.x).toBeCloseTo(br.x, 8)
  expect(br.y).toBeCloseTo(bl.y, 8)
  expect(bl.x).toBeCloseTo(tl.x, 8)
  expect((tl.x + br.x) / 2).toBeCloseTo((start.x + end.x) / 2, 8)
  expect((tl.y + br.y) / 2).toBeCloseTo((start.y + end.y) / 2, 8)
}

describe('rectangle drawing on a rotated image', () => {
  it.each([0, 25, 90, 135, 270])('stays screen-aligned at %s degrees through drawing, saving and reload', async (rotation) => {
    const vm = await openView(rotation)
    // Exercise the actual wheel and pan handlers before drawing.
    state.canvas.handlers.get('mouse:wheel')({ e: new WheelEvent('wheel', { clientX: 500, clientY: 400, deltaY: -350 }) })
    document.body.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', key: ' ', bubbles: true }))
    emitPointer('mouse:down', 100, 100)
    emitPointer('mouse:move', 160, 130)
    emitPointer('mouse:up', 160, 130)
    document.body.dispatchEvent(new KeyboardEvent('keyup', { code: 'Space', key: ' ', bubbles: true }))
    vm.setTool('rect')
    const start = new Point(280, 210)
    const end = new Point(620, 480)
    emitPointer('mouse:down', start.x, start.y)
    emitPointer('mouse:move', end.x, end.y)
    expectHorizontalRectangle(drawingRectangle(), start, end)
    emitPointer('mouse:up', end.x, end.y)
    vm.metaDraft.category = '测试类别'
    await vm.confirmMeta()
    await vm.saveToLocal()
    expect(state.saved?.annotations).toHaveLength(1)
    expect(state.saved?.annotations[0].type).toBe('rect')
    expectHorizontalRectangle(drawingRectangle(), start, end)
    const beforeReload = drawingRectangle().getCenterPoint()
    await vm.loadForImage('rotation-test')
    const rect = drawingRectangle()
    const corners = rect.getCoords()
    expect(corners[0].y).toBeCloseTo(corners[1].y, 8)
    expect(corners[1].x).toBeCloseTo(corners[2].x, 8)
    expect(rect.getCenterPoint().x).toBeCloseTo(beforeReload.x, 8)
    expect(rect.getCenterPoint().y).toBeCloseTo(beforeReload.y, 8)
  })

  it('supports reverse diagonal drags and rejects a zero-height drag', async () => {
    const vm = await openView(25)
    vm.setTool('rect')
    const start = new Point(620, 210)
    const end = new Point(280, 480)
    emitPointer('mouse:down', start.x, start.y)
    emitPointer('mouse:move', end.x, end.y)
    expectHorizontalRectangle(drawingRectangle(), start, end)
    emitPointer('mouse:up', end.x, end.y)
    vm.cancelMeta()
    vm.setTool('rect')
    emitPointer('mouse:down', 280, 210)
    emitPointer('mouse:move', 620, 210)
    emitPointer('mouse:up', 620, 210)
    expect(drawingRectangle()).toBeUndefined()
  })
})

describe('square drawing and exact source-pixel dimensions', () => {
  it.each([0, 25, 90, 135, 270])('constrains Shift to a square at %s degrees and preserves edited dimensions through save/reload', async (rotation) => {
    const vm = await openView(rotation)
    vm.setTool('rect')
    emitPointer('mouse:down', 300, 240)
    state.canvas.handlers.get('mouse:move')({ e: new MouseEvent('mousemove', { clientX: 380, clientY: 280, shiftKey: true }) })
    expect(vm.sizeOverlay.width).toBeCloseTo(vm.sizeOverlay.height, 8)
    expect(vm.sizeOverlay.width).toBeCloseTo(160, 8)
    emitPointer('mouse:up', 380, 280)
    expect(vm.metaDialogVisible).toBe(true)
    expect(vm.tool).toBe('select')
    vm.startSizeEdit()
    vm.sizeDraft = { width: 112, height: 96 }
    vm.applySizeEdit()
    expect(vm.sizeOverlay.width).toBeCloseTo(112, 8)
    expect(vm.sizeOverlay.height).toBeCloseTo(96, 8)
    vm.metaDraft.category = '舰船'
    await vm.confirmMeta()
    await vm.saveToLocal()
    await vm.loadForImage('rotation-test')
    const annotation = state.saved!.annotations[0]
    expect(annotation.type).toBe('rect')
    if (annotation.type !== 'rect') throw new Error('Expected rectangle')
    const points = annotation.points!
    if ([0, 90, 270].includes(rotation)) {
      for (const point of points) {
        expect(point.x).toBe(Math.round(point.x)); expect(point.y).toBe(Math.round(point.y))
      }
    }
    expect(Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)).toBeCloseTo(112, 8)
    expect(Math.hypot(points[3].x - points[0].x, points[3].y - points[0].y)).toBeCloseTo(96, 8)
    vm.selectAnnotation(annotation.id)
    vm.updateSizeOverlay()
    expect(vm.sizeOverlay.width).toBeCloseTo(112, 8)
    expect(vm.sizeOverlay.height).toBeCloseTo(96, 8)
  })

  it('updates a stationary drag when Shift is pressed and released and cancels an unfinished draft', async () => {
    const vm = await openView(25)
    vm.setTool('rect')
    emitPointer('mouse:down', 500, 400)
    emitPointer('mouse:move', 440, 370)
    expect(vm.sizeOverlay.width).toBeCloseTo(120)
    expect(vm.sizeOverlay.height).toBeCloseTo(60)
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift', bubbles: true }))
    expect(vm.sizeOverlay.width).toBeCloseTo(vm.sizeOverlay.height)
    document.body.dispatchEvent(new KeyboardEvent('keyup', { key: 'Shift', bubbles: true }))
    expect(vm.sizeOverlay.height).toBeCloseTo(60)
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(vm.isDrawingSize).toBe(false)
    expect(drawingRectangle()).toBeUndefined()
  })

  it('keeps the unfinished shape editable until a category is entered, then remembers the category', async () => {
    const vm = await openView(0)
    vm.setTool('rect')
    emitPointer('mouse:down', 300, 200); emitPointer('mouse:move', 400, 300); emitPointer('mouse:up', 400, 300)
    await vm.confirmMeta()
    expect(vm.annotations).toHaveLength(0)
    expect(vm.metaDialogVisible).toBe(true)
    const input = document.createElement('input'); input.value = '车辆'
    vm.onCategoryQueryInput({ target: input })
    await vm.confirmMeta()
    expect(vm.annotations).toHaveLength(1)
    vm.setTool('rect')
    emitPointer('mouse:down', 400, 300); emitPointer('mouse:move', 500, 400); emitPointer('mouse:up', 500, 400)
    expect(vm.metaDraft.category).toBe('车辆')
    vm.cancelMeta()
    expect(vm.annotations).toHaveLength(1)
  })

  it('pans with the middle button without moving the draft or creating an annotation, and stops on release or blur', async () => {
    const vm = await openView(0)
    vm.setTool('rect')
    const middle = (event: string, x: number, y: number) => state.canvas.handlers.get(event)({
      e: new MouseEvent(event, { button: 1, clientX: x, clientY: y, cancelable: true })
    })
    const initialPan = { ...vm.viewPan }
    middle('mouse:down', 100, 120); middle('mouse:move', 160, 150); middle('mouse:up', 160, 150)
    expect(vm.viewPan).toEqual({ x: initialPan.x + 60, y: initialPan.y + 30 })
    expect(drawingRectangle()).toBeUndefined()
    emitPointer('mouse:down', 300, 200); emitPointer('mouse:move', 400, 300); emitPointer('mouse:up', 400, 300)
    const draft = drawingRectangle(), corners = draft.getCoords()
    middle('mouse:down', 350, 250); middle('mouse:move', 390, 290)
    expect(draft.getCoords()).toEqual(corners)
    window.dispatchEvent(new Event('blur'))
    const stoppedPan = { ...vm.viewPan }
    emitPointer('mouse:move', 420, 310)
    expect(vm.viewPan).toEqual(stoppedPan)
    expect(vm.annotations).toHaveLength(0)
    expect(vm.metaDialogVisible).toBe(true)
  })

  it('edits the dimension badge inline, tabs between fields, confirms on leaving, and cancels with Escape', async () => {
    const vm = await openView(0)
    vm.setTool('rect')
    emitPointer('mouse:down', 300, 200); emitPointer('mouse:move', 400, 300); emitPointer('mouse:up', 400, 300)
    await nextTick()
    expect(wrapper!.find('.canvas-wrap .annotation-draft').exists()).toBe(false)
    expect(wrapper!.find('.sidebar .annotation-draft').exists()).toBe(true)
    await wrapper!.get('[data-testid="annotation-size"]').trigger('click')
    expect(wrapper!.find('.size-editor').exists()).toBe(false)
    const width = wrapper!.get('input[aria-label="标注宽度"]'), height = wrapper!.get('input[aria-label="标注高度"]')
    await width.setValue('112'); await height.setValue('96')
    await width.trigger('focusout', { relatedTarget: height.element })
    expect(vm.sizeEditing).toBe(true)
    await height.trigger('focusout', { relatedTarget: null })
    expect(vm.sizeEditing).toBe(false)
    expect(vm.sizeOverlay.width).toBeCloseTo(112)
    expect(vm.sizeOverlay.height).toBeCloseTo(96)
    await wrapper!.get('[data-testid="annotation-size"]').trigger('click')
    await wrapper!.get('input[aria-label="标注宽度"]').setValue('180')
    await wrapper!.get('input[aria-label="标注宽度"]').trigger('keydown', { key: 'Escape' })
    expect(vm.metaDialogVisible).toBe(true)
    expect(vm.sizeEditing).toBe(false)
    expect(vm.sizeOverlay.width).toBeCloseTo(112)
  })

  it('confirms inline sizes with Enter and retains the old shape for invalid or out-of-image values', async () => {
    const vm = await openView(0)
    vm.setTool('rect')
    emitPointer('mouse:down', 300, 200); emitPointer('mouse:move', 400, 300); emitPointer('mouse:up', 400, 300)
    await nextTick()
    await wrapper!.get('[data-testid="annotation-size"]').trigger('click')
    await wrapper!.get('input[aria-label="标注宽度"]').setValue('0')
    await wrapper!.get('input[aria-label="标注宽度"]').trigger('keydown', { key: 'Enter' })
    expect(vm.sizeEditing).toBe(true)
    expect(vm.sizeOverlay.width).toBeCloseTo(200)
    vm.sizeDraft.width = 10000
    expect(vm.applySizeEdit()).toBe(false)
    expect(vm.sizeOverlay.width).toBeCloseTo(200)
    await wrapper!.get('input[aria-label="标注宽度"]').setValue('120')
    await wrapper!.get('input[aria-label="标注宽度"]').trigger('keydown', { key: 'Enter' })
    expect(vm.sizeEditing).toBe(false)
    expect(vm.sizeOverlay.width).toBeCloseTo(120)
    expect(vm.metaDialogVisible).toBe(true)
  })
})
