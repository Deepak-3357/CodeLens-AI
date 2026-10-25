import type { AnalysisResult, Diagnostic, ParseNode, Token } from './api'

export type DiffLine = { kind: 'same' | 'added' | 'removed'; original?: string; generated?: string; originalEnding?: string; generatedEnding?: string; line: number }
export type DiagnosticChange = { code: string; message: string; severity: string; count: number }
export type DiagnosticRow = { code: string; message: string; severity: string; originalCount: number; generatedCount: number; status: 'added' | 'removed' | 'persistent' }
export type AstComparisonStatus = 'match' | 'different' | 'original_invalid' | 'generated_invalid' | 'both_invalid' | 'missing_analysis' | 'stale' | 'language_mismatch'
export type AstComparison = { status: AstComparisonStatus; comparable: boolean; structureEqual: boolean | null; message: string }
export type ComparisonContext = { originalAnalyzed?: boolean; generatedAnalyzed?: boolean; originalCurrent?: boolean; generatedCurrent?: boolean; languagesMatch?: boolean }

export type ComparisonReport = {
  original: AnalysisResult
  generated: AnalysisResult
  tokenTypeCounts: { original: Record<string, number>; generated: Record<string, number> }
  tokenSequenceEqual: boolean
  diagnosticCodes: { original: Record<string, number>; generated: Record<string, number>; added: DiagnosticChange[]; removed: DiagnosticChange[]; persistent: DiagnosticChange[]; rows: DiagnosticRow[] }
  astAvailable: boolean
  astStructureEqual: boolean | null
  astComparison: AstComparison
  sourceDiff: DiffLine[]
}

type RawLine = { text: string; ending: string }

function counts(values: string[]): Record<string, number> {
  return values.reduce<Record<string, number>>((result, value) => {
    result[value] = (result[value] ?? 0) + 1
    return result
  }, {})
}

function tokenSignature(token: Token): string {
  return `${token.type}\u0000${token.lexeme}`
}

function normalizeTree(node: ParseNode | null): unknown {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return null
  const attributes = Object.entries(node.attributes ?? {})
    .filter(([key]) => !['line', 'column', 'end_line', 'end_column', 'position', 'id', 'node_id'].includes(key))
    .sort(([left], [right]) => left.localeCompare(right))
    .reduce<Record<string, unknown>>((result, [key, value]) => {
      result[key] = value
      return result
    }, {})
  return { type: node.type, attributes, children: (node.children ?? []).map(normalizeTree) }
}

function splitRawLines(source: string): RawLine[] {
  if (source.length === 0) return []
  const lines: RawLine[] = []
  let start = 0
  for (let index = 0; index < source.length; index += 1) {
    if (source[index] === '\n' || source[index] === '\r') {
      const ending = source[index] === '\r' && source[index + 1] === '\n' ? '\r\n' : source[index]
      lines.push({ text: source.slice(start, index), ending })
      start = index + ending.length
      index += ending.length - 1
    }
  }
  if (start < source.length) lines.push({ text: source.slice(start), ending: '' })
  return lines
}

function rawLineKey(line: RawLine): string {
  return `${line.text}\u0000${line.ending}`
}

function sourceDiff(original: string, generated: string): DiffLine[] {
  const left = splitRawLines(original)
  const right = splitRawLines(generated)
  const table = Array.from({ length: left.length + 1 }, () => Array<number>(right.length + 1).fill(0))
  for (let row = left.length - 1; row >= 0; row -= 1) {
    for (let column = right.length - 1; column >= 0; column -= 1) {
      table[row][column] = rawLineKey(left[row]) === rawLineKey(right[column]) ? table[row + 1][column + 1] + 1 : Math.max(table[row + 1][column], table[row][column + 1])
    }
  }
  const diff: DiffLine[] = []
  let row = 0; let column = 0; let line = 1
  while (row < left.length && column < right.length) {
    if (rawLineKey(left[row]) === rawLineKey(right[column])) {
      diff.push({ kind: 'same', original: left[row].text, generated: right[column].text, originalEnding: left[row].ending, generatedEnding: right[column].ending, line }); row += 1; column += 1
    } else if (table[row + 1][column] >= table[row][column + 1]) {
      diff.push({ kind: 'removed', original: left[row].text, originalEnding: left[row].ending, line }); row += 1
    } else {
      diff.push({ kind: 'added', generated: right[column].text, generatedEnding: right[column].ending, line }); column += 1
    }
    line += 1
  }
  while (row < left.length) { diff.push({ kind: 'removed', original: left[row].text, originalEnding: left[row].ending, line }); row += 1; line += 1 }
  while (column < right.length) { diff.push({ kind: 'added', generated: right[column].text, generatedEnding: right[column].ending, line }); column += 1; line += 1 }
  return diff
}

function diagnosticSignature(diagnostic: Diagnostic): string {
  return `${diagnostic.code}\u0000${diagnostic.severity}\u0000${diagnostic.message}`
}

function diagnosticChanges(original: Diagnostic[], generated: Diagnostic[]): ComparisonReport['diagnosticCodes'] {
  const originalCounts = counts(original.map(diagnosticSignature))
  const generatedCounts = counts(generated.map(diagnosticSignature))
  const details = new Map<string, Diagnostic>()
  for (const diagnostic of [...original, ...generated]) details.set(diagnosticSignature(diagnostic), diagnostic)
  const keys = [...new Set([...Object.keys(originalCounts), ...Object.keys(generatedCounts)])]
  const toChange = (key: string, count: number): DiagnosticChange => {
    const diagnostic = details.get(key) as Diagnostic
    return { code: diagnostic.code, message: diagnostic.message, severity: diagnostic.severity, count }
  }
  const rows = keys.map((key) => {
    const originalCount = originalCounts[key] ?? 0
    const generatedCount = generatedCounts[key] ?? 0
    const diagnostic = details.get(key) as Diagnostic
    return { code: diagnostic.code, message: diagnostic.message, severity: diagnostic.severity, originalCount, generatedCount, status: generatedCount > originalCount ? 'added' as const : originalCount > generatedCount ? 'removed' as const : 'persistent' as const }
  })
  return {
    original: counts(original.map((diagnostic) => diagnostic.code)),
    generated: counts(generated.map((diagnostic) => diagnostic.code)),
    added: keys.filter((key) => (generatedCounts[key] ?? 0) > (originalCounts[key] ?? 0)).map((key) => toChange(key, (generatedCounts[key] ?? 0) - (originalCounts[key] ?? 0))),
    removed: keys.filter((key) => (originalCounts[key] ?? 0) > (generatedCounts[key] ?? 0)).map((key) => toChange(key, (originalCounts[key] ?? 0) - (generatedCounts[key] ?? 0))),
    persistent: keys.filter((key) => Boolean(originalCounts[key]) && Boolean(generatedCounts[key])).map((key) => toChange(key, Math.min(originalCounts[key], generatedCounts[key]))),
    rows,
  }
}

function analysisHasErrors(analysis: AnalysisResult): boolean {
  return !analysis.success || !analysis.lexical_valid || !analysis.syntax_valid || analysis.diagnostics.length > 0
}

function invalidSourceLabel(analysis: AnalysisResult): string {
  if (!analysis.lexical_valid) return 'lexical errors'
  if (!analysis.syntax_valid) return 'syntax errors'
  return 'analysis errors'
}

function astComparison(original: AnalysisResult, generated: AnalysisResult, context: ComparisonContext = {}): AstComparison {
  if (context.languagesMatch === false) return { status: 'language_mismatch', comparable: false, structureEqual: null, message: 'Choose the same language for both editors before comparing.' }
  if (context.originalAnalyzed === false || context.generatedAnalyzed === false) return { status: 'missing_analysis', comparable: false, structureEqual: null, message: 'Analyze both programs before comparing AST structures.' }
  if (context.originalCurrent === false || context.generatedCurrent === false) return { status: 'stale', comparable: false, structureEqual: null, message: 'Re-analyze the modified source before comparing.' }
  const originalComplete = original.parse_status === 'valid_complete' && original.tree_complete === true
  const generatedComplete = generated.parse_status === 'valid_complete' && generated.tree_complete === true
  const originalInvalid = analysisHasErrors(original) || !originalComplete
  const generatedInvalid = analysisHasErrors(generated) || !generatedComplete
  if (originalInvalid && generatedInvalid) return { status: 'both_invalid', comparable: false, structureEqual: null, message: 'Structural comparison limited — both sources have analysis errors.' }
  if (originalInvalid) return { status: 'original_invalid', comparable: false, structureEqual: null, message: `Structural comparison limited — original source has ${invalidSourceLabel(original)}.` }
  if (generatedInvalid) return { status: 'generated_invalid', comparable: false, structureEqual: null, message: `Structural comparison limited — generated source has ${invalidSourceLabel(generated)}.` }
  const equal = JSON.stringify(normalizeTree(original.tree)) === JSON.stringify(normalizeTree(generated.tree))
  return { status: equal ? 'match' : 'different', comparable: true, structureEqual: equal, message: equal ? 'AST structures match' : 'AST structures differ' }
}

export function buildComparison(original: AnalysisResult, generated: AnalysisResult, originalSource: string, generatedSource: string, context: ComparisonContext = {}): ComparisonReport {
  const astResult = astComparison(original, generated, context)
  return {
    original,
    generated,
    tokenTypeCounts: { original: counts(original.tokens.map((token) => token.type)), generated: counts(generated.tokens.map((token) => token.type)) },
    tokenSequenceEqual: original.tokens.map(tokenSignature).join('\u0001') === generated.tokens.map(tokenSignature).join('\u0001'),
    diagnosticCodes: diagnosticChanges(original.diagnostics, generated.diagnostics),
    astAvailable: astResult.comparable,
    astStructureEqual: astResult.structureEqual,
    astComparison: astResult,
    sourceDiff: sourceDiff(originalSource, generatedSource),
  }
}
