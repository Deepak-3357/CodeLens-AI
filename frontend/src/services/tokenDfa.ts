import type { Token } from './api'

export type TokenDfaSelection = {
  lexeme: string
  tokenType: string
  line: number
  column: number
  automatonId: 'identifier' | 'integer' | 'arithmetic_operator' | 'relational_operator'
  explanation: string
}

type TokenDfaMapping = { automatonId: TokenDfaSelection['automatonId']; explanation: string }

const arithmeticOperators = new Set(['+', '-', '*', '/', '%'])
const relationalOperators = new Set(['<', '>', '<=', '>=', '==', '!='])

/**
 * Maps only lexer categories and lexemes covered by the educational DFAs.
 * This is intentionally not a claim that these DFAs are the internal lexer.
 */
export function mapTokenToDfa(token: Token): TokenDfaSelection | null {
  const mapping = mappingForToken(token)
  if (!mapping) return null
  return { ...token, tokenType: token.type, ...mapping }
}

export function tokenDfaUnavailableReason(token: Token): string {
  const mapping = mappingForToken(token)
  if (mapping) return ''
  if (token.type === 'NUMBER' && !/^\p{N}+$/u.test(token.lexeme)) return 'This number is not a digit-only integer accepted by the educational Integer DFA.'
  if (token.type === 'OPERATOR') return `The operator ${JSON.stringify(token.lexeme)} is not in the supported educational DFA operator sets.`
  if (token.type === 'KEYWORD') return 'Keywords are not identifiers in the lexer and are not mapped to an educational DFA.'
  if (token.type === 'STRING' || token.type === 'CHARACTER') return 'String and character literals do not have a matching educational DFA.'
  if (token.type === 'DELIMITER') return 'Punctuation does not have a matching educational DFA.'
  if (token.type === 'EOF' || token.type === 'NEWLINE' || token.type === 'INDENT' || token.type === 'DEDENT') return 'Layout and end-of-file tokens are not selected because the lexers do not preserve ordinary whitespace tokens.'
  return 'This token type does not have a matching educational DFA in the current visualizer.'
}

function mappingForToken(token: Token): TokenDfaMapping | null {
  if (token.type === 'IDENTIFIER' && /^[\p{L}_][\p{L}\p{N}_]*$/u.test(token.lexeme)) return { automatonId: 'identifier', explanation: 'IDENTIFIER lexemes use the educational letter-or-underscore followed by letter, digit, or underscore pattern.' }
  if (token.type === 'NUMBER' && /^\p{N}+$/u.test(token.lexeme)) return { automatonId: 'integer', explanation: 'This NUMBER is digit-only, matching the educational Integer DFA.' }
  if (token.type === 'OPERATOR' && arithmeticOperators.has(token.lexeme)) return { automatonId: 'arithmetic_operator', explanation: 'This OPERATOR is one of the five single-character arithmetic operators supported by the educational DFA.' }
  if (token.type === 'OPERATOR' && relationalOperators.has(token.lexeme)) return { automatonId: 'relational_operator', explanation: 'This OPERATOR is one of the relational lexemes supported by the educational DFA.' }
  return null
}
