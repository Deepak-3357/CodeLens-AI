import { useEffect, useMemo, useRef, useState } from 'react'
import { getAutomata, getAutomaton, simulateAutomaton, type AutomatonDefinition, type AutomatonSimulation, type AutomatonTraceStep } from '../services/api'
import type { TokenDfaSelection } from '../services/tokenDfa'

const positions = [{ x: 90, y: 130 }, { x: 300, y: 130 }, { x: 510, y: 130 }, { x: 720, y: 130 }, { x: 930, y: 130 }]

export default function AutomataLab({ selectedToken }: { selectedToken: TokenDfaSelection | null }) {
  const [catalog, setCatalog] = useState<AutomatonDefinition[]>([])
  const [selectedId, setSelectedId] = useState('identifier')
  const [definition, setDefinition] = useState<AutomatonDefinition | null>(null)
  const [input, setInput] = useState('student2')
  const [simulation, setSimulation] = useState<AutomatonSimulation | null>(null)
  const [cursor, setCursor] = useState(-1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => { getAutomata().then((response) => setCatalog(response.automata)).catch(() => setError('Automata definitions could not be loaded.')).finally(() => setLoading(false)) }, [])
  useEffect(() => {
    setSimulation(null)
    setCursor(-1)
    if (selectedId) getAutomaton(selectedId).then(setDefinition).catch(() => setError('The selected automaton could not be loaded.'))
  }, [selectedId])

  useEffect(() => {
    if (!selectedToken) return
    setSelectedId(selectedToken.automatonId)
    setInput(selectedToken.lexeme)
    setSimulation(null)
    setCursor(-1)
  }, [selectedToken])

  useEffect(() => {
    if (!selectedToken || definition?.id !== selectedToken.automatonId) return
    let cancelled = false
    setError('')
    simulateAutomaton(selectedToken.automatonId, selectedToken.lexeme)
      .then((result) => { if (!cancelled) { setSimulation(result); setCursor(-1) } })
      .catch((requestError) => { if (!cancelled) setError(requestError instanceof Error ? requestError.message : 'Simulation failed.') })
    return () => { cancelled = true }
  }, [definition, selectedToken])

  const activeStep = simulation && cursor >= 0 ? simulation.trace[cursor] : null
  const activeState = activeStep ? activeStep.next_state : definition?.start_state
  const activeTransition = activeStep ? { from: activeStep.current_state, to: activeStep.next_state, label: activeStep.transition } : null

  async function run() {
    setError('')
    setSimulation(null)
    setCursor(-1)
    try {
      const result = await simulateAutomaton(selectedId, input)
      setSimulation(result)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Simulation failed.')
    }
  }

  function reset() { setSimulation(null); setCursor(-1) }

  function step(delta: number) {
    if (!simulation || simulation.trace.length === 0) return
    setCursor((current) => Math.max(-1, Math.min(simulation.trace.length - 1, current + delta)))
  }

  return <section className="automata-lab" aria-labelledby="automata-heading"><div className="lab-heading"><div><p className="eyebrow">AUTOMATA LAB</p><h2 id="automata-heading">DFA lexical pattern visualizer</h2><p className="lab-description">Explore how deterministic state transitions recognize limited regular patterns used in lexical analysis.</p></div><label>Automaton<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={loading}>{catalog.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></div>{error && <p className="error-message" role="alert">{error}</p>}{definition && <><div className="automaton-meta"><strong>{definition.name}</strong><span>{definition.description}</span><code>{definition.pattern}</code></div>{selectedToken?.automatonId === definition.id && <div className="token-context" aria-label="Selected token for DFA inspection"><strong>Inspecting token <code>{selectedToken.lexeme}</code></strong><span>{selectedToken.tokenType} · line {selectedToken.line}, column {selectedToken.column}</span><small>{selectedToken.explanation}</small></div>}<DfaGraph definition={definition} activeState={activeState} activeTransition={activeTransition} animationKey={cursor} /><SimulationStepStatus simulation={simulation} activeStep={activeStep} cursor={cursor} /><div className="simulation-controls"><label htmlFor={`automata-input-${selectedId}`}>Test input</label><input id={`automata-input-${selectedId}`} value={input} onChange={(event) => { setInput(event.target.value); reset() }} placeholder="Enter characters to simulate" /><button type="button" onClick={run} disabled={loading}>Run</button><button type="button" className="secondary-button" onClick={() => step(-1)} disabled={!simulation || cursor < 0}>Previous step</button><button type="button" className="secondary-button" onClick={() => step(1)} disabled={!simulation || cursor >= simulation.trace.length - 1}>Next step</button><button type="button" className="secondary-button" onClick={reset}>Reset</button></div>{simulation ? <SimulationResult simulation={simulation} cursor={cursor} /> : <p className="lab-empty">Run the automaton to create an execution trace. A result is not shown before simulation.</p>}</>}</section>
}

function useReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(false)
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(mediaQuery.matches)
    update()
    mediaQuery.addEventListener('change', update)
    return () => mediaQuery.removeEventListener('change', update)
  }, [])
  return reducedMotion
}

type ActiveTransition = { from: string; to: string; label: string } | null

function DfaGraph({ definition, activeState, activeTransition, animationKey }: { definition: AutomatonDefinition; activeState?: string; activeTransition: ActiveTransition; animationKey: number }) {
  const graphWidth = Math.max(1040, definition.states.length * 160 + 80)
  const locations = useMemo(() => Object.fromEntries(definition.states.map((state, index) => [state.id, positions[index] ?? { x: 90 + index * 160, y: 130 }])), [definition.states])
  const reducedMotion = useReducedMotion()
  return <div className="dfa-graph-wrap"><svg className="dfa-graph" style={{ width: graphWidth }} viewBox={`0 0 ${graphWidth} 250`} role="img" aria-label={`${definition.name} deterministic finite automaton graph`}><defs><marker id="dfa-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="currentColor" /></marker></defs><line x1="15" y1="130" x2="55" y2="130" className="start-arrow" markerEnd="url(#dfa-arrow)" />{definition.transitions.map((transition, index) => { const from = locations[transition.from]; const to = locations[transition.to]; if (!from || !to) return null; const active = activeTransition?.from === transition.from && activeTransition.to === transition.to && activeTransition.label === transition.label; const selfLoop = transition.from === transition.to; const path = selfLoop ? `M ${from.x - 20} ${from.y - 27} Q ${from.x} ${from.y - 82} ${from.x + 20} ${from.y - 27}` : `M ${from.x + 34} ${from.y} L ${to.x - 34} ${to.y}`; const pathId = `dfa-transition-${definition.id}-${index}`; return <g key={`${transition.from}-${transition.to}-${index}`} className={active ? 'active-edge' : ''}>{selfLoop ? <><path id={pathId} d={path} markerEnd="url(#dfa-arrow)" /><text x={from.x} y={from.y - 82} textAnchor="middle">{transition.label}</text></> : <><path id={pathId} d={path} markerEnd="url(#dfa-arrow)" /><text x={(from.x + to.x) / 2} y={from.y - 12} textAnchor="middle">{transition.label}</text></>}{active && <TransitionMarker key={`${pathId}-${animationKey}`} path={path} reducedMotion={reducedMotion} />}</g> })}{definition.states.map((state) => { const point = locations[state.id]; const accepting = definition.accepting_states.includes(state.id); const active = state.id === activeState; return <g key={state.id} className={`${accepting ? 'accepting-state' : ''} ${active ? 'active-state' : ''}`}><circle cx={point.x} cy={point.y} r="34" /><text x={point.x} y={point.y + 4} textAnchor="middle">{state.id}</text><text x={point.x} y={point.y + 54} textAnchor="middle">{state.label}</text></g> })}</svg></div>
}

function TransitionMarker({ path, reducedMotion }: { path: string; reducedMotion: boolean }) {
  if (reducedMotion) return <circle className="transition-marker" cx="0" cy="0" r="7" aria-hidden="true"><animateMotion path={path} dur="0s" fill="freeze" /></circle>
  return <circle className="transition-marker" cx="0" cy="0" r="7" aria-hidden="true"><animateMotion path={path} dur="700ms" fill="freeze" /></circle>
}

function SimulationStepStatus({ simulation, activeStep, cursor }: { simulation: AutomatonSimulation | null; activeStep: AutomatonTraceStep | null; cursor: number }) {
  if (!simulation) return null
  if (!activeStep) return <div className="simulation-step-status" aria-live="polite"><strong>Ready to step</strong><span>0 of {simulation.trace.length} characters consumed · Starting at {simulation.trace[0]?.current_state ?? 'the start state'}</span></div>
  const selfLoop = activeStep.current_state === activeStep.next_state
  return <div className={`simulation-step-status ${selfLoop ? 'self-loop-status' : ''}`} aria-live="polite"><strong>Step {activeStep.step} of {simulation.trace.length} — Reading <code>{formatCharacter(activeStep.character)}</code></strong><span>{activeStep.current_state} → {activeStep.next_state}{selfLoop ? ' (self-loop)' : ''} · {cursor === simulation.trace.length - 1 ? 'End of input' : 'Transition highlighted'}</span></div>
}

function formatCharacter(character: string) { return character === ' ' ? 'space' : character === '\t' ? 'tab' : `"${character}"` }

function SimulationResult({ simulation, cursor }: { simulation: AutomatonSimulation; cursor: number }) {
  const activeRowRef = useRef<HTMLTableRowElement | null>(null)
  useEffect(() => { activeRowRef.current?.scrollIntoView({ block: 'nearest' }) }, [cursor])
  return <div className="simulation-result"><div className={`simulation-status ${simulation.accepted ? 'success' : 'failure'}`}><strong>{simulation.accepted ? 'Accepted' : 'Rejected'}</strong><span>Final state: {simulation.final_state} · {simulation.characters_processed} character(s) processed</span></div><p>{simulation.explanation}</p><div className="trace-scroll"><table className="trace-table"><thead><tr><th>Step</th><th>Character</th><th>Current state</th><th>Transition</th><th>Next state</th></tr></thead><tbody>{simulation.trace.map((step, index) => <tr ref={index === cursor ? activeRowRef : undefined} className={index === cursor ? 'active-trace' : ''} key={step.step}><td>{step.step}</td><td><code>{formatCharacter(step.character)}</code></td><td>{step.current_state}</td><td>{step.transition}</td><td>{step.next_state}</td></tr>)}</tbody></table></div></div>
}
