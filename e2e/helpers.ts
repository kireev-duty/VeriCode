import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const TOKEN_KEY = 'fsp_talent_token'

export async function demoToken(request: APIRequestContext, role: 'employer' | 'candidate' | 'candidate_new'): Promise<string> {
  const r = await request.post(`/api/auth/demo-login?role=${role}`)
  expect(r.ok(), 'demo data must be loaded (SEED_DEMO=true)').toBeTruthy()
  return (await r.json()).access_token
}

/** Opens the app already signed in: the token goes to localStorage before any script of the page runs. */
export async function signIn(page: Page, token: string) {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [TOKEN_KEY, token])
}

export async function tokenOf(page: Page): Promise<string> {
  const token = await page.evaluate((key) => window.localStorage.getItem(key), TOKEN_KEY)
  expect(token).toBeTruthy()
  return token as string
}

/** Answers the current adaptive test until the result page: the first option or "1" for open answers. */
export async function passTest(page: Page) {
  const result = page.getByText(/Результат теста/)
  const submit = page.getByRole('button', { name: /Ответить/ })
  for (let i = 0; i < 40; i++) {
    await expect(submit.or(result).first()).toBeVisible()
    if (await result.isVisible()) return
    const radio = page.locator('input[type="radio"][name="opt"]').first()
    if (await radio.count()) await radio.check()
    else await page.getByPlaceholder(/Число|Ответ — как его выведет программа/).fill('1')
    await expect(submit).toBeEnabled()
    // wait for the server to accept the answer: the next item (or the result) replaces the form
    await Promise.all([page.waitForResponse((r) => r.url().includes('/answer') && r.request().method() === 'POST'), submit.click()])
  }
  throw new Error('the test did not finish in 40 items')
}
