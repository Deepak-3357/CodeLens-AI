import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { analyzeCode, generateAlternative, getHealth, getLanguages, type AlternativeGeneration, type AnalysisResult, type Diagnostic, type Language, type ParseNode } from './services/api'
import { buildComparison } from './services/comparison'
import AutomataLab from './components/AutomataLab'
import AlternativePanel from './components/AlternativePanel'
import CodeEditorPanel from './components/CodeEditorPanel'
import ComparisonReport from './components/ComparisonReport'
import { mapTokenToDfa, tokenDfaUnavailableReason, type TokenDfaSelection } from './services/tokenDfa'

const lexicalCodes = new Set(['PY_INVALID_CHARACTER', 'PY_MALFORMED_NUMBER', 'PY_UNTERMINATED_STRING', 'PY_INDENT_TAB', 'PY_INCONSISTENT_DEDENT', 'C_INVALID_CHARACTER', 'C_MALFORMED_NUMBER', 'C_UNTERMINATED_STRING', 'C_UNTERMINATED_CHARACTER', 'C_INVALID_CHARACTER_LITERAL', 'C_UNTERMINATED_COMMENT'])
type ValidatedResult = { result: AnalysisResult; source: string; language: string }

function isCurrent(value: ValidatedResult | null, source: string, language: string): value is ValidatedResult {
  return Boolean(value && value.source === source && value.language === language)
}

function App() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [originalLanguage, setOriginalLanguage] = useState('mini_python')
  const [generatedLanguage, setGeneratedLanguage] = useState('mini_python')
  const [originalSource, setOriginalSource] = useState('x = 10\ny = 20\nprint(x + y)\n')
  const [generatedSource, setGeneratedSource] = useState('')
  const [connection, setConnection] = useState<'checking' | 'connected' | 'failed'>('checking')
  const [originalAnalysis, setOriginalAnalysis] = useState<ValidatedResult | null>(null)
  const [generatedAnalysis, setGeneratedAnalysis] = useState<ValidatedResult | null>(null)
  const [originalLoading, setOriginalLoading] = useState(false)
  const [generatedLoading, setGeneratedLoading] = useState(false)
  const [originalError, setOriginalError] = useState('')
  const [generatedError, setGeneratedError] = useState('')
  const [activeView, setActiveView] = useState<'analyzer' | 'automata'>('analyzer')
  const [selectedToken, setSelectedToken] = useState<TokenDfaSelection | null>(null)
  const [tokenNotice, setTokenNotice] = useState('')
  const [alternative, setAlternative] = useState<AlternativeGeneration | null>(null)
  const [generationLoading, setGenerationLoading] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [generatedOrigin, setGeneratedOrigin] = useState<{ source: string; language: string } | null>(null)
  const [generatedEdited, setGeneratedEdited] = useState(false)
  const [showComparison, setShowComparison] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')
  const [editorNotice, setEditorNotice] = useState('')
  const originalRequest = useRef(0)
  const generatedRequest = useRef(0)
  const generationRequest = useRef(0)
  const originalSourceRef = useRef<HTMLTextAreaElement>(null)
  const generatedSourceRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    Promise.all([getHealth(), getLanguages()])
      .then(([, response]) => { setLanguages(response.languages); setConnection('connected') })
      .catch(() => { setConnection('failed'); setOriginalError('The backend is unavailable. Start FastAPI or check VITE_API_BASE_URL.') })
  }, [])

  function updateOriginalSource(value: string) {
    setOriginalSource(value); setOriginalAnalysis(null); setOriginalError(''); setSelectedToken(null); setTokenNotice(''); setEditorNotice(''); setShowComparison(false); originalRequest.current += 1
  }

  function updateOriginalLanguage(value: string) {
    setOriginalLanguage(value); setOriginalAnalysis(null); setOriginalError(''); setSelectedToken(null); setTokenNotice(''); setShowComparison(false); originalRequest.current += 1
  }

  function updateGeneratedSource(value: string) {
    setGeneratedSource(value); setGeneratedAnalysis(null); setGeneratedError(''); setGeneratedEdited(Boolean(generatedOrigin)); setShowComparison(false); generatedRequest.current += 1
  }

  function updateGeneratedLanguage(value: string) {
    setGeneratedLanguage(value); setGeneratedAnalysis(null); setGeneratedError(''); setShowComparison(false); generatedRequest.current += 1
  }

  async function handleAnalyzeOriginal() {
    if (!originalSource.trim()) { setOriginalError('Enter source code before analyzing.'); return }
    const requestId = ++originalRequest.current
    const submittedSource = originalSource; const submittedLanguage = originalLanguage
    setOriginalLoading(true); setOriginalError(''); setOriginalAnalysis(null)
    try {
      const result = await analyzeCode(submittedLanguage, submittedSource)
      if (originalRequest.current === requestId && originalSource === submittedSource && originalLanguage === submittedLanguage) setOriginalAnalysis({ result, source: submittedSource, language: submittedLanguage })
    } catch (requestError) { if (originalRequest.current === requestId) setOriginalError(requestError instanceof Error ? requestError.message : 'Analysis failed.') }
    finally { if (originalRequest.current === requestId) setOriginalLoading(false) }
  }

  async function handleAnalyzeGenerated() {
    if (!generatedSource.trim()) { setGeneratedError('Generate or enter code before analyzing.'); return }
    const requestId = ++generatedRequest.current
    const submittedSource = generatedSource; const submittedLanguage = generatedLanguage
    setGeneratedLoading(true); setGeneratedError(''); setGeneratedAnalysis(null)
    try {
      const result = await analyzeCode(submittedLanguage, submittedSource)
      if (generatedRequest.current === requestId && generatedSource === submittedSource && generatedLanguage === submittedLanguage) setGeneratedAnalysis({ result, source: submittedSource, language: submittedLanguage })
    } catch (requestError) { if (generatedRequest.current === requestId) setGeneratedError(requestError instanceof Error ? requestError.message : 'Generated-code analysis failed.') }
    finally { if (generatedRequest.current === requestId) setGeneratedLoading(false) }
  }

  async function handleGenerateAlternative() {
    if (!originalSource.trim()) { setGenerationError('Enter source code before generating an alternative.'); return }
    const requestId = ++generationRequest.current
    const submittedSource = originalSource; const submittedLanguage = originalLanguage
    setGenerationLoading(true); setGenerationError(''); setCopyStatus(''); setEditorNotice('')
    try {
      const result = await generateAlternative(submittedLanguage, submittedSource)
      if (generationRequest.current === requestId && originalSource === submittedSource && originalLanguage === submittedLanguage) {
        setAlternative(result); setGeneratedSource(result.generated_code); setGeneratedLanguage(result.language); setGeneratedOrigin({ source: submittedSource, language: submittedLanguage }); setGeneratedEdited(false); setGeneratedAnalysis(null); setGeneratedError(''); setShowComparison(false)
      }
    } catch (requestError) { if (generationRequest.current === requestId) setGenerationError(requestError instanceof Error ? requestError.message : 'Alternative generation failed.') }
    finally { if (generationRequest.current === requestId) setGenerationLoading(false) }
  }

  function clearGenerated() {
    generationRequest.current += 1; generatedRequest.current += 1; setAlternative(null); setGeneratedSource(''); setGeneratedAnalysis(null); setGeneratedOrigin(null); setGeneratedEdited(false); setGeneratedError(''); setGenerationError(''); setCopyStatus(''); setShowComparison(false)
  }

  async function copyAlternative(code: string) {
    try { await navigator.clipboard.writeText(code); setCopyStatus('Copied') } catch { setCopyStatus('Copy failed; select the code manually.') }
  }

  function inspectToken(token: AnalysisResult['tokens'][number]) {
    const selection = mapTokenToDfa(token)
    if (!selection) { setSelectedToken(null); setTokenNotice(tokenDfaUnavailableReason(token)); return }
    setSelectedToken(selection); setTokenNotice(''); setActiveView('automata')
  }

  function locateDiagnostic(diagnostic: Diagnostic, source: string, sourceRef: RefObject<HTMLTextAreaElement | null>) {
    if (!diagnostic.line) return
    const linesBefore = source.split('\n').slice(0, diagnostic.line - 1).join('\n')
    const lineStart = linesBefore.length + (diagnostic.line > 1 ? 1 : 0)
    const lineText = source.split('\n')[diagnostic.line - 1] ?? ''
    const columnOffset = Math.max((diagnostic.column ?? 1) - 1, 0)
    sourceRef.current?.focus(); sourceRef.current?.setSelectionRange(lineStart + Math.min(columnOffset, lineText.length), lineStart + lineText.length)
  }

  const originalCurrent = isCurrent(originalAnalysis, originalSource, originalLanguage)
  const generatedCurrent = isCurrent(generatedAnalysis, generatedSource, generatedLanguage)
  const languagesMatch = originalLanguage === generatedLanguage
  const canCompare = originalCurrent && generatedCurrent && languagesMatch
  const comparison = useMemo(() => canCompare ? buildComparison(originalAnalysis.result, generatedAnalysis.result, originalSource, generatedSource) : null, [canCompare, originalAnalysis, generatedAnalysis, originalSource, generatedSource])
  const relationshipStale = Boolean(generatedOrigin && (generatedOrigin.source !== originalSource || generatedOrigin.language !== originalLanguage))

  return <main className="app-shell">
    <header className="hero"><div><p className="eyebrow">CODE ANALYSIS WORKSPACE</p><h1>CodeLens AI</h1><p className="subtitle">Dual validation for Mini Python and Mini C</p></div><div className={`connection connection-${connection}`} role="status"><span className="status-dot" />{connection === 'checking' ? 'Checking backend…' : connection === 'connected' ? 'Backend connected' : 'Backend unavailable'}</div></header>
    <nav className="workspace-nav" aria-label="Workspace sections" role="tablist"><button type="button" role="tab" aria-selected={activeView === 'analyzer'} className={activeView === 'analyzer' ? 'active-tab' : ''} onClick={() => setActiveView('analyzer')}>Dual Analyzer</button><button type="button" role="tab" aria-selected={activeView === 'automata'} className={activeView === 'automata' ? 'active-tab' : ''} onClick={() => setActiveView('automata')}>Automata Lab</button></nav>
    {activeView === 'analyzer' && <>
      <section className="workflow-intro"><strong>Analyze, validate, compare</strong><span>Groq-generated code is placed in Editor B automatically. Both editors use the deterministic analyzer independently.</span></section>
      <div className="dual-editors">
        <CodeEditorPanel kind="original" source={originalSource} language={originalLanguage} languages={languages} loading={originalLoading} error={originalError} valid={originalCurrent ? originalAnalysis.result.success : null} edited={false} relationshipStale={false} onSourceChange={updateOriginalSource} onLanguageChange={updateOriginalLanguage} onAnalyze={handleAnalyzeOriginal} sourceRef={originalSourceRef} />
        <CodeEditorPanel kind="generated" source={generatedSource} language={generatedLanguage} languages={languages} loading={generatedLoading || generationLoading} error={generatedError || generationError} valid={generatedCurrent ? generatedAnalysis.result.success : null} edited={generatedEdited} relationshipStale={relationshipStale} onSourceChange={updateGeneratedSource} onLanguageChange={updateGeneratedLanguage} onAnalyze={handleAnalyzeGenerated} onGenerate={handleGenerateAlternative} onClear={clearGenerated} sourceRef={generatedSourceRef} />
      </div>
      <div className="generation-note">{alternative ? <AlternativePanel alternative={alternative} copyStatus={copyStatus} onCopy={copyAlternative} onUse={() => { generatedSourceRef.current?.focus(); setEditorNotice('Generated code is ready in Editor B. Validate it independently before comparing.') }} /> : <div className="ai-placeholder"><div><p className="eyebrow">GROQ GENERATION</p><h2>Generate an alternative</h2><p>Generate a separate educational implementation from the original source. Editor A will never be overwritten.</p></div><button type="button" className="secondary-button" onClick={handleGenerateAlternative} disabled={generationLoading}>{generationLoading ? 'Generating…' : 'Generate Alternative'}</button></div>}{editorNotice && <p className="editor-notice" role="status">{editorNotice}</p>}</div>
      {originalCurrent && <AnalysisResults title="Original Analysis Output" analysis={originalAnalysis.result} onLocate={(diagnostic) => locateDiagnostic(diagnostic, originalSource, originalSourceRef)} onInspectToken={inspectToken} tokenNotice={tokenNotice} />}
      {generatedCurrent && <AnalysisResults title="Generated Analysis Output" analysis={generatedAnalysis.result} onLocate={(diagnostic) => locateDiagnostic(diagnostic, generatedSource, generatedSourceRef)} />}
      <section className="comparison-section" aria-labelledby="comparison-action-heading"><div className="comparison-action"><div><p className="eyebrow">COMPARE RESULTS</p><h2 id="comparison-action-heading">Original versus generated</h2><p>{canCompare ? 'Both current analysis results are ready.' : !generatedSource ? 'Generate or enter code in Editor B, then validate both sides.' : !originalCurrent || !generatedCurrent ? 'Validate both current source versions to enable comparison.' : 'The languages must match before comparison.'}</p></div><div className="comparison-controls"><span className="pill">{canCompare ? 'Ready' : 'Waiting for current results'}</span><button type="button" onClick={() => setShowComparison(true)} disabled={!canCompare}>Compare Results</button></div></div>{showComparison && comparison && <ComparisonReport report={comparison} language={originalLanguage} />}</section>
    </>}
    {activeView === 'automata' && <AutomataLab selectedToken={selectedToken} />}
    <footer>Mini Python and Mini C are educational subsets. CodeLens AI analyzes source text only; it never executes submitted code.</footer>
  </main>
}

function AnalysisResults({ title, analysis, onLocate, onInspectToken, tokenNotice }: { title: string; analysis: AnalysisResult; onLocate: (diagnostic: Diagnostic) => void; onInspectToken?: (token: AnalysisResult['tokens'][number]) => void; tokenNotice?: string }) {
  const lexicalDiagnostics = useMemo(() => analysis.diagnostics.filter((diagnostic) => lexicalCodes.has(diagnostic.code)), [analysis.diagnostics])
  const syntaxDiagnostics = useMemo(() => analysis.diagnostics.filter((diagnostic) => !lexicalCodes.has(diagnostic.code)), [analysis.diagnostics])
  const warningCount = analysis.diagnostics.filter((diagnostic) => diagnostic.severity === 'warning').length
  return <section className="analysis-results" aria-label={title}><div className="analysis-output-heading"><div><p className="eyebrow">VALIDATION RESULTS</p><h2>{title}</h2></div><span className={`validation-pill ${analysis.success ? 'valid' : 'invalid'}`}>{analysis.success ? 'Lexical and syntax checks passed.' : 'Lexical or syntax diagnostics present.'}</span></div><div className={`analysis-status ${analysis.success ? 'success' : 'failure'}`}><div><strong>{analysis.success ? 'Lexical and syntax checks passed.' : 'Issues found'}</strong><span>{analysis.language === 'mini_python' ? 'Mini Python' : 'Mini C'} · {analysis.grammar_version}</span></div><span>{analysis.success ? 'No lexical or syntax diagnostics' : `${analysis.diagnostics.length} diagnostic${analysis.diagnostics.length === 1 ? '' : 's'}`}</span></div><div className="summary-row"><span><strong>{analysis.tokens.length}</strong> tokens</span><span><strong>{lexicalDiagnostics.length}</strong> lexical</span><span><strong>{syntaxDiagnostics.length}</strong> syntax</span><span><strong>{warningCount}</strong> warnings</span></div><p className="validation-explanation">{analysis.success ? 'Static lexical and syntax analysis found no errors in the supported language subset. This does not establish runtime correctness or semantic equivalence.' : 'Static analysis found lexical or syntax diagnostics in the supported language subset. It does not execute the source or establish runtime correctness.'}</p><div className="results-grid analysis-grid"><TokenPanel tokens={analysis.tokens} onInspectToken={onInspectToken} tokenNotice={tokenNotice ?? ''} /><DiagnosticPanel title="Lexical diagnostics" diagnostics={lexicalDiagnostics} onLocate={onLocate} /><DiagnosticPanel title="Syntax diagnostics" diagnostics={syntaxDiagnostics} onLocate={onLocate} /><AstPanel tree={analysis.parse_tree ?? analysis.tree} /></div><p className="analysis-limit">Static analysis only. This output does not execute the source or establish runtime behavior.</p></section>
}

function TokenPanel({ tokens, onInspectToken, tokenNotice }: { tokens: AnalysisResult['tokens']; onInspectToken?: (token: AnalysisResult['tokens'][number]) => void; tokenNotice: string }) {
  return <article className="result-panel token-panel"><h3>Token stream <span>{tokens.length}</span></h3><div className="table-scroll"><table><thead><tr><th>Type</th><th>Lexeme</th><th>Location</th></tr></thead><tbody>{tokens.map((token, index) => { const selection = mapTokenToDfa(token); const unavailableReason = tokenDfaUnavailableReason(token); return <tr key={`${token.type}-${index}`}><td>{token.type}</td><td>{selection && onInspectToken ? <button type="button" className="token-inspect" onClick={() => onInspectToken(token)} title="Inspect token with DFA" aria-label={`Inspect ${token.lexeme || token.type} token with DFA`}><code>{token.lexeme || '∅'}</code></button> : <code title={unavailableReason}>{token.lexeme || '∅'}</code>}</td><td>{token.line}:{token.column}{selection && onInspectToken ? <span className="token-action-hint"> · DFA</span> : <span className="token-unavailable"> · static</span>}</td></tr> })}</tbody></table></div>{tokenNotice && <p className="token-notice" role="status">{tokenNotice}</p>}<p className="token-help">{onInspectToken ? 'Validated eligible lexemes can be inspected with the educational DFAs.' : 'Generated tokens are independently analyzed; DFA navigation remains available from the original token stream.'}</p></article>
}

function DiagnosticPanel({ title, diagnostics, onLocate }: { title: string; diagnostics: Diagnostic[]; onLocate: (diagnostic: Diagnostic) => void }) {
  return <article className="result-panel diagnostic-panel"><h3>{title} <span>{diagnostics.length}</span></h3>{diagnostics.length === 0 ? <p className="diagnostic-clear">No diagnostics</p> : <ul>{diagnostics.map((diagnostic, index) => <li key={`${diagnostic.code}-${index}`}><button type="button" className={`diagnostic-item severity-${diagnostic.severity}`} onClick={() => onLocate(diagnostic)} disabled={!diagnostic.line} aria-label={`Locate ${diagnostic.code} at line ${diagnostic.line ?? 'unknown'}`}><strong>{diagnostic.code}</strong><span>{diagnostic.message}</span><small>{diagnostic.line ? `Line ${diagnostic.line}, column ${diagnostic.column ?? '?'}` : 'Location unavailable'}</small></button></li>)}</ul>}</article>
}

function AstPanel({ tree }: { tree: ParseNode | null }) {
  return <article className="result-panel tree-panel"><h3>Parse tree / AST</h3><p className="tree-help">Grammar nodes are shown with terminal lexemes and source locations where the parser produced them.</p>{tree && typeof tree === 'object' && typeof tree.type === 'string' ? <ul className="tree-root"><TreeNode tree={tree} depth={0} /></ul> : <p>No complete parse tree was produced; see diagnostics and available tokens.</p>}</article>
}

function TreeNode({ tree, depth }: { tree: ParseNode; depth: number }) {
  const [open, setOpen] = useState(true)
  const children = Array.isArray(tree.children) ? tree.children.filter((child): child is ParseNode => Boolean(child && typeof child === 'object' && typeof child.type === 'string')) : []
  const attributes = tree.attributes && typeof tree.attributes === 'object' ? tree.attributes : {}
  const incomplete = attributes.incomplete === true || tree.type.startsWith('Error')
  if (depth > 100) return <li className="tree-node tree-incomplete">Tree depth limit reached.</li>
  if (tree.type === 'Terminal') {
    const tokenType = typeof attributes.token_type === 'string' ? attributes.token_type : 'TOKEN'
    const lexeme = typeof attributes.lexeme === 'string' ? attributes.lexeme : ''
    const location = attributes.line ? ` · ${attributes.line}:${attributes.column ?? '?'}` : ''
    return <li className="tree-node tree-terminal"><span className="tree-terminal-marker">•</span><span className="tree-type">{tokenType}</span><code>{lexeme || '∅'}</code><small>{location}</small></li>
  }
  return <li className={`tree-node ${incomplete ? 'tree-incomplete' : ''}`}><button className="tree-toggle" type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} ${tree.type} node`}>{children.length > 0 ? (open ? '⌄' : '›') : '•'}</button><span className="tree-type">{tree.type}</span>{incomplete && <span className="tree-warning">incomplete/error</span>}<span className="tree-attributes">{Object.entries(attributes).filter(([key]) => key !== 'incomplete').map(([key, value]) => `${key}=${String(value)}`).join(' · ')}</span>{open && children.length > 0 && <ul>{children.map((child, index) => <TreeNode key={`${child.type}-${index}`} tree={child} depth={depth + 1} />)}</ul>}</li>
}

export default App
