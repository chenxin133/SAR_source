<template>
  <div class="echo-data">
    <div class="header-actions">
      <div><h2>回波信号管理</h2><p>管理二进制 dat 回波，查看脉冲与 I/Q 采样。</p></div>
      <div class="actions"><el-button @click="openImport">导入 dat 文件</el-button>
        <el-button type="primary" @click="simulateVisible = true">生成仿真回波</el-button></div>
    </div>
    <el-alert type="info" :closable="false" show-icon
      title="文件布局：int32 Na、int32 Nr；每个脉冲为 uint32 iGate + Nr 组 uint16 I/Q。默认小端，最大 64 MiB。" />
    <div class="filters">
      <el-input v-model="query" placeholder="按信号名称搜索" clearable @keyup.enter="search" @clear="search" />
      <el-select v-model="source" placeholder="全部来源" clearable @change="search">
        <el-option label="仿真数据" value="simulated" /><el-option label="导入数据" value="imported" />
      </el-select>
      <el-select v-model="band" placeholder="全部频段" clearable @change="search">
        <el-option v-for="item in bands" :key="item.band" :label="item.band + ' 频段'" :value="item.band" />
      </el-select>
      <el-button @click="search">查询</el-button><el-button @click="load">刷新</el-button>
    </div>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" border empty-text="暂无回波信号，请导入 dat 文件或生成仿真回波">
      <el-table-column prop="name" label="信号名称" min-width="190" show-overflow-tooltip />
      <el-table-column label="频段 / GHz" width="130"><template #default="{ row }">
        {{ row.frequency_band || '未标注' }}{{ row.center_frequency_ghz ? ' / ' + row.center_frequency_ghz : '' }}
      </template></el-table-column>
      <el-table-column label="来源" width="100"><template #default="{ row }">
        <el-tag :type="row.source === 'simulated' ? 'warning' : 'success'">{{ row.source === 'simulated' ? '仿真' : '导入' }}</el-tag>
      </template></el-table-column>
      <el-table-column prop="na" label="脉冲数 Na" width="110" /><el-table-column prop="nr" label="采样点 Nr" width="110" />
      <el-table-column label="文件大小" width="110"><template #default="{ row }">{{ fileSize(row.size_bytes) }}</template></el-table-column>
      <el-table-column label="入库时间" min-width="170"><template #default="{ row }">{{ dateTime(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="260" fixed="right"><template #default="{ row }">
        <el-button link type="primary" @click="view(row)">查看</el-button><el-button link type="primary" @click="edit(row)">编辑</el-button>
        <el-button link type="primary" @click="download(row)">下载</el-button><el-button link type="danger" @click="remove(row)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" />

    <el-dialog v-model="importVisible" title="导入回波 dat" width="560px" :close-on-click-modal="!busy" :show-close="!busy">
      <el-form label-width="100px" :disabled="busy">
        <el-form-item label="dat 文件"><input ref="fileInput" type="file" accept=".dat" aria-label="选择回波 dat 文件" @change="selectFile" /></el-form-item>
        <el-form-item label="信号名称"><el-input v-model="importForm.name" maxlength="200" /></el-form-item>
        <el-form-item label="频段（可选）"><el-select v-model="importForm.frequency_band" clearable placeholder="未标注">
          <el-option v-for="item in bands" :key="item.band" :label="item.band" :value="item.band" />
        </el-select></el-form-item>
        <el-form-item label="字节序"><el-select v-model="importForm.byte_order">
          <el-option label="小端 little-endian" value="little" /><el-option label="大端 big-endian" value="big" />
        </el-select></el-form-item>
        <el-form-item label="I/Q 偏置"><el-select v-model="importForm.iq_offset">
          <el-option label="32768（偏置二进制，仿真默认）" :value="32768" /><el-option label="0（按原始无符号数计算幅度）" :value="0" />
        </el-select></el-form-item>
        <el-form-item label="备注"><el-input v-model="importForm.remark" type="textarea" maxlength="2000" /></el-form-item>
      </el-form>
      <p class="hint">偏置仅用于计算幅度和相位；dat 中的 I/Q 原值保持不变。</p>
      <template #footer><el-button :disabled="busy" @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="importData">校验并导入</el-button></template>
    </el-dialog>

    <el-dialog v-model="simulateVisible" title="生成仿真回波" width="580px" :close-on-click-modal="!busy" :show-close="!busy">
      <el-alert type="warning" :closable="false" title="教学与管理验证数据：三点目标基带线性调频回波 + 高斯噪声，不代表实测数据。" />
      <el-form label-width="130px" :disabled="busy" class="simulation-form">
        <el-form-item label="信号名称"><el-input v-model="simulation.name" maxlength="200" /></el-form-item>
        <el-form-item label="仿真频段"><el-select v-model="simulation.frequency_band">
          <el-option v-for="item in bands" :key="item.band" :label="item.band + ' / ' + item.frequency + ' GHz'" :value="item.band" />
        </el-select></el-form-item>
        <el-form-item label="脉冲数 Na"><el-input-number v-model="simulation.na" :min="1" :max="4096" :precision="0" /></el-form-item>
        <el-form-item label="采样点数 Nr"><el-input-number v-model="simulation.nr" :min="8" :max="8192" :precision="0" /></el-form-item>
        <el-form-item label="随机种子"><el-input-number v-model="simulation.seed" :min="0" :max="4294967295" :precision="0" /></el-form-item>
        <el-form-item label="噪声标准差"><el-input-number v-model="simulation.noise_std" :min="0" :max="5000" /></el-form-item>
        <el-form-item label="iGate"><el-input-number v-model="simulation.gate_start" :min="0" :max="4294967295" :precision="0" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="simulation.remark" type="textarea" maxlength="2000" /></el-form-item>
      </el-form>
      <p class="hint">小端 uint16，I/Q 偏置 32768。固定种子可复现；最多 4,194,304 个复采样点。</p>
      <template #footer><el-button :disabled="busy" @click="simulateVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="generate">生成并入库</el-button></template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑回波信息" width="500px" :close-on-click-modal="!busy">
      <el-form label-width="80px"><el-form-item label="名称"><el-input v-model="editForm.name" maxlength="200" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.remark" type="textarea" maxlength="2000" /></el-form-item></el-form>
      <template #footer><el-button :disabled="busy" @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveEdit">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="回波信号详情" width="min(1060px, 94vw)" @closed="closeDetail">
      <template v-if="selected">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="名称">{{ selected.name }}</el-descriptions-item>
          <el-descriptions-item label="Na × Nr">{{ selected.na }} × {{ selected.nr }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ selected.source === 'simulated' ? '仿真数据' : '导入数据' }}</el-descriptions-item>
          <el-descriptions-item label="频段">{{ selected.frequency_band || '未标注' }}</el-descriptions-item>
          <el-descriptions-item label="中心频率">{{ selected.center_frequency_ghz ? selected.center_frequency_ghz + ' GHz' : '未提供' }}</el-descriptions-item>
          <el-descriptions-item label="字节序">{{ selected.byte_order }}</el-descriptions-item>
          <el-descriptions-item label="I/Q 偏置">{{ selected.iq_offset }}</el-descriptions-item>
          <el-descriptions-item label="iGate 范围">{{ selected.gate_min }} – {{ selected.gate_max }}</el-descriptions-item>
          <el-descriptions-item label="原始文件">{{ selected.original_filename }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ fileSize(selected.size_bytes) }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ selected.remark || '无' }}</el-descriptions-item>
          <el-descriptions-item label="SHA-256" :span="3"><span class="checksum">{{ selected.checksum_sha256 }}</span></el-descriptions-item>
        </el-descriptions>
        <p v-if="selected.simulation" class="hint">仿真参数：种子 {{ selected.simulation.seed }}；
          采样率 {{ Number(selected.simulation.sample_rate_hz) / 1e6 }} MHz；
          带宽 {{ Number(selected.simulation.bandwidth_hz) / 1e6 }} MHz；PRF {{ selected.simulation.prf_hz }} Hz。</p>
        <h3>幅度预览</h3>
        <p class="hint">横轴：距离采样点 0 – {{ selected.nr - 1 }}；纵轴：脉冲 0 – {{ selected.na - 1 }}。取样至最多 512 × 256，逐文件对数归一化，亮色表示幅度较大。</p>
        <img class="heatmap" :src="selected.preview_url" alt="回波幅度热力图" />
        <div class="pulse-controls"><span>脉冲索引（从 0 开始）</span>
          <el-input-number v-model="pulseIndex" :min="0" :max="selected.na - 1" :precision="0" />
          <el-button :loading="pulseLoading" @click="loadPulse">查看脉冲</el-button><span v-if="pulse">iGate = {{ pulse.igate }}</span>
        </div>
        <el-alert v-if="pulseError" :title="pulseError" type="error" :closable="false" />
        <template v-if="pulse">
          <div class="legend"><span class="i">I − {{ selected.iq_offset }}</span><span class="q">Q − {{ selected.iq_offset }}</span><span class="magnitude">幅度</span></div>
          <svg class="waveform" viewBox="0 0 960 200" role="img" aria-label="单脉冲 I/Q 与幅度曲线">
            <line x1="0" y1="100" x2="960" y2="100" stroke="#ccd3de" />
            <polyline :points="wave(centeredI)" fill="none" stroke="#2563eb" stroke-width="1.2" />
            <polyline :points="wave(centeredQ)" fill="none" stroke="#d97706" stroke-width="1.2" />
            <polyline :points="wave(pulse.magnitude)" fill="none" stroke="#059669" stroke-width="1.4" />
          </svg>
          <p class="hint">曲线与下表均匀取样至最多 1024 点；相位单位为弧度，幅度 = √((I−偏置)² + (Q−偏置)²)。I/Q 列显示原始 uint16 数值。</p>
          <el-table :data="pulseRows" height="230" border size="small">
            <el-table-column prop="index" label="采样点索引" /><el-table-column prop="i" label="I (uint16)" />
            <el-table-column prop="q" label="Q (uint16)" /><el-table-column prop="magnitude" label="幅度" /><el-table-column prop="phase" label="相位 (rad)" />
          </el-table>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { echoesApi, type EchoPulse, type EchoSignal } from '../../services/echoesApi'

const rows = ref<EchoSignal[]>([])
const loading = ref(false), busy = ref(false), loadError = ref('')
const query = ref(''), source = ref(''), page = ref(1), total = ref(0)
const band = ref('')
const bands = [{ band: 'C', frequency: 5.3 }, { band: 'X', frequency: 9.6 }, { band: 'Ku', frequency: 15 }, { band: 'Ka', frequency: 35 }]
const importVisible = ref(false), simulateVisible = ref(false), editVisible = ref(false), detailVisible = ref(false)
const fileInput = ref<HTMLInputElement>(), file = ref<File | null>(null)
const importForm = reactive({ name: '', remark: '', byte_order: 'little', iq_offset: 32768, frequency_band: '' })
const simulation = reactive({ name: '三点目标仿真回波', remark: '', na: 256, nr: 512, seed: 20261023, noise_std: 300, gate_start: 1000, frequency_band: 'X' })
const editForm = reactive({ id: '', name: '', remark: '' })
const selected = ref<EchoSignal | null>(null), pulse = ref<EchoPulse | null>(null), pulseIndex = ref(0)
const pulseLoading = ref(false), pulseError = ref('')
let listRequest = 0, pulseRequest = 0
const errorText = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error)
  try {
    const body = JSON.parse(message)
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((item: { msg: string }) => item.msg).join('；')
  } catch { /* Plain error message. */ }
  return message
}
const fileSize = (bytes: number) => bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1048576).toFixed(2)} MiB`
const dateTime = (value: string) => new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString()
const load = async () => {
  const request = ++listRequest
  loading.value = true; loadError.value = ''
  try {
    const result = await echoesApi.list(query.value, source.value, page.value, band.value)
    if (request !== listRequest) return
    rows.value = result.data; total.value = result.total
  } catch (error) { if (request === listRequest) loadError.value = errorText(error) }
  finally { if (request === listRequest) loading.value = false }
}
const search = () => { page.value = 1; void load() }
const openImport = () => {
  file.value = null
  Object.assign(importForm, { name: '', remark: '', byte_order: 'little', iq_offset: 32768, frequency_band: '' })
  if (fileInput.value) fileInput.value.value = ''
  importVisible.value = true
}
const selectFile = (event: Event) => {
  file.value = (event.target as HTMLInputElement).files?.[0] || null
  if (file.value && !importForm.name) importForm.name = file.value.name.replace(/\.dat$/i, '').slice(0, 200)
}
const importData = async () => {
  if (!file.value || !/\.dat$/i.test(file.value.name)) return void ElMessage.warning('请选择 .dat 文件')
  if (file.value.size > 64 * 1048576) return void ElMessage.warning('文件不能超过 64 MiB')
  busy.value = true
  try {
    await echoesApi.upload(file.value, importForm); importVisible.value = false
    ElMessage.success('回波文件已校验并入库'); search()
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { busy.value = false }
}
const generate = async () => {
  if (!simulation.name.trim()) return void ElMessage.warning('请输入信号名称')
  if (simulation.na * simulation.nr > 4194304) return void ElMessage.warning('仿真最多 4,194,304 个复采样点')
  busy.value = true
  try {
    await echoesApi.simulate(simulation); simulateVisible.value = false
    ElMessage.success('仿真回波已生成并入库'); search()
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { busy.value = false }
}
const edit = (row: EchoSignal) => { Object.assign(editForm, { id: row.id, name: row.name, remark: row.remark }); editVisible.value = true }
const saveEdit = async () => {
  if (!editForm.name.trim()) return void ElMessage.warning('请输入信号名称')
  busy.value = true
  try { await echoesApi.edit(editForm.id, editForm); editVisible.value = false; await load(); ElMessage.success('已保存') }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { busy.value = false }
}
const download = async (row: EchoSignal) => {
  try { await echoesApi.download(row) } catch (error) { ElMessage.error(errorText(error)) }
}
const remove = async (row: EchoSignal) => {
  try {
    await ElMessageBox.confirm(`删除“${row.name}”及其 dat 文件？`, '删除回波', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await echoesApi.remove(row.id)
    if (rows.value.length === 1 && page.value > 1) page.value--
    await load(); ElMessage.success('已删除')
  } catch (error) { ElMessage.error(errorText(error)) }
}
const view = (row: EchoSignal) => {
  selected.value = row; pulse.value = null; pulseIndex.value = 0; detailVisible.value = true; void loadPulse()
}
const closeDetail = () => { pulseRequest++; selected.value = null; pulse.value = null }
const loadPulse = async () => {
  if (!selected.value || pulseIndex.value == null) return
  const request = ++pulseRequest
  pulseLoading.value = true; pulseError.value = ''; pulse.value = null
  try {
    const result = await echoesApi.pulse(selected.value.id, pulseIndex.value)
    if (request === pulseRequest) pulse.value = result
  } catch (error) { if (request === pulseRequest) pulseError.value = errorText(error) }
  finally { if (request === pulseRequest) pulseLoading.value = false }
}
const centeredI = computed(() => pulse.value?.i.map(value => value - (selected.value?.iq_offset || 0)) || [])
const centeredQ = computed(() => pulse.value?.q.map(value => value - (selected.value?.iq_offset || 0)) || [])
const waveScale = computed(() => Math.max(1, ...(pulse.value?.magnitude || [])))
const wave = (values: number[]) => values.map((value, index) => `${index * 960 / Math.max(1, values.length - 1)},${100 - value / waveScale.value * 92}`).join(' ')
const pulseRows = computed(() => pulse.value?.indices.map((index, n) => ({ index,
  i: pulse.value!.i[n], q: pulse.value!.q[n], magnitude: pulse.value!.magnitude[n]!.toFixed(2), phase: pulse.value!.phase[n]!.toFixed(4)
})) || [])
onMounted(load)
</script>

<style scoped>
.header-actions, .actions, .filters, .pulse-controls, .legend { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.header-actions { justify-content: space-between; margin-bottom: 20px; }
h2 { margin: 0 0 8px; } p { margin: 6px 0; color: #606266; }
.filters { margin: 20px 0; }.filters .el-input { width: 260px; }.filters .el-select { width: 160px; }
.el-pagination { margin-top: 18px; justify-content: flex-end; }.simulation-form { margin-top: 20px; }
.hint { font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }.checksum { overflow-wrap: anywhere; font-family: monospace; }
.heatmap { width: 100%; height: 230px; object-fit: fill; background: #101b30; image-rendering: pixelated; }
.pulse-controls { margin: 18px 0; }.legend { font-size: 12px; margin-top: 12px; }
.i { color: #2563eb; }.q { color: #d97706; }.magnitude { color: #059669; }
.waveform { width: 100%; height: 200px; background: #f8fafc; border: 1px solid #e5e7eb; }
</style>
