import { useMutation, useQuery } from '@tanstack/react-query'
import { Fingerprint, Gauge, Layers, RefreshCw, Shield, Shuffle, Timer, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import { CodeBlock } from '../../components/CodeBlock'
import { Badge, Button, Card, ChipToggle, ProgressBar, RichText, SectionTitle, Textarea } from '../../components/ui'

const SAMPLES = [
  {
    title: 'Python backend',
    text: 'Ищем Middle Python-разработчика в команду платёжного шлюза: FastAPI, PostgreSQL, асинхронность, REST API. Будет плюсом Kafka и Docker. Удалённо, 220–300 тыс. ₽.',
  },
  {
    title: 'React frontend',
    text: 'Senior Frontend-разработчик: React, TypeScript, HTML/CSS, производительность интерфейсов. Желательно опыт с дизайн-системами. Гибрид, Москва.',
  },
  {
    title: 'DevOps',
    text: 'DevOps-инженер: Linux, Docker, Kubernetes, CI/CD (GitLab CI), мониторинг Prometheus/Grafana. Будет плюсом Terraform. Офис или гибрид.',
  },
  {
    title: 'Data Scientist',
    text: 'Data Scientist в антифрод: Python, машинное обучение, статистика и A/B-тесты, SQL. Будет плюсом опыт с pandas.',
  },
]

interface Preview {
  vacancy_title: string | null
  specialization: string
  detected_skills: string[]
  blueprint: { skill: string; title: string; weight: number; families: number }[]
  samples: { skill: string; skill_title: string; family: string; tier: number; difficulty_b: number; prompt: string; kind: string; code: string; lang: string; options: string[] }[]
}

interface Bank {
  families: number
  items: { key: string; family: string; skill: string; tier: number; a: number; b: number; exposures: number; responses: number; p_correct: number | null; status: string }[]
}

const WEIGHTS = [
  ['Стек', 0.3, 'Покрытие обязательных и желательных навыков. Навык, подтверждённый тестом, весит больше заявленного; близкие технологии (Django ≈ FastAPI) дают частичный зачёт.'],
  ['Грейд', 0.2, 'Совпадение категории с запрошенным грейдом; соседние грейды — с понижающим коэффициентом.'],
  ['Результат теста', 0.15, 'Насколько уверенно способности кандидата на нужных навыках превышают порог грейда.'],
  ['Достижения ФСП', 0.1, 'Уровень соревнования × результат × давность × релевантность дисциплины. Без истории ФСП — ноль, а не штраф.'],
  ['Зарплата', 0.1, 'Ожидания кандидата относительно вилки работодателя.'],
  ['Формат и город', 0.07, 'Офис / гибрид / удалёнка и готовность к релокации.'],
  ['Актуальность', 0.05, 'Свежесть теста и регулярных заданий.'],
  ['Описание', 0.03, 'Семантическая близость текста потребности и профиля (символьные n-граммы).'],
] as const

export function How() {
  const [text, setText] = useState(SAMPLES[0].text)
  const preview = useMutation({ mutationFn: () => api.post<Preview>('/api/assessment/blueprint-preview', { text, samples: 4 }) })
  const { data: bank } = useQuery({ queryKey: ['bank'], queryFn: () => api.get<Bank>('/api/assessment/bank') })
  const skills = bank ? new Set(bank.items.map((i) => i.skill)).size : 0
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <div className="mono-label text-brand-500">Механики решения</div>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">Как работают тестирование и подбор</h1>
      <p className="mt-3 max-w-3xl text-lg text-muted">
        Категория кандидата определяется не резюме, а опросом и адаптивным тестом. Задания устойчивы к утечкам, сложность сопоставима между кандидатами, а результат не зависит от заявленного грейда.
      </p>

      <section className="mt-12">
        <SectionTitle label="01 · Тестирование" title="Параметрические семейства заданий + адаптивный тест (IRT/CAT)" />
        <div className="grid gap-4 md:grid-cols-3">
          {[
            [Shuffle, 'Семейство, а не задание', 'Задание — это шаблон: структура фиксирована, а данные, имена, константы и ветки генерируются из случайного зерна. Правильный ответ вычисляется исполнением кода, SQL-движком или точной моделью семантики, а не пишется вручную или LLM.'],
            [Gauge, 'Сопоставимая сложность', 'Каждое семейство разбито на уровни сложности; у уровня есть параметры IRT: сложность b и дискриминативность a. Структура одна — значит, у разных экземпляров одинаковая сложность.'],
            [Layers, 'Адаптивность', 'Следующее задание выбирается по максимуму информации Фишера в текущей оценке способностей с балансом навыков по blueprint. Тест заканчивается, когда грейд определён уверенно: обычно за 10–18 заданий.'],
            [Fingerprint, 'Честная оценка', 'Заявленный грейд влияет только на стартовую точку, а оценка способностей строится с общим априорным распределением N(0,1). Завысить себе результат, заявив Senior, нельзя.'],
            [Shield, 'Детектор утечек', 'CUSUM по остаткам «наблюдаемая − ожидаемая доля верных ответов»: если на семейство вдруг отвечают лучше, чем предсказывают способности, оно уходит из ротации на проверку.'],
            [Timer, 'Сигналы, а не баны', 'Лимит времени на задание, вставка из буфера и уход со вкладки фиксируются в отчёте как сигналы целостности, но не штрафуют автоматически.'],
          ].map(([Icon, t, d]) => {
            const I = Icon as typeof Shuffle
            return (
              <Card key={t as string}>
                <I className="size-6 text-brand-500" />
                <div className="mt-3 font-semibold">{t as string}</div>
                <p className="mt-1 text-sm text-muted">{d as string}</p>
              </Card>
            )
          })}
        </div>

        <Card className="mt-6 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="mono-label text-brand-500">Живая демонстрация</div>
              <div className="mt-1 text-lg font-semibold">Вакансия → blueprint → задания для кандидата</div>
            </div>
            <div className="flex flex-wrap gap-2">
              {SAMPLES.map((s) => (
                <ChipToggle key={s.title} size="sm" active={text === s.text} onClick={() => setText(s.text)}>
                  {s.title}
                </ChipToggle>
              ))}
            </div>
          </div>
          <Textarea className="mt-4" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button icon={<Wand2 className="size-4" />} onClick={() => preview.mutate()} loading={preview.isPending}>
              Сформировать тест
            </Button>
            {preview.data && (
              <Button variant="secondary" icon={<RefreshCw className="size-4" />} onClick={() => preview.mutate()}>
                Сгенерировать другие экземпляры
              </Button>
            )}
          </div>
          {preview.data && (
            <div className="mt-6 grid gap-6 lg:grid-cols-[280px_1fr]">
              <div>
                <div className="text-sm font-medium">Blueprint теста</div>
                <p className="mt-1 text-xs text-muted">70% — навыки вакансии, 30% — ядро специализации. Доли определяют, сколько заданий придётся на каждый навык.</p>
                <div className="mt-3 space-y-3">
                  {preview.data.blueprint.map((b) => (
                    <div key={b.skill}>
                      <div className="flex justify-between text-sm">
                        <span>{b.title}</span>
                        <span className="font-mono text-muted">{Math.round(b.weight * 100)}%</span>
                      </div>
                      <ProgressBar value={b.weight / Math.max(...preview.data!.blueprint.map((x) => x.weight))} className="mt-1" />
                      <div className="mt-0.5 text-[11px] text-muted">{b.families} семейств заданий</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                {preview.data.samples.map((s, i) => (
                  <div key={i} className="animate-fade-in rounded-xl border border-line p-4">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge tone="brand">{s.skill_title}</Badge>
                      <Badge>{s.family}</Badge>
                      <Badge>уровень {s.tier} · b = {s.difficulty_b.toFixed(1)}</Badge>
                    </div>
                    <RichText text={s.prompt} className="text-sm" />
                    {s.code && (
                      <div className="mt-2">
                        <CodeBlock code={s.code} lang={s.lang} />
                      </div>
                    )}
                    {s.options.length > 0 && (
                      <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                        {s.options.map((o) => (
                          <div key={o} className="rounded-lg border border-line px-3 py-1.5 text-sm">{o}</div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
        {bank && (
          <p className="mt-3 text-sm text-muted">
            Банк: {bank.families} семейств, {bank.items.length} калиброванных позиций (семейство × уровень), {skills} навыков. Каждая позиция порождает практически неограниченное число уникальных экземпляров.
          </p>
        )}
      </section>

      <section className="mt-16">
        <SectionTitle label="02 · Грейд" title="Правила присвоения и смены грейда" />
        <div className="grid gap-4 md:grid-cols-4">
          {[
            ['Подтверждён', 'P(θ ≥ порог заявленного грейда) ≥ 70% — категория присвоена.'],
            ['С запасом', 'Если уверенно выше и следующего порога — сразу доступен тест на грейд выше (7 дней).'],
            ['Не подтверждён', 'Грейд не понижается принудительно: сразу можно пройти тест на уровень ниже.'],
            ['Частота', 'Смена грейда — не чаще раза в 90 дней; повтор того же грейда — через 30 дней.'],
          ].map(([t, d]) => (
            <Card key={t}>
              <div className="font-semibold">{t}</div>
              <p className="mt-1 text-sm text-muted">{d}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <SectionTitle label="03 · Подбор" title="Объяснимый скоринг и честный выход на контакт" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="p-6">
            <div className="font-semibold">Из чего складывается соответствие</div>
            <p className="mt-1 text-sm text-muted">Сумма вкладов с весами из одного конфига. Каждая карточка в подборке показывает вклады — работодатель видит, почему кандидат в топе.</p>
            <div className="mt-4 space-y-3">
              {WEIGHTS.map(([t, w, d]) => (
                <div key={t}>
                  <div className="flex justify-between text-sm font-medium">
                    <span>{t}</span>
                    <span className="font-mono text-brand-600">{Math.round(w * 100)}%</span>
                  </div>
                  <ProgressBar value={w / 0.3} className="mt-1" />
                  <div className="mt-1 text-xs text-muted">{d}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card className="p-6">
            <div className="font-semibold">Сценарий контакта</div>
            <ol className="mt-4 space-y-4 text-sm">
              {[
                ['Потребность', 'Работодатель описывает задачу текстом — NLP извлекает специализацию, грейд, стек (обязательный и «будет плюсом»), формат и вилку.'],
                ['Категории и подборка', 'Показываются целевая и соседние категории; внутри — кандидаты по силе подтверждённого профиля и соответствию.'],
                ['Анонимная витрина', 'Видны навыки, подтверждённые тестом, результаты ФСП и опыт без названий компаний. ФИО, возраст и контакты скрыты.'],
                ['Проверка вилки', 'Перед отправкой: «вилка попадает в ожидания / немного ниже / заметно ниже» — без раскрытия суммы кандидата.'],
                ['Приглашение', 'Позиция, описание, вилка от–до, способ связи; квота 20 приглашений в неделю против спама. Можно приложить задание-челлендж.'],
                ['Ответ кандидата', 'Принятие открывает контакты. Отказ — с причиной: работодатель получает обратную связь, а веса его ранжирования адаптируются.'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-50 font-mono text-xs font-semibold text-brand-600">{i + 1}</span>
                  <div>
                    <div className="font-medium">{t}</div>
                    <div className="text-muted">{d}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </section>
    </div>
  )
}
