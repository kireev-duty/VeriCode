import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BadgeCheck, EyeOff, Shuffle, Trophy, Wallet } from 'lucide-react'
import { Link } from 'react-router'
import { api } from '../../api/client'
import { Badge, Card, GradeBadge } from '../../components/ui'
import { DemoButtons } from './Auth'

interface Stats {
  candidates: number
  with_fsp: number
  companies: number
  vacancies: number
  invitations: number
  accepted: number
}

function InvitationMock() {
  return (
    <div className="relative">
      <div className="absolute -top-6 -left-6 hidden h-40 w-40 rounded-full bg-brand-200 blur-3xl md:block" />
      <Card className="relative space-y-4 p-6 shadow-xl shadow-brand-500/10">
        <div className="flex items-center justify-between">
          <div className="mono-label text-brand-500">Новое приглашение</div>
          <Badge tone="ok">Надёжный работодатель · 87</Badge>
        </div>
        <div>
          <div className="text-sm text-muted">Кодовая Гавань · Финтех</div>
          <div className="mt-1 text-xl font-semibold">Middle Python backend</div>
        </div>
        <div className="rounded-xl bg-brand-50 p-4">
          <div className="text-xs text-brand-700">Зарплата — видна до начала общения</div>
          <div className="mt-1 text-2xl font-semibold text-brand-700">240 000 – 300 000 ₽</div>
        </div>
        <div className="space-y-1.5 text-sm">
          <div className="text-muted">Почему вас выбрали:</div>
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="ok">Python подтверждён тестом</Badge>
            <Badge tone="ok">Грейд Middle</Badge>
            <Badge tone="brand">Призёр ФСП 2025</Badge>
          </div>
        </div>
        <div className="flex gap-2 pt-1">
          <div className="flex-1 rounded-xl bg-brand-500 py-2.5 text-center text-sm font-medium text-white">Принять</div>
          <div className="flex-1 rounded-xl border border-line py-2.5 text-center text-sm font-medium">Отклонить</div>
        </div>
      </Card>
      <Card className="relative mt-4 ml-10 flex items-center gap-3 p-4 shadow-lg md:-mt-6 md:ml-24">
        <GradeBadge grade="middle" title="Middle" spec="Backend" />
        <span className="text-sm text-muted">категория подтверждена адаптивным тестом</span>
      </Card>
    </div>
  )
}

const FEATURES = [
  { icon: Shuffle, title: 'Задания не утекают', text: 'Каждое задание — шаблон с параметрами. У каждого кандидата свой экземпляр, ответ вычисляется системой. Слитый ответ бесполезен.' },
  { icon: Wallet, title: 'Вилка до разговора', text: 'Зарплата обязательна в каждом приглашении. Работодатель заранее видит, попадает ли вилка в ваши ожидания, — без раскрытия суммы.' },
  { icon: EyeOff, title: 'Анонимно до согласия', text: 'Работодатель видит подтверждённые навыки, а не ФИО, возраст и фото. Контакты открываются, только когда вы приняли приглашение.' },
  { icon: Trophy, title: 'Достижения ФСП', text: 'Результаты соревнований подтягиваются из реестра по ФСП ID и поднимают вас внутри категории. Нет истории — нет штрафа.' },
]

export function Landing() {
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: () => api.get<Stats>('/api/public/stats') })
  return (
    <div>
      <section className="trace-bg border-b border-line">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 md:grid-cols-[1.1fr_0.9fr] md:py-24">
          <div>
            <div className="mono-label text-brand-500">ФСП Талант · подбор с обратной механикой</div>
            <h1 className="mt-4 text-4xl leading-tight font-semibold tracking-tight md:text-5xl">
              Работодатель сам приходит к вам — <span className="text-brand-500">с задачей и зарплатой</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg text-muted">
              Пройдите адаптивный тест один раз и получите подтверждённую категорию. Компании находят вас по результату и достижениям ФСП, а не по ключевым словам в резюме.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register?role=candidate" className="inline-flex h-12 items-center gap-2 rounded-xl bg-brand-500 px-6 font-medium text-white hover:bg-brand-600">
                Я ищу работу <ArrowRight className="size-4" />
              </Link>
              <Link to="/register?role=employer" className="inline-flex h-12 items-center gap-2 rounded-xl border border-line bg-white px-6 font-medium hover:border-brand-300">
                Я нанимаю
              </Link>
            </div>
            {stats && (
              <div className="mt-10 flex flex-wrap gap-8">
                {[
                  [stats.candidates, 'кандидатов с подтверждённым грейдом'],
                  [stats.with_fsp, 'с достижениями ФСП'],
                  [stats.companies, 'компаний'],
                ].map(([v, l]) => (
                  <div key={l as string}>
                    <div className="text-3xl font-semibold">{v}</div>
                    <div className="text-sm text-muted">{l}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <InvitationMock />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="grid gap-6 md:grid-cols-2">
          <Card className="p-7">
            <div className="mono-label text-brand-500">Кандидату</div>
            <ol className="mt-4 space-y-4">
              {[
                ['Опрос', 'Отрасль, специализация, стек и предполагаемый грейд — 3 минуты.'],
                ['Адаптивный тест', '10–18 заданий, сложность подстраивается под ответы. Грейд не понижается принудительно.'],
                ['Категория', 'Например, «Backend · Middle». Именно её видят работодатели.'],
                ['Приглашения', 'Компании пишут сами: позиция, задачи и вилка. Вы решаете, открывать ли контакты.'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-4">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-50 font-mono text-sm font-semibold text-brand-600">{i + 1}</span>
                  <div>
                    <div className="font-medium">{t}</div>
                    <div className="text-sm text-muted">{d}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
          <Card className="p-7">
            <div className="mono-label text-brand-500">Работодателю</div>
            <ol className="mt-4 space-y-4">
              {[
                ['Опишите потребность', 'Своими словами: стек, грейд, формат, вилка. Система сама разберёт текст.'],
                ['Получите подборку', 'Рекомендованные категории и кандидаты, ранжированные с объяснением.'],
                ['Уточняйте без потерь', 'Фильтры по стеку, ФСП, формату — подборка сохраняется, закреплённые остаются.'],
                ['Пригласите', 'Персональное предложение с зарплатой. Контакты откроются после согласия.'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-4">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-sm font-semibold text-white">{i + 1}</span>
                  <div>
                    <div className="font-medium">{t}</div>
                    <div className="text-sm text-muted">{d}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </section>

      <section className="border-y border-line bg-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-16 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.title}>
              <f.icon className="size-7 text-brand-500" />
              <div className="mt-3 font-semibold">{f.title}</div>
              <p className="mt-1 text-sm text-muted">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="grid items-center gap-8 rounded-3xl bg-ink p-8 text-white md:grid-cols-2 md:p-12">
          <div>
            <BadgeCheck className="size-8 text-brand-300" />
            <h2 className="mt-4 text-2xl font-semibold">Проверьте решение за 5 минут</h2>
            <p className="mt-2 text-white/70">
              Демо-аккаунты с готовыми данными: 500 кандидатов с грейдами, полученными прогоном адаптивного теста, 15 компаний, вакансии и история приглашений.
            </p>
            <Link to="/how" className="mt-4 inline-flex items-center gap-1 text-brand-200 hover:text-white">
              Как устроены тест и подбор <ArrowRight className="size-4" />
            </Link>
          </div>
          <div className="rounded-2xl bg-white p-5 text-ink">
            <div className="mono-label mb-3 text-brand-500">Войти как</div>
            <DemoButtons />
          </div>
        </div>
      </section>
    </div>
  )
}
