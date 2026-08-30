import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  // Метка сборки: прошивается в bundle при каждой сборке и выводится в Title
  // вкладки — однозначно идентифицирует, какой build загружен в браузере.
  define: {
    __BUILD_STAMP__: JSON.stringify(new Date().toISOString()),
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
});
