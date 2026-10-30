import { defineConfig } from '@playwright/test'
export default defineConfig({ testDir: './e2e_18000', use: { baseURL: 'http://127.0.0.1:18000' }, timeout: 30000 })