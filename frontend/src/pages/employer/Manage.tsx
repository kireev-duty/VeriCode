import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Check, CircleAlert, Plus, Trash2, Wand2, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../../api/client'
import type { CandidateCard, GradeId, TrustInfo, Vacancy, WorkFormat } from '../../api/types'
import { Alert, Badge, Button, Card, ChipToggle, Empty, Field, Input, Modal, MultiChips, PageHeader, PageLoader, ProgressBar, SectionTitle, Select, Textarea } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { APPLICATION_STATUS, ago, salaryRange } from '../../lib/format'
import { CandidateRow } from './shared'

// ------------------------------------------------------------------------------------------- vacancies

type VacForm = Pick<Vacancy, 'title' | 'description' | 'specialization' | 'grade' | 'must_skills' | 'nice_skills' | 'work_formats' | 'city' | 'salary_from' | 'salary_to' | 'status'>

const EMPTY_VAC: VacForm = {
  title: '',
  description: '',
  specialization: 'backend',
  grade: 'middle',
  must_skills: [],
  nice_skills: [],
  work_formats: ['remote'],
  city: '',
  salary_from: 0,
  salary_to: 0,
  status: 'published',
}

function VacancyEditor({ vacancy, onClose }: { vacancy: Vacancy | 'new' | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { catalog, skillTitle } = useCatalog()
  const [f, setF] = useState<VacForm>(EMPTY_VAC)
  useEffect(() => {
    if (vacancy && vacancy !== 'new') setF({ ...vacancy })
    else setF(EMPTY_VAC)
  }, [vacancy])
  const parse = useMutation({
    mutationFn: () => api.post<{ specialization: string | null; grade: GradeId | null; must_skills: string[]; nice_skills: string[]; work_formats: WorkFormat[]; city: string; salary_from: number | null; salary_to: number | null }>('/api/employer/needs/parse', { text: f.description }),
    onSuccess: (p) =>
      setF({
        ...f,
        specialization: p.specialization ?? f.specialization,
        grade: p.grade ?? f.grade,
        must_skills: p.must_skills,
        nice_skills: p.nice_skills,
        work_formats: p.work_formats.length ? p.work_formats : f.work_formats,
        city: p.city || f.city,
        salary_from: p.salary_from ?? f.salary_from,
        salary_to: p.salary_to ?? f.salary_to,
      }),
  })
  const save = useMutation({
    mutationFn: () => (vacancy && vacancy !== 'new' ? api.put(`/api/employer/vacancies/${vacancy.id}`, f) : api.post('/api/employer/vacancies', f)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['emp-vacancies'] })
      onClose()
    },
  })
  if (!catalog) return null
  const set = <K extends keyof VacForm>(k: K, v: VacForm[K]) => setF({ ...f, [k]: v })
  const spec = catalog.specializations.find((s) => s.id === f.specialization)
  return (
    <Modal open={!!vacancy} onClose={onClose} title={vacancy === 'new' ? 'Новая вакансия' : 'Редактирование вакансии'} wide>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <Field label="Название"><Input required value={f.title} onChange={(e) => set('title', e.target.value)} /></Field>
        <Field label="Описание">
          <Textarea rows={5} value={f.description} onChange={(e) => set('description', e.target.value)} />
        </Field>
        <Button type="button" size="sm" variant="secondary" icon={<Wand2 className="size-4" />} loading={parse.isPending} disabled={f.description.length < 10} onClick={() => parse.mutate()}>
          Заполнить поля из описания
        </Button>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Специализация">
            <Select value={f.specialization} onChange={(e) => set('specialization', e.target.value)}>
              {catalog.specializations.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </Select>
          </Field>
          <Field label="Грейд">
            <div className="flex flex-wrap gap-2">
              {catalog.grades.map((g) => (
                <ChipToggle key={g.id} size="sm" active={f.grade === g.id} onClick={() => set('grade', g.id)}>{g.title}</ChipToggle>
              ))}
            </div>
          </Field>
        </div>
        <Field label="Обязательные навыки">
          <MultiChips size="sm" options={(spec?.stack_options ?? []).concat(f.must_skills.filter((s) => !spec?.stack_options.includes(s))).map((s) => ({ id: s, title: skillTitle(s) }))} value={f.must_skills} onChange={(v) => set('must_skills', v)} />
        </Field>
        <Field label="Будет плюсом">
          <MultiChips size="sm" options={(spec?.stack_options ?? []).concat(f.nice_skills.filter((s) => !spec?.stack_options.includes(s))).filter((s) => !f.must_skills.includes(s)).map((s) => ({ id: s, title: skillTitle(s) }))} value={f.nice_skills} onChange={(v) => set('nice_skills', v)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Зарплата от, ₽"><Input type="number" required min={1} step={5000} value={f.salary_from || ''} onChange={(e) => set('salary_from', Number(e.target.value))} /></Field>
          <Field label="Зарплата до, ₽"><Input type="number" required min={1} step={5000} value={f.salary_to || ''} onChange={(e) => set('salary_to', Number(e.target.value))} /></Field>
          <Field label="Формат">
            <MultiChips size="sm" options={(Object.entries(catalog.work_formats) as [WorkFormat, string][]).map(([id, title]) => ({ id, title }))} value={f.work_formats} onChange={(v) => set('work_formats', v)} />
          </Field>
          <Field label="Город"><Input value={f.city} onChange={(e) => set('city', e.target.value)} /></Field>
          <Field label="Статус">
            <Select value={f.status} onChange={(e) => set('status', e.target.value as VacForm['status'])}>
              <option value="published">Опубликована</option>
              <option value="draft">Черновик</option>
              <option value="closed">Закрыта</option>
            </Select>
          </Field>
        </div>
        {save.error && <Alert tone="danger">{(save.error as Error).message}</Alert>}
        <Button className="w-full" size="lg" loading={save.isPending}>Сохранить</Button>
      </form>
    </Modal>
  )
}

export function EmployerVacancies() {
  const { skillTitle } = useCatalog()
  const [edit, setEdit] = useState<Vacancy | 'new' | null>(null)
  const { data } = useQuery({ queryKey: ['emp-vacancies'], queryFn: () => api.get<Vacancy[]>('/api/employer/vacancies') })
  if (!data) return <PageLoader />
  return (
    <div>
      <PageHeader
        label="Классический сценарий"
        title="Вакансии и отклики"
        subtitle="Опубликованные вакансии видят кандидаты, которые пока не получили приглашений. Отклик открывает их контакты."
        action={<Button icon={<Plus className="size-4" />} onClick={() => setEdit('new')}>Новая вакансия</Button>}
      />
      {data.length === 0 ? (
        <Empty icon={<Briefcase className="size-8" />} title="Вакансий пока нет" />
      ) : (
        <div className="space-y-3">
          {data.map((v) => (
            <Card key={v.id} className="flex flex-wrap items-center gap-4 p-5">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{v.title}</span>
                  <Badge tone="brand">{v.specialization_title} · {v.grade_title}</Badge>
                  <Badge tone={v.status === 'published' ? 'ok' : 'muted'}>{{ published: 'опубликована', draft: 'черновик', closed: 'закрыта' }[v.status]}</Badge>
                </div>
                <div className="mt-1 text-sm text-muted">
                  {salaryRange(v.salary_from, v.salary_to)} · {v.must_skills.map(skillTitle).join(', ')} · {ago(v.created_at)}
                </div>
              </div>
              <Link to={`/e/vacancies/${v.id}`} className="text-sm font-medium text-brand-600">
                Отклики: {v.applications}
                {!!v.new_applications && <Badge tone="danger" className="ml-1">+{v.new_applications}</Badge>}
              </Link>
              <Button size="sm" variant="secondary" onClick={() => setEdit(v)}>Изменить</Button>
            </Card>
          ))}
        </div>
      )}
      <VacancyEditor vacancy={edit} onClose={() => setEdit(null)} />
    </div>
  )
}

interface AppRow {
  id: number
  status: string
  cover_letter: string
  employer_comment: string
  created_at: string
  candidate: CandidateCard & { contacts: { full_name: string; email: string; phone: string; telegram: string } | null }
}

export function VacancyApplications() {
  const { id } = useParams()
  const qc = useQueryClient()
  const { data: vacancies } = useQuery({ queryKey: ['emp-vacancies'], queryFn: () => api.get<Vacancy[]>('/api/employer/vacancies') })
  const { data } = useQuery({ queryKey: ['applications', id], queryFn: () => api.get<AppRow[]>(`/api/employer/vacancies/${id}/applications`) })
  const status = useMutation({
    mutationFn: ({ appId, s }: { appId: number; s: string }) => api.post(`/api/employer/applications/${appId}/status`, { status: s }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['applications', id] }),
  })
  const v = vacancies?.find((x) => String(x.id) === id)
  if (!data) return <PageLoader />
  return (
    <div>
      <Link to="/e/vacancies" className="mb-4 inline-block text-sm text-brand-600">← к вакансиям</Link>
      <PageHeader label="Отклики" title={v?.title ?? 'Вакансия'} subtitle="Отклики отсортированы по соответствию вакансии. Контакты кандидатов открыты: они откликнулись сами." />
      {data.length === 0 ? (
        <Empty title="Откликов пока нет" />
      ) : (
        <div className="space-y-4">
          {data.map((a) => (
            <div key={a.id}>
              <CandidateRow c={a.candidate} />
              <Card className="-mt-2 rounded-t-none border-t-0 p-4">
                {a.cover_letter && <p className="mb-3 text-sm whitespace-pre-line">«{a.cover_letter}»</p>}
                {a.candidate.contacts && (
                  <div className="mb-3 text-sm">
                    <b>{a.candidate.contacts.full_name}</b> · {a.candidate.contacts.email} · {a.candidate.contacts.phone} · {a.candidate.contacts.telegram}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={APPLICATION_STATUS[a.status]?.tone}>{APPLICATION_STATUS[a.status]?.label}</Badge>
                  <span className="text-xs text-muted">{ago(a.created_at)}</span>
                  {a.status !== 'withdrawn' && (
                    <div className="ml-auto flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => status.mutate({ appId: a.id, s: 'invited' })}>Пригласить на интервью</Button>
                      <Button size="sm" variant="ghost" onClick={() => status.mutate({ appId: a.id, s: 'rejected' })}>Отказать</Button>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- tasks

interface EmpTask {
  id: number
  title: string
  body: string
  kind: string
  specialization: string
  min_grade: string
  skills: string[]
  rubric: { point: string; keywords: string[] }[]
  active: boolean
  offered: number
  submitted: number
  avg_score: number | null
}

export function EmployerTasks() {
  const qc = useQueryClient()
  const { catalog, specShort, gradeTitle } = useCatalog()
  const [create, setCreate] = useState(false)
  const [subsFor, setSubsFor] = useState<EmpTask | null>(null)
  const [form, setForm] = useState({ title: '', body: '', specialization: 'backend', min_grade: 'junior', rubric: [{ point: '', keywords: '' }] })
  const { data } = useQuery({ queryKey: ['emp-tasks'], queryFn: () => api.get<EmpTask[]>('/api/employer/tasks') })
  const { data: subs } = useQuery({
    queryKey: ['task-subs', subsFor?.id],
    queryFn: () => api.get<{ id: number; candidate_id: number; candidate_code: string; answer: string; score: number; feedback: { point: string; hit: boolean }[]; created_at: string }[]>(`/api/employer/tasks/${subsFor!.id}/submissions`),
    enabled: !!subsFor,
  })
  const save = useMutation({
    mutationFn: () =>
      api.post('/api/employer/tasks', {
        title: form.title,
        body: form.body,
        kind: 'approach',
        specialization: form.specialization,
        min_grade: form.min_grade,
        rubric: form.rubric.filter((r) => r.point).map((r) => ({ point: r.point, keywords: r.keywords.split(',').map((k) => k.trim()).filter(Boolean), weight: 1 })),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['emp-tasks'] })
      setCreate(false)
    },
  })
  if (!data || !catalog) return <PageLoader />
  return (
    <div>
      <PageHeader
        label="Регулярные задания"
        title="Задачи для кандидатов"
        subtitle="Раз в неделю кандидаты подходящих категорий получают короткую задачу: решить или предложить подход. Ответы оцениваются по вашей рубрике и обновляют актуальность профиля."
        action={<Button icon={<Plus className="size-4" />} onClick={() => setCreate(true)}>Новое задание</Button>}
      />
      {data.length === 0 ? (
        <Empty icon={<Zap className="size-8" />} title="Заданий пока нет" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((t) => (
            <Card key={t.id} className="p-5">
              <div className="flex flex-wrap gap-2">
                <Badge tone="brand">{specShort(t.specialization)} · от {gradeTitle(t.min_grade)}</Badge>
              </div>
              <div className="mt-2 font-semibold">{t.title}</div>
              <p className="mt-1 line-clamp-3 text-sm text-muted">{t.body}</p>
              <div className="mt-3 text-xs text-muted">Рубрика: {t.rubric.map((r) => r.point).join(' · ')}</div>
              <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-sm">
                <span>Выдано {t.offered} · решено {t.submitted}{t.avg_score != null && ` · средняя оценка ${Math.round(t.avg_score * 100)}%`}</span>
                <Button size="sm" variant="secondary" disabled={!t.submitted} onClick={() => setSubsFor(t)}>Решения</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal open={create} onClose={() => setCreate(false)} title="Новое регулярное задание" wide>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
          <Field label="Название"><Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Условие" hint="Опишите ситуацию из реальной работы команды"><Textarea required minLength={20} rows={4} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Специализация"><Select value={form.specialization} onChange={(e) => setForm({ ...form, specialization: e.target.value })}>{catalog.specializations.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}</Select></Field>
            <Field label="Минимальный грейд"><Select value={form.min_grade} onChange={(e) => setForm({ ...form, min_grade: e.target.value })}>{catalog.grades.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}</Select></Field>
          </div>
          <div>
            <div className="mb-2 text-sm font-medium">Рубрика оценки</div>
            <div className="space-y-2">
              {form.rubric.map((r, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <Input placeholder="Ключевой пункт ответа" value={r.point} onChange={(e) => { const rubric = [...form.rubric]; rubric[i] = { ...r, point: e.target.value }; setForm({ ...form, rubric }) }} />
                  <Input placeholder="Слова-маркеры через запятую" value={r.keywords} onChange={(e) => { const rubric = [...form.rubric]; rubric[i] = { ...r, keywords: e.target.value }; setForm({ ...form, rubric }) }} />
                  <button type="button" className="p-2 text-muted hover:text-accent-500" onClick={() => setForm({ ...form, rubric: form.rubric.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></button>
                </div>
              ))}
            </div>
            <Button type="button" size="sm" variant="ghost" className="mt-2" icon={<Plus className="size-4" />} onClick={() => setForm({ ...form, rubric: [...form.rubric, { point: '', keywords: '' }] })}>Пункт рубрики</Button>
          </div>
          {save.error && <Alert tone="danger">{(save.error as Error).message}</Alert>}
          <Button className="w-full" loading={save.isPending}>Создать</Button>
        </form>
      </Modal>
      <Modal open={!!subsFor} onClose={() => setSubsFor(null)} title={`Решения: ${subsFor?.title ?? ''}`} wide>
        <div className="space-y-4">
          {subs?.map((s) => (
            <div key={s.id} className="rounded-xl border border-line p-4">
              <div className="flex items-center justify-between">
                <Link to={`/e/candidates/${s.candidate_id}`} className="font-mono text-sm font-semibold text-brand-600">{s.candidate_code}</Link>
                <Badge tone={s.score >= 0.6 ? 'ok' : 'warn'}>{Math.round(s.score * 100)}%</Badge>
              </div>
              <p className="mt-2 text-sm whitespace-pre-line">{s.answer}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {s.feedback.map((f) => <Badge key={f.point} tone={f.hit ? 'ok' : 'muted'}>{f.hit ? <Check className="size-3" /> : null}{f.point}</Badge>)}
              </div>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- company

interface CompanyFull {
  id: number
  name: string
  description: string
  industry: string
  website: string
  city: string
  size: string
  contact_name: string
  contact_email: string
  contact_phone: string
  contact_telegram: string
  inn: string
  webhook_url: string
  webhook_secret: string
  logo_color: string
  ranking_weights: Record<string, number>
  quota_left: number
  trust: TrustInfo
}

interface Analytics {
  funnel: Record<string, number>
  acceptance_rate: number | null
  median_response_hours: number | null
  decline_reasons: { reason: string; title: string; count: number }[]
  weights: { component: string; title: string; default: number; current: number }[]
}

export function EmployerCompany() {
  const qc = useQueryClient()
  const { catalog } = useCatalog()
  const { data } = useQuery({ queryKey: ['company'], queryFn: () => api.get<CompanyFull>('/api/employer/company') })
  const { data: analytics } = useQuery({ queryKey: ['analytics'], queryFn: () => api.get<Analytics>('/api/employer/analytics') })
  const [f, setF] = useState<CompanyFull | null>(null)
  useEffect(() => {
    if (data) setF(data)
  }, [data])
  const save = useMutation({
    mutationFn: () => api.put<CompanyFull>('/api/employer/company', { ...f, ranking_weights: undefined, quota_left: undefined, trust: undefined, id: undefined, webhook_secret: undefined }),
    onSuccess: (d) => {
      qc.setQueryData(['company'], d)
      qc.invalidateQueries({ queryKey: ['me'] })
    },
  })
  if (!f || !catalog) return <PageLoader />
  const set = <K extends keyof CompanyFull>(k: K, v: CompanyFull[K]) => setF({ ...f, [k]: v })
  const funnel = analytics ? [
    { name: 'Отправлено', v: analytics.funnel.sent },
    { name: 'Просмотрено', v: analytics.funnel.viewed },
    { name: 'Принято', v: analytics.funnel.accepted },
    { name: 'Отклонено', v: analytics.funnel.declined },
  ] : []
  return (
    <div>
      <PageHeader label="Компания" title={f.name || 'Профиль компании'} subtitle="Профиль виден кандидатам в приглашениях. Полнота и проверяемость данных повышают траст-скор." />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card className="p-6">
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
              <Field label="Название"><Input required value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
              <Field label="Отрасль">
                <Select value={f.industry} onChange={(e) => set('industry', e.target.value)}>
                  <option value="">—</option>
                  {catalog.industries.map((i) => <option key={i}>{i}</option>)}
                </Select>
              </Field>
              <Field label="Описание" className="sm:col-span-2"><Textarea rows={3} value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
              <Field label="Сайт"><Input value={f.website} placeholder="example.ru" onChange={(e) => set('website', e.target.value)} /></Field>
              <Field label="ИНН" hint="Проверяется контрольная сумма"><Input value={f.inn} onChange={(e) => set('inn', e.target.value)} /></Field>
              <Field label="Город"><Input value={f.city} onChange={(e) => set('city', e.target.value)} /></Field>
              <Field label="Размер"><Select value={f.size} onChange={(e) => set('size', e.target.value)}><option value="">—</option>{['1–50', '50–200', '200–500', '500–1000', '1000+'].map((s) => <option key={s}>{s}</option>)}</Select></Field>
              <Field label="Контактное лицо"><Input value={f.contact_name} onChange={(e) => set('contact_name', e.target.value)} /></Field>
              <Field label="Email для кандидатов" hint="Корпоративный домен = домен сайта повышает доверие"><Input value={f.contact_email} onChange={(e) => set('contact_email', e.target.value)} /></Field>
              <Field label="Telegram"><Input value={f.contact_telegram} onChange={(e) => set('contact_telegram', e.target.value)} /></Field>
              <Field label="Телефон"><Input value={f.contact_phone} onChange={(e) => set('contact_phone', e.target.value)} /></Field>
              <div className="border-t border-line pt-4 sm:col-span-2">
                <div className="mono-label mb-2 text-brand-500">Интеграция с ATS</div>
                <Field label="Webhook URL" hint="События invitation.sent / accepted / declined и application.created приходят POST-запросом с подписью HMAC-SHA256 в заголовке X-FSP-Talent-Signature.">
                  <Input value={f.webhook_url} placeholder="https://ats.example.ru/hooks/fsp" onChange={(e) => set('webhook_url', e.target.value)} />
                </Field>
                {f.webhook_secret && <div className="mt-2 font-mono text-xs text-muted">secret: {f.webhook_secret}</div>}
              </div>
              {save.error && <Alert tone="danger" className="sm:col-span-2">{(save.error as Error).message}</Alert>}
              {save.isSuccess && <Alert tone="ok" className="sm:col-span-2">Сохранено</Alert>}
              <Button className="sm:col-span-2" loading={save.isPending}>Сохранить</Button>
            </form>
          </Card>

          {analytics && (
            <Card className="p-6">
              <SectionTitle label="Аналитика" title="Воронка приглашений" />
              <div className="h-48">
                <ResponsiveContainer>
                  <BarChart data={funnel} margin={{ left: -20 }}>
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: 'var(--color-brand-50)' }} />
                    <Bar dataKey="v" name="Приглашений" fill="var(--color-brand-500)" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-4 grid gap-6 md:grid-cols-2">
                <div>
                  <div className="mb-2 text-sm font-medium">Причины отказов</div>
                  {analytics.decline_reasons.length ? (
                    <div className="space-y-2">
                      {analytics.decline_reasons.map((r) => (
                        <div key={r.reason} className="flex items-center justify-between text-sm">
                          <span>{r.title}</span>
                          <Badge>{r.count}</Badge>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted">Отказов не было</div>
                  )}
                  {analytics.median_response_hours != null && <div className="mt-3 text-xs text-muted">Медиана времени ответа: {analytics.median_response_hours} ч</div>}
                </div>
                <div>
                  <div className="mb-2 text-sm font-medium">Веса ранжирования для вашей компании</div>
                  <div className="space-y-2">
                    {analytics.weights.map((w) => (
                      <div key={w.component}>
                        <div className="flex justify-between text-xs">
                          <span>{w.title}</span>
                          <span className="font-mono">
                            {w.current.toFixed(2)}
                            {w.current > w.default + 0.001 && <span className="text-ok"> ↑</span>}
                          </span>
                        </div>
                        <ProgressBar value={w.current / 0.6} className="mt-1 h-1.5" />
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-muted">Отказ с причиной «зарплата» или «стек» повышает вес этого компонента в ваших будущих подборках.</p>
                </div>
              </div>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card className="p-6">
            <div className="mono-label text-brand-500">Защита от фиктивных вакансий</div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-4xl font-semibold">{data!.trust.score}</span>
              <span className="mb-1 text-muted">/ 100 траст-скор</span>
            </div>
            <ProgressBar value={data!.trust.score / 100} tone={data!.trust.level === 'high' ? 'ok' : data!.trust.level === 'medium' ? 'warn' : 'danger'} className="mt-3" />
            <ul className="mt-4 space-y-2 text-sm">
              {data!.trust.signals.map((s) => (
                <li key={s.text} className="flex gap-2">
                  {s.ok ? <Check className="mt-0.5 size-4 shrink-0 text-ok" /> : <CircleAlert className="mt-0.5 size-4 shrink-0 text-warn" />}
                  <span>{s.text}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-muted">Кандидаты видят уровень доверия в каждом приглашении. Жалобы и нереалистичные вилки снижают оценку.</p>
          </Card>
          <Card className="p-6">
            <div className="font-semibold">Квота приглашений</div>
            <p className="mt-1 text-sm text-muted">Осталось на этой неделе: <b className="text-ink">{data!.quota_left}</b> из 20. Квота защищает кандидатов от массовых рассылок.</p>
          </Card>
        </div>
      </div>
    </div>
  )
}
