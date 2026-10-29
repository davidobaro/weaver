import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { version } from './package.json'

const builtAt = new Date().toISOString()

export default defineConfig({
  plugins: [react()],
  define: {
    __WEAVER_VERSION__: JSON.stringify(version),
    __WEAVER_BUILT_AT__: JSON.stringify(builtAt),
  },
  server: { port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
