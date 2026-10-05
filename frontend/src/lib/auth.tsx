import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
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
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<User>('/api/auth/me'),
    enabled: !!getToken(),
    retry: false,
    staleTime: 60_000,
  })

  const signIn = useCallback(
    (token: string, user: User) => {
      setToken(token)
      qc.clear()
      qc.setQueryData(['me'], user)
    },
    [qc],
  )

  const signOut = useCallback(() => {
    setToken(null)
    qc.clear()
    qc.setQueryData(['me'], null)
  }, [qc])

  useEffect(() => {
    const onLogout = () => signOut()
    window.addEventListener('fsp:logout', onLogout)
    return () => window.removeEventListener('fsp:logout', onLogout)
  }, [signOut])

  const value = useMemo<AuthState>(
    () => ({
      user: getToken() ? (data ?? null) : null,
      loading: !!getToken() && isLoading,
      signIn,
      signOut,
      refresh: () => void refetch(),
    }),
    [data, isLoading, signIn, signOut, refetch],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
