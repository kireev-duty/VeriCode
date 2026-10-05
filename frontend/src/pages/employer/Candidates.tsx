import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { BadgeCheck, Lock, Mail, Phone, Send, Trophy, Unlock, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { api } from '../../api/client'
import { emptyFilters, type CandidateCard, type CandidateDetail, type EmployerInvitation, type Filters, type Need } from '../../api/types'
import { Alert, Badge, Button, Card, CodeAvatar, Empty, GradeBadge, Input, PageHeader, PageLoader, ProgressBar, ScoreRing, SectionTitle, Tabs } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { ago, date, INVITATION_STATUS, salaryRange, skillLevel, thetaPercentile, years } from '../../lib/format'
import { CategoryMap } from './Matching'
import { CandidateRow, FiltersPanel, InviteModal } from './shared'

const COMPONENT_TITLES: Record<string, string> = {
  skills: 'Стек',
  grade: 'Грейд',
  test: 'Результат теста',
  fsp: 'Достижения ФСП',
  salary: 'Зарплата',
  format: 'Формат и город',
  freshness: 'Актуальность',
  text: 'Описание',
}

export function EmployerCandidate() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const needId = params.get('need')
  const { skillTitle } = useCatalog()
  const [invite, setInvite] = useState<CandidateCard | null>(null)
  const { data: c } = useQuery({
    queryKey: ['emp-candidate', id, needId],
    queryFn: () => api.get<CandidateDetail>(`/api/employer/candidates/${id}${needId ? `?need_id=${needId}` : ''}`),
  })
  const { data: need } = useQuery({ queryKey: ['need', needId], queryFn: () => api.get<Need>(`/api/employer/needs/${needId}`), enabled: !!needId })
  if (!c) return <PageLoader />
  const active = c.invitations.find((i) => i.status === 'sent' || i.status === 'viewed')
  return (
    <div>
      {needId && need && (
        <Link to={`/e/needs/${needId}`} className="mb-4 inline-block text-sm text-brand-600">← к подборке «{need.title}»</Link>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card className="p-6">
            <div className="flex flex-wrap items-start gap-4">
              <CodeAvatar code={c.code} />
              <div className="min-w-0 flex-1">
                <div className="mono-label text-muted">Анонимный профиль · {c.code}</div>
                <h1 className="mt-1 text-2xl font-semibold">{c.contacts?.full_name || c.headline || 'Кандидат'}</h1>
                {c.contacts?.full_name && <div className="text-muted">{c.headline}</div>}
                <div className="mt-2 flex flex-wrap gap-2">
                  <GradeBadge grade={c.grade} title={c.grade_title} spec={c.specialization_title} />
                  {c.has_fsp && <Badge tone="brand"><Trophy className="size-3" /> ФСП{c.fsp_rank ? ` · разряд ${c.fsp_rank}` : ''}</Badge>}
                  {!c.has_fsp && <Badge>нет данных ФСП</Badge>}
                </div>
                <div className="mt-2 text-sm text-muted">
                  {[years(c.experience_years) + ' опыта', c.city, c.relocation && 'готов к релокации'].filter(Boolean).join(' · ')}
                </div>
              </div>
            </div>
            {c.about && <p className="mt-4 text-sm whitespace-pre-line">{c.about}</p>}
          </Card>

          <Card className="p-6">
            <SectionTitle label="Подтверждено платформой" title="Паспорт навыков" />
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <div className="mb-2 text-sm text-muted">
                  Адаптивный тест · {date(c.grade_confirmed_at)} · выше, чем у {c.theta != null ? thetaPercentile(c.theta) : '—'}% кандидатов
                </div>
                <div className="space-y-2.5">
                  {Object.entries(c.skill_theta)
                    .sort((a, b) => b[1] - a[1])
                    .map(([s, t]) => {
                      const lvl = skillLevel(t)
                      return (
                        <div key={s}>
                          <div className="flex justify-between text-sm">
                            <span className="flex items-center gap-1"><BadgeCheck className="size-3.5 text-ok" />{skillTitle(s)}</span>
                            <span className="text-muted">{lvl.label}</span>
                          </div>
                          <ProgressBar value={lvl.value} className="mt-1 h-1.5" />
                        </div>
                      )
                    })}
                </div>
              </div>
              <div>
                <div className="mb-2 text-sm text-muted">Стек из профиля</div>
                <div className="flex flex-wrap gap-1.5">
                  {c.skills.map((s) => (
                    <Badge key={s.id} tone={s.verified ? 'ok' : 'muted'}>
                      {s.title}
                      {s.years ? ` · ${s.years} г.` : ''}
                    </Badge>
                  ))}
                </div>
                {(c.team_roles.length > 0 || c.soft_skills.length > 0) && (
                  <>
                    <div className="mt-4 mb-2 text-sm text-muted">Роли и soft skills</div>
                    <div className="flex flex-wrap gap-1.5">
                      {[...c.team_roles, ...c.soft_skills].map((s) => (
                        <Badge key={s}>{s}</Badge>
                      ))}
                    </div>
                  </>
                )}
                <div className="mt-4 text-xs text-muted">
                  Регулярные задания: {c.last_task_at ? `последнее ${ago(c.last_task_at)}, средняя оценка ${Math.round(c.task_score * 100)}%` : 'пока не решал'}
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle label="Реестр ФСП" title="Достижения" />
            {c.achievements.length ? (
              <div className="space-y-3">
                {c.achievements.map((a, i) => (
                  <div key={i} className="flex gap-3 rounded-xl border border-line p-3">
                    <Trophy className={clsx('mt-0.5 size-5 shrink-0', a.result === 'Победитель' || a.result === 'Призёр' ? 'text-brand-500' : 'text-muted')} />
                    <div className="text-sm">
                      <div className="font-medium">{a.event_name}</div>
                      <div className="text-muted">
                        {a.result}
                        {a.place ? `, ${a.place} место из ${a.participants}` : ''} · {a.level} · {a.year}
                      </div>
                      <div className="text-xs text-muted">{a.discipline}{a.team_role && ` · роль: ${a.team_role}`}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted">Кандидат не участвовал в соревнованиях ФСП или не привязал ФСП ID. Категория подтверждена тестом.</div>
            )}
          </Card>

          <Card className="p-6">
            <SectionTitle title="Опыт работы" />
            {c.experience.length ? (
              <div className="space-y-4">
                {c.experience.map((e, i) => (
                  <div key={i}>
                    <div className="font-medium">{e.position}</div>
                    <div className="text-sm text-muted">
                      {e.company === 'скрыто' ? 'Компания скрыта кандидатом' : e.company} · {e.from} — {e.to || 'н. в.'}
                    </div>
                    {e.summary && <p className="mt-1 text-sm">{e.summary}</p>}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted">Не указан</div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card className={clsx('p-6', c.contacts_open ? 'border-ok/40' : '')}>
            <div className="flex items-center gap-2 font-semibold">
              {c.contacts_open ? <Unlock className="size-5 text-ok" /> : <Lock className="size-5 text-muted" />}
              Контакты
            </div>
            {c.contacts_open && c.contacts ? (
              <div className="mt-3 space-y-2 text-sm">
                <div className="flex items-center gap-2"><UserRound className="size-4 text-muted" />{c.contacts.full_name}</div>
                <div className="flex items-center gap-2"><Mail className="size-4 text-muted" /><a className="text-brand-600" href={`mailto:${c.contacts.email}`}>{c.contacts.email}</a></div>
                {c.contacts.phone && <div className="flex items-center gap-2"><Phone className="size-4 text-muted" />{c.contacts.phone}</div>}
                {c.contacts.telegram && <div className="flex items-center gap-2"><Send className="size-4 text-muted" />{c.contacts.telegram}</div>}
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted">Откроются, когда кандидат примет ваше приглашение или откликнется на вашу вакансию.</p>
            )}
            {!c.contacts_open && (
              <Button
                className="mt-4 w-full"
                disabled={!c.open_to_offers || !!active}
                icon={<Send className="size-4" />}
                onClick={() => setInvite(c)}
              >
                {active ? 'Приглашение отправлено' : c.open_to_offers ? 'Пригласить' : 'Не принимает предложения'}
              </Button>
            )}
            {c.invitations.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-line pt-3">
                {c.invitations.map((i) => (
                  <div key={i.id} className="flex items-center justify-between text-sm">
                    <span className="truncate">{i.position_title}</span>
                    <Badge tone={INVITATION_STATUS[i.status].tone}>{INVITATION_STATUS[i.status].label}</Badge>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {c.match && (
            <Card className="p-6">
              <div className="flex items-center gap-4">
                <ScoreRing value={c.match.score} size={64} />
                <div>
                  <div className="font-semibold">Соответствие потребности</div>
                  <div className="text-sm text-muted">{need?.title}</div>
                </div>
              </div>
              <div className="mt-5 space-y-3">
                {Object.entries(c.match.components).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between text-sm">
                      <span>{COMPONENT_TITLES[k]}</span>
                      <span className="font-mono text-xs text-muted">
                        {Math.round(v * 100)}% × {Math.round(c.match!.weights[k] * 100)}
                      </span>
                    </div>
                    <ProgressBar value={v} className="mt-1 h-1.5" tone={v >= 0.7 ? 'ok' : v >= 0.4 ? 'warn' : 'danger'} />
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-muted">Значение компонента × его вес; сумма даёт итоговую оценку. Веса адаптируются по причинам отказов кандидатов вашей компании.</p>
            </Card>
          )}

          {c.test_history.length > 0 && (
            <Card className="p-6">
              <div className="mb-3 font-semibold">История грейда</div>
              <div className="space-y-2 text-sm">
                {c.test_history.map((h, i) => (
                  <div key={i}>
                    <div>{h.reason}</div>
                    <div className="text-xs text-muted">{date(h.created_at)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
      <InviteModal
        candidate={invite}
        onClose={() => setInvite(null)}
        need={need ? { id: need.id, title: need.title, salary_from: need.salary_from, salary_to: need.salary_to, work_formats: need.work_formats, team_description: need.team_description } : undefined}
      />
    </div>
  )
}

// ------------------------------------------------------------------------------------------- bank search

export function EmployerSearch() {
  const [params, setParams] = useSearchParams()
  const { catalog } = useCatalog()
  const [q, setQ] = useState('')
  const [invite, setInvite] = useState<CandidateCard | null>(null)
  const spec = params.get('spec')
  const grade = params.get('grade')
  const [filters, setFilters] = useState<Filters>({
    ...emptyFilters,
    specializations: spec ? [spec] : [],
    grades: grade ? [grade] : [],
  })
  const { data, isFetching } = useQuery({
    queryKey: ['bank-search', q, filters],
    queryFn: () => api.post<CandidateCard[]>('/api/employer/search', { q, filters }),
    placeholderData: keepPreviousData,
  })
  const skills = filters.specializations.length
    ? Array.from(new Set(catalog?.specializations.filter((s) => filters.specializations.includes(s.id)).flatMap((s) => s.stack_options) ?? []))
    : ['python', 'javascript', 'typescript', 'react', 'sql', 'docker', 'kubernetes', 'ml', 'test_design', 'go', 'java']
  return (
    <div>
      <PageHeader
        label="Банк кандидатов"
        title="Поиск по всей базе"
        subtitle="Фильтры по специализации, грейду, стеку и достижениям ФСП. Внутри выдачи — ранжирование по силе подтверждённого профиля."
      />
      <Card className="mb-6 p-5">
        <CategoryMap
          onPick={(s, g) => {
            setFilters({ ...filters, specializations: [s], grades: [g] })
            setParams({ spec: s, grade: g })
          }}
        />
      </Card>
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <div className="lg:sticky lg:top-24 lg:h-fit">
          <FiltersPanel value={filters} onChange={setFilters} skills={skills} showSpecs />
        </div>
        <div>
          <Input placeholder="Поиск по заголовку и описанию профиля…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 h-11" />
          <div className="mb-3 text-sm text-muted">
            {data ? `${data.length}${data.length === 50 ? '+' : ''} кандидатов` : ''} {isFetching && '· обновляем…'}
          </div>
          {data?.length === 0 ? (
            <Empty title="Никого не нашлось">Измените фильтры.</Empty>
          ) : (
            <div className="space-y-3">
              {data?.map((c) => (
                <CandidateRow key={c.id} c={c} onInvite={setInvite} />
              ))}
            </div>
          )}
        </div>
      </div>
      <InviteModal candidate={invite} onClose={() => setInvite(null)} />
    </div>
  )
}

// ------------------------------------------------------------------------------------------- invitations

export function EmployerInvitations() {
  const [tab, setTab] = useState<string>('all')
  const { data } = useQuery({ queryKey: ['emp-invitations'], queryFn: () => api.get<EmployerInvitation[]>('/api/employer/invitations') })
  if (!data) return <PageLoader />
  const counts = data.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.status]: (acc[i.status] ?? 0) + 1 }), {})
  const list = tab === 'all' ? data : data.filter((i) => i.status === tab)
  return (
    <div>
      <PageHeader label="Выход на контакт" title="Приглашения" subtitle="Статусы обновляются, когда кандидат открывает приглашение и отвечает. Контакты появляются после принятия." />
      <div className="mb-4">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'all', title: `Все (${data.length})` },
            ...['sent', 'viewed', 'accepted', 'declined', 'expired'].map((s) => ({ id: s, title: `${INVITATION_STATUS[s].label} (${counts[s] ?? 0})` })),
          ]}
        />
      </div>
      {list.length === 0 ? (
        <Empty icon={<Send className="size-8" />} title="Пусто" action={<Link to="/e" className="text-brand-600">К подбору →</Link>} />
      ) : (
        <div className="space-y-3">
          {list.map((i) => (
            <Card key={i.id} className="p-5">
              <div className="flex flex-wrap items-start gap-4">
                <CodeAvatar code={i.candidate.code} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/e/candidates/${i.candidate.id}`} className="font-semibold hover:text-brand-600">
                      {i.candidate.contacts?.full_name || i.candidate.headline || i.candidate.code}
                    </Link>
                    <GradeBadge grade={i.candidate.grade} title={i.candidate.grade_title} />
                  </div>
                  <div className="text-sm text-muted">
                    {i.position_title} · {salaryRange(i.salary_from, i.salary_to)} · {ago(i.created_at)}
                  </div>
                  {i.status === 'accepted' && i.candidate.contacts && (
                    <Alert tone="ok" className="mt-3">
                      Контакты: {i.candidate.contacts.email} · {i.candidate.contacts.phone} · {i.candidate.contacts.telegram}
                    </Alert>
                  )}
                  {i.status === 'declined' && (
                    <div className="mt-2 text-sm">
                      Причина: <b>{i.decline_reason_title}</b>
                      {i.decline_comment && <span className="text-muted"> — «{i.decline_comment}»</span>}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 text-right">
                  <Badge tone={INVITATION_STATUS[i.status].tone}>{INVITATION_STATUS[i.status].label}</Badge>
                  {i.viewed_at && i.status !== 'accepted' && i.status !== 'declined' && <span className="text-xs text-muted">просмотрено {ago(i.viewed_at)}</span>}
                  {i.match_score != null && <span className="text-xs text-muted">соответствие {Math.round(i.match_score * 100)}</span>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
