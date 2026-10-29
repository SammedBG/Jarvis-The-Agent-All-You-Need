# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: layout.spec.ts >> layout 1280
- Location: e2e/layout.spec.ts:18:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.evaluate: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('.sidebar').first()

```

# Page snapshot

```yaml
- generic [ref=f1e4]:
  - heading "JARVIS" [level=1] [ref=f1e5]
  - paragraph [ref=f1e6]: Sign in to continue.
  - generic [ref=f1e7]:
    - generic [ref=f1e8]:
      - text: Username
      - textbox "Username" [ref=f1e9]
    - generic [ref=f1e10]:
      - text: Password
      - generic [ref=f1e11]:
        - textbox "Password Show" [ref=f1e12]
        - button "Show" [ref=f1e13] [cursor=pointer]
    - button "Sign in" [ref=f1e14] [cursor=pointer]
```

# Test source

```ts
  1  | import { test, expect, request } from '@playwright/test'
  2  | 
  3  | async function ensureLogin(page: any) {
  4  |   try {
  5  |     await page.request.post('http://127.0.0.1:8000/api/auth/setup', { data: { username: 'samxtech', password: 'supersecret1234' }, headers: { 'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8000' } })
  6  |   } catch {}
  7  |   await page.goto('http://127.0.0.1:8000/login', { waitUntil: 'networkidle' })
  8  |   const inputs = page.locator('input')
  9  |   if (await inputs.count() > 0) {
  10 |     await inputs.nth(0).fill('samxtech')
  11 |     await inputs.nth(1).fill('supersecret1234')
  12 |     await page.getByRole('button', { name: /sign in/i }).click()
  13 |     await page.waitForURL('**/', { timeout: 10000 }).catch(() => {})
  14 |     await page.waitForTimeout(500)
  15 |   }
  16 | }
  17 | 
  18 | test('layout 1280', async ({ page }) => {
  19 |   await ensureLogin(page)
  20 |   await page.goto('http://localhost:8000/', { waitUntil: 'networkidle' })
  21 |   await page.setViewportSize({ width: 1280, height: 800 })
  22 |   const sidebar = page.locator('.sidebar').first()
> 23 |   const w = await sidebar.evaluate((el) => el.getBoundingClientRect().width)
     |                           ^ Error: locator.evaluate: Test timeout of 30000ms exceeded.
  24 |   expect(w).toBeCloseTo(264, 1)
  25 | 
  26 |   const navLinks = page.locator('.navlink')
  27 |   const count = await navLinks.count()
  28 |   let prevBottom = 0
  29 |   for (let i = 0; i < count; i++) {
  30 |     const box = await navLinks.nth(i).boundingBox()
  31 |     if (!box) continue
  32 |     if (i > 0) expect(box.y).toBeGreaterThan(prevBottom - 1)
  33 |     prevBottom = box.y + box.height
  34 |   }
  35 | 
  36 |   const composer = page.locator('.composer').first()
  37 |   const cbox = await composer.boundingBox()
  38 |   expect(cbox).not.toBeNull()
  39 |   expect(800 - (cbox!.y + cbox!.height)).toBeLessThanOrEqual(40)
  40 | 
  41 |   const textarea = page.locator('.composer textarea')
  42 |   const bg = await textarea.evaluate((el) => getComputedStyle(el as any).backgroundColor)
  43 |   expect(bg.toLowerCase()).not.toBe('rgb(255, 255, 255)')
  44 | 
  45 |   const msgCol = page.locator('.msg-body').first()
  46 |   if (await msgCol.count()) {
  47 |     const box = await msgCol.boundingBox()
  48 |     const cx = box!.x + box!.width / 2
  49 |     expect(Math.abs(cx - 640)).toBeLessThan(100)
  50 |   }
  51 |   await page.screenshot({ path: 'screenshots/chat-1280.png', fullPage: false })
  52 | })
  53 | 
  54 | test('layout 375', async ({ page }) => {
  55 |   await ensureLogin(page)
  56 |   await page.goto('http://localhost:8000/', { waitUntil: 'networkidle' })
  57 |   await page.setViewportSize({ width: 375, height: 800 })
  58 |   const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  59 |   expect(scrollWidth).toBeLessThanOrEqual(375 + 2)
  60 |   const sidebar = page.locator('.sidebar').first()
  61 |   if (await sidebar.count()) {
  62 |     const box = await sidebar.boundingBox()
  63 |     if (box) {
  64 |       const visible = box.x + box.width > 0 && box.x < 375
  65 |       expect(visible).not.toBe(true)
  66 |     }
  67 |   }
  68 |   await page.screenshot({ path: 'screenshots/chat-375.png', fullPage: false })
  69 | })
  70 | 
  71 | test('setup/login inputs', async ({ page }) => {
  72 |   for (const route of ['setup', 'login']) {
  73 |     await page.goto(`http://localhost:8000/${route}`, { waitUntil: 'networkidle' })
  74 |     const input = page.locator('input').first()
  75 |     if (await input.count()) {
  76 |       const border = await input.evaluate((el) => getComputedStyle(el as any).borderWidth)
  77 |       const pad = await input.evaluate((el) => getComputedStyle(el as any).paddingTop)
  78 |       // just assert non-zero-ish strings
  79 |       expect(border).not.toBe('0px')
  80 |       const cardWidth = await page.locator('.card.auth-card').evaluate((el) => el.getBoundingClientRect().width).catch(() => 0)
  81 |       // card present
  82 |     }
  83 |     const w = await page.viewportSize()
  84 |     await page.setViewportSize({ width: w?.width ?? 1280, height: 800 })
  85 |   }
  86 |   await page.screenshot({ path: 'screenshots/setup-1280.png', fullPage: true })
  87 |   await page.setViewportSize({ width: 375, height: 800 })
  88 |   await page.screenshot({ path: 'screenshots/setup-375.png', fullPage: true })
  89 | })
```