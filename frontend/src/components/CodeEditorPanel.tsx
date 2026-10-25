import type { RefObject } from 'react'
import type { Language } from '../services/api'

export default function CodeEditorPanel({ kind, source, language, languages, loading, error, valid, edited, relationshipStale, onSourceChange, onLanguageChange, onAnalyze, onGenerate, onClear, sourceRef }: { kind: 'original' | 'generated'; source: string; language: string; languages: Language[]; loading: boolean; error: string; valid: boolean | null; edited: boolean; relationshipStale: boolean; onSourceChange: (value: string) => void; onLanguageChange: (value: string) => void; onAnalyze: () => void; onGenerate?: () => void; onClear?: () => void; sourceRef: RefObject<HTMLTextAreaElement | null> }) {
  const title = kind === 'original' ? 'Original User Code' : 'Groq-Generated Code'
  const label = kind === 'original' ? 'Original source' : 'Generated source'
  const lineCount = Math.max(source.split('\n').length, 1)
  return <section className={`code-editor-panel ${kind}-editor`} aria-labelledby={`${kind}-editor-heading`}>
    <div className="editor-panel-heading"><div><p className="eyebrow">{kind === 'original' ? 'EDITOR A' : 'EDITOR B'}</p><h2 id={`${kind}-editor-heading`}>{title}</h2></div><span className={`validation-pill ${valid === true ? 'valid' : valid === false ? 'invalid' : 'pending'}`}>{valid === true ? 'Validated' : valid === false ? 'Issues found' : 'Not validated'}</span></div>
    <label>{kind === 'original' ? 'Language' : 'Language indicator'}<select value={language} onChange={(event) => onLanguageChange(event.target.value)}>{languages.length > 0 ? languages.map((item) => <option key={item.id} value={item.id}>{item.name}</option>) : <><option value="mini_python">Mini Python</option><option value="mini_c">Mini C</option></>}</select></label>
    <label className="editor-label" htmlFor={`${kind}-source`}>{label}{kind === 'generated' && edited && <span className="edited-label"> · edited after generation</span>}</label>
    <div className="editor-shell"><div className="line-gutter" aria-hidden="true">{Array.from({ length: lineCount }, (_, index) => <span key={index}>{index + 1}</span>)}</div><textarea ref={sourceRef} id={`${kind}-source`} value={source} onChange={(event) => onSourceChange(event.target.value)} placeholder={kind === 'generated' ? 'Generate an alternative to populate this editor…' : 'Paste Mini Python or Mini C source here…'} spellCheck={false} /></div>
    <div className="editor-actions"><button type="button" onClick={onAnalyze} disabled={loading || !source.trim()}>{loading ? 'Validating…' : 'Analyze / Validate'}</button>{kind === 'generated' && onGenerate && <button type="button" className="secondary-button" onClick={onGenerate} disabled={loading}>{source ? 'Regenerate Alternative' : 'Generate Alternative'}</button>}{kind === 'generated' && onClear && source && <button type="button" className="text-button" onClick={onClear}>Clear</button>}</div>
    {error && <p className="error-message" role="alert">{error}</p>}{relationshipStale && <p className="stale-message" role="status">Generated from an older original source or language. Regenerate to refresh the relationship.</p>}
  </section>
}
