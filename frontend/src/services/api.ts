export type Language = {
  id: 'mini_python' | 'mini_c'
  name: string
  status: string
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`)
  if (!response.ok) {
    throw new Error(`Backend request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export function getHealth(): Promise<{ status: string; service: string }> {
  return getJson('/api/health')
}

export function getLanguages(): Promise<{ languages: Language[] }> {
  return getJson('/api/languages')
}
