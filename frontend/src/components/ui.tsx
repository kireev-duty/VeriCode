import { useQueryClient, type Query, type QueryCache } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, Loader2, X } from 'lucide-react'
import {
  isValidElement,
  useEffect,
  useId,
  useSyncExternalStore,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

type Tone = 'brand' | 'ok' | 'warn' | 'muted' | 'danger' | 'ink'

// ------------------------------------------------------------------------------------------- Button

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'dark'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
}

export function Button({ variant = 'primary', size = 'md', loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        {
          primary: 'bg-brand-500 text-white hover:bg-brand-600 active:bg-brand-700',
          secondary: 'border border-line bg-white text-ink hover:border-brand-300 hover:bg-brand-50',
          ghost: 'text-ink hover:bg-brand-50',
          danger: 'border border-accent-500/30 bg-white text-accent-600 hover:bg-accent-50',
          dark: 'bg-ink text-white hover:bg-black',
        }[variant],
        { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4 text-sm', lg: 'h-12 px-6 text-base' }[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

// ------------------------------------------------------------------------------------------- Layout bits

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx('rounded-2xl border border-line bg-white p-5', className)} {...rest}>
      {children}
    </div>
  )
}

export function SectionTitle({ label, title, action }: { label?: string; title: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        {label && <div className="mono-label mb-1 text-brand-500">{label}</div>}
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      {action}
    </div>
  )
}

export function PageHeader({ label, title, subtitle, action }: { label?: string; title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {label && <div className="mono-label mb-2 text-brand-500">{label}</div>}
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-3xl text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function Badge({ tone = 'muted', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        {
          brand: 'bg-brand-50 text-brand-700',
          ok: 'bg-ok-50 text-ok',
          warn: 'bg-warn-50 text-warn',
          muted: 'bg-surface text-muted',
          danger: 'bg-accent-50 text-accent-600',
          ink: 'bg-ink text-white',
        }[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Alert({ tone = 'brand', title, children, className }: { tone?: Tone; title?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <div
      className={clsx(
        'rounded-xl border px-4 py-3 text-sm',
        {
          brand: 'border-brand-200 bg-brand-50 text-brand-900',
          ok: 'border-ok/20 bg-ok-50 text-ok',
          warn: 'border-warn/20 bg-warn-50 text-warn',
          muted: 'border-line bg-surface text-muted',
          danger: 'border-accent-500/20 bg-accent-50 text-accent-600',
          ink: 'border-ink bg-ink text-white',
        }[tone],
        className,
      )}
    >
      {title && <div className="font-semibold">{title}</div>}
      {children && <div className={clsx(title && 'mt-1', 'opacity-90')}>{children}</div>}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('size-5 animate-spin text-brand-500', className)} />
}

function failedQuery(cache: QueryCache): Query | undefined {
  return cache.findAll({ type: 'active' }).find((q) => q.state.status === 'error' && q.state.fetchStatus === 'idle')
}

/** Page placeholder while data loads. If a query of the page has failed, it shows the error and a retry button
 * instead of spinning forever (pages render it as `if (!data) return <PageLoader />`). */
export function PageLoader() {
  const qc = useQueryClient()
  const cache = qc.getQueryCache()
  const failed = useSyncExternalStore(
    (cb) => cache.subscribe(cb),
    () => failedQuery(cache),
  )
  if (failed) {
    const message = failed.state.error instanceof Error ? failed.state.error.message : ''
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-4">
        <div className="max-w-md rounded-2xl border border-line bg-white p-6 text-center">
          <AlertTriangle className="mx-auto size-7 text-warn" />
          <div className="mt-3 font-semibold">Не удалось загрузить данные</div>
          <p className="mt-1 text-sm text-muted">{message || 'Проверьте соединение и попробуйте ещё раз.'}</p>
          <Button className="mt-4" variant="secondary" onClick={() => qc.refetchQueries({ predicate: (q) => q.state.status === 'error' })}>
            Повторить
          </Button>
        </div>
      </div>
    )
  }
  return (
    <div className="flex min-h-[40vh] items-center justify-center" role="status" aria-label="Загрузка">
      <Spinner className="size-7" />
    </div>
  )
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-line bg-white px-6 py-12 text-center">
      {icon && <div className="mb-3 text-brand-400">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'brand' | 'ok' }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={clsx('mt-1 text-2xl font-semibold', tone === 'brand' && 'text-brand-500', tone === 'ok' && 'text-ok')}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  )
}

export function ProgressBar({ value, tone = 'brand', className }: { value: number; tone?: 'brand' | 'ok' | 'warn' | 'danger'; className?: string }) {
  return (
    <div className={clsx('h-2 overflow-hidden rounded-full bg-surface', className)}>
      <div
        className={clsx('h-full rounded-full transition-all', {
          brand: 'bg-brand-500',
          ok: 'bg-ok',
          warn: 'bg-warn',
          danger: 'bg-accent-500',
        }[tone])}
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }}
      />
    </div>
  )
}

export function ScoreRing({ value, size = 56, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 6) / 2
  const c = 2 * Math.PI * r
  const v = Math.max(0, Math.min(1, value))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} title={label}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-brand-50)" strokeWidth={6} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-brand-500)"
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={`${c * v} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-sm font-semibold">{Math.round(v * 100)}</div>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- Forms

const FIELD_CONTROLS: unknown[] = ['input', 'select', 'textarea']

/** A labelled form row. With one input inside it is a <label>; with anything else (chips, toggles, several
 * controls) it is a group: a <label> around buttons would name the first button after the whole row and
 * forward every click on the caption to it. */
export function Field({ label, hint, error, children, className }: { label?: ReactNode; hint?: ReactNode; error?: string | null; children: ReactNode; className?: string }) {
  const captionId = useId()
  const single = isValidElement(children) && [...FIELD_CONTROLS, Input, Select, Textarea].includes(children.type)
  const body = (
    <>
      {label && (
        <span id={captionId} className="mb-1.5 block text-sm font-medium">
          {label}
        </span>
      )}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-accent-600">{error}</span>}
    </>
  )
  if (single) return <label className={clsx('block', className)}>{body}</label>
  return (
    <div role="group" aria-labelledby={label ? captionId : undefined} className={clsx('block', className)}>
      {body}
    </div>
  )
}

const inputCls =
  'w-full rounded-xl border border-line bg-white px-3 text-sm outline-none transition placeholder:text-muted/80 focus:border-brand-400 focus:ring-2 focus:ring-brand-100 disabled:bg-surface'

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(inputCls, 'h-10', className)} {...rest} />
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(inputCls, 'min-h-24 py-2', className)} {...rest} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(inputCls, 'h-10 pr-8', className)} {...rest}>
      {children}
    </select>
  )
}

export function Checkbox({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode }) {
  const id = useId()
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 accent-brand-500"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id} className="text-sm">
        {label}
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </label>
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex w-full items-start justify-between gap-4 text-left">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </span>
      <span className={clsx('relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition', checked ? 'bg-brand-500' : 'bg-line')}>
        <span className={clsx('absolute top-0.5 size-5 rounded-full bg-white shadow transition', checked ? 'left-[22px]' : 'left-0.5')} />
      </span>
    </button>
  )
}

export function ChipToggle({ active, onClick, children, size = 'md' }: { active: boolean; onClick: () => void; children: ReactNode; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'rounded-full border font-medium transition',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-sm',
        active ? 'border-brand-500 bg-brand-500 text-white' : 'border-line bg-white text-ink hover:border-brand-300',
      )}
    >
      {children}
    </button>
  )
}

export function MultiChips<T extends string>({ options, value, onChange, size }: { options: { id: T; title: string }[]; value: T[]; onChange: (v: T[]) => void; size?: 'sm' | 'md' }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <ChipToggle
          key={o.id}
          size={size}
          active={value.includes(o.id)}
          onClick={() => onChange(value.includes(o.id) ? value.filter((x) => x !== o.id) : [...value, o.id])}
        >
          {o.title}
        </ChipToggle>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- Modal & Tabs

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={clsx('animate-fade-in max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-6 shadow-xl sm:rounded-2xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-surface" aria-label="Закрыть">
            <X className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; title: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={clsx(
            'shrink-0 rounded-lg px-3.5 py-1.5 text-sm font-medium transition',
            value === t.id ? 'bg-white text-ink shadow-sm' : 'text-muted hover:text-ink',
          )}
        >
          {t.title}
        </button>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- Domain bits

const GRADE_TONE: Record<string, string> = {
  intern: 'bg-surface text-muted border-line',
  junior: 'bg-brand-50 text-brand-700 border-brand-100',
  middle: 'bg-brand-100 text-brand-800 border-brand-200',
  senior: 'bg-brand-500 text-white border-brand-500',
}

export function GradeBadge({ grade, title, spec, claimed }: { grade: string | null; title?: string | null; spec?: string | null; claimed?: string | null }) {
  if (!grade && claimed)
    return (
      <span title="Кандидат проходил тест на этот грейд, но не подтвердил его">
        <Badge tone="warn">
          {spec ? `${spec} · ` : ''}заявлен {claimed} · не подтверждён
        </Badge>
      </span>
    )
  if (!grade) return <Badge>Грейд не подтверждён</Badge>
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap', GRADE_TONE[grade])}>
      {spec && <span className="font-normal opacity-80">{spec} ·</span>}
      {title ?? grade}
    </span>
  )
}

export function TrustBadge({ trust }: { trust?: { score: number; level: string; signals?: { text: string; ok: boolean }[] } }) {
  if (!trust) return null
  const tone = trust.level === 'high' ? 'ok' : trust.level === 'medium' ? 'warn' : 'danger'
  const label = trust.level === 'high' ? 'Надёжный работодатель' : trust.level === 'medium' ? 'Проверка частичная' : 'Мало данных о компании'
  return (
    <span title={trust.signals?.map((s) => (s.ok ? '✓ ' : '• ') + s.text).join('\n')}>
      <Badge tone={tone}>
        {label} · {trust.score}
      </Badge>
    </span>
  )
}

export function CodeAvatar({ code, color }: { code: string; color?: string }) {
  return (
    <div
      className="flex size-11 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-semibold text-white"
      style={{ background: color ?? 'var(--color-ink)' }}
    >
      {code.replace('К-', '').slice(0, 3)}
    </div>
  )
}

/** Minimal markdown: **bold**, `code`, line breaks. Prompts are generated by our templates only. */
export function RichText({ text, className }: { text: string; className?: string }) {
  return (
    <div className={clsx('space-y-2', className)}>
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i} className="whitespace-pre-line">
          {para.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, j) => {
            if (part.startsWith('**')) return <strong key={j}>{part.slice(2, -2)}</strong>
            if (part.startsWith('`'))
              return (
                <code key={j} className="rounded bg-surface px-1 py-0.5 font-mono text-[0.9em]">
                  {part.slice(1, -1)}
                </code>
              )
            return <span key={j}>{part}</span>
          })}
        </p>
      ))}
    </div>
  )
}
