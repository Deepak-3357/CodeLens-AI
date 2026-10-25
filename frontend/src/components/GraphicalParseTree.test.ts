import { describe, expect, it } from 'vitest'
import { createTreeLayout, nodeLabel, treeDisplayState } from '../services/treeLayout'
import type { ParseNode } from '../services/api'

const terminal = (token_type: string, lexeme: string, line = 1, column = 1): ParseNode => ({ type: 'Terminal', attributes: { token_type, lexeme, line, column } })

const miniPythonTree: ParseNode = {
  type: 'Program',
  children: [
    { type: 'Assignment', children: [terminal('IDENTIFIER', 'x'), terminal('OPERATOR', '='), { type: 'NumberLiteral', children: [terminal('NUMBER', '10')] }] },
    { type: 'Assignment', children: [terminal('IDENTIFIER', 'y'), terminal('OPERATOR', '='), { type: 'NumberLiteral', children: [terminal('NUMBER', '20')] }] },
    { type: 'PrintStatement', children: [terminal('KEYWORD', 'print'), terminal('DELIMITER', '('), { type: 'BinaryExpression', children: [terminal('IDENTIFIER', 'x'), terminal('OPERATOR', '+'), terminal('IDENTIFIER', 'y')] }, terminal('DELIMITER', ')')] },
  ],
}

const miniCTree: ParseNode = {
  type: 'Program',
  children: [{ type: 'Declaration', attributes: { declared_type: 'int', name: 'x' }, children: [terminal('KEYWORD', 'int'), terminal('IDENTIFIER', 'x'), terminal('OPERATOR', '='), { type: 'NumberLiteral', children: [terminal('NUMBER', '10')] }, terminal('DELIMITER', ';')] }, { type: 'PrintfStatement', children: [terminal('KEYWORD', 'printf'), terminal('DELIMITER', '('), { type: 'StringLiteral', children: [terminal('STRING', '"%d"')] }, terminal('DELIMITER', ','), terminal('IDENTIFIER', 'x'), terminal('DELIMITER', ')'), terminal('DELIMITER', ';')] }],
}

describe('hierarchical parse-tree layout', () => {
  it('lays out the root, every node, and every parent-child edge exactly once', () => {
    const layout = createTreeLayout(miniPythonTree)
    expect(layout.nodes[0].node.type).toBe('Program')
    expect(layout.nodes).toHaveLength(19)
    expect(layout.edges).toHaveLength(layout.nodes.length - 1)
    expect(new Set(layout.nodes.map((node) => node.id)).size).toBe(layout.nodes.length)
  })

  it('preserves assignment and binary-expression hierarchy', () => {
    const layout = createTreeLayout(miniPythonTree)
    const assignment = layout.nodes.find((item) => item.node.type === 'Assignment')
    const binary = layout.nodes.find((item) => item.node.type === 'BinaryExpression')
    expect(assignment?.children).toHaveLength(3)
    expect(binary?.children).toHaveLength(3)
    expect(layout.edges).toContainEqual({ id: '0->0.0', from: '0', to: '0.0' })
    expect(layout.edges).toContainEqual({ id: '0.2->0.2.2', from: '0.2', to: '0.2.2' })
  })

  it('renders exact terminal lexemes, token types, and locations in labels', () => {
    expect(nodeLabel(terminal('IDENTIFIER', 'student2', 4, 7))).toEqual({ title: 'student2', subtitle: 'IDENTIFIER · 4:7', lexeme: 'student2' })
    expect(nodeLabel(terminal('NEWLINE', '')).title).toBe('∅')
  })

  it('supports the Mini C hierarchy without inventing nodes', () => {
    const layout = createTreeLayout(miniCTree)
    expect(layout.nodes.map((item) => item.node.type)).toContain('Declaration')
    expect(layout.nodes.map((item) => item.node.type)).toContain('PrintfStatement')
    expect(layout.nodes.filter((item) => item.node.type === 'Terminal')).toHaveLength(12)
  })

  it('marks partial and missing trees separately', () => {
    expect(treeDisplayState(miniPythonTree, 'valid_complete', true)).toBe('complete')
    expect(treeDisplayState({ ...miniPythonTree, attributes: { incomplete: true } }, 'invalid_partial', false)).toBe('partial')
    expect(treeDisplayState(null, 'invalid_no_tree', false)).toBe('empty')
  })

  it('does not overlap long identifiers and collapses descendants deterministically', () => {
    const longTree: ParseNode = { type: 'Program', children: [{ type: 'Identifier', children: [terminal('IDENTIFIER', 'a'.repeat(120))] }, { type: 'Identifier', children: [terminal('IDENTIFIER', 'b'.repeat(120))] }] }
    const expanded = createTreeLayout(longTree)
    const collapsed = createTreeLayout(longTree, new Set(['0.0']))
    expect(expanded.width).toBeGreaterThan(500)
    expect(expanded.nodes).toHaveLength(5)
    expect(collapsed.nodes).toHaveLength(4)
    expect(collapsed.edges).toHaveLength(3)
  })
})
