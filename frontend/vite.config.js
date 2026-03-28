import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,  // WebSocket proxy for /api/simulation/{id}/stream
      },
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
})
