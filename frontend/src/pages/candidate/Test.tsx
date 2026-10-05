import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, CheckCircle2, ChevronDown, Clock, Lock, Sparkles, TrendingDown, TrendingUp, XCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, ApiError } from '../../api/client'
import type { CandidateProfile, Eligibility, GradeId, SessionState } from '../../api/types'
import { CodeBlock } from '../../components/CodeBlock'
import { Alert, Badge, Button, Card, GradeBadge, Input, PageHeader, PageLoader, ProgressBar, RichText, SectionTitle } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { date, skillLevel, thetaPercentile } from '../../lib/format'

const GRADE_DESCR: Record<GradeId, string> = {
  intern: 'Учебные и пет-проекты, опыт до года',
  junior: 'Типовые задачи под присмотром, 1–2 года',
  middle: 'Самостоятельно ведёт задачи и модули, 2–5 лет',
  senior: 'Проектирует системы и менторит, 5+ лет',
}

// ------------------------------------------------------------------------------------------- intro

export function TestHome() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { gradeTitle } = useCatalog()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: () => api.get<CandidateProfile>('/api/candidate/profile') })
  const { data: elig } = useQuery({ queryKey: ['eligibility'], queryFn: () => api.get<Eligibility>('/api/assessment/eligibility') })
  const { data: history } = useQuery({
    queryKey: ['assessment-history'],
    queryFn: () => api.get<{ sessions: SessionState[]; grade_history: { grade: string | null; previous_grade: string | null; reason: string; created_at: string }[] }>('/api/assessment/history'),
  })
  const [target, setTarget] = useState<GradeId | null>(null)
  const start = useMutation({
    mutationFn: (grade: GradeId) => api.post<SessionState>('/api/assessment/sessions', { target_grade: grade }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['eligibility'] })
      nav(`/c/test/${s.id}`)
    },
  })

  useEffect(() => {
    if (elig?.active_session_id) nav(`/c/test/${elig.active_session_id}`, { replace: true })
  }, [elig, nav])

  if (!profile || !elig) return <PageLoader />
  if (!profile.onboarding_done)
    return (
      <Card className="mx-auto max-w-xl p-8 text-center">
        <h2 className="text-xl font-semibold">Сначала короткий опрос</h2>
        <p className="mt-2 text-muted">Выберите специализацию, стек и предполагаемый грейд — по ним соберётся тест.</p>
        <Link to="/c/onboarding" className="mt-6 inline-flex h-10 items-center rounded-xl bg-brand-500 px-5 font-medium text-white">
          Пройти опрос
        </Link>
      </Card>
    )

  const chosen = target ?? elig.suggested_grade ?? (profile.grade ? null : profile.declared_grade) ?? null
  const startErr = start.error as ApiError | null
  return (
    <div>
      <PageHeader
        label="Тест и грейд"
        title={profile.grade ? <>Ваша категория: {profile.specialization_title} · {profile.grade_title}</> : 'Подтвердите грейд тестом'}
        subtitle={
          profile.grade
            ? `Подтверждено ${date(profile.grade_confirmed_at)}. Можно пройти тест на грейд выше или ниже — с ограничением по частоте.`
            : 'Адаптивный тест подбирает задания под ваши ответы. Результат определяет категорию, в которой вас видят работодатели.'
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card className="p-6">
          <SectionTitle label="Шаг 1" title="Выберите грейд для теста" />
          {elig.suggested_grade && (
            <Alert tone="brand" className="mb-4" title={`Рекомендуем: тест на ${gradeTitle(elig.suggested_grade)}`}>
              {profile.grade ? 'Прошлый результат был уверенно выше порога — попробуйте следующий грейд.' : 'Прошлый тест не подтвердил заявленный грейд — тест на уровень ниже доступен сразу.'}
            </Alert>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            {elig.grades.map((g) => (
              <button
                key={g.grade}
                disabled={!g.allowed}
                onClick={() => setTarget(g.grade)}
                className={clsx(
                  'rounded-xl border p-4 text-left transition',
                  !g.allowed && 'cursor-not-allowed bg-surface opacity-70',
                  g.allowed && chosen === g.grade ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-100' : g.allowed && 'border-line hover:border-brand-300',
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{g.title}</span>
                  {profile.grade === g.grade && <Badge tone="ok">текущий</Badge>}
                  {!g.allowed && <Lock className="size-4 text-muted" />}
                </div>
                <div className="mt-1 text-sm text-muted">{GRADE_DESCR[g.grade]}</div>
                {!g.allowed && (
                  <div className="mt-2 text-xs text-warn">
                    {g.reason}
                    {g.available_from && ` · с ${date(g.available_from)}`}
                  </div>
                )}
              </button>
            ))}
          </div>
          {startErr && <Alert tone="danger" className="mt-4">{startErr.message}</Alert>}
          <Button size="lg" className="mt-6 w-full sm:w-auto" disabled={!chosen} loading={start.isPending} onClick={() => chosen && start.mutate(chosen)} icon={<ArrowRight className="size-4" />}>
            Начать тест{chosen ? ` на ${gradeTitle(chosen)}` : ''}
          </Button>
        </Card>
        <Card className="h-fit p-6">
          <div className="mono-label text-brand-500">Правила</div>
          <ul className="mt-3 space-y-3 text-sm">
            <li className="flex gap-2"><Sparkles className="mt-0.5 size-4 shrink-0 text-brand-500" />10–18 заданий: тест заканчивается, как только грейд определён уверенно.</li>
            <li className="flex gap-2"><Clock className="mt-0.5 size-4 shrink-0 text-brand-500" />На каждое задание — свой лимит времени (1–4 минуты). Документацией пользоваться можно, но время ограничено.</li>
            <li className="flex gap-2"><TrendingDown className="mt-0.5 size-4 shrink-0 text-brand-500" />Грейд не понижается принудительно: если тест не подтвердит уровень, сразу доступен тест на грейд ниже.</li>
            <li className="flex gap-2"><TrendingUp className="mt-0.5 size-4 shrink-0 text-brand-500" />Уверенный результат открывает тест на грейд выше. Смена грейда — не чаще раза в 90 дней.</li>
            <li className="flex gap-2"><Lock className="mt-0.5 size-4 shrink-0 text-brand-500" />У каждого кандидата свои экземпляры заданий — искать ответы в интернете бесполезно.</li>
          </ul>
        </Card>
      </div>

      {!!history?.sessions.length && (
        <Card className="mt-6 p-6">
          <SectionTitle label="История" title="Попытки и изменения грейда" />
          <div className="divide-y divide-line">
            {history.sessions.map((s) => (
              <Link key={s.id} to={`/c/test/${s.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 hover:bg-surface">
                <div>
                  <div className="font-medium">
                    Тест на {s.target_grade_title} · {s.specialization_title}
                  </div>
                  <div className="text-sm text-muted">{date(s.created_at)}</div>
                </div>
                {s.status === 'active' ? (
                  <Badge tone="brand">в процессе</Badge>
                ) : (
                  <Badge tone={s.result?.outcome === 'not_confirmed' ? 'danger' : 'ok'}>
                    {s.result?.outcome === 'not_confirmed' ? 'не подтверждён' : s.result?.outcome === 'upgrade_available' ? 'подтверждён с запасом' : 'подтверждён'}
                  </Badge>
                )}
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- runner

function useCountdown(shownAt: string | undefined, limit: number | undefined) {
  const [left, setLeft] = useState(() =>
    shownAt && limit ? Math.max(0, Math.round(limit - (Date.now() - new Date(shownAt).getTime()) / 1000)) : (limit ?? 0),
  )
  useEffect(() => {
    if (!shownAt || !limit) return
    const tick = () => setLeft(Math.max(0, Math.round(limit - (Date.now() - new Date(shownAt).getTime()) / 1000)))
    tick()
    const id = setInterval(tick, 500)
    return () => clearInterval(id)
  }, [shownAt, limit])
  return left
}

function Runner({ session }: { session: SessionState }) {
  const qc = useQueryClient()
  const item = session.current_item!
  const [value, setValue] = useState<string>('')
  const signals = useRef({ paste: 0, blur: 0, copy: 0 })
  const left = useCountdown(item.shown_at, item.time_limit_s)
  const submitted = useRef(false)

  useEffect(() => {
    const onVis = () => document.hidden && (signals.current.blur += 1)
    const onCopy = () => (signals.current.copy += 1)
    document.addEventListener('visibilitychange', onVis)
    document.addEventListener('copy', onCopy)
    return () => {
      document.removeEventListener('visibilitychange', onVis)
      document.removeEventListener('copy', onCopy)
    }
  }, [])

  const answer = useMutation({
    mutationFn: (response: string | number | null) =>
      api.post<SessionState>(`/api/assessment/sessions/${session.id}/answer`, { item_id: item.id, response, signals: signals.current }),
    onSuccess: (s) => {
      qc.setQueryData(['session', String(session.id)], s)
      if (s.status === 'finished') {
        qc.invalidateQueries({ queryKey: ['profile'] })
        qc.invalidateQueries({ queryKey: ['eligibility'] })
        qc.invalidateQueries({ queryKey: ['dashboard'] })
      }
    },
  })

  const submit = useCallback(() => {
    if (submitted.current) return
    submitted.current = true
    const response = item.kind === 'single' ? (value === '' ? null : Number(value)) : value.trim() || null
    answer.mutate(response)
  }, [answer, item.kind, value])

  const skip = () => {
    if (submitted.current) return
    submitted.current = true
    answer.mutate(null)
  }

  useEffect(() => {
    if (left === 0 && !submitted.current) submit()
  }, [left, submit])

  const progress = session.answered / session.max_items
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GradeBadge grade={session.target_grade} title={`Тест на ${session.target_grade_title}`} spec={session.specialization_title} />
        </div>
        <div className={clsx('flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-sm', left <= 15 ? 'bg-accent-50 text-accent-500' : 'bg-white text-ink')}>
          <Clock className="size-4" />
          {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
        </div>
      </div>
      <div className="mb-6">
        <div className="mb-1.5 flex justify-between text-xs text-muted">
          <span>Задание {item.position}</span>
          <span>обычно {session.min_items}–{session.max_items} заданий</span>
        </div>
        <ProgressBar value={progress} />
      </div>
      <Card className="animate-fade-in p-6" key={item.id}>
        <div className="mb-4 flex flex-wrap gap-2">
          <Badge tone="brand">{item.skill_title}</Badge>
          <Badge>{item.family_title}</Badge>
          <Badge>{item.format}</Badge>
        </div>
        <RichText text={item.prompt} className="text-[15px]" />
        {item.code && (
          <div className="mt-4">
            <CodeBlock code={item.code} lang={item.lang} />
          </div>
        )}
        <form
          className="mt-6"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          {item.kind === 'single' ? (
            <div className="grid gap-2">
              {item.options.map((o, i) => (
                <label
                  key={i}
                  className={clsx(
                    'flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition',
                    value === String(i) ? 'border-brand-500 bg-brand-50' : 'border-line hover:border-brand-300',
                  )}
                >
                  <input type="radio" name="opt" className="accent-brand-500" checked={value === String(i)} onChange={() => setValue(String(i))} />
                  <span className="font-mono text-xs text-muted">{String.fromCharCode(65 + i)}</span>
                  <span>{o}</span>
                </label>
              ))}
            </div>
          ) : (
            <div>
              <Input
                autoFocus
                inputMode={item.kind === 'number' ? 'decimal' : 'text'}
                placeholder={item.kind === 'number' ? 'Число' : 'Ответ — как его выведет программа'}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onPaste={() => (signals.current.paste += 1)}
                className="h-12 font-mono text-base"
              />
              <p className="mt-1.5 text-xs text-muted">
                {item.kind === 'number' ? 'Только число.' : 'Пробелы и вид кавычек не важны.'}
              </p>
            </div>
          )}
          {answer.error && <Alert tone="danger" className="mt-4">{(answer.error as Error).message}</Alert>}
          <div className="mt-6 flex items-center justify-between gap-3">
            <button type="button" className="text-sm text-muted hover:text-ink" onClick={skip}>
              Не знаю, пропустить
            </button>
            <Button size="lg" loading={answer.isPending} disabled={value === ''}>
              Ответить <ArrowRight className="size-4" />
            </Button>
          </div>
        </form>
      </Card>
      <p className="mt-4 text-center text-xs text-muted">Правильность ответов не показывается до конца теста: так результат не зависит от подсказок.</p>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- result

function AbilityScale({ theta, ci }: { theta: number; ci: [number, number] }) {
  const { catalog } = useCatalog()
  const min = -3
  const max = 3
  const x = (v: number) => `${((Math.max(min, Math.min(max, v)) - min) / (max - min)) * 100}%`
  const grades = catalog?.grades ?? []
  return (
    <div className="pt-6 pb-2">
      <div className="relative h-10">
        <div className="absolute inset-x-0 top-4 flex h-2 overflow-hidden rounded-full">
          {grades.map((g, i) => {
            const lo = i === 0 ? min : g.theta_min
            const hi = i + 1 < grades.length ? grades[i + 1].theta_min : max
            return <div key={g.id} className={['bg-line', 'bg-brand-100', 'bg-brand-300', 'bg-brand-500'][i]} style={{ width: `${((hi - lo) / (max - min)) * 100}%` }} />
          })}
        </div>
        <div className="absolute top-2.5 h-5 rounded-full border-2 border-ink/60 bg-ink/10" style={{ left: x(ci[0]), width: `calc(${x(ci[1])} - ${x(ci[0])})` }} />
        <div className="absolute top-0 -ml-2 flex flex-col items-center" style={{ left: x(theta) }}>
          <div className="size-4 rounded-full border-2 border-white bg-accent-500 shadow" />
        </div>
      </div>
      <div className="relative mt-1 h-4 text-[11px] text-muted">
        {grades.map((g, i) => {
          const lo = i === 0 ? min : g.theta_min
          const hi = i + 1 < grades.length ? grades[i + 1].theta_min : max
          return (
            <span key={g.id} className="absolute -translate-x-1/2" style={{ left: x((lo + hi) / 2) }}>
              {g.title}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function Result({ session }: { session: SessionState }) {
  const r = session.result!
  const nav = useNavigate()
  const qc = useQueryClient()
  const { gradeTitle } = useCatalog()
  const [open, setOpen] = useState(false)
  const start = useMutation({
    mutationFn: (grade: GradeId) => api.post<SessionState>('/api/assessment/sessions', { target_grade: grade }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['eligibility'] })
      nav(`/c/test/${s.id}`)
    },
  })
  const confirmed = r.outcome !== 'not_confirmed'
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Card className={clsx('p-8', confirmed ? 'border-ok/30' : 'border-warn/30')}>
        <div className="flex flex-wrap items-start gap-5">
          {confirmed ? <CheckCircle2 className="size-12 shrink-0 text-ok" /> : <XCircle className="size-12 shrink-0 text-warn" />}
          <div className="min-w-0 flex-1">
            <div className="mono-label text-muted">Результат теста · {date(r.finished_at)}</div>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">
              {confirmed ? `Грейд ${session.target_grade_title} подтверждён` : `Грейд ${session.target_grade_title} пока не подтверждён`}
            </h1>
            <p className="mt-2 text-muted">
              {r.outcome === 'confirmed' && `Ваша категория — ${session.specialization_title} · ${session.target_grade_title}. Работодатели видят её в подборках.`}
              {r.outcome === 'upgrade_available' &&
                `Результат уверенно выше порога. Категория ${session.specialization_title} · ${session.target_grade_title} присвоена, и в течение 7 дней доступен тест на ${gradeTitle(r.suggested_grade)}.`}
              {r.outcome === 'not_confirmed' &&
                (r.suggested_grade
                  ? `Это не понижение: можно сразу пройти тест на ${gradeTitle(r.suggested_grade)}, а повторить попытку на ${session.target_grade_title} — через 30 дней.`
                  : 'Повторить попытку можно через 30 дней.')}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {r.suggested_grade && (
                <Button onClick={() => start.mutate(r.suggested_grade!)} loading={start.isPending} icon={r.outcome === 'not_confirmed' ? <TrendingDown className="size-4" /> : <TrendingUp className="size-4" />}>
                  Тест на {gradeTitle(r.suggested_grade)}
                </Button>
              )}
              <Link to="/c" className="inline-flex h-10 items-center rounded-xl border border-line bg-white px-4 text-sm font-medium hover:border-brand-300">
                В кабинет
              </Link>
            </div>
            {start.error && <Alert tone="danger" className="mt-3">{(start.error as Error).message}</Alert>}
          </div>
        </div>
      </Card>

      <div className="grid gap-6 md:grid-cols-[1.2fr_1fr]">
        <Card className="p-6">
          <SectionTitle label="Оценка способностей" title={`Выше, чем у ${thetaPercentile(r.theta)}% кандидатов`} />
          <AbilityScale theta={r.theta} ci={r.ci90} />
          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-sm">
            <div className="rounded-xl bg-surface p-3">
              <div className="font-mono text-lg font-semibold">{r.theta.toFixed(2)}</div>
              <div className="text-xs text-muted">θ (шкала N(0,1))</div>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <div className="font-mono text-lg font-semibold">±{(1.645 * r.se).toFixed(2)}</div>
              <div className="text-xs text-muted">90% интервал</div>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <div className="font-mono text-lg font-semibold">{Math.round(r.p_target * 100)}%</div>
              <div className="text-xs text-muted">P(≥ {session.target_grade_title})</div>
            </div>
          </div>
          <p className="mt-4 text-xs text-muted">
            Решено {r.correct} из {session.answered} заданий. Число верных ответов само по себе не определяет грейд: учитываются сложность и дискриминативность каждого задания (модель IRT).
          </p>
        </Card>
        <Card className="p-6">
          <SectionTitle label="Навыки" title="Профиль по навыкам" />
          <div className="space-y-3">
            {r.skill_theta.map((s) => {
              const lvl = skillLevel(s.theta)
              return (
                <div key={s.skill}>
                  <div className="flex justify-between text-sm">
                    <span>{s.title}</span>
                    <span className="text-muted">{lvl.label}</span>
                  </div>
                  <ProgressBar value={lvl.value} className="mt-1" />
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      {session.review && (
        <Card className="p-6">
          <button className="flex w-full items-center justify-between" onClick={() => setOpen(!open)}>
            <span className="font-semibold">Разбор заданий ({session.review.length})</span>
            <ChevronDown className={clsx('size-5 transition', open && 'rotate-180')} />
          </button>
          {open && (
            <div className="mt-4 space-y-4">
              {session.review.map((it) => (
                <div key={it.id} className="rounded-xl border border-line p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    {it.is_correct ? <CheckCircle2 className="size-4 text-ok" /> : <XCircle className="size-4 text-accent-500" />}
                    <span className="text-sm font-medium">{it.position}. {it.family_title}</span>
                    <Badge>{it.skill_title}</Badge>
                  </div>
                  <RichText text={it.prompt} className="text-sm" />
                  {it.code && <div className="mt-2"><CodeBlock code={it.code} lang={it.lang} /></div>}
                  <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                    <div className="rounded-lg bg-surface px-3 py-2">
                      Ваш ответ: <b className="font-mono">{it.kind === 'single' && it.response != null ? it.options[Number(it.response)] : String(it.response ?? '—')}</b>
                    </div>
                    <div className="rounded-lg bg-ok-50 px-3 py-2 text-ok">
                      Верно: <b className="font-mono">{it.kind === 'single' ? it.options[Number(it.answer)] : String(it.answer)}</b>
                    </div>
                  </div>
                  {it.explanation && <p className="mt-2 text-xs text-muted">{it.explanation}</p>}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

export function TestSession() {
  const { id } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['session', id],
    queryFn: () => api.get<SessionState>(`/api/assessment/sessions/${id}`),
  })
  if (isLoading || !data) return <PageLoader />
  // keyed by item: every task gets a fresh runner (timer, answer, integrity signals)
  if (data.status === 'active' && data.current_item) return <Runner key={data.current_item.id} session={data} />
  if (data.status === 'finished') return <Result session={data} />
  return <Alert tone="muted">Сессия недоступна</Alert>
}
