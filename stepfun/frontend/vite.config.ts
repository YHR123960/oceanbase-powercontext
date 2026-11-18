import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: true,
      },
    },
  },
  // 让 transformers.js 的 WASM 线程与 ONNX Runtime 资源可被正确打包
  optimizeDeps: {
    exclude: ['@huggingface/transformers'],
  },
});
