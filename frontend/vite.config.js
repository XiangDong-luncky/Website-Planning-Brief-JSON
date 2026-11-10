import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境把 /api 开头的请求转发到 Spring Boot，浏览器视角下同源，不会有跨域问题
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true
      }
    }
  }
})
