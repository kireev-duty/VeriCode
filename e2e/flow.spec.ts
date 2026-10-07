import { expect, test } from '@playwright/test'
import { demoToken, passTest, signIn, tokenOf } from './helpers'

/**
 * The end-to-end scenario of the spec (3.3): registration with e-mail confirmation -> survey -> adaptive test ->
 * category -> the employer describes a need and gets a shortlist -> an invitation with a salary range to a specific
 * person -> the candidate accepts -> contacts open; plus the classic application to a vacancy.
 */
test('reverse matching: from registration to opened contacts, and an application', async ({ browser, request }) => {
  const email = `e2e.${Date.now()}@example.com`
  const cand = await browser.newPage()

  // 1. registration and e-mail confirmation (the demo stand shows the confirmation link right away)
  await cand.goto('/register')
  await cand.getByRole('button', { name: /Я ищу работу/ }).click()
  await cand.getByLabel('Email').fill(email)
  await cand.getByLabel('Пароль').fill('e2e-password-1')
  await cand.getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(cand.getByRole('heading', { name: 'Подтвердите email' })).toBeVisible()
  await cand.getByRole('link', { name: 'подтвердите сразу' }).click()
  await cand.waitForURL(/\/c\/onboarding/)

  // 2. survey: consents -> specialization -> stack -> questions about work -> declared grade
  await cand.getByRole('checkbox', { name: /обработку персональных данных/ }).check()
  await cand.getByRole('checkbox', { name: /публикацию обезличенного профиля/ }).check()
  await cand.getByRole('button', { name: 'Далее' }).click()
  await cand.getByRole('button', { name: /Backend-разработка/ }).click()
  await cand.getByRole('button', { name: 'Далее' }).click()
  for (const skill of ['Python', 'PostgreSQL', 'Docker']) await cand.getByRole('button', { name: skill, exact: true }).click()
  await cand.getByRole('button', { name: 'Далее' }).click()
  const questions = cand.locator('div.font-medium + div.grid')
  for (let i = 0; i < (await questions.count()); i++) await questions.nth(i).locator('button').nth(1).click()
  await cand.getByRole('button', { name: 'Далее' }).click()
  await cand.getByRole('button', { name: /^Junior/ }).click()
  await cand.getByRole('button', { name: 'Перейти к тесту' }).click()

  // 3. adaptive test -> category
  await cand.waitForURL(/\/c\/test/)
  await cand.getByRole('button', { name: /^Junior/ }).click()
  await cand.getByRole('button', { name: /Начать тест/ }).click()
  await passTest(cand)
  await expect(cand.getByText(/Грейд .* (подтверждён|пока не подтверждён)/)).toBeVisible()
  const candToken = await tokenOf(cand)
  let profile = await (await request.get('/api/candidate/profile', { headers: { Authorization: `Bearer ${candToken}` } })).json()
  if (!profile.grade) {
    // not confirmed on Junior: the lower grade is available right away, as the policy says
    const first = cand.url()
    await cand.getByRole('button', { name: /Тест на Intern/ }).click()
    await cand.waitForURL((u) => u.toString() !== first)
    await passTest(cand)
    profile = await (await request.get('/api/candidate/profile', { headers: { Authorization: `Bearer ${candToken}` } })).json()
  }
  expect(profile.grade).toBeTruthy()
  await request.put('/api/candidate/profile', {
    headers: { Authorization: `Bearer ${candToken}` },
    data: { full_name: 'Тест Тестов', phone: '+79990001122', salary_expectation: 150000 },
  })

  // 4. employer: a need in plain text -> parsed -> shortlist with explanations
  const emp = await browser.newPage()
  await signIn(emp, await demoToken(request, 'employer'))
  await emp.goto('/e/needs/new')
  await emp
    .locator('textarea')
    .first()
    .fill('Ищем Junior Python-разработчика: Django или FastAPI, PostgreSQL, Docker. Удалённо, 120–180 тыс. ₽.')
  await emp.getByRole('button', { name: 'Разобрать текст' }).click()
  await expect(emp.getByText(/Разобрано правилами/)).toBeVisible()
  await emp.getByRole('button', { name: 'Найти кандидатов' }).click()
  await emp.waitForURL(/\/e\/needs\/\d+$/)
  await expect(emp.getByText(/Рекомендованные категории|Подборка/).first()).toBeVisible()

  // 5. contact with a specific person: invitation with a mandatory salary range
  await emp.goto(`/e/candidates/${profile.id}`)
  await expect(emp.getByText('Контакты')).toBeVisible()
  await expect(emp.getByText('+79990001122')).toHaveCount(0) // hidden before acceptance
  await emp.getByRole('button', { name: 'Пригласить' }).click()
  await emp.getByLabel('Позиция').fill('Junior Python-разработчик')
  await emp.getByLabel('Зарплата от, ₽/мес').fill('140000')
  await emp.getByLabel('Зарплата до, ₽/мес').fill('180000')
  await expect(emp.getByText('Проверка вилки')).toBeVisible()
  await emp.getByRole('button', { name: /Отправить ·/ }).click()
  await expect(emp.getByRole('button', { name: 'Приглашение отправлено' })).toBeVisible()

  // 6. the candidate sees the offer with salary before any contact and accepts
  await cand.goto('/c/invitations')
  await expect(cand.getByText('Junior Python-разработчик').first()).toBeVisible()
  await cand.getByText('Junior Python-разработчик').first().click()
  await cand.getByRole('button', { name: 'Принять и открыть контакты' }).click()
  await cand.getByRole('button', { name: /^Все/ }).click()
  await expect(cand.getByText('Принято').first()).toBeVisible()

  // 7. contacts are open for the employer now
  await emp.reload()
  await expect(emp.getByText('Тест Тестов').first()).toBeVisible()

  // 8. classic flow: the candidate applies to a published vacancy
  await cand.goto('/c/vacancies')
  await cand.getByRole('button', { name: 'Откликнуться' }).first().click()
  await cand.getByRole('dialog').getByRole('button', { name: /Откликнуться|Отправить/ }).click()
  await cand.goto('/c/applications')
  await expect(cand.getByText(/Отправлен|отправлен/).first()).toBeVisible()
})
