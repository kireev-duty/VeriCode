import { useMutation, useQuery } from '@tanstack/react-query'
import { BadgeCheck, ShieldCheck, Trophy } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { api } from '../../api/client'
import mark from '../../assets/mark-on-light.svg'
import { Alert, Badge, Button, Card, Field, Input, PageLoader, Spinner } from '../../components/ui'
import { date } from '../../lib/format'

interface Verified {
  code: string
  full_name: string
  specialization: string | null
  grade: string | null
  grade_confirmed_at: string | null
  verified_skills: string[]
  fsp_linked: boolean
  achievements: { event_name: string; year: number; result: string; level: string }[]
}

export function VerifyProfile() {
  const { code } = useParams()
  const { data, isLoading, error } = useQuery({ queryKey: ['verify', code], queryFn: () => api.get<Verified>(`/api/public/verify/${code}`), retry: false })
  if (isLoading) return <PageLoader />
  if (error || !data)
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Alert tone="danger" title="Профиль не найден">Ссылка проверки недействительна — документ мог быть подделан.</Alert>
      </div>
    )
  return (
    <div className="mx-auto max-w-lg px-4 py-16">
      <Card className="p-8">
        <div className="flex items-center gap-3 text-ok">
          <ShieldCheck className="size-8" />
          <div>
            <div className="font-semibold">Профиль подлинный</div>
            <div className="text-sm text-muted">Данные подтверждены платформой ФСП Талант</div>
          </div>
        </div>
        <div className="mt-6 space-y-4">
          <div>
            <div className="text-sm text-muted">Кандидат</div>
            <div className="text-xl font-semibold">{data.full_name || data.code}</div>
          </div>
          <div>
            <div className="text-sm text-muted">Категория</div>
            <div className="font-medium">
              {data.specialization ?? '—'} · {data.grade ?? 'грейд не подтверждён'}
            </div>
            {data.grade_confirmed_at && <div className="text-sm text-muted">подтверждено тестом {date(data.grade_confirmed_at)}</div>}
          </div>
          {data.verified_skills.length > 0 && (
            <div>
              <div className="mb-1.5 text-sm text-muted">Навыки, проверенные тестом</div>
              <div className="flex flex-wrap gap-1.5">
                {data.verified_skills.map((s) => (
                  <Badge key={s} tone="ok">
                    <BadgeCheck className="size-3" /> {s}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="mb-1.5 text-sm text-muted">Достижения ФСП</div>
            {data.achievements.length ? (
              <ul className="space-y-1.5 text-sm">
                {data.achievements.map((a, i) => (
                  <li key={i} className="flex gap-2">
                    <Trophy className="mt-0.5 size-4 shrink-0 text-brand-500" />
                    <span>
                      {a.result} — {a.event_name} ({a.year}, {a.level.toLowerCase()})
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-sm text-muted">{data.fsp_linked ? 'ФСП ID привязан, результатов нет' : 'ФСП ID не привязан'}</div>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}

/** Stand-in for the FSP ID login page when Keycloak is not running (FSP_OIDC_ENABLED=false). */
export function FspMockLogin() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [fspId, setFspId] = useState('FSP-123457')
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <Card className="w-full max-w-sm p-8">
        <div className="flex items-center gap-3">
          <img src={mark} className="size-10" alt="" />
          <div>
            <div className="font-semibold">ФСП ID</div>
            <div className="text-xs text-muted">Демо-провайдер (OIDC отключён)</div>
          </div>
        </div>
        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            nav(`/fsp/callback?code=${encodeURIComponent('mock:' + fspId)}&state=${encodeURIComponent(params.get('state') ?? '')}`)
          }}
        >
          <Field label="ID участника ФСП" hint="FSP-…0 — участник без истории, FSP-9… — нет в реестре">
            <Input value={fspId} onChange={(e) => setFspId(e.target.value.toUpperCase())} />
          </Field>
          <Button className="w-full">Войти и разрешить доступ</Button>
          <p className="text-xs text-muted">ФСП Талант получит доступ к вашему ID участника и результатам соревнований.</p>
        </form>
      </Card>
    </div>
  )
}

export function FspCallback() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const done = useRef(false)
  const cb = useMutation({
    mutationFn: () => api.post('/api/candidate/fsp/callback', { code: params.get('code'), state: params.get('state') }),
    onSuccess: () => setTimeout(() => nav('/c/settings?fsp=linked'), 700),
  })
  useEffect(() => {
    if (!done.current) {
      done.current = true
      cb.mutate()
    }
  }, [cb])
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <Card className="w-full max-w-md p-8 text-center">
        {cb.isPending && (
          <>
            <Spinner className="mx-auto size-8" />
            <p className="mt-3 text-muted">Получаем достижения из реестра ФСП…</p>
          </>
        )}
        {cb.isSuccess && (
          <>
            <Trophy className="mx-auto size-10 text-brand-500" />
            <div className="mt-3 font-semibold">ФСП ID привязан</div>
          </>
        )}
        {cb.isError && (
          <>
            <div className="font-semibold">Не удалось привязать ФСП ID</div>
            <p className="mt-1 text-sm text-muted">{(cb.error as Error).message}</p>
            <Link to="/c/settings" className="mt-4 inline-block text-brand-600">Вернуться в настройки</Link>
          </>
        )}
      </Card>
    </div>
  )
}
