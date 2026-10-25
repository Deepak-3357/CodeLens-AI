import type { AnalysisResult, ParseNode, Token } from './api'

export type DiffLine = { kind: 'same' | 'added' | 'removed'; original?: string; generated?: string; line: number }

export type ComparisonReport = {
  original: AnalysisResult
  generated: AnalysisResult
  tokenTypeCounts: { original: Record<string, number>; generated: Record<string, number> }
  tokenSequenceEqual: boolean
  diagnosticCodes: { original: Record<string, number>; generated: Record<string, number>; added: string[]; removed: string[]; persistent: string[] }
  astAvailable: boolean
  astStructureEqual: boolean | null
  sourceDiff: DiffLine[]
}

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
  return {
    type: node.type,
    attributes,
    children: (node.children ?? []).map(normalizeTree),
  }
}

function sourceDiff(original: string, generated: string): DiffLine[] {
  const left = original.split('\n')
  const right = generated.split('\n')
  const table = Array.from({ length: left.length + 1 }, () => Array<number>(right.length + 1).fill(0))
  for (let row = left.length - 1; row >= 0; row -= 1) {
    for (let column = right.length - 1; column >= 0; column -= 1) {
      table[row][column] = left[row] === right[column] ? table[row + 1][column + 1] + 1 : Math.max(table[row + 1][column], table[row][column + 1])
    }
  }
  const diff: DiffLine[] = []
  let row = 0
  let column = 0
  let line = 1
  while (row < left.length && column < right.length) {
    if (left[row] === right[column]) {
      diff.push({ kind: 'same', original: left[row], generated: right[column], line })
      row += 1
      column += 1
    } else if (table[row + 1][column] >= table[row][column + 1]) {
      diff.push({ kind: 'removed', original: left[row], line })
      row += 1
    } else {
      diff.push({ kind: 'added', generated: right[column], line })
      column += 1
    }
    line += 1
  }
  while (row < left.length) { diff.push({ kind: 'removed', original: left[row], line }); row += 1; line += 1 }
  while (column < right.length) { diff.push({ kind: 'added', generated: right[column], line }); column += 1; line += 1 }
  return diff
}

export function buildComparison(original: AnalysisResult, generated: AnalysisResult, originalSource: string, generatedSource: string): ComparisonReport {
  const originalCodes = counts(original.diagnostics.map((diagnostic) => diagnostic.code))
  const generatedCodes = counts(generated.diagnostics.map((diagnostic) => diagnostic.code))
  const allCodes = new Set([...Object.keys(originalCodes), ...Object.keys(generatedCodes)])
  return {
    original,
    generated,
    tokenTypeCounts: { original: counts(original.tokens.map((token) => token.type)), generated: counts(generated.tokens.map((token) => token.type)) },
    tokenSequenceEqual: original.tokens.map(tokenSignature).join('\u0001') === generated.tokens.map(tokenSignature).join('\u0001'),
    diagnosticCodes: {
      original: originalCodes,
      generated: generatedCodes,
      added: [...allCodes].filter((code) => (generatedCodes[code] ?? 0) > (originalCodes[code] ?? 0)),
      removed: [...allCodes].filter((code) => (originalCodes[code] ?? 0) > (generatedCodes[code] ?? 0)),
      persistent: [...allCodes].filter((code) => Boolean(originalCodes[code]) && Boolean(generatedCodes[code])),
    },
    astAvailable: Boolean(original.tree && generated.tree),
    astStructureEqual: original.tree && generated.tree ? JSON.stringify(normalizeTree(original.tree)) === JSON.stringify(normalizeTree(generated.tree)) : null,
    sourceDiff: sourceDiff(originalSource, generatedSource),
  }
}
