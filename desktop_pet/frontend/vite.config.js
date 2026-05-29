import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'pixi-live2d': ['pixi.js', 'pixi-live2d-display'],
          'vad': ['@ricky0123/vad-react'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
})