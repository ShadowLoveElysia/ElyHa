import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(({mode}) => {
  const isProd = mode === 'production';
  return {
    // FastAPI serves built files under /static
    base: isProd ? '/static/' : '/',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // Set DISABLE_HMR=true to disable HMR in environments with unstable file watching.
      hmr: process.env.DISABLE_HMR !== 'true',
    },
  };
});
