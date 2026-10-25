export type Language = {
  id: 'mini_python' | 'mini_c'
  name: string
  status: string
}

export type Token = { type: string; lexeme: string; line: number; column: number; end_line: number; end_column: number }
export type Diagnostic = { severity: string; code: string; message: string; line: number | null; column: number | null; end_line: number | null; end_column: number | null }
export type ParseNode = { type: string; attributes?: Record<string, unknown>; children?: ParseNode[] }
export type AnalysisResult = { language: string; grammar_version: string; lexical_valid: boolean; syntax_valid: boolean; success: boolean; tokens: Token[]; diagnostics: Diagnostic[]; tree: ParseNode | null; summary: { token_count: number; diagnostic_count: number } }
export type AutomatonState = { id: string; label: string }
export type AutomatonTransition = { from: string; to: string; label: string; matcher: string }
export type AutomatonDefinition = { id: string; name: string; description: string; pattern: string; start_state: string; accepting_states: string[]; states: AutomatonState[]; transitions: AutomatonTransition[]; examples?: { accepted: string[]; rejected: string[] } }
export type AutomatonTraceStep = { step: number; index: number; character: string; current_state: string; transition: string; next_state: string; accepted: boolean }
export type AutomatonSimulation = { automaton_id: string; input: string; trace: AutomatonTraceStep[]; final_state: string; accepted: boolean; characters_processed: number; failed_transition: { index: number; character: string; from_state: string; to_state: string; transition: string } | null; explanation: string }
export type AlternativeGeneration = { language: 'mini_python' | 'mini_c'; generated_code: string; provider: 'grok'; model: string }

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

export function getAutomata(): Promise<{ automata: AutomatonDefinition[] }> {
  return getJson('/api/automata')
}

export function getAutomaton(id: string): Promise<AutomatonDefinition> {
  return getJson(`/api/automata/${id}`)
}

export async function simulateAutomaton(id: string, input: string): Promise<AutomatonSimulation> {
  const response = await fetch(`${apiBaseUrl}/api/automata/${id}/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input }) })
  if (!response.ok) throw new Error(`Automaton simulation failed (${response.status})`)
  return response.json() as Promise<AutomatonSimulation>
}

export async function generateAlternative(language: string, sourceCode: string): Promise<AlternativeGeneration> {
  const response = await fetch(`${apiBaseUrl}/api/generate-alternative`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language, source_code: sourceCode }) })
  if (!response.ok) {
    let detail = `Alternative generation failed (${response.status})`
    try { const body = await response.json() as { detail?: string }; if (body.detail) detail = body.detail } catch { /* Preserve the status error. */ }
    throw new Error(detail)
  }
  return response.json() as Promise<AlternativeGeneration>
}
