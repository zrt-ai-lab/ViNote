import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8999',
      '/static': 'http://localhost:8999',
    },
  },
  build: {
    outDir: '../static-build',
    emptyOutDir: true,
  },
})
