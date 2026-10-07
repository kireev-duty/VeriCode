import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Link2, RefreshCw, Trophy, Unlink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { api } from '../../api/client'
import type { CandidateProfile } from '../../api/types'
import { Alert, Badge, Button, Card, Field, Input, Modal, PageHeader, PageLoader, SectionTitle, Toggle } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import { useCatalog } from '../../lib/catalog'
import { date } from '../../lib/format'

export function CandidateSettings() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { signOut } = useAuth()
  const [params] = useSearchParams()
  const { catalog } = useCatalog()
  const { data: p } = useQuery({ queryKey: ['profile'], queryFn: () => api.get<CandidateProfile>('/api/candidate/profile') })
  const [minSalary, setMinSalary] = useState<string>('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    if (p) setMinSalary(p.min_salary_for_invites ? String(p.min_salary_for_invites) : '')
  }, [p])
  const update = (data: CandidateProfile) => {
    qc.setQueryData(['profile'], data)
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const privacy = useMutation({ mutationFn: (body: object) => api.put<CandidateProfile>('/api/candidate/privacy', body), onSuccess: update })
  const consents = useMutation({ mutationFn: (body: object) => api.post<CandidateProfile>('/api/candidate/consents', body), onSuccess: update })
  const fspStart = useMutation({
    mutationFn: () => api.get<{ mode: string; url: string }>('/api/candidate/fsp/start'),
    onSuccess: (d) => {
      if (d.mode === 'mock') nav(new URL(d.url).pathname + new URL(d.url).search)
      else window.location.href = d.url
    },
  })
  const fspRefresh = useMutation({ mutationFn: () => api.post<CandidateProfile>('/api/candidate/fsp/refresh'), onSuccess: update })
  const fspUnlink = useMutation({ mutationFn: () => api.del<CandidateProfile>('/api/candidate/fsp'), onSuccess: update })
  const del = useMutation({
    mutationFn: () => api.del('/api/candidate/account'),
    onSuccess: () => {
      signOut()
      nav('/')
    },
  })
  if (!p || !catalog) return <PageLoader />
  return (
    <div>
      <PageHeader label="Настройки" title="Приватность, согласия и ФСП ID" />
      {params.get('fsp') === 'linked' && <Alert tone="ok" className="mb-6" title="ФСП ID привязан">Достижения загружены из реестра и отмечены как подтверждённые.</Alert>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle label="Что видит работодатель" title="Приватность" />
          <div className="space-y-5">
            <Toggle
              checked={p.visible_to_employers}
              onChange={(v) => privacy.mutate({ visible_to_employers: v })}
              label="Показывать профиль в подборках"
              hint="Выключите, чтобы временно исчезнуть из поиска. Отклики на вакансии остаются доступны."
            />
            <Toggle checked={p.open_to_offers} onChange={(v) => privacy.mutate({ open_to_offers: v })} label="Открыт к предложениям" hint="Если выключено, работодатели видят профиль, но не могут отправить приглашение." />
            <Toggle checked={p.privacy.show_city} onChange={(v) => privacy.mutate({ privacy: { show_city: v } })} label="Показывать город" />
            <Toggle checked={p.privacy.show_fsp} onChange={(v) => privacy.mutate({ privacy: { show_fsp: v } })} label="Показывать достижения ФСП" />
            <Toggle checked={p.privacy.show_companies} onChange={(v) => privacy.mutate({ privacy: { show_companies: v } })} label="Показывать названия прошлых работодателей" hint="По умолчанию названия скрыты." />
            <Field label="Минимальная зарплата для приглашений, ₽/мес до НДФЛ" hint="Приглашения с вилкой ниже будут помечены. Работодатель не видит эту сумму.">
              <div className="flex gap-2">
                <Input type="number" step={1000} value={minSalary} onChange={(e) => setMinSalary(e.target.value)} />
                <Button variant="secondary" onClick={() => privacy.mutate({ min_salary_for_invites: minSalary ? Number(minSalary) : null })}>
                  Сохранить
                </Button>
              </div>
            </Field>
            <p className="text-xs text-muted">ФИО, контакты, возраст и фото не показываются никогда до вашего согласия на конкретное приглашение или собственного отклика.</p>
          </div>
        </Card>

        <div className="space-y-6">
          <Card className="p-6">
            <SectionTitle
              label="ФСП ID · Keycloak-совместимо"
              title="Достижения ФСП"
              action={
                p.fsp_id ? (
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" icon={<RefreshCw className="size-3.5" />} loading={fspRefresh.isPending} onClick={() => fspRefresh.mutate()}>
                      Обновить
                    </Button>
                    <Button size="sm" variant="ghost" icon={<Unlink className="size-3.5" />} onClick={() => fspUnlink.mutate()}>
                      Отвязать
                    </Button>
                  </div>
                ) : null
              }
            />
            {p.fsp_id ? (
              <>
                <div className="flex flex-wrap gap-2 text-sm">
                  <Badge tone="brand">{p.fsp_id}</Badge>
                  {p.fsp_profile.rank && <Badge>разряд {p.fsp_profile.rank}</Badge>}
                  {!!p.fsp_profile.rating && <Badge>рейтинг {p.fsp_profile.rating}</Badge>}
                  {p.fsp_profile.region && <Badge>{p.fsp_profile.region}</Badge>}
                </div>
                {p.achievements.length ? (
                  <ul className="mt-4 space-y-3">
                    {p.achievements.map((a) => (
                      <li key={a.id} className="flex gap-3 rounded-xl border border-line p-3">
                        <Trophy className="mt-0.5 size-5 shrink-0 text-brand-500" />
                        <div className="min-w-0 text-sm">
                          <div className="font-medium">{a.event_name}</div>
                          <div className="text-muted">
                            {catalog.fsp.results[a.result_type]}
                            {a.place ? `, ${a.place} место из ${a.participants}` : ''} · {catalog.fsp.levels[a.event_level]} · {date(a.date)}
                          </div>
                          <div className="text-xs text-muted">
                            {catalog.fsp.disciplines[a.discipline]}
                            {a.team_role && ` · ${a.team_role} в команде «${a.team_name}»`}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Alert tone="muted" className="mt-4">В реестре ФСП пока нет ваших результатов. Профиль от этого не хуже: категорию определяет тест.</Alert>
                )}
              </>
            ) : (
              <>
                <p className="text-sm text-muted">
                  Войдите через ФСП ID — результаты соревнований подтянутся из реестра ФСП и будут отмечены как подтверждённые. Это поднимет вас внутри категории. Без истории ФСП профиль полноценен.
                </p>
                <Button className="mt-4" icon={<Link2 className="size-4" />} loading={fspStart.isPending} onClick={() => fspStart.mutate()}>
                  Привязать ФСП ID
                </Button>
              </>
            )}
            {(fspStart.error || fspRefresh.error) && <Alert tone="danger" className="mt-3">{((fspStart.error || fspRefresh.error) as Error).message}</Alert>}
          </Card>

          <Card className="p-6">
            <SectionTitle label="152-ФЗ" title="Согласия" />
            <div className="space-y-4">
              <Toggle
                checked={!!p.consent_processing_at}
                onChange={(v) => consents.mutate({ processing: v, publication: v && !!p.consent_publication_at })}
                label="Обработка персональных данных"
                hint={p.consent_processing_at ? `Дано ${date(p.consent_processing_at)}` : 'Без него недоступны тест и отклики'}
              />
              <Toggle
                checked={!!p.consent_publication_at}
                onChange={(v) => consents.mutate({ processing: !!p.consent_processing_at || v, publication: v })}
                label="Публикация обезличенного профиля"
                hint={p.consent_publication_at ? `Дано ${date(p.consent_publication_at)}` : 'Без него вы не попадаете в подборки'}
              />
            </div>
            <div className="mt-6 border-t border-line pt-4">
              <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                Удалить аккаунт и все данные
              </Button>
            </div>
          </Card>
          <a href="/api/docs" className="flex items-center gap-1 text-xs text-muted hover:text-ink">
            <ExternalLink className="size-3" /> API платформы
          </a>
        </div>
      </div>
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Удалить аккаунт?">
        <p className="text-sm text-muted">Профиль, результаты тестов, достижения, приглашения и отклики будут удалены безвозвратно.</p>
        <Button className="mt-4 w-full" variant="danger" loading={del.isPending} onClick={() => del.mutate()}>
          Да, удалить всё
        </Button>
      </Modal>
    </div>
  )
}
