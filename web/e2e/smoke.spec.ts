import { test, expect } from '@playwright/test'

test('shell layout', async ({ page }) => {
  await page.goto('http://localhost:8000/login', { waitUntil: 'networkidle' }).catch(()=>{})
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 800 })
    await page.screenshot({ path: `screenshots/login-${w}.png`, fullPage: true })
  }
})
test('chat', async ({ page }) => {
  await page.goto('http://localhost:8000/', { waitUntil: 'networkidle' }).catch(()=>{})
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.screenshot({ path: 'screenshots/chat-1280.png', fullPage: false })
  await page.setViewportSize({ width: 375, height: 800 })
  await page.screenshot({ path: 'screenshots/chat-375.png', fullPage: false })
})
test('setup', async ({ page }) => {
  await page.goto('http://localhost:8000/setup', { waitUntil: 'networkidle' }).catch(()=>{})
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 800 })
    await page.screenshot({ path: `screenshots/setup-${w}.png`, fullPage: true })
  }
})