import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Catalog } from '../api/types'

export function useCatalog() {
  const { data } = useQuery({
    queryKey: ['catalog'],
    queryFn: () => api.get<Catalog>('/api/catalog'),
    staleTime: Infinity,
  })
  const skillTitle = (id: string) => data?.skills.find((s) => s.id === id)?.title ?? id
  const specTitle = (id: string | null | undefined) => data?.specializations.find((s) => s.id === id)?.title ?? id ?? '—'
  const specShort = (id: string | null | undefined) => data?.specializations.find((s) => s.id === id)?.short ?? id ?? '—'
  const gradeTitle = (id: string | null | undefined) => data?.grades.find((g) => g.id === id)?.title ?? id ?? '—'
  return { catalog: data, skillTitle, specTitle, specShort, gradeTitle }
}
