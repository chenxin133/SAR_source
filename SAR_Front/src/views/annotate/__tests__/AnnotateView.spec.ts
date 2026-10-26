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
  ElMessage: { success: vi.fn(), error: vi.fn() },
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
    requestRenderAll() {}
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
        'el-dialog', 'Pointer', 'Crop', 'Connection'
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
