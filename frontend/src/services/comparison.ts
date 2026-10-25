import type { AnalysisResult, Diagnostic, ParseNode, Token } from './api'

export type DiffLine = { kind: 'same' | 'added' | 'removed'; original?: string; generated?: string; originalEnding?: string; generatedEnding?: string; line: number }
export type DiagnosticChange = { code: string; message: string; severity: string; count: number }

export type ComparisonReport = {
  original: AnalysisResult
  generated: AnalysisResult
  tokenTypeCounts: { original: Record<string, number>; generated: Record<string, number> }
  tokenSequenceEqual: boolean
  diagnosticCodes: { original: Record<string, number>; generated: Record<string, number>; added: DiagnosticChange[]; removed: DiagnosticChange[]; persistent: DiagnosticChange[] }
  astAvailable: boolean
  astStructureEqual: boolean | null
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
  return {
    original: counts(original.map((diagnostic) => diagnostic.code)),
    generated: counts(generated.map((diagnostic) => diagnostic.code)),
    added: keys.filter((key) => (generatedCounts[key] ?? 0) > (originalCounts[key] ?? 0)).map((key) => toChange(key, (generatedCounts[key] ?? 0) - (originalCounts[key] ?? 0))),
    removed: keys.filter((key) => (originalCounts[key] ?? 0) > (generatedCounts[key] ?? 0)).map((key) => toChange(key, (originalCounts[key] ?? 0) - (generatedCounts[key] ?? 0))),
    persistent: keys.filter((key) => Boolean(originalCounts[key]) && Boolean(generatedCounts[key])).map((key) => toChange(key, Math.min(originalCounts[key], generatedCounts[key]))),
  }
}

export function buildComparison(original: AnalysisResult, generated: AnalysisResult, originalSource: string, generatedSource: string): ComparisonReport {
  return {
    original,
    generated,
    tokenTypeCounts: { original: counts(original.tokens.map((token) => token.type)), generated: counts(generated.tokens.map((token) => token.type)) },
    tokenSequenceEqual: original.tokens.map(tokenSignature).join('\u0001') === generated.tokens.map(tokenSignature).join('\u0001'),
    diagnosticCodes: diagnosticChanges(original.diagnostics, generated.diagnostics),
    astAvailable: Boolean(original.tree && generated.tree),
    astStructureEqual: original.tree && generated.tree ? JSON.stringify(normalizeTree(original.tree)) === JSON.stringify(normalizeTree(generated.tree)) : null,
    sourceDiff: sourceDiff(originalSource, generatedSource),
  }
}
