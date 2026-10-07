import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, Check, CircleDashed, Eye, EyeOff, Mail, Trophy, Zap } from 'lucide-react'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { CandidateProfile, Invitation, TaskSub } from '../../api/types'
import { Badge, Card, Empty, PageHeader, PageLoader, ProgressBar, SectionTitle } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { ago, date, INVITATION_STATUS, salaryRange, skillLevel } from '../../lib/format'

interface Dashboard {
  profile: CandidateProfile
  steps: { key: string; title: string; done: boolean; optional?: boolean }[]
  active_session_id: number | null
  invitations: { new: number; active: number; accepted: number; total: number }
  applications: { total: number; active: number }
  pending_task: TaskSub | null
}

const STEP_LINK: Record<string, string> = {
  consent: '/c/settings',
  onboarding: '/c/onboarding',
  test: '/c/test',
  profile: '/c/profile',
  fsp: '/c/settings',
  publish: '/c/settings',
}

export function CandidateDashboard() {
  const { skillTitle } = useCatalog()
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: () => api.get<Dashboard>('/api/candidate/dashboard') })
  const { data: invitations } = useQuery({ queryKey: ['my-invitations'], queryFn: () => api.get<Invitation[]>('/api/candidate/invitations') })
  if (!data) return <PageLoader />
  const p = data.profile
  const done = data.steps.filter((s) => s.done && !s.optional).length
  const required = data.steps.filter((s) => !s.optional).length
  const fresh = p.last_task_at ?? p.grade_confirmed_at
  return (
    <div>
      <PageHeader label={`Кабинет кандидата · ${p.code}`} title={p.full_name ? `Здравствуйте, ${p.full_name.split(' ')[0]}!` : 'Добро пожаловать!'} />
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="relative overflow-hidden p-6">
          <div className="absolute -top-16 -right-16 size-48 rounded-full bg-brand-50" />
          <div className="relative">
            <div className="mono-label text-brand-500">Ваша категория</div>
            {p.grade ? (
              <>
                <div className="mt-2 text-3xl font-semibold">
                  {p.specialization_title} · {p.grade_title}
                </div>
                <div className="mt-1 text-sm text-muted">Подтверждено тестом {date(p.grade_confirmed_at)}</div>
                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  {Object.entries(p.skill_theta)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 6)
                    .map(([s, t]) => {
                      const lvl = skillLevel(t)
                      return (
                        <div key={s}>
                          <div className="flex justify-between text-xs">
                            <span>{skillTitle(s)}</span>
                            <span className="text-muted">{lvl.label}</span>
                          </div>
                          <ProgressBar value={lvl.value} className="mt-1 h-1.5" />
                        </div>
                      )
                    })}
                </div>
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <Badge tone={p.searchable ? 'ok' : 'warn'}>
                    {p.searchable ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
                    {p.searchable ? 'Вас видят работодатели' : 'Профиль скрыт от работодателей'}
                  </Badge>
                  <Link to="/c/test" className="text-sm font-medium text-brand-600 hover:underline">Тест на другой грейд</Link>
                </div>
              </>
            ) : (
              <>
                <div className="mt-2 text-2xl font-semibold">Категория ещё не присвоена</div>
                <p className="mt-1 text-muted">Пройдите адаптивный тест — после него работодатели увидят вас в подборках.</p>
                <Link
                  to={data.active_session_id ? `/c/test/${data.active_session_id}` : p.onboarding_done ? '/c/test' : '/c/onboarding'}
                  className="mt-5 inline-flex h-11 items-center gap-2 rounded-xl bg-brand-500 px-5 font-medium text-white hover:bg-brand-600"
                >
                  {data.active_session_id ? 'Продолжить тест' : p.onboarding_done ? 'Пройти тест' : 'Начать с опроса'} <ArrowRight className="size-4" />
                </Link>
              </>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle label={`${done} из ${required}`} title="Готовность профиля" />
          <ul className="space-y-2.5">
            {data.steps.map((s) => (
              <li key={s.key}>
                <Link to={STEP_LINK[s.key]} className="flex items-center gap-3 text-sm hover:text-brand-600">
                  {s.done ? (
                    <span className="flex size-5 items-center justify-center rounded-full bg-ok text-white">
                      <Check className="size-3" />
                    </span>
                  ) : (
                    <CircleDashed className="size-5 text-muted" />
                  )}
                  <span className={clsx(s.done && 'text-muted line-through decoration-muted/40')}>{s.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-2">
          <SectionTitle
            label="Обратная механика"
            title="Приглашения от работодателей"
            action={<Link to="/c/invitations" className="text-sm font-medium text-brand-600">Все →</Link>}
          />
          {!invitations?.length ? (
            <Empty icon={<Mail className="size-6" />} title="Пока приглашений нет">
              Работодатели находят кандидатов по категории — держите профиль актуальным.
            </Empty>
          ) : (
            <div className="divide-y divide-line">
              {invitations.slice(0, 4).map((i) => (
                <Link key={i.id} to="/c/invitations" className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{i.position_title}</div>
                    <div className="text-sm text-muted">
                      {i.company.name} · {ago(i.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-brand-600">{salaryRange(i.salary_from, i.salary_to)}</span>
                    <Badge tone={INVITATION_STATUS[i.status].tone}>{INVITATION_STATUS[i.status].label}</Badge>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <Zap className="size-5 text-brand-500" />
              <div className="font-semibold">Задание недели</div>
            </div>
            {data.pending_task ? (
              <>
                <div className="mt-3 font-medium">{data.pending_task.task.title}</div>
                <p className="mt-1 line-clamp-3 text-sm text-muted">{data.pending_task.task.body}</p>
                <div className="mt-1 text-xs text-muted">от {data.pending_task.task.company}</div>
                <Link to="/c/tasks" className="mt-3 inline-block text-sm font-medium text-brand-600">Решить →</Link>
              </>
            ) : (
              <p className="mt-2 text-sm text-muted">Новое задание появится в течение недели. Решения поддерживают профиль актуальным.</p>
            )}
            <div className="mt-4 border-t border-line pt-3 text-xs text-muted">Профиль подтверждён активностью: {ago(fresh)}</div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <Trophy className="size-5 text-brand-500" />
              <div className="font-semibold">Достижения ФСП</div>
            </div>
            {p.fsp_id ? (
              <p className="mt-2 text-sm text-muted">
                ФСП ID {p.fsp_id} · {p.achievements.length} результатов{p.fsp_profile?.rank ? ` · разряд ${p.fsp_profile.rank}` : ''}. Достижения поднимают вас внутри категории.
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">Привяжите ФСП ID — результаты соревнований подтянутся автоматически. Без истории ФСП профиль полноценен.</p>
            )}
            <Link to="/c/settings" className="mt-3 inline-block text-sm font-medium text-brand-600">
              {p.fsp_id ? 'Подробнее' : 'Привязать ФСП ID'} →
            </Link>
          </Card>
        </div>
      </div>
    </div>
  )
}
