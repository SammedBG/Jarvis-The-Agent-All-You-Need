import { test } from '@playwright/test'
test('dbg5', async ({ page }) => {
  await page.goto('http://127.0.0.1:8000/login')
  await page.fill('input >> nth=0', 'samxtech')
  await page.fill('input[type=password]', 'supersecret1234')
  const btn = page.getByRole('button', { name: /sign in/i })
  await btn.click()
  await page.waitForTimeout(2000)
  console.log('URL', page.url())
  const txt = await page.content()
  console.log(txt.includes('sidebar') ? 'HAS SIDEBAR' : 'NO SIDEBAR')
})
EOF