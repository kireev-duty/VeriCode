import { expect, test } from '@playwright/test'
import { demoToken, signIn } from './helpers'

/**
 * Every page at desktop (1440) and phone (375) width: a screenshot to e2e/screens/ for the UX review and the
 * presentation, and a check that the page has no horizontal scroll (the mobile layout is a criterion of the spec).
 */
const PUBLIC = ['/', '/how', '/login', '/register']
const CANDIDATE = ['/c', '/c/test', '/c/invitations', '/c/vacancies', '/c/applications', '/c/tasks', '/c/profile', '/c/settings']
const EMPLOYER = ['/e', '/e/needs/new', '/e/search', '/e/invitations', '/e/vacancies', '/e/tasks', '/e/company']
const WIDTHS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'phone', width: 375, height: 812 },
]

function fileName(role: string, path: string, width: string) {
  const slug = path === '/' ? 'home' : path.replace(/^\//, '').replace(/\//g, '-')
  return `screens/${width}/${role}-${slug}.png`
}

for (const w of WIDTHS) {
  test.describe(`${w.name} ${w.width}px`, () => {
    test.use({ viewport: { width: w.width, height: w.height } })

    for (const [role, paths] of [['public', PUBLIC], ['candidate', CANDIDATE], ['employer', EMPLOYER]] as const) {
      test(`${role} pages`, async ({ page, request }) => {
        if (role !== 'public') await signIn(page, await demoToken(request, role))
        const overflow: string[] = []
        for (const path of paths) {
          await page.goto(path)
          await page.waitForLoadState('networkidle')
          await expect(page.locator('main')).toBeVisible()
          await page.screenshot({ path: fileName(role, path, w.name), fullPage: true })
          const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
          if (wide > 1) overflow.push(`${path}: +${wide}px`)
        }
        expect(overflow, 'pages with a horizontal scroll').toEqual([])
      })
    }
  })
}
