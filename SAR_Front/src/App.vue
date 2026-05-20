<script setup lang="ts">
import { RouterView } from 'vue-router'
import { entrySatellites } from './constants/satellites'
</script>

<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        default-active="1"
        class="el-menu-vertical-demo"
        router
      >
        <el-menu-item index="/">
          <el-icon><DataLine /></el-icon>
          <span>首页</span>
        </el-menu-item>
        
        <el-sub-menu index="1">
          <template #title>
            <el-icon><Files /></el-icon>
            <span>数据管理</span>
          </template>
          <el-menu-item index="/data/raw">原始影像</el-menu-item>
          <el-menu-item index="/data/samples">样本数据</el-menu-item>
          <el-menu-item index="/data/echo">回波信号</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="2">
          <template #title>
            <el-icon><Upload /></el-icon>
            <span>特定卫星影像录入</span>
          </template>
          <el-menu-item
            v-for="s in entrySatellites"
            :key="s.id"
            :index="`/satellite/${s.id}`"
          >
            {{ s.name }}
          </el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/samples/manage">
          <el-icon><Grid /></el-icon>
          <span>样本管理</span>
        </el-menu-item>

        <el-menu-item index="/annotate">
          <el-icon><Edit /></el-icon>
          <span>图像标注</span>
        </el-menu-item>

      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header>
        <h1>SAR数据管理系统</h1>
      </el-header>
      <el-main>
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
}
.el-aside {
  background-color: #f5f7fa;
  border-right: 1px solid #dcdfe6;
}
.el-header {
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
}
.el-main {
  background-color: #f0f2f5;
  padding: 20px;
}
</style>
