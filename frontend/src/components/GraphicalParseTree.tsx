import { useState } from 'react'
import type { ParseNode } from '../services/api'

function attributesFor(node: ParseNode): Record<string, unknown> {
  return node.attributes && typeof node.attributes === 'object' ? node.attributes : {}
}

function textFallback(node: ParseNode, prefix = ''): string {
  const attributes = attributesFor(node)
  const label = node.type === 'Terminal'
    ? `${typeof attributes.token_type === 'string' ? attributes.token_type : 'TOKEN'} ${typeof attributes.lexeme === 'string' ? JSON.stringify(attributes.lexeme) : '∅'}`
    : node.type
  const children = Array.isArray(node.children)
    ? node.children.filter((child): child is ParseNode => Boolean(child && typeof child === 'object' && typeof child.type === 'string'))
    : []
  return [`${prefix}${label}`, ...children.flatMap((child) => textFallback(child, `${prefix}  `))]
    .join('\n')
}

function GraphicalTreeNode({ tree, depth }: { tree: ParseNode; depth: number }) {
  const [open, setOpen] = useState(true)
  const attributes = attributesFor(tree)
  const children = Array.isArray(tree.children) ? tree.children.filter((child): child is ParseNode => Boolean(child && typeof child === 'object' && typeof child.type === 'string')) : []
  const terminal = tree.type === 'Terminal'
  const incomplete = attributes.incomplete === true || tree.type.startsWith('Error')
  if (depth > 100) return <li className="graph-tree-item"><div className="graph-tree-node graph-tree-error">Tree depth limit reached.</div></li>

  if (terminal) {
    const tokenType = typeof attributes.token_type === 'string' ? attributes.token_type : 'TOKEN'
    const lexeme = typeof attributes.lexeme === 'string' ? attributes.lexeme : ''
    const location = attributes.line ? `${attributes.line}:${attributes.column ?? '?'}` : 'location unavailable'
    return <li className="graph-tree-item"><div className="graph-tree-node graph-tree-terminal" aria-label={`${tokenType} ${lexeme || 'empty lexeme'} at ${location}`}><span className="graph-tree-kind">Terminal</span><strong>{tokenType}</strong><code>{lexeme || '∅'}</code><small>{location}</small></div></li>
  }

  const details = Object.entries(attributes).filter(([key]) => !['incomplete', 'line', 'column', 'end_line', 'end_column'].includes(key)).map(([key, value]) => `${key}=${String(value)}`).join(' · ')
  return <li className="graph-tree-item"><div className={`graph-tree-node graph-tree-nonterminal ${incomplete ? 'graph-tree-error' : ''}`}><button type="button" className="graph-tree-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} ${tree.type} node`}>{children.length > 0 ? (open ? '−' : '+') : '•'}</button><span className="graph-tree-kind">Grammar</span><strong>{tree.type}</strong>{details && <span className="graph-tree-details">{details}</span>}{incomplete && <span className="tree-warning">incomplete/error</span>}</div>{open && children.length > 0 && <ul className="graph-tree-children">{children.map((child, index) => <GraphicalTreeNode key={`${child.type}-${index}`} tree={child} depth={depth + 1} />)}</ul>}</li>
}

export default function GraphicalParseTree({ tree }: { tree: ParseNode | null }) {
  if (!tree || typeof tree !== 'object' || typeof tree.type !== 'string') return <p>No complete parse tree was produced; see diagnostics and available tokens.</p>
  return <div className="graph-tree-shell"><div className="graph-tree-legend" aria-label="Parse tree legend"><span><i className="legend-swatch legend-grammar" />Grammar node</span><span><i className="legend-swatch legend-terminal" />Terminal/token</span></div><div className="graph-tree-viewport"><ul className="graph-tree-root" aria-label="Graphical parse tree"><GraphicalTreeNode tree={tree} depth={0} /></ul></div><details className="graph-tree-fallback"><summary>Accessible text tree</summary><pre>{textFallback(tree)}</pre></details><p className="sr-only">The parse tree is presented as a hierarchical list. Grammar nodes contain terminal token nodes with exact lexemes, token types, and source locations.</p></div>
}
