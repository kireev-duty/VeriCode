import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import type { Role } from './api/types'
import { AppShell, PublicShell } from './components/Layout'
import { PageLoader } from './components/ui'
import { useAuth } from './lib/auth'
import { CandidateDashboard } from './pages/candidate/Dashboard'
import { CandidateInvitations } from './pages/candidate/Invitations'
import { Onboarding } from './pages/candidate/Onboarding'
import { CandidateProfilePage } from './pages/candidate/Profile'
import { CandidateSettings } from './pages/candidate/Settings'
import { CandidateTasks } from './pages/candidate/Tasks'
import { TestHome, TestSession } from './pages/candidate/Test'
import { CandidateVacancies } from './pages/candidate/Vacancies'
import { EmployerCandidate, EmployerInvitations, EmployerSearch } from './pages/employer/Candidates'
import { EmployerCompany, EmployerTasks, EmployerVacancies, VacancyApplications } from './pages/employer/Manage'
import { EmployerHome, NeedEditor, ShortlistPage } from './pages/employer/Matching'
import { Login, Register, VerifyEmail } from './pages/public/Auth'
import { How } from './pages/public/How'
import { Landing } from './pages/public/Landing'
import { FspCallback, FspMockLogin, VerifyProfile } from './pages/public/Misc'

function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <PageLoader />
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  if (user.role !== role) return <Navigate to={user.role === 'employer' ? '/e' : '/c'} replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicShell />}>
        <Route index element={<Landing />} />
        <Route path="how" element={<How />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="verify-email" element={<VerifyEmail />} />
        <Route path="verify/:code" element={<VerifyProfile />} />
      </Route>
      <Route path="fsp/mock-login" element={<FspMockLogin />} />
      <Route
        path="fsp/callback"
        element={
          <RequireRole role="candidate">
            <FspCallback />
          </RequireRole>
        }
      />
      <Route
        path="c"
        element={
          <RequireRole role="candidate">
            <AppShell />
          </RequireRole>
        }
      >
        <Route index element={<CandidateDashboard />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="test" element={<TestHome />} />
        <Route path="test/:id" element={<TestSession />} />
        <Route path="invitations" element={<CandidateInvitations />} />
        <Route path="invitations/:id" element={<CandidateInvitations />} />
        <Route path="vacancies" element={<CandidateVacancies />} />
        <Route path="applications" element={<CandidateVacancies />} />
        <Route path="tasks" element={<CandidateTasks />} />
        <Route path="profile" element={<CandidateProfilePage />} />
        <Route path="settings" element={<CandidateSettings />} />
      </Route>
      <Route
        path="e"
        element={
          <RequireRole role="employer">
            <AppShell />
          </RequireRole>
        }
      >
        <Route index element={<EmployerHome />} />
        <Route path="needs/new" element={<NeedEditor />} />
        <Route path="needs/:id" element={<ShortlistPage />} />
        <Route path="needs/:id/edit" element={<NeedEditor />} />
        <Route path="candidates/:id" element={<EmployerCandidate />} />
        <Route path="search" element={<EmployerSearch />} />
        <Route path="invitations" element={<EmployerInvitations />} />
        <Route path="vacancies" element={<EmployerVacancies />} />
        <Route path="vacancies/:id" element={<VacancyApplications />} />
        <Route path="tasks" element={<EmployerTasks />} />
        <Route path="company" element={<EmployerCompany />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
