import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@ledger': path.resolve(__dirname, '../data/processed/quarantine_ledger.json'),
    },
  },
  server: {
    fs: {
      allow: ['..'],
    },
  },
})