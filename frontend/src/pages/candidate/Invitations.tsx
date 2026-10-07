import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Building2, Check, Flag, Mail, MessageCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Invitation } from '../../api/types'
import { Alert, Badge, Button, Card, Empty, Field, Modal, PageHeader, PageLoader, Select, Tabs, Textarea, TrustBadge } from '../../components/ui'
import { ago, date, DECLINE_REASONS, INVITATION_STATUS, salaryRange } from '../../lib/format'

function InvitationCard({ inv }: { inv: Invitation }) {
  const qc = useQueryClient()
  const [decline, setDecline] = useState(false)
  const [complain, setComplain] = useState(false)
  const [reason, setReason] = useState('salary')
  const [comment, setComment] = useState('')
  const [complaint, setComplaint] = useState('fake')
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['my-invitations'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const view = useMutation({ mutationFn: () => api.post(`/api/candidate/invitations/${inv.id}/view`), onSuccess: refresh })
  const accept = useMutation({ mutationFn: () => api.post(`/api/candidate/invitations/${inv.id}/accept`), onSuccess: refresh })
  const decl = useMutation({
    mutationFn: () => api.post(`/api/candidate/invitations/${inv.id}/decline`, { reason, comment }),
    onSuccess: () => {
      setDecline(false)
      refresh()
    },
  })
  const comp = useMutation({
    mutationFn: () => api.post(`/api/candidate/invitations/${inv.id}/complain`, { reason: complaint, comment }),
    onSuccess: () => setComplain(false),
  })
  useEffect(() => {
    if (inv.status === 'sent') view.mutate()
    // mark as viewed once when the card is rendered
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inv.id])
  const active = inv.status === 'sent' || inv.status === 'viewed'
  const st = INVITATION_STATUS[inv.status]
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: inv.company.logo_color }}>
          <Building2 className="size-6" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{inv.company.name}</span>
            <TrustBadge trust={inv.company.trust} />
          </div>
          <div className="text-sm text-muted">
            {[inv.company.industry, inv.company.city, inv.company.size && `${inv.company.size} сотрудников`].filter(Boolean).join(' · ')}
          </div>
        </div>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-[1fr_260px]">
        <div>
          <h3 className="text-xl font-semibold">{inv.position_title}</h3>
          <p className="mt-2 text-sm whitespace-pre-line">{inv.message}</p>
          {inv.match_explanation?.length > 0 && (
            <div className="mt-4">
              <div className="mb-1.5 text-xs text-muted">Почему компания выбрала вас</div>
              <div className="flex flex-wrap gap-1.5">
                {inv.match_explanation
                  .filter((c) => c.kind === 'positive')
                  .map((c) => (
                    <Badge key={c.text} tone="ok">{c.text}</Badge>
                  ))}
              </div>
            </div>
          )}
        </div>
        <div className="space-y-3">
          <div className="rounded-xl bg-brand-50 p-4">
            <div className="text-xs text-brand-700">Зарплата, ₽/мес до НДФЛ</div>
            <div className="mt-1 text-xl font-semibold text-brand-700">{salaryRange(inv.salary_from, inv.salary_to)}</div>
            {inv.work_format && <div className="mt-1 text-xs text-brand-700">формат: {({ remote: 'удалённо', hybrid: 'гибрид', office: 'офис' } as Record<string, string>)[inv.work_format]}</div>}
          </div>
          {inv.below_expectation && (
            <Alert tone="warn">
              <AlertTriangle className="mr-1 inline size-4" />
              Вилка ниже вашего минимального порога
            </Alert>
          )}
          <div className="text-xs text-muted">
            Получено {ago(inv.created_at)}
            {active && ` · действует до ${date(inv.expires_at)}`}
          </div>
        </div>
      </div>

      {inv.status === 'accepted' && (
        <Alert tone="ok" className="mt-5" title="Вы приняли приглашение — контакты открыты обеим сторонам">
          <MessageCircle className="mr-1 inline size-4" /> Связь с компанией: <b>{inv.contact_method}</b>
        </Alert>
      )}
      {inv.status === 'declined' && inv.decline_reason && <div className="mt-4 text-sm text-muted">Причина отказа: {DECLINE_REASONS[inv.decline_reason]}</div>}

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
        {active ? (
          <>
            <Button onClick={() => accept.mutate()} loading={accept.isPending} icon={<Check className="size-4" />}>
              Принять и открыть контакты
            </Button>
            <Button variant="secondary" onClick={() => setDecline(true)}>
              Отклонить
            </Button>
          </>
        ) : (
          <span className="text-sm text-muted">{inv.contact_method_hint ?? ''}</span>
        )}
        <button className="ml-auto flex items-center gap-1 text-xs text-muted hover:text-accent-600" onClick={() => setComplain(true)}>
          <Flag className="size-3.5" /> Пожаловаться
        </button>
      </div>
      {accept.error && <Alert tone="danger" className="mt-3">{(accept.error as Error).message}</Alert>}

      <Modal open={decline} onClose={() => setDecline(false)} title="Почему не подходит?">
        <p className="mb-4 text-sm text-muted">Причина поможет работодателю: следующие подборки этой компании будут точнее.</p>
        <div className="space-y-4">
          <Field label="Причина">
            <Select value={reason} onChange={(e) => setReason(e.target.value)}>
              {Object.entries(DECLINE_REASONS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </Select>
          </Field>
          <Field label="Комментарий (необязательно)">
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <Button className="w-full" variant="dark" loading={decl.isPending} onClick={() => decl.mutate()}>
            Отклонить приглашение
          </Button>
        </div>
      </Modal>
      <Modal open={complain} onClose={() => setComplain(false)} title="Жалоба на работодателя">
        <div className="space-y-4">
          <Field label="Что не так?">
            <Select value={complaint} onChange={(e) => setComplaint(e.target.value)}>
              <option value="fake">Похоже на фиктивную вакансию</option>
              <option value="salary_mismatch">Условия не соответствуют приглашению</option>
              <option value="spam">Спам, массовая рассылка</option>
              <option value="rude">Некорректное общение</option>
              <option value="other">Другое</option>
            </Select>
          </Field>
          <Field label="Подробности">
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          {comp.isSuccess && <Alert tone="ok">Жалоба отправлена — она снижает траст-скор компании.</Alert>}
          <Button className="w-full" variant="danger" loading={comp.isPending} onClick={() => comp.mutate()}>
            Отправить жалобу
          </Button>
        </div>
      </Modal>
    </Card>
  )
}

export function CandidateInvitations() {
  const [tab, setTab] = useState<'active' | 'all'>('active')
  const { data } = useQuery({ queryKey: ['my-invitations'], queryFn: () => api.get<Invitation[]>('/api/candidate/invitations') })
  if (!data) return <PageLoader />
  const list = tab === 'active' ? data.filter((i) => i.status === 'sent' || i.status === 'viewed') : data
  return (
    <div>
      <PageHeader
        label="Обратная механика"
        title="Приглашения"
        subtitle="Работодатели сами выходят на вас с позицией и вилкой. Контакты открываются, только когда вы примете приглашение."
      />
      <div className="mb-4">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'active', title: `Ждут ответа (${data.filter((i) => i.status === 'sent' || i.status === 'viewed').length})` },
            { id: 'all', title: `Все (${data.length})` },
          ]}
        />
      </div>
      {list.length === 0 ? (
        <Empty icon={<Mail className="size-8" />} title="Нет приглашений">
          Работодатели ищут кандидатов по категориям. Подтвердите грейд, привяжите ФСП ID и решайте задания недели — так вы выше в подборках.
        </Empty>
      ) : (
        <div className="space-y-4">
          {list.map((i) => (
            <InvitationCard key={i.id} inv={i} />
          ))}
        </div>
      )}
    </div>
  )
}
