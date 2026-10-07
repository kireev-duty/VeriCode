import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { BadgeCheck, EyeOff, Minus, Pin, Plus, Send, Trophy, X } from 'lucide-react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { CandidateCard, Filters, WorkFormat } from '../../api/types'
import { Alert, Badge, Button, Card, Checkbox, CodeAvatar, Field, GradeBadge, Input, Modal, MultiChips, ScoreRing, Select, Textarea, Toggle } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { INVITATION_STATUS, rub, years } from '../../lib/format'

// ------------------------------------------------------------------------------------------- candidate list

/** Confirmed grades first, then the candidates whose grade is not confirmed yet, below a divider: they are not hidden
 * (they would drop out of circulation), but the employer sees that the test did not confirm the claim. */
export function CandidateList({ items, render }: { items: CandidateCard[]; render: (c: CandidateCard) => ReactNode }) {
  const confirmed = items.filter((c) => c.grade_confirmed !== false)
  const tail = items.filter((c) => c.grade_confirmed === false)
  return (
    <div className="space-y-3">
      {confirmed.map((c) => <Fragment key={c.id}>{render(c)}</Fragment>)}
      {tail.length > 0 && (
        <div className="pt-4">
          <div className="mono-label text-muted">Грейд не подтверждён тестом · {tail.length}</div>
          <p className="mt-1 text-sm text-muted">
            Кандидаты проходили тест на этот грейд, но не подтвердили его и ещё не пересдали. Показаны ниже основной выдачи.
          </p>
        </div>
      )}
      {tail.map((c) => <Fragment key={c.id}>{render(c)}</Fragment>)}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- candidate card

export function CandidateRow({
  c,
  needId,
  onInvite,
  onPin,
  onHide,
}: {
  c: CandidateCard
  needId?: number
  onInvite?: (c: CandidateCard) => void
  onPin?: (c: CandidateCard) => void
  onHide?: (c: CandidateCard) => void
}) {
  const verified = c.skills.filter((s) => s.verified)
  const declared = c.skills.filter((s) => !s.verified)
  const inv = c.invitation_status ? INVITATION_STATUS[c.invitation_status] : null
  return (
    <Card className={clsx('p-5 transition hover:border-brand-200', c.pinned && 'border-brand-300 ring-1 ring-brand-100')}>
      <div className="flex flex-wrap items-start gap-4">
        <CodeAvatar code={c.code} color={c.grade === 'senior' ? 'var(--color-brand-500)' : undefined} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/e/candidates/${c.id}${needId ? `?need=${needId}` : ''}`} className="font-semibold hover:text-brand-600">
              {c.headline || 'Кандидат'} <span className="font-mono text-xs font-normal text-muted">{c.code}</span>
            </Link>
            <GradeBadge grade={c.grade} title={c.grade_title} spec={c.specialization_title} claimed={c.claimed_grade_title} />
            {c.has_fsp && (
              <Badge tone="brand">
                <Trophy className="size-3" /> ФСП{c.fsp_rank ? ` · ${c.fsp_rank}` : ''}
              </Badge>
            )}
            {c.pinned && <Badge tone="ink"><Pin className="size-3" /> закреплён</Badge>}
            {inv && <Badge tone={inv.tone}>Приглашение: {inv.label.toLowerCase()}</Badge>}
          </div>
          <div className="mt-1 text-sm text-muted">
            {[years(c.experience_years) + ' опыта', c.city, c.work_formats.map((f) => ({ remote: 'удалённо', hybrid: 'гибрид', office: 'офис' })[f]).join(', '), c.relocation && 'готов к релокации']
              .filter(Boolean)
              .join(' · ')}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {verified.map((s) => (
              <Badge key={s.id} tone="ok">
                <BadgeCheck className="size-3" /> {s.title}
              </Badge>
            ))}
            {declared.slice(0, 6).map((s) => (
              <Badge key={s.id}>{s.title}</Badge>
            ))}
          </div>
          {c.match && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {c.match.chips.map((ch) => (
                <span
                  key={ch.text}
                  className={clsx(
                    'inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs',
                    ch.kind === 'positive' && 'bg-ok-50 text-ok',
                    ch.kind === 'negative' && 'bg-accent-50 text-accent-600',
                    ch.kind === 'neutral' && 'bg-surface text-muted',
                  )}
                >
                  {ch.kind === 'positive' ? <Plus className="size-3" /> : ch.kind === 'negative' ? <Minus className="size-3" /> : null}
                  {ch.text}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-3">
          {c.match ? (
            <ScoreRing value={c.match.score} label="Соответствие потребности" />
          ) : c.strength != null ? (
            <div className="text-right">
              <div className="text-xs text-muted">Сила профиля</div>
              <div className="font-mono text-lg font-semibold">{Math.round(c.strength * 100)}</div>
            </div>
          ) : null}
        </div>
      </div>
      {(onInvite || onPin || onHide) && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {onInvite && (
            <Button size="sm" onClick={() => onInvite(c)} disabled={!c.open_to_offers || c.invitation_status === 'sent' || c.invitation_status === 'viewed'} icon={<Send className="size-3.5" />}>
              {c.open_to_offers ? 'Пригласить' : 'Не принимает предложения'}
            </Button>
          )}
          <Link to={`/e/candidates/${c.id}${needId ? `?need=${needId}` : ''}`} className="inline-flex h-8 items-center rounded-xl border border-line px-3 text-sm font-medium hover:border-brand-300">
            Профиль
          </Link>
          {onPin && (
            <Button size="sm" variant="ghost" onClick={() => onPin(c)} icon={<Pin className="size-3.5" />}>
              {c.pinned ? 'Открепить' : 'Закрепить'}
            </Button>
          )}
          {onHide && (
            <Button size="sm" variant="ghost" onClick={() => onHide(c)} icon={<EyeOff className="size-3.5" />}>
              Скрыть
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------------------------------- filters

export function FiltersPanel({
  value,
  onChange,
  skills,
  grades,
  showSpecs,
}: {
  value: Filters
  onChange: (f: Filters) => void
  skills: string[]
  grades?: string[]
  showSpecs?: boolean
}) {
  const { catalog, skillTitle } = useCatalog()
  if (!catalog) return null
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => onChange({ ...value, [k]: v })
  const active =
    value.grades.length + value.skills.length + value.verified_skills.length + value.work_formats.length + value.specializations.length +
    (value.fsp_only ? 1 : 0) + (value.city ? 1 : 0) + (value.max_salary ? 1 : 0) + (value.min_experience ? 1 : 0)
  return (
    <Card className="space-y-5 p-5">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Уточнить</div>
        {active > 0 && (
          <button
            className="flex items-center gap-1 text-xs text-muted hover:text-ink"
            onClick={() =>
              onChange({ grades: [], skills: [], verified_skills: [], fsp_only: false, work_formats: [], city: '', max_salary: null, min_experience: null, specializations: [] })
            }
          >
            <X className="size-3" /> Сбросить ({active})
          </button>
        )}
      </div>
      {showSpecs && (
        <Field label="Специализация">
          <MultiChips size="sm" options={catalog.specializations.map((s) => ({ id: s.id, title: s.short }))} value={value.specializations} onChange={(v) => set('specializations', v)} />
        </Field>
      )}
      <Field label="Грейд">
        <MultiChips
          size="sm"
          options={catalog.grades.filter((g) => !grades || grades.includes(g.id)).map((g) => ({ id: g.id, title: g.title }))}
          value={value.grades}
          onChange={(v) => set('grades', v)}
        />
      </Field>
      <Field label="Стек (в профиле или тесте)">
        <MultiChips size="sm" options={skills.map((s) => ({ id: s, title: skillTitle(s) }))} value={value.skills} onChange={(v) => set('skills', v)} />
      </Field>
      <Field label="Подтверждено тестом">
        <MultiChips size="sm" options={skills.map((s) => ({ id: s, title: skillTitle(s) }))} value={value.verified_skills} onChange={(v) => set('verified_skills', v)} />
      </Field>
      <Toggle checked={value.fsp_only} onChange={(v) => set('fsp_only', v)} label="Только с достижениями ФСП" />
      <Field label="Формат">
        <MultiChips
          size="sm"
          options={(Object.entries(catalog.work_formats) as [WorkFormat, string][]).map(([id, title]) => ({ id, title }))}
          value={value.work_formats as WorkFormat[]}
          onChange={(v) => set('work_formats', v)}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Город">
          <Input value={value.city} onChange={(e) => set('city', e.target.value)} placeholder="любой" />
        </Field>
        <Field label="Опыт от, лет">
          <Input type="number" min={0} value={value.min_experience ?? ''} onChange={(e) => set('min_experience', e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </div>
      <Field label="Ожидания не выше, ₽/мес до НДФЛ">
        <Input type="number" step={10000} value={value.max_salary ?? ''} onChange={(e) => set('max_salary', e.target.value ? Number(e.target.value) : null)} />
      </Field>
    </Card>
  )
}

// ------------------------------------------------------------------------------------------- invite

interface Company {
  name: string
  contact_telegram: string
  contact_email: string
  quota_left: number
}

interface Preview {
  salary_status: 'fits' | 'close' | 'above' | 'unknown' | 'below_threshold'
  hint: string
  quota_left: number
  open_to_offers: boolean
  grade_warning?: string | null
}

const SALARY_TONE: Record<Preview['salary_status'], 'ok' | 'warn' | 'danger' | 'muted'> = {
  fits: 'ok',
  close: 'warn',
  above: 'danger',
  unknown: 'muted',
  below_threshold: 'danger',
}

export function InviteModal({
  candidate,
  onClose,
  need,
}: {
  candidate: CandidateCard | null
  onClose: () => void
  need?: { id: number; title: string; salary_from: number; salary_to: number; work_formats: string[]; team_description?: string }
}) {
  const qc = useQueryClient()
  const { data: company } = useQuery({ queryKey: ['company'], queryFn: () => api.get<Company>('/api/employer/company') })
  const { data: tasks } = useQuery({ queryKey: ['emp-tasks'], queryFn: () => api.get<{ id: number; title: string }[]>('/api/employer/tasks') })
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [from, setFrom] = useState(0)
  const [to, setTo] = useState(0)
  const [format, setFormat] = useState('')
  const [contact, setContact] = useState('')
  const [challenge, setChallenge] = useState('')
  const [withChallenge, setWithChallenge] = useState(false)

  useEffect(() => {
    if (!candidate) return
    setTitle(need?.title ?? candidate.headline ?? '')
    setFrom(need?.salary_from ?? 0)
    setTo(need?.salary_to ?? 0)
    setFormat(need?.work_formats?.[0] ?? '')
    setMessage(
      `Здравствуйте! Мы в «${company?.name ?? 'нашей компании'}» посмотрели ваш профиль: ${candidate.grade_title} в ${candidate.specialization_title}` +
        (candidate.has_fsp ? ' и результаты на соревнованиях ФСП' : '') +
        '. Хотим предложить вам позицию в нашей команде.' +
        (need?.team_description ? `\n\nО команде: ${need.team_description}` : '') +
        '\n\nБудем рады обсудить задачи и условия.',
    )
    setContact(company?.contact_telegram || company?.contact_email || '')
  }, [candidate, need, company])

  const preview = useQuery({
    queryKey: ['invite-preview', candidate?.id, from, to],
    queryFn: () => api.post<Preview>('/api/employer/invitations/preview', { candidate_id: candidate!.id, salary_from: from, salary_to: to }),
    enabled: !!candidate && from > 0 && to >= from,
  })
  const send = useMutation({
    mutationFn: () =>
      api.post('/api/employer/invitations', {
        candidate_id: candidate!.id,
        need_id: need?.id,
        position_title: title,
        message,
        salary_from: from,
        salary_to: to,
        work_format: format,
        contact_method: contact,
        challenge_task_id: withChallenge && challenge ? Number(challenge) : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shortlist'] })
      qc.invalidateQueries({ queryKey: ['emp-invitations'] })
      qc.invalidateQueries({ queryKey: ['company'] })
      qc.invalidateQueries({ queryKey: ['emp-candidate'] })
      onClose()
    },
  })
  const p = preview.data
  return (
    <Modal open={!!candidate} onClose={onClose} title={`Приглашение кандидату ${candidate?.code ?? ''}`} wide>
      {candidate && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            send.mutate()
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Позиция" className="sm:col-span-2">
              <Input required value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="Зарплата от, ₽/мес до НДФЛ">
              <Input type="number" required min={0} step={1000} value={from || ''} onChange={(e) => setFrom(Number(e.target.value))} />
            </Field>
            <Field label="Зарплата до, ₽/мес до НДФЛ">
              <Input type="number" required min={0} step={1000} value={to || ''} onChange={(e) => setTo(Number(e.target.value))} />
            </Field>
          </div>
          {p && (
            <Alert tone={SALARY_TONE[p.salary_status]} title="Проверка вилки">
              {p.hint}. Сумма ожиданий кандидата не раскрывается.
            </Alert>
          )}
          {p?.grade_warning && (
            <Alert tone="warn" title="Грейд не подтверждён">
              {p.grade_warning}. Приглашение отправить можно: уровень стоит уточнить на собеседовании.
            </Alert>
          )}
          <Field label="Описание предложения" hint="Персональное сообщение повышает шанс согласия. Кандидат увидит его до раскрытия контактов.">
            <Textarea required minLength={20} rows={6} value={message} onChange={(e) => setMessage(e.target.value)} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Формат работы">
              <Select value={format} onChange={(e) => setFormat(e.target.value)}>
                <option value="">не указан</option>
                <option value="remote">Удалённо</option>
                <option value="hybrid">Гибрид</option>
                <option value="office">Офис</option>
              </Select>
            </Field>
            <Field label="Способ связи" hint="Кандидат увидит его после принятия">
              <Input required value={contact} onChange={(e) => setContact(e.target.value)} placeholder="@hr_telegram или email" />
            </Field>
          </div>
          {!!tasks?.length && (
            <div className="rounded-xl border border-line p-4">
              <Checkbox checked={withChallenge} onChange={setWithChallenge} label="Приложить задание-челлендж" hint="Кандидат получит короткую задачу от вашей компании; решение увидите в разделе «Задания»." />
              {withChallenge && (
                <Select className="mt-3" value={challenge} onChange={(e) => setChallenge(e.target.value)}>
                  <option value="">Выберите задание</option>
                  {tasks.map((t) => (
                    <option key={t.id} value={t.id}>{t.title}</option>
                  ))}
                </Select>
              )}
            </div>
          )}
          {send.error && <Alert tone="danger">{(send.error as Error).message}</Alert>}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted">Осталось приглашений на неделю: {p?.quota_left ?? company?.quota_left ?? '—'} · вилка обязательна</span>
            <Button size="lg" loading={send.isPending} icon={<Send className="size-4" />} disabled={!from || !to || to < from}>
              Отправить · {rub(from)} – {rub(to)}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}
