export type Role = 'candidate' | 'employer'
export type GradeId = 'intern' | 'junior' | 'middle' | 'senior'
export type WorkFormat = 'office' | 'hybrid' | 'remote'

export interface User {
  id: number
  email: string
  role: Role
  email_verified: boolean
  is_demo: boolean
  company_name: string | null
  onboarding_done: boolean | null
}

export interface Catalog {
  grades: { id: GradeId; title: string; order: number; theta_min: number; description: string }[]
  specializations: {
    id: string
    title: string
    short: string
    description: string
    core_skills: string[]
    stack_options: string[]
  }[]
  skills: { id: string; title: string; group: string }[]
  industries: string[]
  work_formats: Record<WorkFormat, string>
  team_roles: string[]
  soft_skills: string[]
  fsp: { disciplines: Record<string, string>; levels: Record<string, string>; results: Record<string, string> }
}

export interface Chip {
  kind: 'positive' | 'negative' | 'neutral'
  component: string
  text: string
  impact: number
}

export interface Match {
  score: number
  components: Record<string, number>
  weights: Record<string, number>
  chips: Chip[]
  salary_status: 'fits' | 'close' | 'above' | 'unknown'
}

export interface Achievement {
  event_name: string
  level: string
  discipline: string
  year: number
  result: string
  place: number | null
  participants: number | null
  team_role: string
  verified: boolean
}

export interface CandidateCard {
  id: number
  code: string
  headline: string
  specialization: string | null
  specialization_title: string | null
  grade: GradeId | null
  grade_title: string | null
  theta: number | null
  skill_theta: Record<string, number>
  grade_confirmed_at: string | null
  experience_years: number
  skills: { id: string; title: string; years: number | null; verified: boolean }[]
  work_formats: WorkFormat[]
  city: string
  relocation: boolean
  team_roles: string[]
  soft_skills: string[]
  has_fsp: boolean
  fsp_linked: boolean
  fsp_rank: string
  achievements: Achievement[]
  fsp_score: number
  open_to_offers: boolean
  match: Match | null
  strength: number | null
  pinned: boolean
  invitation_status: string | null
}

export interface CandidateDetail extends CandidateCard {
  experience: { position: string; company: string; from: string; to: string; summary: string }[]
  about: string
  last_task_at: string | null
  task_score: number
  test_history: { grade: string | null; reason: string; created_at: string }[]
  contacts_open: boolean
  contacts: { full_name: string; email: string; phone: string; telegram: string } | null
  invitations: { id: number; status: string; position_title: string; created_at: string }[]
}

export interface TrustInfo {
  score: number
  level: 'high' | 'medium' | 'low'
  signals: { text: string; ok: boolean; points: number }[]
}

export interface Need {
  id: number
  title: string
  raw_text: string
  team_description: string
  specialization: string
  specialization_title: string
  grade: GradeId
  grade_title: string
  must_skills: string[]
  nice_skills: string[]
  work_formats: WorkFormat[]
  city: string
  salary_from: number
  salary_to: number
  require_fsp: boolean
  pinned: number[]
  hidden: number[]
  created_at: string
  updated_at: string
}

export interface Shortlist {
  need_id: number
  total_in_categories: number
  after_filters: number
  categories: { specialization: string; grade: GradeId; grade_title: string; is_target: boolean; count: number; avg_score: number }[]
  candidates: CandidateCard[]
}

export interface Filters {
  grades: string[]
  skills: string[]
  verified_skills: string[]
  fsp_only: boolean
  work_formats: string[]
  city: string
  max_salary: number | null
  min_experience: number | null
  specializations: string[]
}

export const emptyFilters: Filters = {
  grades: [],
  skills: [],
  verified_skills: [],
  fsp_only: false,
  work_formats: [],
  city: '',
  max_salary: null,
  min_experience: null,
  specializations: [],
}

export interface Vacancy {
  id: number
  title: string
  description: string
  specialization: string
  specialization_title: string
  grade: GradeId
  grade_title: string
  must_skills: string[]
  nice_skills: string[]
  work_formats: WorkFormat[]
  city: string
  salary_from: number
  salary_to: number
  status: 'draft' | 'published' | 'closed'
  created_at: string
  company: { id: number; name: string; industry: string; logo_color: string; domain_verified: boolean }
  match?: Match | null
  application_status?: string | null
  company_trust?: TrustInfo
  applications?: number
  new_applications?: number
}

export interface AssessmentItem {
  id: number
  position: number
  skill: string
  skill_title: string
  family_title: string
  format: string
  time_limit_s: number
  shown_at: string
  prompt: string
  kind: 'single' | 'text' | 'number'
  code: string
  lang: string
  options: string[]
}

export interface SessionState {
  id: number
  status: 'active' | 'finished' | 'abandoned'
  specialization: string
  specialization_title: string
  target_grade: GradeId
  target_grade_title: string
  blueprint: { skill: string; title: string; weight: number }[]
  answered: number
  min_items: number
  max_items: number
  current_item: AssessmentItem | null
  created_at: string
  result?: {
    outcome: 'confirmed' | 'upgrade_available' | 'not_confirmed'
    grade: GradeId | null
    theta: number
    se: number
    p_target: number
    ci90: [number, number]
    measured_grade: GradeId
    suggested_grade: GradeId | null
    skill_theta: { skill: string; title: string; theta: number }[]
    flags: Record<string, number | string>
    finished_at: string
    correct: number
  }
  review?: (AssessmentItem & { response: string | number | null; is_correct: boolean; answer: unknown; explanation: string })[]
}

export interface Eligibility {
  grades: { grade: GradeId; title: string; allowed: boolean; reason: string; available_from: string | null }[]
  active_session_id: number | null
  suggested_grade: GradeId | null
  current_grade: GradeId | null
  cooldown_until: string | null
}

export interface Invitation {
  id: number
  status: 'sent' | 'viewed' | 'accepted' | 'declined' | 'expired' | 'withdrawn'
  position_title: string
  message: string
  salary_from: number
  salary_to: number
  work_format: string
  contact_method: string | null
  contact_method_hint: string | null
  below_expectation: boolean
  decline_reason: string | null
  company: {
    id: number
    name: string
    industry: string
    city: string
    website: string
    description: string
    size: string
    domain_verified: boolean
    logo_color: string
    trust?: TrustInfo
  }
  match_explanation: Chip[]
  created_at: string
  viewed_at: string | null
  responded_at: string | null
  expires_at: string
}

export interface EmployerInvitation {
  id: number
  status: Invitation['status']
  position_title: string
  message: string
  salary_from: number
  salary_to: number
  work_format: string
  contact_method: string
  decline_reason: string | null
  decline_reason_title: string | null
  decline_comment: string
  below_expectation: boolean
  match_score: number | null
  need_id: number | null
  vacancy_id: number | null
  created_at: string
  viewed_at: string | null
  responded_at: string | null
  expires_at: string
  candidate: {
    id: number
    code: string
    headline: string
    grade: GradeId | null
    grade_title: string | null
    specialization: string | null
    contacts: { full_name: string; email: string; phone: string; telegram: string } | null
  }
}

export interface CandidateProfile {
  id: number
  code: string
  verify_code: string
  full_name: string
  phone: string
  telegram: string
  contact_email: string
  birth_year: number | null
  headline: string
  about: string
  city: string
  work_formats: WorkFormat[]
  relocation: boolean
  salary_expectation: number | null
  experience_years: number
  skills: { id: string; years: number | null }[]
  team_roles: string[]
  soft_skills: string[]
  experience: { company: string; position: string; from: string; to: string; summary: string }[]
  education: unknown[]
  industries: string[]
  specialization: string | null
  specialization_title: string | null
  declared_grade: GradeId | null
  onboarding_done: boolean
  grade: GradeId | null
  grade_title: string | null
  theta: number | null
  theta_se: number | null
  skill_theta: Record<string, number>
  grade_confirmed_at: string | null
  grade_changed_at: string | null
  last_task_at: string | null
  task_score: number
  fsp_id: string | null
  fsp_linked_at: string | null
  fsp_profile: { rank?: string; rating?: number; region?: string; disciplines?: string[] }
  achievements: {
    id: number
    event_name: string
    event_level: string
    discipline: string
    date: string
    place: number | null
    participants: number | null
    team_name: string
    team_role: string
    result_type: string
    certificate_url: string
  }[]
  consent_processing_at: string | null
  consent_publication_at: string | null
  visible_to_employers: boolean
  open_to_offers: boolean
  min_salary_for_invites: number | null
  privacy: { show_city: boolean; show_fsp: boolean; show_companies: boolean }
  searchable: boolean
}

export interface TaskSub {
  id: number
  status: 'offered' | 'submitted' | 'skipped'
  score: number | null
  feedback: { point: string; hit: boolean }[]
  answer: string
  created_at: string
  task: { id: number; title: string; body: string; kind: string; options: string[]; skills: string[]; company: string }
}

export interface Notifications {
  unread: number
  items: { id: number; kind: string; title: string; link: string; read: boolean; created_at: string }[]
}
