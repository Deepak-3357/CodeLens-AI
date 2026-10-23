import { useEffect, useMemo, useRef, useState } from 'react'
import { analyzeCode, getHealth, getLanguages, type AnalysisResult, type Diagnostic, type Language, type ParseNode } from './services/api'

const lexicalCodes = new Set(['PY_INVALID_CHARACTER', 'PY_MALFORMED_NUMBER', 'PY_UNTERMINATED_STRING', 'PY_INDENT_TAB', 'PY_INCONSISTENT_DEDENT', 'C_INVALID_CHARACTER', 'C_MALFORMED_NUMBER', 'C_UNTERMINATED_STRING', 'C_UNTERMINATED_CHARACTER', 'C_INVALID_CHARACTER_LITERAL', 'C_UNTERMINATED_COMMENT'])

function App() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState('mini_python')
  const [source, setSource] = useState('x = 10\ny = 20\nprint(x + y)\n')
  const [connection, setConnection] = useState<'checking' | 'connected' | 'failed'>('checking')
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeLine, setActiveLine] = useState<number | null>(null)
  const sourceRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    Promise.all([getHealth(), getLanguages()])
      .then(([, response]) => { setLanguages(response.languages); setConnection('connected') })
      .catch(() => { setConnection('failed'); setError('The backend is unavailable. Start FastAPI or check VITE_API_BASE_URL.') })
  }, [])

  const lineCount = Math.max(source.split('\n').length, 1)

  function updateSource(value: string) {
    setSource(value)
    setAnalysis(null)
    setActiveLine(null)
    setError('')
  }

  function updateLanguage(value: string) {
    setSelectedLanguage(value)
    setAnalysis(null)
    setActiveLine(null)
    setError('')
  }

  async function handleAnalyze() {
    setError('')
    setAnalysis(null)
    setActiveLine(null)
    if (!source.trim()) { setError('Enter source code before analyzing.'); return }
    setLoading(true)
    try { setAnalysis(await analyzeCode(selectedLanguage, source)) }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : 'Analysis failed.') }
    finally { setLoading(false) }
  }

  function locateDiagnostic(diagnostic: Diagnostic) {
    if (!diagnostic.line) return
    const linesBefore = source.split('\n').slice(0, diagnostic.line - 1).join('\n')
    const lineStart = linesBefore.length + (diagnostic.line > 1 ? 1 : 0)
    const lineText = source.split('\n')[diagnostic.line - 1] ?? ''
    const columnOffset = Math.max((diagnostic.column ?? 1) - 1, 0)
    sourceRef.current?.focus()
    sourceRef.current?.setSelectionRange(lineStart + Math.min(columnOffset, lineText.length), lineStart + lineText.length)
    setActiveLine(diagnostic.line)
  }

  return <main className="app-shell">
    <header className="hero"><div><p className="eyebrow">CODE ANALYSIS WORKSPACE</p><h1>CodeLens AI</h1><p className="subtitle">Multi-Language Analyzer for Mini Python and Mini C</p></div><div className={`connection connection-${connection}`} role="status"><span className="status-dot" />{connection === 'checking' ? 'Checking backend…' : connection === 'connected' ? 'Backend connected' : 'Backend unavailable'}</div></header>
    <section className="workspace-card" aria-labelledby="workspace-heading">
      <div className="section-heading"><div><p className="eyebrow">SOURCE INPUT</p><h2 id="workspace-heading">Analyze a program</h2></div><label>Language<select value={selectedLanguage} onChange={(event) => updateLanguage(event.target.value)}>{languages.length > 0 ? languages.map((language) => <option key={language.id} value={language.id}>{language.name}</option>) : <><option value="mini_python">Mini Python</option><option value="mini_c">Mini C</option></>}</select></label></div>
      <label className="editor-label" htmlFor="source-code">Original code</label>
      <div className="editor-shell"><div className="line-gutter" aria-hidden="true">{Array.from({ length: lineCount }, (_, index) => { const line = index + 1; return <span className={activeLine === line ? 'active-line' : ''} key={line}>{line}</span> })}</div><textarea ref={sourceRef} id="source-code" value={source} onChange={(event) => updateSource(event.target.value)} placeholder="Paste Mini Python or Mini C source here…" spellCheck={false} /></div>
      <div className="action-row"><button type="button" onClick={handleAnalyze} disabled={loading}>{loading ? 'Analyzing…' : 'Analyze program'}</button><span className="scope-note">Syntax analysis only. Submitted code is never executed.</span></div>
      {error && <p className="error-message" role="alert">{error}</p>}
    </section>
    {loading && <div className="loading-card" role="status">Analyzing {selectedLanguage === 'mini_python' ? 'Mini Python' : 'Mini C'} source…</div>}
    {analysis && <AnalysisResults analysis={analysis} onLocate={locateDiagnostic} />}
    {!analysis && !loading && <div className="empty-results"><strong>Results are waiting</strong><span>Run the analyzer to view tokens, diagnostics, and the parse tree.</span></div>}
    <section className="ai-placeholder"><div><p className="eyebrow">PLANNED FEATURES</p><h2>AI alternatives and comparison</h2><p>AI-assisted alternative generation and evidence-based comparison are planned for a later phase. They are not enabled.</p></div><span className="pill">Not enabled</span></section>
    <footer>Mini Python and Mini C are educational subsets. CodeLens AI analyzes source text only; it never executes submitted code.</footer>
  </main>
}

function AnalysisResults({ analysis, onLocate }: { analysis: AnalysisResult; onLocate: (diagnostic: Diagnostic) => void }) {
  const lexicalDiagnostics = useMemo(() => analysis.diagnostics.filter((diagnostic) => lexicalCodes.has(diagnostic.code)), [analysis.diagnostics])
  const syntaxDiagnostics = useMemo(() => analysis.diagnostics.filter((diagnostic) => !lexicalCodes.has(diagnostic.code)), [analysis.diagnostics])
  const warningCount = analysis.diagnostics.filter((diagnostic) => diagnostic.severity === 'warning').length
  return <section className="analysis-results" aria-label="Analysis results">
    <div className={`analysis-status ${analysis.success ? 'success' : 'failure'}`}><div><strong>{analysis.success ? 'Analysis valid' : 'Issues found'}</strong><span>{analysis.language === 'mini_python' ? 'Mini Python' : 'Mini C'} · {analysis.grammar_version}</span></div><span>{analysis.success ? 'No error-level diagnostics' : `${analysis.diagnostics.length} diagnostic${analysis.diagnostics.length === 1 ? '' : 's'}`}</span></div>
    <div className="summary-row"><span><strong>{analysis.tokens.length}</strong> tokens</span><span><strong>{lexicalDiagnostics.length}</strong> lexical</span><span><strong>{syntaxDiagnostics.length}</strong> syntax</span><span><strong>{warningCount}</strong> warnings</span></div>
    <div className="results-grid analysis-grid"><TokenPanel tokens={analysis.tokens} /><DiagnosticPanel title="Lexical diagnostics" diagnostics={lexicalDiagnostics} onLocate={onLocate} /><DiagnosticPanel title="Syntax diagnostics" diagnostics={syntaxDiagnostics} onLocate={onLocate} /><AstPanel tree={analysis.tree} /></div>
  </section>
}

function TokenPanel({ tokens }: { tokens: AnalysisResult['tokens'] }) {
  return <article className="result-panel token-panel"><h3>Token stream <span>{tokens.length}</span></h3><div className="table-scroll"><table><thead><tr><th>Type</th><th>Lexeme</th><th>Location</th></tr></thead><tbody>{tokens.map((token, index) => <tr key={`${token.type}-${index}`}><td>{token.type}</td><td><code>{token.lexeme || '∅'}</code></td><td>{token.line}:{token.column}</td></tr>)}</tbody></table></div></article>
}

function DiagnosticPanel({ title, diagnostics, onLocate }: { title: string; diagnostics: Diagnostic[]; onLocate: (diagnostic: Diagnostic) => void }) {
  return <article className="result-panel diagnostic-panel"><h3>{title} <span>{diagnostics.length}</span></h3>{diagnostics.length === 0 ? <p className="diagnostic-clear">No diagnostics</p> : <ul>{diagnostics.map((diagnostic, index) => <li key={`${diagnostic.code}-${index}`}><button type="button" className={`diagnostic-item severity-${diagnostic.severity}`} onClick={() => onLocate(diagnostic)} disabled={!diagnostic.line} aria-label={`Locate ${diagnostic.code} at line ${diagnostic.line ?? 'unknown'}`}><strong>{diagnostic.code}</strong><span>{diagnostic.message}</span><small>{diagnostic.line ? `Line ${diagnostic.line}, column ${diagnostic.column ?? '?'}` : 'Location unavailable'}</small></button></li>)}</ul>}</article>
}

function AstPanel({ tree }: { tree: ParseNode | null }) {
  return <article className="result-panel tree-panel"><h3>Parse tree / AST</h3>{tree && typeof tree === 'object' && typeof tree.type === 'string' ? <ul className="tree-root"><TreeNode tree={tree} depth={0} /></ul> : <p>No parse tree was produced.</p>}</article>
}

function TreeNode({ tree, depth }: { tree: ParseNode; depth: number }) {
  const [open, setOpen] = useState(true)
  const children = Array.isArray(tree.children) ? tree.children.filter((child): child is ParseNode => Boolean(child && typeof child === 'object' && typeof child.type === 'string')) : []
  const attributes = tree.attributes && typeof tree.attributes === 'object' ? tree.attributes : {}
  const incomplete = attributes.incomplete === true || tree.type.startsWith('Error')
  if (depth > 100) return <li className="tree-node tree-incomplete">Tree depth limit reached.</li>
  return <li className={`tree-node ${incomplete ? 'tree-incomplete' : ''}`}><button className="tree-toggle" type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} ${tree.type} node`}>{children.length > 0 ? (open ? '⌄' : '›') : '•'}</button><span className="tree-type">{tree.type}</span>{incomplete && <span className="tree-warning">incomplete/error</span>}<span className="tree-attributes">{Object.entries(attributes).filter(([key]) => key !== 'incomplete').map(([key, value]) => `${key}=${String(value)}`).join(' · ')}</span>{open && children.length > 0 && <ul>{children.map((child, index) => <TreeNode key={`${child.type}-${index}`} tree={child} depth={depth + 1} />)}</ul>}</li>
}

export default App
