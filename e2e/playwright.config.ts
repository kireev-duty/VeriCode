import { defineConfig } from '@playwright/test'

// Runs against a stand started with `docker compose up -d --build` (demo data loaded).
// BASE_URL overrides the address, e.g. a deployed stand.
export default defineConfig({
  testDir: '.',
  timeout: 420_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8080',
    locale: 'ru-RU',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
