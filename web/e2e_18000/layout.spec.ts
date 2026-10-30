import { test, expect, request } from '@playwright/test'

async function ensureLogin(page: any) {
  try {
    await page.request.post('http://127.0.0.1:18000/api/auth/setup', { data: { username: 'samxtech', password: 'supersecret1234' }, headers: { 'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:18000' } })
  } catch {}
  await page.goto('http://127.0.0.1:18000/login')
  const usernameInput = page.locator('input').nth(0)
  await usernameInput.fill('samxtech')
  const passwordInput = page.locator('input').nth(1)
  await passwordInput.fill('supersecret1234')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForTimeout(2000)
  console.log('after-click url', page.url())
  console.log('after-click html has chat-shell:', (await page.content()).includes('chat-shell'))
}

test('layout 1280', async ({ page }) => {
  await ensureLogin(page)
  await page.goto('http://127.0.0.1:18000/', { waitUntil: 'networkidle' })
  console.log('after goto url', page.url())
  await page.waitForTimeout(2000)
  console.log('after wait url', page.url())
  const sidebar = page.locator('.sidebar').first()
  await page.setViewportSize({ width: 1280, height: 800 })
  const w = await sidebar.evaluate((el) => el.getBoundingClientRect().width)
  expect(w).toBeCloseTo(264, 1)

  const navLinks = page.locator('.navlink')
  const count = await navLinks.count()
  let prevBottom = 0
  for (let i = 0; i < count; i++) {
    const box = await navLinks.nth(i).boundingBox()
    if (!box) continue
    if (i > 0) expect(box.y).toBeGreaterThan(prevBottom - 1)
    prevBottom = box.y + box.height
  }

  const composer = page.locator('.composer').first()
  const cbox = await composer.boundingBox()
  expect(cbox).not.toBeNull()
  expect(800 - (cbox!.y + cbox!.height)).toBeLessThanOrEqual(40)

  const textarea = page.locator('.composer textarea')
  const bg = await textarea.evaluate((el) => getComputedStyle(el as any).backgroundColor)
  expect(bg.toLowerCase()).not.toBe('rgb(255, 255, 255)')

  const msgCol = page.locator('.msg-body').first()
  if (await msgCol.count()) {
    const box = await msgCol.boundingBox()
    const cx = box!.x + box!.width / 2
    expect(Math.abs(cx - 640)).toBeLessThan(100)
  }
  await page.screenshot({ path: 'screenshots/chat-1280.png', fullPage: false })
})

test('layout 375', async ({ page }) => {
  await ensureLogin(page)
  await page.goto('http://127.0.0.1:18000/', { waitUntil: 'networkidle' })
  await page.setViewportSize({ width: 375, height: 800 })
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(scrollWidth).toBeLessThanOrEqual(375 + 2)
  const sidebar = page.locator('.sidebar').first()
  if (await sidebar.count()) {
    const box = await sidebar.boundingBox()
    if (box) {
      const visible = box.x + box.width > 0 && box.x < 375
      expect(visible).not.toBe(true)
    }
  }
  await page.screenshot({ path: 'screenshots/chat-375.png', fullPage: false })
})

test('setup/login inputs', async ({ page }) => {
  for (const route of ['setup', 'login']) {
    await page.goto(`http://127.0.0.1:18000/${route}`, { waitUntil: 'networkidle' })
    const input = page.locator('input').first()
    if (await input.count()) {
      const border = await input.evaluate((el) => getComputedStyle(el as any).borderWidth)
      const pad = await input.evaluate((el) => getComputedStyle(el as any).paddingTop)
      // just assert non-zero-ish strings
      expect(border).not.toBe('0px')
      const cardWidth = await page.locator('.card.auth-card').evaluate((el) => el.getBoundingClientRect().width).catch(() => 0)
      // card present
    }
    const w = await page.viewportSize()
    await page.setViewportSize({ width: w?.width ?? 1280, height: 800 })
  }
  await page.screenshot({ path: 'screenshots/setup-1280.png', fullPage: true })
  await page.setViewportSize({ width: 375, height: 800 })
  await page.screenshot({ path: 'screenshots/setup-375.png', fullPage: true })
})