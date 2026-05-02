import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const configDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(configDir, '..', '..')
const certDir = resolve(repoRoot, 'ssl-certs')
const certFile = resolve(certDir, 'bgpx.net.crt')
const keyFile = resolve(certDir, 'bgpx.net.key')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    ...(existsSync(certFile) && existsSync(keyFile)
      ? {
          https: {
            cert: readFileSync(certFile),
            key: readFileSync(keyFile),
          },
        }
      : {}),
    proxy: {
      '/api': {
        target: 'https://localhost:443',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
