import type { ParseNode, ParseStatus } from './api'

export type TreeLayoutNode = { id: string; node: ParseNode; x: number; y: number; width: number; height: number; children: string[] }
export type TreeLayoutEdge = { id: string; from: string; to: string }
export type TreeLayout = { width: number; height: number; nodes: TreeLayoutNode[]; edges: TreeLayoutEdge[] }

const NODE_HEIGHT = 58
const LEVEL_GAP = 78
const SIBLING_GAP = 28
const PADDING = 32

function attributesFor(node: ParseNode): Record<string, unknown> {
  return node.attributes && typeof node.attributes === 'object' ? node.attributes : {}
}

function childrenFor(node: ParseNode): ParseNode[] {
  return Array.isArray(node.children) ? node.children.filter((child): child is ParseNode => Boolean(child && typeof child === 'object' && typeof child.type === 'string')) : []
}

export function nodeLabel(node: ParseNode): { title: string; subtitle: string; lexeme?: string } {
  const attributes = attributesFor(node)
  if (node.type === 'Terminal') {
    const tokenType = typeof attributes.token_type === 'string' ? attributes.token_type : 'TOKEN'
    const lexeme = typeof attributes.lexeme === 'string' ? attributes.lexeme : ''
    const location = attributes.line ? `${attributes.line}:${attributes.column ?? '?'}` : 'location unavailable'
    return { title: lexeme || '∅', subtitle: `${tokenType} · ${location}`, lexeme }
  }
  const details = Object.entries(attributes).filter(([key]) => !['incomplete', 'line', 'column', 'end_line', 'end_column'].includes(key)).map(([key, value]) => `${key}=${String(value)}`).join(' · ')
  return { title: node.type, subtitle: details }
}

function nodeWidth(node: ParseNode): number {
  const label = nodeLabel(node)
  const longest = Math.max(label.title.length, label.subtitle.length)
  return Math.max(node.type === 'Terminal' ? 132 : 150, Math.min(360, 42 + longest * 7))
}

export function createTreeLayout(tree: ParseNode, collapsed: ReadonlySet<string> = new Set()): TreeLayout {
  const dimensions = new Map<string, { width: number; children: string[] }>()
  const measure = (node: ParseNode, id: string): number => {
    const children = childrenFor(node)
    const childIds = children.map((_, index) => `${id}.${index}`)
    if (collapsed.has(id) || childIds.length === 0) {
      dimensions.set(id, { width: nodeWidth(node), children: [] })
      return nodeWidth(node)
    }
    const childrenWidth = children.reduce((total, child, index) => total + measure(child, childIds[index]), 0) + SIBLING_GAP * (childIds.length - 1)
    const width = Math.max(nodeWidth(node), childrenWidth)
    dimensions.set(id, { width, children: childIds })
    return width
  }
  const rootWidth = measure(tree, '0')
  const nodes: TreeLayoutNode[] = []
  const edges: TreeLayoutEdge[] = []
  let maxDepth = 0
  const place = (node: ParseNode, id: string, left: number, depth: number) => {
    const dimension = dimensions.get(id) ?? { width: nodeWidth(node), children: [] }
    const childWidths = dimension.children.map((childId) => dimensions.get(childId)?.width ?? nodeWidth(node))
    const childrenTotal = childWidths.reduce((total, width) => total + width, 0) + SIBLING_GAP * Math.max(0, childWidths.length - 1)
    let cursor = left + Math.max(0, (dimension.width - childrenTotal) / 2)
    const x = left + dimension.width / 2
    const y = PADDING + depth * (NODE_HEIGHT + LEVEL_GAP)
    nodes.push({ id, node, x, y, width: nodeWidth(node), height: NODE_HEIGHT, children: dimension.children })
    maxDepth = Math.max(maxDepth, depth)
    dimension.children.forEach((childId, index) => {
      const childParts = childId.split('.')
      const childIndex = Number(childParts[childParts.length - 1])
      const child = childrenFor(node)[childIndex]
      if (!child) return
      place(child, childId, cursor, depth + 1)
      edges.push({ id: `${id}->${childId}`, from: id, to: childId })
      cursor += childWidths[index] + SIBLING_GAP
    })
  }
  place(tree, '0', PADDING, 0)
  return { width: rootWidth + PADDING * 2, height: PADDING * 2 + (maxDepth + 1) * NODE_HEIGHT + maxDepth * LEVEL_GAP, nodes, edges }
}

export function treeDisplayState(tree: ParseNode | null, parseStatus?: ParseStatus, treeComplete?: boolean): 'complete' | 'partial' | 'empty' {
  if (!tree || typeof tree !== 'object' || typeof tree.type !== 'string' || parseStatus === 'invalid_no_tree') return 'empty'
  return parseStatus === 'invalid_partial' || treeComplete === false ? 'partial' : 'complete'
}

export function nodeIsIncomplete(node: ParseNode): boolean {
  const attributes = attributesFor(node)
  return attributes.incomplete === true || node.type.startsWith('Error')
}

export function treeChildren(node: ParseNode): ParseNode[] {
  return childrenFor(node)
}
