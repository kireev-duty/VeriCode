import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bell, HelpCircle, LogOut, Menu, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { api } from '../api/client'
import type { Notifications } from '../api/types'
import logo from '../assets/logo-on-light.svg'
import logoDark from '../assets/logo-on-dark.svg'
import { useAuth } from '../lib/auth'
import { ago } from '../lib/format'

const CANDIDATE_NAV = [
  { to: '/c', label: 'Главная', end: true },
  { to: '/c/test', label: 'Тест и грейд' },
  { to: '/c/invitations', label: 'Приглашения' },
  { to: '/c/vacancies', label: 'Вакансии' },
  { to: '/c/tasks', label: 'Задания' },
  { to: '/c/profile', label: 'Профиль' },
  { to: '/c/settings', label: 'Настройки' },
]

const EMPLOYER_NAV = [
  { to: '/e', label: 'Подбор', end: true },
  { to: '/e/search', label: 'Банк кандидатов' },
  { to: '/e/invitations', label: 'Приглашения' },
  { to: '/e/vacancies', label: 'Вакансии' },
  { to: '/e/tasks', label: 'Задания' },
  { to: '/e/company', label: 'Компания' },
]

function Bellmenu() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get<Notifications>('/api/notifications'),
    refetchInterval: 30_000,
  })
  const readAll = useMutation({
    mutationFn: () => api.post('/api/notifications/read'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
  return (
    <div className="relative">
      <button
        className="relative rounded-xl p-2 text-muted hover:bg-brand-50 hover:text-ink"
        onClick={() => {
          setOpen(!open)
          if (!open && data?.unread) readAll.mutate()
        }}
        aria-label="Уведомления"
      >
        <Bell className="size-5" />
        {!!data?.unread && (
          <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-accent-500 text-[10px] font-bold text-white">
            {data.unread > 9 ? '9+' : data.unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-40 mt-2 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-xl">
            <div className="border-b border-line px-4 py-3 text-sm font-semibold">Уведомления</div>
            <div className="max-h-96 overflow-y-auto">
              {!data?.items.length && <div className="px-4 py-6 text-center text-sm text-muted">Пока пусто</div>}
              {data?.items.map((n) => (
                <button
                  key={n.id}
                  className="block w-full border-b border-line px-4 py-3 text-left text-sm last:border-0 hover:bg-surface"
                  onClick={() => {
                    setOpen(false)
                    if (n.link) nav(n.link.replace('/candidate/', '/c/').replace('/employer/', '/e/'))
                  }}
                >
                  <div className={clsx(!n.read && 'font-medium')}>{n.title}</div>
                  <div className="mt-0.5 text-xs text-muted">{ago(n.created_at)}</div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export function AppShell() {
  const { user, signOut } = useAuth()
  const [menu, setMenu] = useState(false)
  const nav = useNavigate()
  const items = user?.role === 'employer' ? EMPLOYER_NAV : CANDIDATE_NAV
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4">
          <Link to={user?.role === 'employer' ? '/e' : '/c'} className="flex shrink-0 items-center gap-2">
            <img src={logo} alt="ФСП" className="h-8" />
            <span className="hidden border-l border-line pl-2 font-semibold sm:block">Талант</span>
          </Link>
          <nav className="hidden flex-1 items-center gap-1 lg:flex">
            {items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end={i.end}
                className={({ isActive }) =>
                  clsx('rounded-lg px-3 py-2 text-sm font-medium transition', isActive ? 'bg-brand-50 text-brand-700' : 'text-muted hover:text-ink')
                }
              >
                {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {user?.is_demo && <span className="mono-label hidden rounded-md bg-warn-50 px-2 py-1 text-warn sm:block">демо</span>}
            <Bellmenu />
            <div className="hidden text-right text-xs leading-tight md:block">
              <div className="font-medium">{user?.role === 'employer' ? user.company_name || 'Компания' : 'Кандидат'}</div>
              <div className="text-muted">{user?.email}</div>
            </div>
            <button
              className="rounded-xl p-2 text-muted hover:bg-brand-50 hover:text-ink"
              title="Выйти"
              onClick={() => {
                signOut()
                nav('/')
              }}
            >
              <LogOut className="size-5" />
            </button>
            <button className="rounded-xl p-2 lg:hidden" onClick={() => setMenu(!menu)} aria-label="Меню">
              {menu ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>
        {menu && (
          <nav className="border-t border-line bg-white px-4 py-2 lg:hidden">
            {items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end={i.end}
                onClick={() => setMenu(false)}
                className={({ isActive }) => clsx('block rounded-lg px-3 py-2.5 text-sm font-medium', isActive ? 'bg-brand-50 text-brand-700' : 'text-ink')}
              >
                {i.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}

export function PublicShell({ children }: { children?: ReactNode }) {
  const { user } = useAuth()
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4">
          <Link to="/" className="flex items-center gap-2">
            <img src={logo} alt="ФСП" className="h-8" />
            <span className="hidden border-l border-line pl-2 font-semibold sm:block">Талант</span>
          </Link>
          <nav className="ml-6 hidden gap-1 md:flex">
            <NavLink to="/how" className={({ isActive }) => clsx('rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'text-brand-600' : 'text-muted hover:text-ink')}>
              Как это работает
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link to="/how" aria-label="Как это работает" className="rounded-xl p-2 text-muted hover:bg-brand-50 hover:text-ink md:hidden">
              <HelpCircle className="size-5" />
            </Link>
            {user ? (
              <Link to={user.role === 'employer' ? '/e' : '/c'} className="rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">
                Мой кабинет
              </Link>
            ) : (
              <>
                <Link to="/login" className="rounded-xl px-4 py-2 text-sm font-medium hover:bg-brand-50">
                  Войти
                </Link>
                <Link to="/register" className="rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">
                  Регистрация
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1">{children ?? <Outlet />}</main>
      <footer className="bg-ink text-white/70">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm">
          <img src={logoDark} alt="ФСП" className="h-8" />
          <div className="flex flex-wrap gap-6">
            <Link to="/how" className="hover:text-white">Механики</Link>
            <a href="/api/docs" className="hover:text-white">API (Swagger)</a>
            <span>Решение для ЛЦТ-2026 · спец. трек ФСП</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
