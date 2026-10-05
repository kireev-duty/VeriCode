const TOKEN_KEY = 'fsp_talent_token'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(path, { method, headers, body: payload })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('fsp:logout'))
  }
  if (!res.ok) {
    let code = 'error'
    let message = `Ошибка ${res.status}`
    try {
      const data = await res.json()
      const d = data.detail
      if (d && typeof d === 'object') {
        code = d.code ?? code
        message = d.message ?? message
      } else if (typeof d === 'string') message = d
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, code, message)
  }
  const type = res.headers.get('content-type') ?? ''
  if (type.includes('application/json')) return (await res.json()) as T
  return (await res.blob()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  del: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<T>('POST', path, fd)
  },
}

export async function downloadFile(path: string, filename: string) {
  const blob = await request<Blob>('GET', path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
