import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from '../api/client'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  loading: boolean
  signIn: (token: string, user: User) => void
  signOut: () => void
  refresh: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  // The token lives in React state as well as in localStorage: signing in must re-render the provider. Otherwise
  // the ['me'] observer stays bound to the query removed by qc.clear() and the next route sees no user
  // (found by the e2e scenario: login and e-mail confirmation bounced back to /login).
  const [token, setTokenState] = useState(getToken)
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['me', token],
    queryFn: () => api.get<User>('/api/auth/me'),
    enabled: !!token,
    retry: false,
    staleTime: 60_000,
  })

  const signIn = useCallback(
    (newToken: string, user: User) => {
      setToken(newToken)
      qc.clear() // nothing of the previous account survives
      qc.setQueryData(['me', newToken], user)
      setTokenState(newToken)
    },
    [qc],
  )

  const signOut = useCallback(() => {
    setToken(null)
    qc.clear()
    setTokenState(null)
  }, [qc])

  useEffect(() => {
    const onLogout = () => signOut()
    window.addEventListener('fsp:logout', onLogout)
    return () => window.removeEventListener('fsp:logout', onLogout)
  }, [signOut])

  const value = useMemo<AuthState>(
    () => ({
      user: token ? (data ?? null) : null,
      loading: !!token && isLoading,
      signIn,
      signOut,
      refresh: () => void refetch(),
    }),
    [token, data, isLoading, signIn, signOut, refetch],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
