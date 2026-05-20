import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/data/raw',
      name: 'raw-data',
      component: () => import('../views/data/RawDataView.vue')
    },
    {
      path: '/data/samples',
      name: 'sample-data',
      component: () => import('../views/data/SampleDataView.vue')
    },
    {
      path: '/data/echo',
      name: 'echo-data',
      component: () => import('../views/data/EchoDataView.vue')
    },
    // Satellite routes will be added dynamically or statically here
    {
      path: '/satellite/:id',
      name: 'satellite-entry',
      component: () => import('../views/satellite/SatelliteEntryView.vue')
    },
    {
      path: '/samples/manage',
      name: 'sample-manage',
      component: () => import('../views/samples/SampleManageView.vue')
    },
    {
      path: '/annotate',
      name: 'annotate',
      component: () => import('../views/annotate/AnnotateView.vue')
    }
  ]
})

export default router
