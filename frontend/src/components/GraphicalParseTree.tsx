import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import type { ParseNode, ParseStatus } from '../services/api'
import { createTreeLayout, nodeIsIncomplete, nodeLabel, treeChildren, treeDisplayState, type TreeLayout } from '../services/treeLayout'

function textFallback(node: ParseNode, prefix = ''): string {
  const label = nodeLabel(node)
  const line = node.type === 'Terminal' ? `${label.subtitle} ${JSON.stringify(label.lexeme ?? '')}` : `${node.type}${label.subtitle ? ` (${label.subtitle})` : ''}`
  return [`${prefix}${line}`, ...treeChildren(node).flatMap((child) => textFallback(child, `${prefix}  `))].join('\n')
}

function statusLabel(parseStatus?: ParseStatus, treeComplete?: boolean): string | null {
  if (parseStatus === 'invalid_partial' || treeComplete === false) return 'Partial parse tree — syntax or lexical diagnostics are present.'
  if (parseStatus === 'invalid_no_tree') return 'No usable parse tree was produced.'
  return null
}

function ZoomButton({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" className="tree-control" onClick={onClick} aria-label={label}>{label}</button>
}

function TreeDiagram({ layout, zoom, collapsed, setCollapsed }: { layout: TreeLayout; zoom: number; collapsed: ReadonlySet<string>; setCollapsed: Dispatch<SetStateAction<Set<string>>> }) {
  return <svg className="tree-diagram" width={layout.width * zoom} height={layout.height * zoom} viewBox={`0 0 ${layout.width} ${layout.height}`}>
    <g className="tree-diagram-edges">{layout.edges.map((edge) => { const from = layout.nodes.find((node) => node.id === edge.from); const to = layout.nodes.find((node) => node.id === edge.to); if (!from || !to) return null; const midY = from.y + from.height / 2 + 39; return <path key={edge.id} d={`M ${from.x} ${from.y + from.height / 2} V ${midY} H ${to.x} V ${to.y - to.height / 2}`} /> })}</g>
    {layout.nodes.map((item) => { const label = nodeLabel(item.node); const terminal = item.node.type === 'Terminal'; const incomplete = nodeIsIncomplete(item.node); const hasChildren = !terminal && treeChildren(item.node).length > 0; const hasHiddenChildren = hasChildren && collapsed.has(item.id); const toggle = () => setCollapsed((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next }); return <g className={`tree-diagram-node ${terminal ? 'tree-diagram-terminal' : 'tree-diagram-grammar'} ${incomplete ? 'tree-diagram-incomplete' : ''}`} key={item.id} transform={`translate(${item.x} ${item.y})`}><rect x={-item.width / 2} y={-item.height / 2} width={item.width} height={item.height} rx="10" /><text className="tree-diagram-kind" x={-item.width / 2 + 12} y="-15">{terminal ? 'TERMINAL' : 'GRAMMAR'}</text>{hasChildren && <rect className="tree-diagram-hit-area" x={item.width / 2 - 30} y={-item.height / 2 + 4} width="24" height="24" role="button" tabIndex={0} aria-label={`${hasHiddenChildren ? 'Expand' : 'Collapse'} ${item.node.type} branch`} onClick={toggle} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle() } }} />}{hasChildren && <text className="tree-diagram-toggle" x={item.width / 2 - 18} y="-15">{hasHiddenChildren ? '+' : '−'}</text>}<text className="tree-diagram-title" x="0" y="7" textAnchor="middle">{label.title}</text><text className="tree-diagram-subtitle" x="0" y="22" textAnchor="middle">{label.subtitle}</text></g> })}
  </svg>
}

export default function GraphicalParseTree({ tree, parseStatus, treeComplete }: { tree: ParseNode | null; parseStatus?: ParseStatus; treeComplete?: boolean }) {
  const state = treeDisplayState(tree, parseStatus, treeComplete)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [zoom, setZoom] = useState(1)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const layout = useMemo(() => tree ? createTreeLayout(tree, collapsed) : null, [tree, collapsed])
  const status = statusLabel(parseStatus, treeComplete)
  useEffect(() => { setCollapsed(new Set()); setZoom(1) }, [tree, parseStatus, treeComplete])

  function fitTree() {
    if (!layout || !viewportRef.current) return
    const availableWidth = Math.max(240, viewportRef.current.clientWidth - 28)
    const availableHeight = Math.max(180, viewportRef.current.clientHeight - 28)
    setZoom(Math.max(0.45, Math.min(1, availableWidth / layout.width, availableHeight / layout.height)))
  }

  if (state === 'empty') return <div className="tree-empty-state" role="status"><strong>No usable parse tree was produced.</strong><span>Review the lexical and syntax diagnostics for this analysis.</span></div>
  if (!tree || !layout) return null
  return <div className="graph-tree-shell">
    <div className="graph-tree-toolbar" role="toolbar" aria-label="Parse tree controls"><span className="graph-tree-zoom-label">Zoom {Math.round(zoom * 100)}%</span><ZoomButton label="Zoom out" onClick={() => setZoom((value) => Math.max(0.45, value - 0.1))} /><ZoomButton label="Zoom in" onClick={() => setZoom((value) => Math.min(1.8, value + 0.1))} /><ZoomButton label="Fit tree" onClick={fitTree} /><ZoomButton label="Reset tree view" onClick={() => { setCollapsed(new Set()); setZoom(1) }} /></div>
    <div className="graph-tree-legend" aria-label="Parse tree legend"><span><i className="legend-swatch legend-grammar" />Grammar/nonterminal</span><span><i className="legend-swatch legend-terminal" />Terminal/token</span></div>
    {status && <p className="graph-tree-status" role="status">{status}</p>}
    <div className="tree-diagram-viewport" ref={viewportRef} aria-label={`${state} scrollable parse tree diagram`}><TreeDiagram layout={layout} zoom={zoom} collapsed={collapsed} setCollapsed={setCollapsed} /></div>
    <details className="graph-tree-fallback"><summary>Accessible text tree</summary><pre>{textFallback(tree)}</pre></details>
  </div>
}
