import { useEffect, useState } from 'react'
import { getHealth, getLanguages, type Language } from './services/api'

const panels = ['Tokens', 'Lexical errors', 'Syntax errors', 'Parse tree / AST', 'Comparison results']

function App() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState('mini_python')
  const [source, setSource] = useState('')
  const [connection, setConnection] = useState<'checking' | 'connected' | 'failed'>('checking')
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getHealth(), getLanguages()])
      .then(([, languageResponse]) => {
        setLanguages(languageResponse.languages)
        setConnection('connected')
      })
      .catch(() => {
        setConnection('failed')
        setError('The backend is unavailable. Start FastAPI or check VITE_API_BASE_URL.')
      })
  }, [])

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">FOUNDATION / PHASE 1</p>
          <h1>CodeLens AI</h1>
          <p className="subtitle">AI-Assisted Mini Python and Mini C Code Analysis</p>
        </div>
        <div className={`connection connection-${connection}`} role="status">
          <span className="status-dot" />
          {connection === 'checking' ? 'Checking backend…' : connection === 'connected' ? 'Backend connected' : 'Backend unavailable'}
        </div>
      </header>

      <section className="workspace-card" aria-labelledby="workspace-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ANALYSIS WORKSPACE</p>
            <h2 id="workspace-heading">Prepare a program</h2>
          </div>
          <label>
            Language
            <select value={selectedLanguage} onChange={(event) => setSelectedLanguage(event.target.value)}>
              {languages.length > 0 ? languages.map((language) => <option key={language.id} value={language.id}>{language.name}</option>) : <><option value="mini_python">Mini Python</option><option value="mini_c">Mini C</option></>}
            </select>
          </label>
        </div>
        <label className="editor-label" htmlFor="source-code">Original code</label>
        <textarea id="source-code" value={source} onChange={(event) => setSource(event.target.value)} placeholder="Paste a Mini Python or Mini C program here…" />
        <div className="action-row">
          <button type="button" onClick={() => setError('Analysis is planned for a later phase.')}>
            Analyze program
          </button>
          <span className="scope-note">Analysis engine coming in a later phase.</span>
        </div>
        {error && <p className="error-message" role="alert">{error}</p>}
      </section>

      <section className="results-grid" aria-label="Analysis results">
        {panels.map((panel) => <article className="result-panel" key={panel}><h3>{panel}</h3><p>Results will appear here after the analysis engine is implemented.</p></article>)}
      </section>

      <section className="ai-placeholder"><div><p className="eyebrow">FUTURE CAPABILITY</p><h2>AI alternative generation</h2><p>Alternative code will be generated and analyzed independently only after the backend provider adapter is added.</p></div><span className="pill">Not enabled</span></section>
      <footer>Mini Python and Mini C are deliberately limited educational subsets. Submitted code is never executed.</footer>
    </main>
  )
}

export default App
