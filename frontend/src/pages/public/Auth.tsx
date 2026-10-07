import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { Briefcase, MailCheck, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, ApiError } from '../../api/client'
import type { Role, User } from '../../api/types'
import { Alert, Button, Card, Field, Input, Spinner } from '../../components/ui'
import { useAuth } from '../../lib/auth'

interface TokenOut {
  access_token: string
  user: User
}

function home(u: User) {
  if (u.role === 'employer') return '/e'
  return u.onboarding_done ? '/c' : '/c/onboarding'
}

export function DemoButtons({ compact }: { compact?: boolean }) {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const demo = useMutation({
    mutationFn: (role: string) => api.post<TokenOut>(`/api/auth/demo-login?role=${role}`),
    onSuccess: (d) => {
      signIn(d.access_token, d.user)
      nav(home(d.user))
    },
  })
  return (
    <div className={clsx('grid gap-2', compact ? 'sm:grid-cols-3' : 'sm:grid-cols-3')}>
      <Button variant="secondary" onClick={() => demo.mutate('candidate')} loading={demo.isPending && demo.variables === 'candidate'}>
        Кандидат с грейдом
      </Button>
      <Button variant="secondary" onClick={() => demo.mutate('candidate_new')} loading={demo.isPending && demo.variables === 'candidate_new'}>
        Новый кандидат
      </Button>
      <Button variant="secondary" onClick={() => demo.mutate('employer')} loading={demo.isPending && demo.variables === 'employer'}>
        Работодатель
      </Button>
      {demo.error && <div className="text-sm text-accent-600 sm:col-span-3">{(demo.error as Error).message}</div>}
    </div>
  )
}

export function Login() {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({
    mutationFn: () => api.post<TokenOut>('/api/auth/login', { email, password }),
    onSuccess: (d) => {
      signIn(d.access_token, d.user)
      nav(home(d.user))
    },
  })
  const resend = useMutation({
    mutationFn: () => api.post<{ dev_verify_link: string | null }>('/api/auth/resend-verification', { email }),
  })
  const err = login.error as ApiError | null
  return (
    <div className="trace-bg flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-4">
        <Card className="p-8">
          <h1 className="text-2xl font-semibold">Вход</h1>
          <p className="mt-1 text-sm text-muted">Кабинет кандидата или работодателя</p>
          <form
            className="mt-6 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              login.mutate()
            }}
          >
            <Field label="Email">
              <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Пароль">
              <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            {err && (
              <Alert tone="danger">
                {err.message}
                {err.code === 'email_not_verified' && (
                  <button type="button" className="ml-1 underline" onClick={() => resend.mutate()}>
                    Отправить письмо ещё раз
                  </button>
                )}
              </Alert>
            )}
            {resend.data?.dev_verify_link && (
              <Alert tone="ok" title="Письмо отправлено">
                Демо-режим: <a className="underline" href={resend.data.dev_verify_link}>подтвердить email</a>
              </Alert>
            )}
            <Button className="w-full" size="lg" loading={login.isPending}>
              Войти
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted">
            Нет аккаунта? <Link to="/register" className="font-medium text-brand-600">Зарегистрироваться</Link>
          </p>
        </Card>
        <Card>
          <div className="mono-label mb-3 text-brand-500">Демо-доступ для проверки</div>
          <DemoButtons />
        </Card>
      </div>
    </div>
  )
}

export function Register() {
  const [params] = useSearchParams()
  const [role, setRole] = useState<Role>((params.get('role') as Role) || 'candidate')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [company, setCompany] = useState('')
  const reg = useMutation({
    mutationFn: () =>
      api.post<{ email: string; email_sent: boolean; dev_verify_link: string | null }>('/api/auth/register', {
        email,
        password,
        role,
        company_name: role === 'employer' ? company : null,
      }),
  })
  if (reg.data) {
    return (
      <div className="trace-bg flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
        <Card className="w-full max-w-md p-8 text-center">
          <MailCheck className="mx-auto size-12 text-brand-500" />
          <h1 className="mt-4 text-2xl font-semibold">Подтвердите email</h1>
          <p className="mt-2 text-muted">
            Мы отправили письмо на <b className="text-ink">{reg.data.email}</b>. Перейдите по ссылке из письма, чтобы завершить регистрацию.
          </p>
          {reg.data.dev_verify_link && (
            <Alert tone="brand" className="mt-6 text-left" title="Демо-стенд">
              Письма приходят в тестовый ящик <a href="/mail/" target="_blank" className="underline">/mail</a>. Или{' '}
              <a href={reg.data.dev_verify_link} className="font-semibold underline">подтвердите сразу</a>.
            </Alert>
          )}
        </Card>
      </div>
    )
  }
  const err = reg.error as ApiError | null
  return (
    <div className="trace-bg flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold">Регистрация</h1>
        <div className="mt-6 grid grid-cols-2 gap-3">
          {(
            [
              ['candidate', 'Я ищу работу', UserRound],
              ['employer', 'Я нанимаю', Briefcase],
            ] as const
          ).map(([r, label, Icon]) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              className={clsx(
                'flex flex-col items-center gap-2 rounded-xl border p-4 text-sm font-medium transition',
                role === r ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-line hover:border-brand-300',
              )}
            >
              <Icon className="size-6" />
              {label}
            </button>
          ))}
        </div>
        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            reg.mutate()
          }}
        >
          {role === 'employer' && (
            <Field label="Название компании">
              <Input required value={company} onChange={(e) => setCompany(e.target.value)} />
            </Field>
          )}
          <Field label="Email" hint={role === 'employer' ? 'Корпоративная почта повышает траст-скор компании' : undefined}>
            <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Пароль" hint="Не короче 8 символов">
            <Input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {err && <Alert tone="danger">{err.message}</Alert>}
          <Button className="w-full" size="lg" loading={reg.isPending}>
            Создать аккаунт
          </Button>
          <p className="text-xs text-muted">
            Регистрируясь, вы соглашаетесь с обработкой email для входа. Согласие на обработку и публикацию данных профиля даётся отдельно в кабинете (152-ФЗ).
          </p>
        </form>
        <p className="mt-4 text-center text-sm text-muted">
          Уже есть аккаунт? <Link to="/login" className="font-medium text-brand-600">Войти</Link>
        </p>
      </Card>
    </div>
  )
}

export function VerifyEmail() {
  const [params] = useSearchParams()
  const { signIn } = useAuth()
  const nav = useNavigate()
  const started = useRef(false)
  const verify = useMutation({
    mutationFn: () => api.post<TokenOut>('/api/auth/verify-email', { token: params.get('token') }),
    onSuccess: (d) => {
      signIn(d.access_token, d.user)
      setTimeout(() => nav(home(d.user)), 900)
    },
  })
  useEffect(() => {
    if (!started.current) {
      started.current = true
      verify.mutate()
    }
  }, [verify])
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <Card className="w-full max-w-md p-8 text-center">
        {verify.isPending && <Spinner className="mx-auto size-8" />}
        {verify.isSuccess && (
          <>
            <MailCheck className="mx-auto size-12 text-ok" />
            <h1 className="mt-4 text-xl font-semibold">Email подтверждён</h1>
            <p className="mt-1 text-muted">Переходим в кабинет…</p>
          </>
        )}
        {verify.isError && (
          <>
            <h1 className="text-xl font-semibold">Ссылка недействительна</h1>
            <p className="mt-1 text-muted">{(verify.error as Error).message}</p>
            <Link to="/login" className="mt-4 inline-block text-brand-600">Ко входу</Link>
          </>
        )}
      </Card>
    </div>
  )
}
