import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia } from 'pinia'
import App from './App.vue'
import HomeView from './views/HomeView.vue'
import SimulationView from './views/SimulationView.vue'

// Router setup
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/simulation/:id',
      name: 'simulation',
      component: SimulationView,
      props: true,
    },
  ],
})

// Pinia store
const pinia = createPinia()

// Create app
const app = createApp(App)
app.use(router)
app.use(pinia)
app.mount('#app')
