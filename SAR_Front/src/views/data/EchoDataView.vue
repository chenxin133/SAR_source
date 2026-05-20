<template>
  <div class="echo-data">
    <div class="header-actions">
      <h2>回波信号管理</h2>
      <el-button type="primary" @click="handleImport">
        <el-icon><Download /></el-icon> 导入信号数据
      </el-button>
    </div>

    <el-table :data="tableData" style="width: 100%" border>
      <el-table-column prop="time" label="接收时间" width="180" />
      <el-table-column prop="frequency" label="中心频率 (GHz)" width="150" />
      <el-table-column prop="polarization" label="极化方式" width="120" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="scope">
            <el-tag :type="scope.row.status === 'Normal' ? 'success' : 'warning'">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="scope">
          <el-button size="small" @click="handleAnalyze(scope.row)">分析</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const tableData = ref([
    { time: '2023-10-01 10:00:00', frequency: '9.6', polarization: 'HH', status: 'Normal' },
    { time: '2023-10-01 10:05:00', frequency: '9.6', polarization: 'HV', status: 'Noisy' },
])

const handleImport = () => {
    ElMessage.info('导入功能待实现')
}

const handleAnalyze = (row: any) => {
    ElMessage.info(`分析信号数据: ${row.time}`)
}
</script>

<style scoped>
.header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}
</style>
