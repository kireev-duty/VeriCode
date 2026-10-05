import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { api } from '../../api/client'
import type { CandidateProfile, GradeId, WorkFormat } from '../../api/types'
import { Alert, Button, Card, Checkbox, Field, Input, MultiChips, PageLoader } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import { useCatalog } from '../../lib/catalog'

const STEPS = ['Согласия', 'Специализация', 'Стек и опыт', 'Самооценка', 'Грейд']

const QUESTIONS = [
  {
    id: 'autonomy',
    q: 'Как вы обычно работаете над задачей?',
    a: [
      ['intern', 'Учусь, нужны подробные инструкции и помощь'],
      ['junior', 'Решаю типовые задачи, иногда прошу совета'],
      ['middle', 'Самостоятельно веду задачи от постановки до релиза'],
      ['senior', 'Определяю, как решать задачи команды, и помогаю другим'],
    ],
  },
  {
    id: 'scope',
    q: 'Какой масштаб решений вы принимали за последний год?',
    a: [
      ['intern', 'В рамках учебных или пет-проектов'],
      ['junior', 'Внутри одной функции или компонента'],
      ['middle', 'Модуль или сервис целиком'],
      ['senior', 'Архитектура нескольких сервисов, выбор технологий'],
    ],
  },
  {
    id: 'review',
    q: 'Ваша роль в код-ревью?',
    a: [
      ['intern', 'Мой код ревьюят, ревью других не провожу'],
      ['junior', 'Иногда ревьюю код коллег'],
      ['middle', 'Регулярно ревьюю, мои замечания принимают'],
      ['senior', 'Формирую стандарты кода в команде'],
    ],
  },
] as const

const ORDER: GradeId[] = ['intern', 'junior', 'middle', 'senior']

export function Onboarding() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { refresh } = useAuth()
  const { catalog, skillTitle } = useCatalog()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: () => api.get<CandidateProfile>('/api/candidate/profile') })
  const [step, setStep] = useState(0)
  const [processing, setProcessing] = useState(true)
  const [publication, setPublication] = useState(true)
  const [spec, setSpec] = useState<string>('')
  const [industries, setIndustries] = useState<string[]>([])
  const [stack, setStack] = useState<Record<string, number | null>>({})
  const [years, setYears] = useState<number>(1)
  const [roles, setRoles] = useState<string[]>([])
  const [formats, setFormats] = useState<WorkFormat[]>(['remote'])
  const [answers, setAnswers] = useState<Record<string, GradeId>>({})
  const [grade, setGrade] = useState<GradeId | null>(null)

  const specObj = catalog?.specializations.find((s) => s.id === spec)
  const hint = useMemo(() => {
    const vals = Object.values(answers).map((g) => ORDER.indexOf(g))
    const byYears = years >= 5 ? 3 : years >= 2 ? 2 : years >= 1 ? 1 : 0
    if (!vals.length) return ORDER[byYears]
    const avg = (vals.reduce((a, b) => a + b, 0) + byYears) / (vals.length + 1)
    return ORDER[Math.round(avg)]
  }, [answers, years])

  const consents = useMutation({ mutationFn: () => api.post('/api/candidate/consents', { processing, publication }) })
  const save = useMutation({
    mutationFn: () =>
      api.post('/api/candidate/onboarding', {
        industries,
        specialization: spec,
        stack: Object.entries(stack).map(([id, y]) => ({ id, years: y })),
        experience_years: years,
        declared_grade: grade,
        team_roles: roles,
        work_formats: formats,
        answers,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profile'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      refresh()
      nav('/c/test')
    },
  })

  if (!catalog || !profile) return <PageLoader />

  const canNext = [processing, !!spec, Object.keys(stack).length >= 2, Object.keys(answers).length === QUESTIONS.length, !!grade][step]
  const next = async () => {
    if (step === 0) await consents.mutateAsync()
    if (step === 3 && !grade) setGrade(hint)
    if (step < STEPS.length - 1) setStep(step + 1)
    else save.mutate()
  }
  const extra = ['git', 'docker', 'sql', 'linux', 'algorithms', 'oop', 'http', 'security'].filter((s) => !specObj?.stack_options.includes(s))

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <div className="mono-label text-brand-500">Опрос · шаг {step + 1} из {STEPS.length}</div>
        <div className="mt-3 flex gap-1.5">
          {STEPS.map((s, i) => (
            <div key={s} className="flex-1">
              <div className={clsx('h-1.5 rounded-full', i <= step ? 'bg-brand-500' : 'bg-line')} />
              <div className={clsx('mt-1.5 hidden text-xs sm:block', i === step ? 'font-medium text-ink' : 'text-muted')}>{s}</div>
            </div>
          ))}
        </div>
      </div>

      <Card className="animate-fade-in p-6 md:p-8" key={step}>
        {step === 0 && (
          <div className="space-y-5">
            <div>
              <h1 className="text-2xl font-semibold">Согласия на обработку данных</h1>
              <p className="mt-1 text-muted">По 152-ФЗ мы спрашиваем отдельно: можно ли обрабатывать данные и можно ли показывать профиль работодателям.</p>
            </div>
            <Checkbox
              checked={processing}
              onChange={setProcessing}
              label="Согласен на обработку персональных данных (обязательно)"
              hint="Профиль, результаты тестов и достижения ФСП хранятся для подбора. Удалить всё можно в настройках в один клик."
            />
            <Checkbox
              checked={publication}
              onChange={setPublication}
              label="Согласен на публикацию обезличенного профиля для работодателей"
              hint="Работодатели видят категорию, навыки и достижения без ФИО и контактов. Контакты открываются только после вашего согласия на конкретное приглашение."
            />
            {!publication && <Alert tone="warn">Без согласия на публикацию вы сможете пройти тест и откликаться на вакансии, но не попадёте в подборки работодателей.</Alert>}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold">Ваша специализация</h1>
              <p className="mt-1 text-muted">По ней формируется тест и категория.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {catalog.specializations.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    setSpec(s.id)
                    setStack({})
                  }}
                  className={clsx('rounded-xl border p-4 text-left transition', spec === s.id ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-100' : 'border-line hover:border-brand-300')}
                >
                  <div className="font-semibold">{s.title}</div>
                  <div className="mt-1 text-sm text-muted">{s.description}</div>
                </button>
              ))}
            </div>
            <Field label="Отрасли, в которых есть опыт" hint="Необязательно">
              <MultiChips size="sm" options={catalog.industries.map((i) => ({ id: i, title: i }))} value={industries} onChange={setIndustries} />
            </Field>
          </div>
        )}

        {step === 2 && specObj && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold">Стек и опыт</h1>
              <p className="mt-1 text-muted">Отметьте технологии, с которыми работали. Тест проверит ключевые из них.</p>
            </div>
            <Field label="Технологии специализации">
              <MultiChips
                options={specObj.stack_options.map((s) => ({ id: s, title: skillTitle(s) }))}
                value={Object.keys(stack)}
                onChange={(v) => setStack(Object.fromEntries(v.map((id) => [id, stack[id] ?? null])))}
              />
            </Field>
            <Field label="Общие навыки">
              <MultiChips
                size="sm"
                options={extra.map((s) => ({ id: s, title: skillTitle(s) }))}
                value={Object.keys(stack).filter((s) => extra.includes(s))}
                onChange={(v) => {
                  const base = Object.fromEntries(Object.entries(stack).filter(([k]) => !extra.includes(k)))
                  setStack({ ...base, ...Object.fromEntries(v.map((id) => [id, stack[id] ?? null])) })
                }}
              />
            </Field>
            {Object.keys(stack).length > 0 && (
              <div>
                <div className="mb-2 text-sm font-medium">Сколько лет с каждой технологией?</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.keys(stack).map((id) => (
                    <div key={id} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2">
                      <span className="text-sm">{skillTitle(id)}</span>
                      <Input
                        type="number"
                        min={0}
                        max={30}
                        step={0.5}
                        className="h-8 w-20"
                        placeholder="лет"
                        value={stack[id] ?? ''}
                        onChange={(e) => setStack({ ...stack, [id]: e.target.value === '' ? null : Number(e.target.value) })}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Общий коммерческий опыт, лет">
                <Input type="number" min={0} max={50} step={0.5} value={years} onChange={(e) => setYears(Number(e.target.value))} />
              </Field>
              <Field label="Формат работы">
                <MultiChips
                  size="sm"
                  options={(Object.entries(catalog.work_formats) as [WorkFormat, string][]).map(([id, title]) => ({ id, title }))}
                  value={formats}
                  onChange={setFormats}
                />
              </Field>
            </div>
            <Field label="Роли в команде">
              <MultiChips size="sm" options={catalog.team_roles.map((r) => ({ id: r, title: r }))} value={roles} onChange={setRoles} />
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold">Немного о вашей работе</h1>
              <p className="mt-1 text-muted">Эти ответы помогут выбрать грейд для теста. Они не попадают в категорию — её определяет только тест.</p>
            </div>
            {QUESTIONS.map((q) => (
              <div key={q.id}>
                <div className="mb-2 font-medium">{q.q}</div>
                <div className="grid gap-2">
                  {q.a.map(([g, text]) => (
                    <button
                      key={g}
                      onClick={() => setAnswers({ ...answers, [q.id]: g })}
                      className={clsx(
                        'rounded-xl border px-4 py-2.5 text-left text-sm transition',
                        answers[q.id] === g ? 'border-brand-500 bg-brand-50' : 'border-line hover:border-brand-300',
                      )}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-5">
            <div>
              <h1 className="text-2xl font-semibold">Предполагаемый грейд</h1>
              <p className="mt-1 text-muted">Тест начнётся с заданий этого уровня. Если не подтвердится — сразу можно пройти тест на уровень ниже, без понижения.</p>
            </div>
            <Alert tone="brand">
              По вашим ответам и опыту ближе всего — <b>{catalog.grades.find((g) => g.id === hint)?.title}</b>.
            </Alert>
            <div className="grid gap-3 sm:grid-cols-2">
              {catalog.grades.map((g) => (
                <button
                  key={g.id}
                  onClick={() => setGrade(g.id)}
                  className={clsx('rounded-xl border p-4 text-left transition', grade === g.id ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-100' : 'border-line hover:border-brand-300')}
                >
                  <div className="flex items-center justify-between font-semibold">
                    {g.title}
                    {grade === g.id && <Check className="size-4 text-brand-500" />}
                  </div>
                  <div className="mt-1 text-sm text-muted">{g.description}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {(save.error || consents.error) && <Alert tone="danger" className="mt-4">{((save.error || consents.error) as Error).message}</Alert>}
        <div className="mt-8 flex justify-between">
          <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)} icon={<ArrowLeft className="size-4" />}>
            Назад
          </Button>
          <Button size="lg" disabled={!canNext} loading={save.isPending || consents.isPending} onClick={next}>
            {step === STEPS.length - 1 ? 'Перейти к тесту' : 'Далее'} <ArrowRight className="size-4" />
          </Button>
        </div>
      </Card>
    </div>
  )
}
