import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import router from './router'
import { createPinia } from 'pinia'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const preloadRouteChunks = () => {
  const preload = () => {
    void import('./views/data/RawDataView.vue')
    void import('./views/data/SampleDataView.vue')
    void import('./views/samples/SampleManageView.vue')
    void import('./views/satellite/SatelliteEntryView.vue')
    void import('./views/annotate/AnnotateView.vue')
  }

  if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(preload, { timeout: 1500 })
    return
  }
  window.setTimeout(preload, 300)
}

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
preloadRouteChunks()
