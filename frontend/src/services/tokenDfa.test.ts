import { describe, expect, it } from 'vitest'
import { mapTokenToDfa, tokenDfaUnavailableReason } from './tokenDfa'

const token = (type: string, lexeme: string) => ({ type, lexeme, line: 2, column: 4, end_line: 2, end_column: 4 + lexeme.length })

describe('source token to DFA mapping', () => {
  it('maps lexer tokens to their matching educational automata without changing their category', () => {
    expect(mapTokenToDfa(token('IDENTIFIER', 'student2'))?.automatonId).toBe('identifier')
    expect(mapTokenToDfa(token('NUMBER', '10'))?.automatonId).toBe('integer')
    expect(mapTokenToDfa(token('OPERATOR', '+'))?.automatonId).toBe('arithmetic_operator')
    expect(mapTokenToDfa(token('OPERATOR', '<='))?.automatonId).toBe('relational_operator')
  })

  it('leaves unsupported categories unmapped and explains why', () => {
    expect(mapTokenToDfa(token('STRING', '"hello"'))).toBeNull()
    expect(tokenDfaUnavailableReason(token('STRING', '"hello"'))).toContain('do not have a matching educational DFA')
    expect(mapTokenToDfa(token('KEYWORD', 'for'))).toBeNull()
  })

  it('does not route invalid or mismatched text through an unrelated DFA', () => {
    expect(mapTokenToDfa(token('IDENTIFIER', '2student'))).toBeNull()
    expect(mapTokenToDfa(token('NUMBER', '1.5'))).toBeNull()
    expect(mapTokenToDfa(token('OPERATOR', '&&'))).toBeNull()
  })
})
