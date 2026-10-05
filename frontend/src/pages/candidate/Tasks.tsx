import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Circle, Zap } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import type { TaskSub } from '../../api/types'
import { Alert, Badge, Button, Card, Empty, PageHeader, PageLoader, ProgressBar, Textarea } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { date } from '../../lib/format'

function Feedback({ sub }: { sub: TaskSub }) {
  return (
    <div className="mt-4 rounded-xl bg-surface p-4">
      <div className="flex items-center justify-between text-sm font-medium">
        <span>Оценка по рубрике</span>
        <span className="font-mono">{Math.round((sub.score ?? 0) * 100)}%</span>
      </div>
      <ProgressBar value={sub.score ?? 0} tone={(sub.score ?? 0) >= 0.6 ? 'ok' : 'warn'} className="mt-2" />
      <ul className="mt-3 space-y-1.5 text-sm">
        {sub.feedback.map((f) => (
          <li key={f.point} className="flex gap-2">
            {f.hit ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted" />}
            <span className={f.hit ? '' : 'text-muted'}>{f.point}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function TaskCard({ sub }: { sub: TaskSub }) {
  const qc = useQueryClient()
  const { skillTitle } = useCatalog()
  const [answer, setAnswer] = useState('')
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['tasks'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const submit = useMutation({ mutationFn: () => api.post(`/api/candidate/tasks/${sub.id}/submit`, { answer }), onSuccess: refresh })
  const skip = useMutation({ mutationFn: () => api.post(`/api/candidate/tasks/${sub.id}/skip`), onSuccess: refresh })
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">от {sub.task.company}</Badge>
        {sub.task.skills.map((s) => (
          <Badge key={s}>{skillTitle(s)}</Badge>
        ))}
        <span className="ml-auto text-xs text-muted">{date(sub.created_at)}</span>
      </div>
      <h3 className="mt-3 text-lg font-semibold">{sub.task.title}</h3>
      <p className="mt-2 text-sm whitespace-pre-line">{sub.task.body}</p>
      {sub.status === 'offered' ? (
        <>
          <Textarea
            className="mt-4"
            rows={7}
            placeholder="Опишите подход: шаги, инструменты, компромиссы. Код не обязателен."
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
          <div className="mt-1 text-xs text-muted">{answer.length} символов · рекомендуем от 300</div>
          {submit.error && <Alert tone="danger" className="mt-3">{(submit.error as Error).message}</Alert>}
          <div className="mt-4 flex gap-2">
            <Button loading={submit.isPending} disabled={answer.trim().length < 20} onClick={() => submit.mutate()}>
              Отправить решение
            </Button>
            <Button variant="ghost" loading={skip.isPending} onClick={() => skip.mutate()}>
              Пропустить
            </Button>
          </div>
        </>
      ) : sub.status === 'submitted' ? (
        <>
          <div className="mt-4 rounded-xl border border-line p-4 text-sm whitespace-pre-line">{sub.answer}</div>
          <Feedback sub={sub} />
        </>
      ) : (
        <div className="mt-3 text-sm text-muted">Пропущено</div>
      )}
    </Card>
  )
}

export function CandidateTasks() {
  const { data } = useQuery({ queryKey: ['tasks'], queryFn: () => api.get<TaskSub[]>('/api/candidate/tasks') })
  if (!data) return <PageLoader />
  return (
    <div>
      <PageHeader
        label="Регулярные задания"
        title="Задание недели"
        subtitle="Раз в неделю — короткая задача от работодателя вашей категории: решить или предложить подход. Решения обновляют профиль и дают работодателям свежий сигнал."
      />
      {data.length === 0 ? (
        <Empty icon={<Zap className="size-8" />} title="Заданий пока нет">Они появляются после подтверждения грейда.</Empty>
      ) : (
        <div className="space-y-4">
          {data.map((s) => (
            <TaskCard key={s.id} sub={s} />
          ))}
        </div>
      )}
    </div>
  )
}
