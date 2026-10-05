import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Send } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import type { Vacancy } from '../../api/types'
import { Alert, Badge, Button, Card, Empty, Field, Modal, PageHeader, PageLoader, ScoreRing, Tabs, Textarea, Toggle, TrustBadge } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'
import { APPLICATION_STATUS, ago, salaryRange } from '../../lib/format'

interface MyApplication {
  id: number
  status: string
  cover_letter: string
  employer_comment: string
  created_at: string
  updated_at: string
  vacancy: Vacancy
}

function VacancyRow({ v, onApply }: { v: Vacancy; onApply: (v: Vacancy) => void }) {
  const { skillTitle } = useCatalog()
  const [open, setOpen] = useState(false)
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start gap-4">
        {v.match && <ScoreRing value={v.match.score} label="Соответствие вашему профилю" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{v.title}</h3>
            <Badge tone="brand">{v.specialization_title} · {v.grade_title}</Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-muted">
            {v.company.name} · {ago(v.created_at)}
            <TrustBadge trust={v.company_trust} />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {v.must_skills.map((s) => (
              <Badge key={s}>{skillTitle(s)}</Badge>
            ))}
            {v.nice_skills.map((s) => (
              <Badge key={s} className="opacity-70">+ {skillTitle(s)}</Badge>
            ))}
          </div>
        </div>
        <div className="text-right">
          <div className="font-semibold text-brand-600">{salaryRange(v.salary_from, v.salary_to)}</div>
          <div className="mt-2">
            {v.application_status ? (
              <Badge tone={APPLICATION_STATUS[v.application_status]?.tone}>Отклик: {APPLICATION_STATUS[v.application_status]?.label}</Badge>
            ) : (
              <Button size="sm" onClick={() => onApply(v)} icon={<Send className="size-3.5" />}>
                Откликнуться
              </Button>
            )}
          </div>
        </div>
      </div>
      {v.description && (
        <button className="mt-3 text-sm text-brand-600" onClick={() => setOpen(!open)}>
          {open ? 'Скрыть описание' : 'Описание'}
        </button>
      )}
      {open && <p className="mt-2 text-sm whitespace-pre-line text-muted">{v.description}</p>}
    </Card>
  )
}

export function CandidateVacancies() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'vacancies' | 'applications'>('vacancies')
  const [onlyMatching, setOnlyMatching] = useState(true)
  const [applyTo, setApplyTo] = useState<Vacancy | null>(null)
  const [cover, setCover] = useState('')
  const { data } = useQuery({
    queryKey: ['vacancies', onlyMatching],
    queryFn: () => api.get<Vacancy[]>(`/api/candidate/vacancies?only_matching=${onlyMatching}`),
  })
  const { data: apps } = useQuery({ queryKey: ['my-applications'], queryFn: () => api.get<MyApplication[]>('/api/candidate/applications') })
  const apply = useMutation({
    mutationFn: () => api.post(`/api/candidate/vacancies/${applyTo!.id}/apply`, { cover_letter: cover }),
    onSuccess: () => {
      setApplyTo(null)
      setCover('')
      qc.invalidateQueries({ queryKey: ['vacancies'] })
      qc.invalidateQueries({ queryKey: ['my-applications'] })
    },
  })
  const withdraw = useMutation({
    mutationFn: (id: number) => api.post(`/api/candidate/applications/${id}/withdraw`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-applications'] })
      qc.invalidateQueries({ queryKey: ['vacancies'] })
    },
  })
  return (
    <div>
      <PageHeader
        label="Своя инициатива"
        title="Вакансии и отклики"
        subtitle="Пока приглашений нет, можно откликнуться самостоятельно. При отклике работодатель увидит ваши контакты."
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'vacancies', title: 'Вакансии' },
            { id: 'applications', title: `Мои отклики (${apps?.length ?? 0})` },
          ]}
        />
        {tab === 'vacancies' && (
          <div className="w-72">
            <Toggle checked={onlyMatching} onChange={setOnlyMatching} label="Только моя специализация" hint="с сортировкой по соответствию" />
          </div>
        )}
      </div>
      {tab === 'vacancies' ? (
        !data ? (
          <PageLoader />
        ) : data.length === 0 ? (
          <Empty icon={<Briefcase className="size-8" />} title="Подходящих вакансий нет">Снимите фильтр, чтобы увидеть все вакансии.</Empty>
        ) : (
          <div className="space-y-3">
            {data.map((v) => (
              <VacancyRow key={v.id} v={v} onApply={setApplyTo} />
            ))}
          </div>
        )
      ) : !apps?.length ? (
        <Empty icon={<Send className="size-8" />} title="Откликов пока нет" />
      ) : (
        <div className="space-y-3">
          {apps.map((a) => (
            <Card key={a.id} className="flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <div className="font-semibold">{a.vacancy.title}</div>
                <div className="text-sm text-muted">
                  {a.vacancy.company.name} · {salaryRange(a.vacancy.salary_from, a.vacancy.salary_to)} · {ago(a.created_at)}
                </div>
                {a.employer_comment && <div className="mt-1 text-sm">Комментарий: {a.employer_comment}</div>}
              </div>
              <div className="flex items-center gap-3">
                <Badge tone={APPLICATION_STATUS[a.status]?.tone}>{APPLICATION_STATUS[a.status]?.label}</Badge>
                {(a.status === 'sent' || a.status === 'viewed') && (
                  <Button size="sm" variant="ghost" onClick={() => withdraw.mutate(a.id)}>
                    Отозвать
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal open={!!applyTo} onClose={() => setApplyTo(null)} title={`Отклик: ${applyTo?.title ?? ''}`}>
        <Alert tone="brand" className="mb-4">После отклика компания «{applyTo?.company.name}» увидит ваши контакты и результаты теста.</Alert>
        <Field label="Сопроводительное письмо (необязательно)">
          <Textarea rows={5} value={cover} onChange={(e) => setCover(e.target.value)} />
        </Field>
        {apply.error && <Alert tone="danger" className="mt-3">{(apply.error as Error).message}</Alert>}
        <Button className="mt-4 w-full" loading={apply.isPending} onClick={() => apply.mutate()}>
          Отправить отклик
        </Button>
      </Modal>
    </div>
  )
}
