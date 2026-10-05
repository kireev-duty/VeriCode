export function rub(n: number | null | undefined): string {
  if (n == null) return '—'
  return new Intl.NumberFormat('ru-RU').format(n) + ' ₽'
}

export function salaryRange(from: number, to: number): string {
  const f = new Intl.NumberFormat('ru-RU')
  return `${f.format(from)} – ${f.format(to)} ₽`
}

export function date(s: string | null | undefined): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function shortDate(s: string | null | undefined): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export function ago(s: string | null | undefined): string {
  if (!s) return 'никогда'
  const days = Math.floor((Date.now() - new Date(s).getTime()) / 86_400_000)
  if (days <= 0) return 'сегодня'
  if (days === 1) return 'вчера'
  if (days < 30) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`
  const months = Math.floor(days / 30)
  return `${months} ${plural(months, 'месяц', 'месяца', 'месяцев')} назад`
}

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

export function years(n: number): string {
  const r = Math.round(n)
  return `${r} ${plural(r, 'год', 'года', 'лет')}`
}

export const percent = (x: number) => `${Math.round(x * 100)}%`

/** Ability on the N(0,1) scale -> percentile of the candidate population. */
export function thetaPercentile(theta: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(theta))
  const d = 0.3989423 * Math.exp((-theta * theta) / 2)
  let p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
  if (theta > 0) p = 1 - p
  return Math.round(p * 100)
}

export function skillLevel(theta: number): { label: string; value: number } {
  const value = Math.max(0.05, Math.min(1, (theta + 2) / 4))
  if (theta >= 1.1) return { label: 'Высокий', value }
  if (theta >= 0.1) return { label: 'Уверенный', value }
  if (theta >= -0.9) return { label: 'Базовый', value }
  return { label: 'Начальный', value }
}

export const INVITATION_STATUS: Record<string, { label: string; tone: 'brand' | 'ok' | 'warn' | 'muted' | 'danger' }> = {
  sent: { label: 'Отправлено', tone: 'brand' },
  viewed: { label: 'Просмотрено', tone: 'warn' },
  accepted: { label: 'Принято', tone: 'ok' },
  declined: { label: 'Отклонено', tone: 'danger' },
  expired: { label: 'Истекло', tone: 'muted' },
  withdrawn: { label: 'Отозвано', tone: 'muted' },
}

export const APPLICATION_STATUS: Record<string, { label: string; tone: 'brand' | 'ok' | 'warn' | 'muted' | 'danger' }> = {
  sent: { label: 'Отправлен', tone: 'brand' },
  viewed: { label: 'Просмотрен', tone: 'warn' },
  invited: { label: 'Приглашение', tone: 'ok' },
  rejected: { label: 'Отказ', tone: 'danger' },
  withdrawn: { label: 'Отозван', tone: 'muted' },
}

export const DECLINE_REASONS: Record<string, string> = {
  salary: 'Не устраивает зарплата',
  stack: 'Не подходит стек или задачи',
  format: 'Не подходит формат работы или город',
  grade: 'Позиция не соответствует уровню',
  company: 'Не интересна компания или сфера',
  not_looking: 'Сейчас не ищу работу',
  other: 'Другое',
}
