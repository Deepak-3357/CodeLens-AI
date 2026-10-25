import { describe, expect, it } from 'vitest'
import { buildComparison } from './comparison'
import type { AnalysisResult } from './api'

function analysis(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    language: 'mini_python',
    grammar_version: 'mini-python-1.0',
    lexical_valid: true,
    syntax_valid: true,
    success: true,
    tokens: [],
    diagnostics: [],
    tree: { type: 'Program', children: [] },
    summary: { token_count: 0, diagnostic_count: 0 },
    ...overrides,
  }
}

describe('comparison source fidelity', () => {
  it('keeps identical source lines and newline endings unchanged', () => {
    const report = buildComparison(analysis(), analysis(), 'x = 1\r\n\r\n', 'x = 1\r\n\r\n')
    expect(report.sourceDiff).toEqual([
      { kind: 'same', original: 'x = 1', generated: 'x = 1', originalEnding: '\r\n', generatedEnding: '\r\n', line: 1 },
      { kind: 'same', original: '', generated: '', originalEnding: '\r\n', generatedEnding: '\r\n', line: 2 },
    ])
  })

  it('distinguishes indentation, trailing spaces, tabs, blank lines, and newline styles', () => {
    const report = buildComparison(analysis(), analysis(), '  x = 1  \r\n\tprint(x)\r\n', ' x = 1\n\n print(x)\n')
    expect(report.sourceDiff.some((line) => line.kind === 'removed' && line.original === '  x = 1  ' && line.originalEnding === '\r\n')).toBe(true)
    expect(report.sourceDiff.some((line) => line.kind === 'added' && line.generated === ' x = 1' && line.generatedEnding === '\n')).toBe(true)
    expect(report.sourceDiff.some((line) => line.kind === 'removed' && line.original === '\tprint(x)')).toBe(true)
    expect(report.sourceDiff.some((line) => line.kind === 'added' && line.generated === '')).toBe(true)
  })

  it('represents inserted and deleted lines and empty source without inventing content', () => {
    const report = buildComparison(analysis(), analysis(), 'a\nb\n', 'a\nc\nb\n')
    expect(report.sourceDiff).toContainEqual({ kind: 'added', generated: 'c', generatedEnding: '\n', line: 2 })
    expect(buildComparison(analysis(), analysis(), '', '').sourceDiff).toEqual([])
    expect(buildComparison(analysis(), analysis(), '', 'x').sourceDiff).toEqual([{ kind: 'added', generated: 'x', generatedEnding: '', line: 1 }])
  })
})

describe('comparison diagnostics and structure', () => {
  it('matches diagnostics by code, severity, and message rather than line number', () => {
    const original = { severity: 'error', code: 'PY_INVALID_CHARACTER', message: 'Unsupported character.', line: 1, column: 4, end_line: 1, end_column: 5 }
    const shifted = { ...original, line: 3, column: 4, end_line: 3, end_column: 5 }
    const added = { ...original, code: 'PY_EXPECTED_TOKEN', message: 'Expected token.' }
    const report = buildComparison(analysis({ diagnostics: [original, original] }), analysis({ diagnostics: [shifted, added] }), 'x', 'y')
    expect(report.diagnosticCodes.persistent).toEqual([{ code: original.code, message: original.message, severity: original.severity, count: 1 }])
    expect(report.diagnosticCodes.added).toEqual([{ code: added.code, message: added.message, severity: added.severity, count: 1 }])
    expect(report.diagnosticCodes.removed).toEqual([{ code: original.code, message: original.message, severity: original.severity, count: 1 }])
  })

  it('keeps structural AST comparison separate from behavioral claims', () => {
    const originalTree = { type: 'Program', children: [{ type: 'Identifier', attributes: { name: 'x' } }] }
    const same = buildComparison(analysis({ tree: originalTree }), analysis({ tree: originalTree }), 'x', 'x')
    const different = buildComparison(analysis({ tree: originalTree }), analysis({ tree: { type: 'Program', children: [{ type: 'Identifier', attributes: { name: 'a' } }] } }), 'x', 'a')
    expect(same.astStructureEqual).toBe(true)
    expect(different.astStructureEqual).toBe(false)
    expect(different.original.success).toBe(true)
    expect(different.generated.success).toBe(true)
    expect(buildComparison(analysis({ tree: null }), analysis(), '', '').astAvailable).toBe(false)
  })
})
