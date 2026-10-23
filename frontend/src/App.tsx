import { useEffect, useState } from 'react'
import { analyzeCode, getHealth, getLanguages, type AnalysisResult, type Language, type ParseNode } from './services/api'

const emptyPanels = ['Lexical errors', 'Syntax diagnostics', 'Comparison results']

function TreeNode({ tree }: { tree: ParseNode }) {
  const [open, setOpen] = useState(true)
  const children = tree.children ?? []
  return <li className="tree-node"><button className="tree-toggle" type="button" onClick={() => setOpen(!open)} aria-expanded={open}>{children.length > 0 ? (open ? '⌄' : '›') : '•'}</button><span className="tree-type">{tree.type}</span>{tree.attributes && <span className="tree-attributes">{Object.entries(tree.attributes).map(([key, value]) => `${key}=${String(value)}`).join(' · ')}</span>}{open && children.length > 0 && <ul>{children.map((child, index) => <TreeNode key={`${child.type}-${index}`} tree={child} />)}</ul>}</li>
}

function App() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState('mini_python')
  const [source, setSource] = useState('x = 10\nprint(x)\n')
  const [connection, setConnection] = useState<'checking' | 'connected' | 'failed'>('checking')
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getHealth(), getLanguages()]).then(([, languageResponse]) => { setLanguages(languageResponse.languages); setConnection('connected') }).catch(() => { setConnection('failed'); setError('The backend is unavailable. Start FastAPI or check VITE_API_BASE_URL.') })
  }, [])

  async function handleAnalyze() {
    setError(''); setAnalysis(null)
    if (!source.trim()) { setError('Enter source code before analyzing.'); return }
    setLoading(true)
    try { setAnalysis(await analyzeCode(selectedLanguage, source)) } catch (requestError) { setError(requestError instanceof Error ? requestError.message : 'Analysis failed.') } finally { setLoading(false) }
  }

  return <main className="app-shell">
    <header className="hero"><div><p className="eyebrow">ANALYZER / PHASE 2</p><h1>CodeLens AI</h1><p className="subtitle">AI-Assisted Mini Python and Mini C Code Analysis</p></div><div className={`connection connection-${connection}`} role="status"><span className="status-dot" />{connection === 'checking' ? 'Checking backend…' : connection === 'connected' ? 'Backend connected' : 'Backend unavailable'}</div></header>
    <section className="workspace-card" aria-labelledby="workspace-heading"><div className="section-heading"><div><p className="eyebrow">ANALYSIS WORKSPACE</p><h2 id="workspace-heading">Analyze a program</h2></div><label>Language<select value={selectedLanguage} onChange={(event) => setSelectedLanguage(event.target.value)}>{languages.length > 0 ? languages.map((language) => <option key={language.id} value={language.id}>{language.name}</option>) : <><option value="mini_python">Mini Python</option><option value="mini_c">Mini C</option></>}</select></label></div><label className="editor-label" htmlFor="source-code">Original code</label><textarea id="source-code" value={source} onChange={(event) => setSource(event.target.value)} placeholder="Paste a Mini Python program here…" spellCheck={false} /><div className="action-row"><button type="button" onClick={handleAnalyze} disabled={loading}>{loading ? 'Analyzing…' : 'Analyze program'}</button><span className="scope-note">Syntax analysis only. Submitted code is never executed.</span></div>{error && <p className="error-message" role="alert">{error}</p>}</section>
    {analysis ? <AnalysisPanels analysis={analysis} /> : <section className="results-grid" aria-label="Analysis results">{emptyPanels.map((panel) => <article className="result-panel" key={panel}><h3>{panel}</h3><p>Run an analysis to see results.</p></article>)}</section>}
    <section className="ai-placeholder"><div><p className="eyebrow">FUTURE CAPABILITY</p><h2>AI alternative generation</h2><p>Alternative code generation, Mini C analysis, and comparison are outside Phase 2.</p></div><span className="pill">Not enabled</span></section><footer>Mini Python is a deliberately limited educational subset. No source code is executed.</footer>
  </main>
}

function AnalysisPanels({ analysis }: { analysis: AnalysisResult }) {
  const lexicalCodes = new Set(['PY_INVALID_CHARACTER', 'PY_MALFORMED_NUMBER', 'PY_UNTERMINATED_STRING', 'PY_INDENT_TAB', 'PY_INCONSISTENT_DEDENT'])
  const lexicalDiagnostics = analysis.diagnostics.filter((diagnostic) => lexicalCodes.has(diagnostic.code))
  const syntaxDiagnostics = analysis.diagnostics.filter((diagnostic) => !lexicalCodes.has(diagnostic.code))
  return <section className="analysis-results" aria-label="Analysis results"><div className={`analysis-status ${analysis.success ? 'success' : 'failure'}`}><strong>{analysis.success ? 'Syntax valid' : 'Syntax issues found'}</strong><span>{analysis.grammar_version} · {analysis.summary.token_count} tokens · {analysis.summary.diagnostic_count} diagnostics</span></div><div className="results-grid analysis-grid"><article className="result-panel token-panel"><h3>Tokens <span>{analysis.tokens.length}</span></h3><div className="table-scroll"><table><thead><tr><th>Type</th><th>Lexeme</th><th>Location</th></tr></thead><tbody>{analysis.tokens.map((token, index) => <tr key={`${token.type}-${index}`}><td>{token.type}</td><td><code>{token.lexeme || '↵'}</code></td><td>{token.line}:{token.column}</td></tr>)}</tbody></table></div></article><DiagnosticPanel title="Lexical diagnostics" diagnostics={lexicalDiagnostics} /><DiagnosticPanel title="Syntax diagnostics" diagnostics={syntaxDiagnostics} /><article className="result-panel tree-panel"><h3>Parse tree / AST</h3>{analysis.tree ? <ul className="tree-root"><TreeNode tree={analysis.tree} /></ul> : <p>No parse tree was produced.</p>}</article></div></section>
}

function DiagnosticPanel({ title, diagnostics }: { title: string; diagnostics: AnalysisResult['diagnostics'] }) {
  return <article className="result-panel diagnostic-panel"><h3>{title} <span>{diagnostics.length}</span></h3>{diagnostics.length === 0 ? <p className="diagnostic-clear">None</p> : <ul>{diagnostics.map((diagnostic, index) => <li key={`${diagnostic.code}-${index}`}><strong>{diagnostic.code}</strong><span>{diagnostic.message}</span><small>{diagnostic.line ?? '?'}:{diagnostic.column ?? '?'}</small></li>)}</ul>}</article>
}

export default App
