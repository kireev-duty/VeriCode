import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileUp, Plus, Trash2, Wand2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, downloadFile } from '../../api/client'
import type { CandidateProfile, WorkFormat } from '../../api/types'
import { Alert, Badge, Button, Card, Checkbox, Field, Input, Modal, MultiChips, PageHeader, PageLoader, SectionTitle, Textarea } from '../../components/ui'
import { useCatalog } from '../../lib/catalog'

interface Parsed {
  full_name: string
  contact_email: string
  phone: string
  telegram: string
  city: string
  experience_years: number
  skills: { id: string; title: string }[]
  headline: string
  positions: string[]
  team_roles: string[]
  soft_skills: string[]
  specialization: string | null
  declared_grade_hint: string
  work_formats: WorkFormat[]
  source: 'rules' | 'rules+llm'
}

type Form = Omit<CandidateProfile, 'achievements'>

export function CandidateProfilePage() {
  const qc = useQueryClient()
  const { catalog, skillTitle, specTitle, gradeTitle } = useCatalog()
  const { data } = useQuery({ queryKey: ['profile'], queryFn: () => api.get<CandidateProfile>('/api/candidate/profile') })
  const [form, setForm] = useState<Form | null>(null)
  const [parsed, setParsed] = useState<Parsed | null>(null)
  const [apply, setApply] = useState<Record<string, boolean>>({})
  const [skillToAdd, setSkillToAdd] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (data && !form) setForm(data)
  }, [data, form])

  const save = useMutation({
    mutationFn: (f: Form) =>
      api.put<CandidateProfile>('/api/candidate/profile', {
        full_name: f.full_name,
        phone: f.phone,
        telegram: f.telegram,
        contact_email: f.contact_email,
        headline: f.headline,
        about: f.about,
        city: f.city,
        work_formats: f.work_formats,
        relocation: f.relocation,
        salary_expectation: f.salary_expectation,
        experience_years: f.experience_years,
        skills: f.skills,
        team_roles: f.team_roles,
        soft_skills: f.soft_skills,
        experience: f.experience,
      }),
    onSuccess: (p) => {
      qc.setQueryData(['profile'], p)
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const upload = useMutation({
    mutationFn: (file: File) => api.upload<Parsed>('/api/candidate/resume', file),
    onSuccess: (p) => {
      setParsed(p)
      setApply({ name: !!p.full_name, contacts: true, headline: !!p.headline, city: !!p.city, years: p.experience_years > 0, skills: true, roles: true })
    },
  })

  if (!form || !catalog) return <PageLoader />
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v })

  const applyParsed = () => {
    if (!parsed) return
    const f = { ...form }
    if (apply.name && parsed.full_name) f.full_name = parsed.full_name
    if (apply.contacts) {
      f.contact_email = parsed.contact_email || f.contact_email
      f.phone = parsed.phone || f.phone
      f.telegram = parsed.telegram || f.telegram
    }
    if (apply.headline && parsed.headline) f.headline = parsed.headline
    if (apply.city && parsed.city) f.city = parsed.city
    if (apply.years) f.experience_years = parsed.experience_years
    if (apply.skills) {
      const have = new Set(f.skills.map((s) => s.id))
      f.skills = [...f.skills, ...parsed.skills.filter((s) => !have.has(s.id)).map((s) => ({ id: s.id, years: null }))]
    }
    if (apply.roles) {
      f.team_roles = Array.from(new Set([...f.team_roles, ...parsed.team_roles]))
      f.soft_skills = Array.from(new Set([...f.soft_skills, ...parsed.soft_skills]))
    }
    setForm(f)
    setParsed(null)
  }

  return (
    <div>
      <PageHeader
        label={`Профиль · ${form.code}`}
        title="Профиль и резюме"
        subtitle="Профиль дополняет категорию: работодатель видит стек, опыт и роли, но категорию определяет только тест."
        action={
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])}
            />
            <Button variant="secondary" icon={<FileUp className="size-4" />} loading={upload.isPending} onClick={() => fileRef.current?.click()}>
              Загрузить PDF-резюме
            </Button>
            <Button variant="secondary" icon={<Download className="size-4" />} onClick={() => downloadFile('/api/candidate/profile.pdf', `profile-${form.code}.pdf`)}>
              PDF-профиль
            </Button>
          </div>
        }
      />
      {upload.error && <Alert tone="danger" className="mb-4">{(upload.error as Error).message}</Alert>}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px] [&>*]:min-w-0">
        <div className="space-y-6">
          <Card className="p-6">
            <SectionTitle label="Скрыто до согласия" title="Личные данные и контакты" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="ФИО"><Input value={form.full_name} onChange={(e) => set('full_name', e.target.value)} /></Field>
              <Field label="Email для связи"><Input type="email" value={form.contact_email} onChange={(e) => set('contact_email', e.target.value)} /></Field>
              <Field label="Телефон"><Input value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
              <Field label="Telegram"><Input value={form.telegram} onChange={(e) => set('telegram', e.target.value)} /></Field>
            </div>
          </Card>
          <Card className="p-6">
            <SectionTitle label="Видно работодателям" title="Профессиональный профиль" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Заголовок" className="sm:col-span-2"><Input value={form.headline} placeholder="Например, Python backend-разработчик" onChange={(e) => set('headline', e.target.value)} /></Field>
              <Field label="О себе" className="sm:col-span-2"><Textarea rows={4} value={form.about} onChange={(e) => set('about', e.target.value)} /></Field>
              <Field label="Город"><Input value={form.city} onChange={(e) => set('city', e.target.value)} /></Field>
              <Field label="Коммерческий опыт, лет"><Input type="number" step={0.5} min={0} value={form.experience_years} onChange={(e) => set('experience_years', Number(e.target.value))} /></Field>
              <Field label="Ожидания по зарплате, ₽/мес до НДФЛ" hint="Работодатель не видит сумму — только попадает ли его вилка в ожидания">
                <Input type="number" step={1000} min={0} value={form.salary_expectation ?? ''} onChange={(e) => set('salary_expectation', e.target.value ? Number(e.target.value) : null)} />
              </Field>
              <Field label="Формат работы">
                <MultiChips
                  size="sm"
                  options={(Object.entries(catalog.work_formats) as [WorkFormat, string][]).map(([id, title]) => ({ id, title }))}
                  value={form.work_formats}
                  onChange={(v) => set('work_formats', v)}
                />
                <div className="mt-2">
                  <Checkbox checked={form.relocation} onChange={(v) => set('relocation', v)} label="Готов к релокации" />
                </div>
              </Field>
            </div>
          </Card>
          <Card className="p-6">
            <SectionTitle title="Стек" />
            <div className="flex flex-wrap gap-2">
              {form.skills.map((s, i) => (
                <span key={s.id} className="inline-flex items-center gap-2 rounded-full border border-line bg-white py-1 pr-1 pl-3 text-sm">
                  {skillTitle(s.id)}
                  {form.skill_theta[s.id] !== undefined && <Badge tone="ok">тест</Badge>}
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    placeholder="лет"
                    className="w-12 rounded-full bg-surface px-2 py-0.5 text-xs outline-none"
                    value={s.years ?? ''}
                    onChange={(e) => {
                      const skills = [...form.skills]
                      skills[i] = { ...s, years: e.target.value ? Number(e.target.value) : null }
                      set('skills', skills)
                    }}
                  />
                  <button className="rounded-full p-1 text-muted hover:bg-surface hover:text-accent-500" onClick={() => set('skills', form.skills.filter((x) => x.id !== s.id))}>
                    <Trash2 className="size-3.5" />
                  </button>
                </span>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <select className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-white px-3 text-sm" value={skillToAdd} onChange={(e) => setSkillToAdd(e.target.value)}>
                <option value="">Добавить навык…</option>
                {catalog.skills
                  .filter((s) => !form.skills.some((x) => x.id === s.id))
                  .map((s) => (
                    <option key={s.id} value={s.id}>{s.title}</option>
                  ))}
              </select>
              <Button
                variant="secondary"
                disabled={!skillToAdd}
                icon={<Plus className="size-4" />}
                onClick={() => {
                  set('skills', [...form.skills, { id: skillToAdd, years: null }])
                  setSkillToAdd('')
                }}
              >
                Добавить
              </Button>
            </div>
          </Card>
          <Card className="p-6">
            <SectionTitle
              title="Опыт работы"
              action={
                <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => set('experience', [...form.experience, { company: '', position: '', from: '', to: '', summary: '' }])}>
                  Добавить
                </Button>
              }
            />
            <div className="space-y-4">
              {form.experience.map((e, i) => {
                const upd = (k: keyof typeof e, v: string) => {
                  const exp = [...form.experience]
                  exp[i] = { ...e, [k]: v }
                  set('experience', exp)
                }
                return (
                  <div key={i} className="grid gap-3 rounded-xl border border-line p-4 sm:grid-cols-2">
                    <Field label="Должность"><Input value={e.position} onChange={(x) => upd('position', x.target.value)} /></Field>
                    <Field label="Компания" hint="Название скрыто от работодателей, если не разрешено в настройках"><Input value={e.company} onChange={(x) => upd('company', x.target.value)} /></Field>
                    <Field label="С (год)"><Input value={e.from} onChange={(x) => upd('from', x.target.value)} /></Field>
                    <Field label="По (пусто — по н. в.)"><Input value={e.to} onChange={(x) => upd('to', x.target.value)} /></Field>
                    <Field label="Чем занимались" className="sm:col-span-2"><Textarea rows={2} value={e.summary} onChange={(x) => upd('summary', x.target.value)} /></Field>
                    <button className="text-left text-xs text-accent-600" onClick={() => set('experience', form.experience.filter((_, j) => j !== i))}>Удалить</button>
                  </div>
                )
              })}
              {!form.experience.length && <div className="text-sm text-muted">Добавьте места работы или загрузите резюме.</div>}
            </div>
          </Card>
          <Card className="p-6">
            <SectionTitle title="Роли в команде и soft skills" />
            <Field label="Роли"><MultiChips size="sm" options={catalog.team_roles.map((r) => ({ id: r, title: r }))} value={form.team_roles} onChange={(v) => set('team_roles', v)} /></Field>
            <Field label="Soft skills" className="mt-4"><MultiChips size="sm" options={catalog.soft_skills.map((r) => ({ id: r, title: r }))} value={form.soft_skills} onChange={(v) => set('soft_skills', v)} /></Field>
          </Card>
        </div>
        <div>
          <Card className="sticky top-24 p-6">
            <div className="text-sm text-muted">Категория</div>
            <div className="font-semibold">{form.grade ? `${specTitle(form.specialization)} · ${gradeTitle(form.grade)}` : 'не подтверждена'}</div>
            <p className="mt-3 text-xs text-muted">Специализация и грейд меняются только через тест. Изменения профиля сразу видны в подборках.</p>
            {save.isSuccess && <Alert tone="ok" className="mt-3">Сохранено</Alert>}
            {save.error && <Alert tone="danger" className="mt-3">{(save.error as Error).message}</Alert>}
            <Button className="mt-4 w-full" loading={save.isPending} onClick={() => save.mutate(form)}>
              Сохранить профиль
            </Button>
          </Card>
        </div>
      </div>

      <Modal open={!!parsed} onClose={() => setParsed(null)} title="Распознано из резюме" wide>
        {parsed && (
          <div className="space-y-4">
            <Alert tone="brand">
              <Wand2 className="mr-1 inline size-4" /> Проверьте поля — в профиль попадёт только то, что вы отметите.{' '}
              {parsed.source === 'rules+llm' ? 'Распознано правилами и уточнено языковой моделью.' : 'Распознано правилами и словарём навыков.'}
            </Alert>
            {[
              ['name', 'ФИО', parsed.full_name],
              ['contacts', 'Контакты', [parsed.contact_email, parsed.phone, parsed.telegram].filter(Boolean).join(' · ')],
              ['headline', 'Должность', parsed.headline],
              ['city', 'Город', parsed.city],
              ['years', 'Опыт', parsed.experience_years ? `${parsed.experience_years} лет` : ''],
              ['skills', 'Стек', parsed.skills.map((s) => s.title).join(', ')],
              ['roles', 'Роли и soft skills', [...parsed.team_roles, ...parsed.soft_skills].join(', ')],
            ]
              .filter(([, , v]) => v)
              .map(([k, label, v]) => (
                <div key={k} className="flex items-start gap-3 rounded-xl border border-line p-3">
                  <input type="checkbox" className="mt-1 accent-brand-500" checked={!!apply[k]} onChange={(e) => setApply({ ...apply, [k]: e.target.checked })} />
                  <div>
                    <div className="text-xs text-muted">{label}</div>
                    <div className="text-sm">{v}</div>
                  </div>
                </div>
              ))}
            {parsed.specialization && (
              <div className="text-sm text-muted">
                Похоже на специализацию «{specTitle(parsed.specialization)}», уровень около {gradeTitle(parsed.declared_grade_hint)} — подтвердить уровень можно тестом.
              </div>
            )}
            <Button className="w-full" onClick={applyParsed}>Применить отмеченное</Button>
          </div>
        )}
      </Modal>
    </div>
  )
}
