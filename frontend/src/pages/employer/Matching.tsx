import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, Check, CircleDashed, Pencil, Plus, Search, Sparkles, Users, Wand2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../../api/client'
import { emptyFilters, type CandidateCard, type Filters, type GradeId, type Need, type Shortlist, type WorkFormat } from '../../api/types'
import { Alert, Badge, Button, Card, ChipToggle, Empty, Field, Input, MultiChips, PageHeader, PageLoader, SectionTitle, Select, Spinner, Textarea, Toggle } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { ago, salaryRange } from '../../lib/format'
import { CandidateList, CandidateRow, FiltersPanel, InviteModal } from './shared'

interface CategoryCell {
  specialization: string
  specialization_title: string
  grade: GradeId
  grade_title: string
  count: number
  with_fsp: number
}

interface Analytics {
  funnel: Record<string, number>
  acceptance_rate: number | null
}

export function CategoryMap({ onPick }: { onPick: (spec: string, grade: string) => void }) {
  const { catalog } = useCatalog()
  const { data } = useQuery({ queryKey: ['categories'], queryFn: () => api.get<CategoryCell[]>('/api/employer/categories') })
  if (!data || !catalog)
    return (
      <div className="flex h-24 items-center justify-center">
        <Spinner />
      </div>
    )
  const max = Math.max(...data.map((d) => d.count), 1)
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-separate border-spacing-1.5 text-sm">
        <thead>
          <tr>
            <th />
            {catalog.grades.map((g) => (
              <th key={g.id} className="px-2 pb-1 text-left text-xs font-medium text-muted">{g.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {catalog.specializations.map((s) => (
            <tr key={s.id}>
              <td className="pr-3 text-xs font-medium whitespace-nowrap">{s.short}</td>
              {catalog.grades.map((g) => {
                const cell = data.find((d) => d.specialization === s.id && d.grade === g.id)
                const v = (cell?.count ?? 0) / max
                return (
                  <td key={g.id}>
                    <button
                      onClick={() => onPick(s.id, g.id)}
                      className="w-full rounded-lg px-3 py-2.5 text-left transition hover:ring-2 hover:ring-brand-300"
                      style={{ background: `rgb(64 47 255 / ${0.06 + v * 0.55})`, color: v > 0.55 ? 'white' : undefined }}
                    >
                      <div className="font-semibold">{cell?.count ?? 0}</div>
                      <div className="text-xs opacity-80">ФСП: {cell?.with_fsp ?? 0}</div>
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const STEPS_KEY = 'fsp-talent:employer-steps-hidden'

function readHidden(): boolean {
  try {
    return localStorage.getItem(STEPS_KEY) === '1'
  } catch {
    return false
  }
}

/** First visit: what to do, in the order of the reverse mechanic. Hidden by the user or once everything is done. */
function FirstSteps({ needs, sent }: { needs: Need[]; sent: number }) {
  const { data: company } = useQuery({ queryKey: ['company'], queryFn: () => api.get<{ description: string; industry: string }>('/api/employer/company') })
  const [hidden, setHidden] = useState(readHidden)
  if (hidden || !company) return null
  const steps = [
    { done: !!(company.description && company.industry), title: 'Заполните профиль компании', hint: 'Описание и сфера видны кандидату в приглашении', to: '/e/company' },
    { done: needs.length > 0, title: 'Опишите, кого ищете', hint: 'Обычным текстом — система разберёт стек, грейд и вилку', to: '/e/needs/new' },
    { done: needs.length > 0, title: 'Посмотрите подборку', hint: 'Категории и кандидаты с объяснением, почему они подходят', to: needs[0] ? `/e/needs/${needs[0].id}` : '/e/needs/new' },
    { done: sent > 0, title: 'Пригласите кандидата', hint: 'С описанием предложения и вилкой: контакты откроются после согласия', to: needs[0] ? `/e/needs/${needs[0].id}` : '/e/search' },
  ]
  if (steps.every((s) => s.done)) return null
  const hide = () => {
    try {
      localStorage.setItem(STEPS_KEY, '1')
    } catch {
      /* storage may be unavailable: hide for this visit only */
    }
    setHidden(true)
  }
  return (
    <Card className="mb-6 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="mono-label text-brand-600">Первые шаги</div>
          <div className="font-semibold">Как найти кандидата за 5 минут</div>
        </div>
        <button className="rounded-lg p-1 text-muted hover:bg-surface hover:text-ink" onClick={hide} aria-label="Скрыть подсказку">
          <X className="size-4" />
        </button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((s, i) => (
          <Link key={s.title} to={s.to} className={clsx('rounded-xl border p-3 transition hover:border-brand-300', s.done ? 'border-ok/20 bg-ok-50' : 'border-line bg-white')}>
            <div className="flex items-center gap-2 text-sm font-medium">
              {s.done ? <Check className="size-4 text-ok" /> : <CircleDashed className="size-4 text-brand-400" />}
              {i + 1}. {s.title}
            </div>
            <div className="mt-1 text-xs text-muted">{s.hint}</div>
          </Link>
        ))}
      </div>
    </Card>
  )
}

export function EmployerHome() {
  const nav = useNavigate()
  const { data: needs } = useQuery({ queryKey: ['needs'], queryFn: () => api.get<Need[]>('/api/employer/needs') })
  const { data: analytics } = useQuery({ queryKey: ['analytics'], queryFn: () => api.get<Analytics>('/api/employer/analytics') })
  const { skillTitle } = useCatalog()
  if (!needs) return <PageLoader />
  return (
    <div>
      <PageHeader
        label="Обратная механика"
        title="Подбор кандидатов"
        subtitle="Опишите, кого ищете, — система предложит категории и кандидатов с подтверждённым грейдом и объяснением, почему они подходят."
        action={
          <Link to="/e/needs/new" className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-500 px-5 font-medium text-white hover:bg-brand-600">
            <Plus className="size-4" /> Новая потребность
          </Link>
        }
      />
      <FirstSteps needs={needs} sent={analytics?.funnel.sent ?? 0} />
      {analytics && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ['Отправлено приглашений', analytics.funnel.sent],
            ['Просмотрено', analytics.funnel.viewed],
            ['Принято', analytics.funnel.accepted],
            ['Доля согласий', analytics.acceptance_rate != null ? `${Math.round(analytics.acceptance_rate * 100)}%` : '—'],
          ].map(([l, v]) => (
            <Card key={l as string} className="p-4">
              <div className="text-xs text-muted">{l}</div>
              <div className="mt-1 text-2xl font-semibold">{v}</div>
            </Card>
          ))}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr] [&>*]:min-w-0">
        <div>
          <SectionTitle label="Сохранённые подборки" title="Ваши потребности" />
          {needs.length === 0 ? (
            <Empty icon={<Sparkles className="size-8" />} title="Опишите первую потребность" action={<Link to="/e/needs/new" className="font-medium text-brand-600">Создать →</Link>}>
              Например: «Ищем Middle Python-разработчика в платёжную команду, FastAPI и PostgreSQL, удалённо, 220–300 тыс.»
            </Empty>
          ) : (
            <div className="space-y-3">
              {needs.map((n) => (
                <Link key={n.id} to={`/e/needs/${n.id}`} className="block">
                  <Card className="p-5 transition hover:border-brand-300">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold">{n.title}</div>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          <Badge tone="brand">{n.specialization_title} · {n.grade_title}</Badge>
                          {n.must_skills.slice(0, 4).map((s) => (
                            <Badge key={s}>{skillTitle(s)}</Badge>
                          ))}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold text-brand-600">{salaryRange(n.salary_from, n.salary_to)}</div>
                        <div className="text-xs text-muted">обновлено {ago(n.updated_at)}</div>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center gap-1 text-sm font-medium text-brand-600">
                      Открыть подборку <ArrowRight className="size-4" />
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
        <Card className="h-fit p-6">
          <SectionTitle label="Банк кандидатов" title="Карта категорий" />
          <p className="mb-3 text-sm text-muted">Число кандидатов с подтверждённым грейдом. Нажмите на категорию, чтобы открыть её.</p>
          <CategoryMap onPick={(s, g) => nav(`/e/search?spec=${s}&grade=${g}`)} />
        </Card>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- need editor

interface Parsed {
  specialization: string | null
  grade: GradeId | null
  must_skills: string[]
  nice_skills: string[]
  work_formats: WorkFormat[]
  city: string
  salary_from: number | null
  salary_to: number | null
  source: 'rules' | 'rules+llm'
}

type NeedForm = Omit<Need, 'id' | 'specialization_title' | 'grade_title' | 'pinned' | 'hidden' | 'created_at' | 'updated_at'>

const EMPTY: NeedForm = {
  title: '',
  raw_text: '',
  team_description: '',
  specialization: 'backend',
  grade: 'middle',
  must_skills: [],
  nice_skills: [],
  work_formats: [],
  city: '',
  salary_from: 0,
  salary_to: 0,
  require_fsp: false,
}

function SkillPicker({ value, onChange, exclude }: { value: string[]; onChange: (v: string[]) => void; exclude: string[] }) {
  const { catalog, skillTitle } = useCatalog()
  const [add, setAdd] = useState('')
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {value.map((s) => (
          <span key={s} className="inline-flex items-center gap-1 rounded-full bg-brand-50 py-1 pr-1 pl-3 text-sm text-brand-700">
            {skillTitle(s)}
            <button type="button" className="rounded-full p-0.5 hover:bg-brand-100" onClick={() => onChange(value.filter((x) => x !== s))}>
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        <select
          className="h-8 rounded-full border border-dashed border-line bg-white px-3 text-sm"
          value={add}
          onChange={(e) => {
            if (e.target.value) onChange([...value, e.target.value])
            setAdd('')
          }}
        >
          <option value="">+ навык</option>
          {catalog?.skills
            .filter((s) => !value.includes(s.id) && !exclude.includes(s.id))
            .map((s) => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
        </select>
      </div>
    </div>
  )
}

export function NeedEditor() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { catalog } = useCatalog()
  const [form, setForm] = useState<NeedForm>(EMPTY)
  const [parsedOnce, setParsedOnce] = useState(!!id)
  const { data: existing } = useQuery({ queryKey: ['need', id], queryFn: () => api.get<Need>(`/api/employer/needs/${id}`), enabled: !!id })
  useEffect(() => {
    if (existing) setForm({ ...EMPTY, ...existing })
  }, [existing])
  const parse = useMutation({
    mutationFn: () => api.post<Parsed>('/api/employer/needs/parse', { text: form.raw_text }),
    onSuccess: (p) => {
      setParsedOnce(true)
      const firstLine = form.raw_text.split(/[.\n]/)[0].slice(0, 80)
      setForm({
        ...form,
        title: form.title || firstLine,
        specialization: p.specialization ?? form.specialization,
        grade: p.grade ?? form.grade,
        must_skills: p.must_skills,
        nice_skills: p.nice_skills,
        work_formats: p.work_formats.length ? p.work_formats : form.work_formats,
        city: p.city || form.city,
        salary_from: p.salary_from ?? form.salary_from,
        salary_to: p.salary_to ?? form.salary_to,
      })
    },
  })
  const save = useMutation({
    mutationFn: () => (id ? api.put<Need>(`/api/employer/needs/${id}`, form) : api.post<Need>('/api/employer/needs', form)),
    onSuccess: (n) => {
      qc.invalidateQueries({ queryKey: ['needs'] })
      qc.invalidateQueries({ queryKey: ['need', String(n.id)] })
      qc.invalidateQueries({ queryKey: ['shortlist'] })
      nav(`/e/needs/${n.id}`)
    },
  })
  if (!catalog) return <PageLoader />
  const set = <K extends keyof NeedForm>(k: K, v: NeedForm[K]) => setForm({ ...form, [k]: v })
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader label={id ? 'Редактирование' : 'Новая потребность'} title="Кого вы ищете?" subtitle="Напишите своими словами — система извлечёт специализацию, грейд, стек, формат и вилку. Всё можно поправить вручную." />
      <Card className="p-6">
        <Field label="Описание потребности">
          <Textarea
            rows={5}
            placeholder="Например: Ищем Middle Python-разработчика в команду платёжного шлюза. FastAPI или Django, PostgreSQL, асинхронность. Будет плюсом Kafka. Удалённо или гибрид, 220–300 тыс. ₽."
            value={form.raw_text}
            onChange={(e) => set('raw_text', e.target.value)}
          />
        </Field>
        <Button className="mt-3" variant={parsedOnce ? 'secondary' : 'primary'} icon={<Wand2 className="size-4" />} loading={parse.isPending} disabled={form.raw_text.trim().length < 10} onClick={() => parse.mutate()}>
          Разобрать текст
        </Button>
        {parse.isSuccess && (
          <Alert tone="ok" className="mt-3">
            Готово: проверьте поля ниже.{' '}
            <span className="text-muted">
              {parse.data.source === 'rules+llm' ? 'Разобрано правилами и уточнено языковой моделью с проверкой по справочнику.' : 'Разобрано правилами и словарём навыков.'}
            </span>
          </Alert>
        )}
      </Card>

      {parsedOnce && (
        <Card className="animate-fade-in mt-6 p-6">
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              save.mutate()
            }}
          >
            <Field label="Название подборки">
              <Input required value={form.title} onChange={(e) => set('title', e.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Специализация">
                <Select value={form.specialization} onChange={(e) => set('specialization', e.target.value)}>
                  {catalog.specializations.map((s) => (
                    <option key={s.id} value={s.id}>{s.title}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Грейд">
                <div className="flex flex-wrap gap-2">
                  {catalog.grades.map((g) => (
                    <ChipToggle key={g.id} size="sm" active={form.grade === g.id} onClick={() => set('grade', g.id)}>
                      {g.title}
                    </ChipToggle>
                  ))}
                </div>
              </Field>
            </div>
            <Field label="Обязательный стек">
              <SkillPicker value={form.must_skills} onChange={(v) => set('must_skills', v)} exclude={form.nice_skills} />
            </Field>
            <Field label="Будет плюсом">
              <SkillPicker value={form.nice_skills} onChange={(v) => set('nice_skills', v)} exclude={form.must_skills} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Зарплата от, ₽/мес до НДФЛ">
                <Input type="number" required min={0} step={1000} value={form.salary_from || ''} onChange={(e) => set('salary_from', Number(e.target.value))} />
              </Field>
              <Field label="Зарплата до, ₽/мес до НДФЛ">
                <Input type="number" required min={0} step={1000} value={form.salary_to || ''} onChange={(e) => set('salary_to', Number(e.target.value))} />
              </Field>
              <Field label="Формат">
                <MultiChips
                  size="sm"
                  options={(Object.entries(catalog.work_formats) as [WorkFormat, string][]).map(([id, title]) => ({ id, title }))}
                  value={form.work_formats}
                  onChange={(v) => set('work_formats', v)}
                />
              </Field>
              <Field label="Город (для офиса и гибрида)">
                <Input value={form.city} onChange={(e) => set('city', e.target.value)} />
              </Field>
            </div>
            <Field label="Чем занимается команда" hint="Попадёт в шаблон приглашения">
              <Textarea rows={2} value={form.team_description} onChange={(e) => set('team_description', e.target.value)} />
            </Field>
            <Toggle checked={form.require_fsp} onChange={(v) => set('require_fsp', v)} label="Только кандидаты с достижениями ФСП" />
            {save.error && <Alert tone="danger">{(save.error as Error).message}</Alert>}
            <Button size="lg" className="w-full" loading={save.isPending} icon={<Users className="size-4" />}>
              {id ? 'Сохранить и пересчитать подборку' : 'Найти кандидатов'}
            </Button>
          </form>
        </Card>
      )}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- shortlist

export function ShortlistPage() {
  const { id } = useParams()
  const qc = useQueryClient()
  const { skillTitle } = useCatalog()
  const storageKey = `need-filters-${id}`
  const [filters, setFilters] = useState<Filters>(() => {
    try {
      return { ...emptyFilters, ...JSON.parse(sessionStorage.getItem(storageKey) || '{}') }
    } catch {
      return emptyFilters
    }
  })
  const [invite, setInvite] = useState<CandidateCard | null>(null)
  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(filters))
    } catch {
      /* ignore */
    }
  }, [filters, storageKey])
  const { data: need } = useQuery({ queryKey: ['need', id], queryFn: () => api.get<Need>(`/api/employer/needs/${id}`) })
  const { data, isFetching } = useQuery({
    queryKey: ['shortlist', id, filters],
    queryFn: () => api.post<Shortlist>(`/api/employer/needs/${id}/shortlist`, filters),
    placeholderData: keepPreviousData,
  })
  const pin = useMutation({
    mutationFn: (c: CandidateCard) => api.post(`/api/employer/needs/${id}/pin`, { candidate_id: c.id, value: !c.pinned }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['shortlist', id] }),
  })
  const hide = useMutation({
    mutationFn: (c: CandidateCard) => api.post(`/api/employer/needs/${id}/hide`, { candidate_id: c.id, value: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['shortlist', id] }),
  })
  if (!need || !data) return <PageLoader />
  const skills = Array.from(new Set([...need.must_skills, ...need.nice_skills]))
  return (
    <div>
      <PageHeader
        label={`Подборка · ${need.specialization_title} · ${need.grade_title}`}
        title={need.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-brand-600">{salaryRange(need.salary_from, need.salary_to)}</span>
            {need.must_skills.map((s) => (
              <Badge key={s}>{skillTitle(s)}</Badge>
            ))}
            {need.nice_skills.map((s) => (
              <Badge key={s} className="opacity-70">+ {skillTitle(s)}</Badge>
            ))}
          </span>
        }
        action={
          <Link to={`/e/needs/${id}/edit`} className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-white px-4 text-sm font-medium hover:border-brand-300">
            <Pencil className="size-4" /> Изменить потребность
          </Link>
        }
      />

      <div className="mb-5">
        <div className="mb-2 text-sm text-muted">Рекомендованные категории</div>
        <div className="flex flex-wrap gap-2">
          {data.categories.map((c) => {
            const active = filters.grades.length === 1 && filters.grades[0] === c.grade
            return (
              <button
                key={c.grade}
                onClick={() => setFilters({ ...filters, grades: active ? [] : [c.grade] })}
                className={clsx(
                  'rounded-xl border px-4 py-2.5 text-left transition',
                  active ? 'border-brand-500 bg-brand-500 text-white' : c.is_target ? 'border-brand-300 bg-brand-50' : 'border-line bg-white hover:border-brand-300',
                )}
              >
                <div className="text-sm font-semibold">
                  {need.specialization_title} · {c.grade_title} {c.is_target && <span className="font-normal opacity-80">(целевая)</span>}
                </div>
                <div className={clsx('text-xs', active ? 'text-white/80' : 'text-muted')}>
                  {c.count} канд. · среднее соответствие {Math.round(c.avg_score * 100)}
                  {!!c.unconfirmed && ` · ещё ${c.unconfirmed} не подтв.`}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <div className="lg:sticky lg:top-24 lg:h-fit">
          <FiltersPanel value={filters} onChange={setFilters} skills={skills.length ? skills : ['python', 'sql']} grades={data.categories.map((c) => c.grade)} />
          <p className="mt-3 px-1 text-xs text-muted">Фильтры сохраняются для этой подборки; закреплённые кандидаты остаются в выдаче при любых фильтрах.</p>
        </div>
        <div>
          <div className="mb-3 flex items-center justify-between text-sm text-muted">
            <span>
              {data.after_filters} из {data.total_in_categories} кандидатов в рекомендованных категориях
            </span>
            {isFetching && <span className="text-xs">обновляем…</span>}
          </div>
          {data.candidates.length === 0 ? (
            <Empty icon={<Search className="size-8" />} title="Никого не нашлось">
              Ослабьте фильтры или измените потребность — например, добавьте соседний грейд или уберите редкий навык.
            </Empty>
          ) : (
            <CandidateList
              items={data.candidates}
              render={(c) => <CandidateRow c={c} needId={Number(id)} onInvite={setInvite} onPin={(x) => pin.mutate(x)} onHide={(x) => hide.mutate(x)} />}
            />
          )}
        </div>
      </div>
      <InviteModal candidate={invite} onClose={() => setInvite(null)} need={need} />
    </div>
  )
}
