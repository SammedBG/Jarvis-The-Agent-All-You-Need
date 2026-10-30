import { test, expect } from '@playwright/test'

async function login(page: any) {
  await page.goto('http://127.0.0.1:18000/login')
  const inputs = page.locator('input')
  await inputs.nth(0).fill('owner')
  await inputs.nth(1).fill('supersecret1234')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForTimeout(1500)
}

test('settings', async ({ page }) => {
  await login(page)
  await page.goto('http://127.0.0.1:18000/settings', { waitUntil: 'networkidle' })
  await page.setViewportSize({ width: 1280, height: 900 })
  await expect(page.getByRole('heading', { name: /settings/i })).toBeVisible()
  const body = await page.content()
  expect(body).toContain('Home location')
  expect(body).toContain('Models')
  expect(body).toContain('API key status')
  expect(body).toContain('Fast-path alias whitelist')
  expect(body).toContain('Account')
  // saving a location
  await page.fill('input[placeholder="e.g. Marine Drive, Mumbai"]', 'Indiranagar, Bengaluru')
  await page.getByRole('button', { name: /save location/i }).first().click()
  await page.waitForTimeout(1500)
  const body2 = await page.content()
  expect(body2).toContain('Indiranagar') || expect(body2).toContain('Saved')
  // invalid model
  const mc = page.locator('input[placeholder="groq:openai/gpt-oss-120b"]').first()
  await mc.fill('groq:foo/bar')
  await page.getByRole('button', { name: /save models/i }).click()
  await page.waitForTimeout(1000)
  const body3 = await page.content()
  expect(body3).toContain('model must be one of')
  await page.screenshot({ path: 'screenshots/settings-1280.png', fullPage: true })
  await page.setViewportSize({ width: 375, height: 800 })
  await page.screenshot({ path: 'screenshots/settings-375.png', fullPage: true })
})
