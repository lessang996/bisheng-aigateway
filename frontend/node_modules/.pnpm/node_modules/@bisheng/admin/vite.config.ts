import { defineConfig, loadEnv } from 'vite'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import UnoCSS from 'unocss/vite'
export default defineConfig(({ mode }) => { const env = loadEnv(mode, '../../', ''); return { plugins: [react(), UnoCSS()], resolve: { alias: { '@bisheng/api': path.resolve(__dirname, '../../packages/api/src'), '@bisheng/auth': path.resolve(__dirname, '../../packages/auth/src'), '@bisheng/config': path.resolve(__dirname, '../../packages/config/src'), '@bisheng/sse': path.resolve(__dirname, '../../packages/sse/src'), '@bisheng/types': path.resolve(__dirname, '../../packages/types/src'), '@bisheng/ui': path.resolve(__dirname, '../../packages/ui/src') } }, server: { port: 5173, proxy: { '/api': { target: env.VITE_API_BASE_URL || 'http://localhost:8000', changeOrigin: true } } } } })
