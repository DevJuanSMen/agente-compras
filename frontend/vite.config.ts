import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo la API corre en :8000 (uvicorn); en produccion el mismo
// FastAPI sirve esta interfaz compilada, asi que las rutas /api son relativas.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
})
