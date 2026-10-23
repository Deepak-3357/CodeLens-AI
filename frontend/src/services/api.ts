export type Language = {
  id: 'mini_python' | 'mini_c'
  name: string
  status: string
}

export type Token = { type: string; lexeme: string; line: number; column: number; end_line: number; end_column: number }
export type Diagnostic = { severity: string; code: string; message: string; line: number | null; column: number | null; end_line: number | null; end_column: number | null }
export type ParseNode = { type: string; attributes?: Record<string, unknown>; children?: ParseNode[] }
export type AnalysisResult = { language: string; grammar_version: string; lexical_valid: boolean; syntax_valid: boolean; success: boolean; tokens: Token[]; diagnostics: Diagnostic[]; tree: ParseNode | null; summary: { token_count: number; diagnostic_count: number } }

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

export async function analyzeCode(language: string, code: string): Promise<AnalysisResult> {
  const response = await fetch(`${apiBaseUrl}/api/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language, code }) })
  if (!response.ok) {
    let detail = `Backend request failed (${response.status})`
    try { const body = await response.json() as { detail?: string }; if (body.detail) detail = body.detail } catch { /* Preserve the status error. */ }
    throw new Error(detail)
  }
  const body = await response.json() as Partial<AnalysisResult>
  if (!body || typeof body.success !== 'boolean' || !Array.isArray(body.tokens) || !Array.isArray(body.diagnostics)) {
    throw new Error('The backend returned an invalid analysis response.')
  }
  return body as AnalysisResult
}
