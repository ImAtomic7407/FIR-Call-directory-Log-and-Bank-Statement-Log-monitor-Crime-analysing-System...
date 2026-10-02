import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { commColor, ETYPE_COLORS, ETYPE_LABEL, SEV } from './theme'
import { GLOSSARY, IMPORTANCE_LABEL, RULE_TEXT, ALERT_TYPE, ALERT_HELP } from './glossary'

// openHelp(sectionId?) from anywhere; set by App.
export const HelpContext = createContext({ openHelp: () => {}, ask: () => {}, openRecord: () => {} })
export const useHelp = () => useContext(HelpContext)

// Small "?" that shows a real popover on hover, keyboard focus, click or tap.
export function Info({ term, text, section }) {
  const { openHelp } = useHelp()
  const [g0, g1, g2] = GLOSSARY[term] || []
  const title = text ? null : g0
  const body = text || g1 || ''
  const sec = section || g2
  const btn = useRef(null)
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [pos, setPos] = useState(null)
  const hideT = useRef(null)

  const show = () => { clearTimeout(hideT.current); setOpen(true) }
  const hide = () => { if (!pinned) hideT.current = setTimeout(() => setOpen(false), 120) }

  useLayoutEffect(() => {
    if (!open || !btn.current) return
    const r = btn.current.getBoundingClientRect()
    const W = 256, vw = window.innerWidth
    const left = Math.min(Math.max(8, r.left + r.width / 2 - W / 2), vw - W - 8)
    const below = r.bottom + 160 < window.innerHeight
    setPos({ left, top: below ? r.bottom + 8 : undefined, bottom: below ? undefined : window.innerHeight - r.top + 8, W })
  }, [open])

  useEffect(() => {
    if (!pinned) return
    const close = e => { if (e.type === 'keydown' ? e.key === 'Escape' : !btn.current?.contains(e.target) && !e.target.closest?.('[data-info-pop]')) { setPinned(false); setOpen(false) } }
    document.addEventListener('mousedown', close); document.addEventListener('keydown', close)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close) }
  }, [pinned])

  return (
    <>
      <button ref={btn} type="button" aria-label={`What is ${title || 'this'}?`} aria-expanded={open}
        onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
        onClick={e => { e.stopPropagation(); setPinned(p => !p); setOpen(true) }}
        className={`ml-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border align-middle text-[9px] font-semibold normal-case leading-none tracking-normal transition-colors ${open ? 'border-sky-400 bg-sky-400/15 text-sky-300' : 'border-slate-600 text-slate-400 hover:border-sky-400 hover:text-sky-300'}`}>?</button>
      {open && pos && createPortal(
        <div data-info-pop role="tooltip" onMouseEnter={show} onMouseLeave={hide}
          style={{ left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.W }}
          className="fixed z-[70] rounded-lg border border-slate-700 bg-slate-900/95 p-3 text-left text-xs normal-case tracking-normal shadow-2xl shadow-black/50 backdrop-blur">
          {title && <div className="mb-1 font-semibold text-slate-100">{title}</div>}
          <p className="font-normal leading-relaxed text-slate-300">{body}</p>
          {sec && <button type="button" onClick={() => { setOpen(false); setPinned(false); openHelp(sec) }} className="mt-2 font-medium text-sky-300 hover:text-sky-200">Learn more in the guide →</button>}
        </div>, document.body)}
    </>
  )
}

const Kbd = ({ children }) => <kbd className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-200">{children}</kbd>

function NodeShape({ type }) {
  const c = type === 'person' ? '#38bdf8' : '#64748b'
  const s = { person: <circle cx="10" cy="10" r="7" />, phone: <rect x="3" y="4" width="14" height="12" rx="3" />, vehicle: <path d="M10 2 18 10 10 18 2 10Z" />,
    org: <path d="M6 3h8l4 7-4 7H6l-4-7Z" />, location: <path d="M10 3 17.5 16H2.5Z" strokeLinejoin="round" /> }[type]
  return <svg viewBox="0 0 20 20" className="h-5 w-5 shrink-0" fill={c} stroke={c}>{s}</svg>
}

function Line({ etype }) {
  const dash = etype === 'reported_use' ? '5 3' : ['uses_phone', 'frequents', 'works_with', 'uses_vehicle'].includes(etype) ? '1.5 3' : undefined
  return <svg viewBox="0 0 36 8" className="h-2 w-9 shrink-0"><line x1="1" y1="4" x2="35" y2="4" stroke={ETYPE_COLORS[etype]} strokeWidth="2.5" strokeDasharray={dash} strokeLinecap="round" />{etype === 'transfer' && <path d="M29 0.5 35 4 29 7.5Z" fill={ETYPE_COLORS[etype]} />}</svg>
}

const EXAMPLES = [
  ['Who matters most', ['Who are the top 5 key persons?', 'Who is Bunty?', 'What is the risk score of Jatin Singhal?']],
  ['Connections', ['How is Bunty connected to Jatin Singhal?', 'Zubair ke contacts batao']],
  ['Money and calls', ['Show transactions above ₹50,000 between Group 1 members', 'Bunty ke calls dikhao']],
  ['Suspicious patterns', ['Koi suspicious pattern dikhao', 'Show circular money flows']],
]

function sections({ health, llm, groups, ask, openRecord }) {
  const pill = 'rounded-md border border-slate-800 bg-slate-800/40'
  return [
    { id: 'start', label: 'Start here', keywords: 'begin tour steps overview how use', body: (
      <div className="space-y-4">
        <p className="text-slate-300">This screen turns police complaints (FIRs), phone call logs and bank transfers into one map of who is connected to whom, and flags patterns worth a closer look. {health && <>It currently holds <b className="text-slate-100">{health.firs} FIRs</b>, <b className="text-slate-100">{health.calls} calls</b>, <b className="text-slate-100">{health.transactions} transfers</b> and <b className="text-slate-100">{health.entities} people</b>.</>} All data is synthetic.</p>
        <ol className="space-y-2">
          {[
            ['Start from an alert', 'The left column lists suspicious patterns, most serious first. Click one: the graph highlights the people involved and the right panel shows the records behind it.'],
            ['Open a person', 'Click any dot (or a name in Key persons). Person details shows their risk score, phones, accounts, and why different FIR mentions were treated as the same person.'],
            ['Check the evidence', 'Every ID chip, like FIR-007, C0123 or T0123, opens the original record. Nothing is shown without a source.'],
            ['Ask in plain words', 'Use Investigator chat in English or Hinglish. Answers cite record IDs and highlight the relevant part of the graph.'],
          ].map(([t, d], i) => (
            <li key={t} className={`flex gap-3 p-3 ${pill}`}>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-xs font-semibold text-sky-300">{i + 1}</span>
              <div><div className="font-medium text-slate-100">{t}</div><div className="text-slate-400">{d}</div></div>
            </li>
          ))}
        </ol>
        <p className="text-slate-400">Too busy? Use <b className="text-slate-300">Filters</b> to hide kinds of dots and lines, narrow the dates, or show one group only. Nothing is deleted, only hidden.</p>
      </div>) },
    { id: 'graph', label: 'Reading the graph', keywords: 'dot node line edge colour color shape size legend zoom fit layout group highlight', body: (
      <div className="space-y-4">
        <div>
          <h4 className="mb-2 font-semibold text-slate-200">Dots</h4>
          <div className="grid grid-cols-2 gap-1.5">
            {[['person', 'Person'], ['phone', 'Phone number'], ['vehicle', 'Vehicle'], ['org', 'Organisation'], ['location', 'Location']].map(([k, v]) => <div key={k} className={`flex items-center gap-2 px-2 py-1.5 ${pill}`}><NodeShape type={k} /><span className="text-slate-300">{v}</span></div>)}
          </div>
          <ul className="mt-2 space-y-1 text-slate-400">
            <li><b className="text-slate-300">Colour</b> = the person's group (people who mostly deal with each other).</li>
            <li><b className="text-slate-300">Size</b> = importance in the network. Bigger means more central.</li>
            <li><span className="mr-1 inline-block h-3 w-3 rounded-full border-2 border-red-500 align-middle" /><b className="text-slate-300">Red ring</b> = risk score 60 or more.</li>
            <li><span className="mr-1 inline-block h-3 w-3 rounded-full border-2 border-yellow-300 align-middle" /><b className="text-slate-300">Yellow ring</b> = highlighted by an alert or a chat answer; everything else fades.</li>
          </ul>
        </div>
        {groups?.length > 0 && <div>
          <h4 className="mb-2 font-semibold text-slate-200">Groups right now</h4>
          <div className="flex flex-wrap gap-1.5">{groups.map(g => <span key={g.id} className={`flex items-center gap-1.5 px-2 py-1 ${pill} text-slate-300`}><i className="h-2 w-2 rounded-full" style={{ background: commColor(g.id) }} />{g.label}</span>)}</div>
        </div>}
        <div>
          <h4 className="mb-2 font-semibold text-slate-200">Lines</h4>
          <div className="grid grid-cols-2 gap-1.5">{Object.entries(ETYPE_LABEL).map(([k, v]) => <div key={k} className={`flex items-center gap-2 px-2 py-1.5 ${pill}`}><Line etype={k} /><span className="text-slate-300">{v}</span></div>)}</div>
          <p className="mt-2 text-slate-400">Thicker lines mean more calls or bigger amounts. Arrows on money lines point to the receiver. Dashed red = a phone number reported for several people.</p>
        </div>
        <div>
          <h4 className="mb-2 font-semibold text-slate-200">Moving around</h4>
          <ul className="space-y-1 text-slate-400"><li>Scroll to zoom, drag the background to pan, drag a dot to move it.</li><li>Click empty space to clear the selection. <b className="text-slate-300">Fit</b> brings everything back in view; <b className="text-slate-300">Re-layout</b> rearranges the dots.</li></ul>
        </div>
      </div>) },
    { id: 'scores', label: 'Scores', keywords: 'risk importance centrality score top 5 key persons number', body: (
      <div className="space-y-4">
        <div>
          <h4 className="mb-1 font-semibold text-slate-200">Risk score (0 to 100)</h4>
          <p className="mb-2 text-slate-400">Three parts added together:</p>
          <div className="flex h-7 overflow-hidden rounded-md text-[10px] font-medium text-slate-950">
            <div className="flex w-[40%] items-center justify-center bg-sky-400">Importance · 40</div>
            <div className="flex w-[40%] items-center justify-center bg-rose-400">Alerts · 40</div>
            <div className="flex w-[20%] items-center justify-center bg-amber-400">Money · 20</div>
          </div>
          <div className="mt-2 flex gap-3 text-slate-400"><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500" />60+ high</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-500" />30 to 59 medium</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />under 30 low</span></div>
          <p className="mt-2 text-slate-500">A high score means "look here first", not "guilty". It is a ranking aid.</p>
        </div>
        <div>
          <h4 className="mb-1 font-semibold text-slate-200">Importance score (0 to 1)</h4>
          <p className="mb-2 text-slate-400">{GLOSSARY.importance[1]} It blends four standard network measures with fixed weights:</p>
          <ul className="space-y-1">{['degree', 'betweenness', 'closeness', 'pagerank'].map(k => <li key={k} className={`px-2 py-1.5 text-slate-300 ${pill}`}>{IMPORTANCE_LABEL[k]}</li>)}</ul>
          <p className="mt-2 text-slate-500">Link strength between two people = calls + 3 × transfers + 2 × FIR links.</p>
        </div>
      </div>) },
    { id: 'alerts', label: 'Alerts', keywords: 'pattern suspicious severity burst circular layering shared vehicle contact location', body: (
      <div className="space-y-3">
        <p className="text-slate-400">{GLOSSARY.alert[1]} Click an alert to highlight it on the graph.</p>
        <div className="flex gap-2">{['high', 'medium', 'low'].map(s => <span key={s} className={`rounded border px-1.5 text-[10px] uppercase ${SEV[s]}`}>{s}</span>)}<span className="text-slate-500">how strongly the pattern stands out</span></div>
        <dl className="space-y-1.5">{Object.entries(ALERT_TYPE).map(([k, v]) => <div key={k} className={`p-2 ${pill}`}><dt className="font-medium text-slate-100">{v}</dt><dd className="text-slate-400">{ALERT_HELP[k]}</dd></div>)}</dl>
      </div>) },
    { id: 'matching', label: 'Same-person matching', keywords: 'resolution alias nickname merge identity shared phone confidence certain likely', body: (
      <div className="space-y-3">
        <p className="text-slate-400">{GLOSSARY.resolution[1]} For example, "Jatinbhai", "J. Singhal" and "Jatin Singhal" become one person.</p>
        <div>
          <h4 className="mb-1.5 font-semibold text-slate-200">Reasons you will see</h4>
          <ul className="space-y-1">{Object.values(RULE_TEXT).map(v => <li key={v} className={`px-2 py-1.5 text-slate-300 ${pill}`}>{v}</li>)}</ul>
        </div>
        <div>
          <h4 className="mb-1.5 font-semibold text-slate-200">How sure</h4>
          <p className="text-slate-400"><b className="text-slate-300">certain</b> 95%+ · <b className="text-slate-300">very likely</b> 85%+ · <b className="text-slate-300">likely</b> 70%+ · <b className="text-slate-300">weak match</b> below that.</p>
        </div>
        <p className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-red-200"><b>Shared phones:</b> {GLOSSARY.shared[1]}</p>
      </div>) },
    { id: 'records', label: 'Records and IDs', keywords: 'fir call transfer transaction id chip evidence source pdf report', body: (
      <div className="space-y-3">
        <p className="text-slate-400">Every number and name traces back to a record. Click a chip to read it. Try these:</p>
        <dl className="space-y-1.5">
          {[['FIR-001', 'FIR', GLOSSARY.fir[1], 'bg-sky-500/15 text-sky-300'], ['C0001', 'Call', GLOSSARY.cdr[1], 'bg-slate-500/20 text-slate-300'], ['T0001', 'Transfer', GLOSSARY.txn[1], 'bg-amber-500/15 text-amber-300'], ['ALR-01', 'Alert', 'One suspicious pattern, with its evidence.', 'bg-rose-500/15 text-rose-300']].map(([id, k, d, cls]) => (
            <div key={id} className={`flex items-start gap-3 p-2 ${pill}`}>
              <button type="button" onClick={() => openRecord(id)} className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] hover:brightness-125 ${cls}`}>{id}</button>
              <div><dt className="font-medium text-slate-100">{k}</dt><dd className="text-slate-400">{d}</dd></div>
            </div>))}
        </dl>
        <p className="text-slate-400"><b className="text-slate-300">Case report PDF</b> (top right) exports the whole network. Each person also has their own PDF in Person details.</p>
      </div>) },
    { id: 'chat', label: 'Asking questions', keywords: 'chat ask question hinglish ai llm model answer template how answered example', body: (
      <div className="space-y-4">
        <div className="space-y-2">
          <p className="text-slate-400">Click an example to ask it now:</p>
          {EXAMPLES.map(([h, qs]) => <div key={h}><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">{h}</div><div className="flex flex-wrap gap-1.5">{qs.map(q => <button key={q} type="button" onClick={() => ask(q)} className="rounded-full border border-slate-700 px-2.5 py-1 text-slate-300 hover:border-sky-500 hover:text-sky-200">{q}</button>)}</div></div>)}
          <p className="text-slate-500">Follow-ups work: after "Who is Bunty?", ask "How is he connected to Jatin Singhal?".</p>
        </div>
        <div>
          <h4 className="mb-1 font-semibold text-slate-200">Can I trust the answer?</h4>
          <p className="text-slate-400">All counting, ranking and path-finding is done by fixed code, not the AI. The AI only works out what you are asking and puts the result into words. If its wording contains any ID or number that is not in the computed result, it is thrown away and a plain template answer is shown instead. Click <b className="text-slate-300">how was this answered?</b> under any reply to see which happened.</p>
        </div>
        <div className={`flex items-start gap-2 p-2 ${pill}`}>
          <i className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${llm?.reachable ? 'bg-emerald-500' : llm?.enabled ? 'bg-amber-500' : 'bg-slate-500'}`} />
          <p className="text-slate-400">{llm?.reachable ? 'The AI model is online: questions are read and answers worded by the AI, then checked.' : llm?.enabled ? 'The AI model is configured but not reachable, so keyword rules and template answers are used. Everything still works.' : 'No AI model is configured: keyword rules and template answers are used. Everything still works.'}</p>
        </div>
      </div>) },
    { id: 'keys', label: 'Shortcuts', keywords: 'keyboard shortcut key', body: (
      <ul className="space-y-1.5">{[[['?'], 'Open this guide'], [['/'], 'Jump to the chat box'], [['Esc'], 'Close a popup or this guide']].map(([k, d]) => <li key={d} className={`flex items-center justify-between px-3 py-2 ${pill}`}><span className="text-slate-300">{d}</span><span className="flex gap-1">{k.map(x => <Kbd key={x}>{x}</Kbd>)}</span></li>)}</ul>) },
  ]
}

const textOf = n => (n == null || typeof n === 'boolean' ? '' : typeof n === 'string' || typeof n === 'number' ? String(n) : Array.isArray(n) ? n.map(textOf).join(' ') : n.props ? textOf(n.props.children) : '')

export function HelpPanel({ section, onClose, ...ctx }) {
  const all = sections(ctx)
  const [cur, setCur] = useState(section || 'start')
  const [q, setQ] = useState('')
  const body = useRef(null)
  useEffect(() => { setCur(section || 'start') }, [section])
  useEffect(() => { body.current?.scrollTo(0, 0) }, [cur])
  useEffect(() => { const k = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [onClose])
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return null
    return all.filter(x => (x.label + ' ' + x.keywords + ' ' + textOf(x.body)).toLowerCase().includes(s))
  }, [q, all])
  const shown = hits ? hits : all.filter(x => x.id === cur)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Guide" className="flex h-[min(640px,88vh)] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 text-sm shadow-2xl shadow-black/60" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-sky-500/20 text-sm font-semibold text-sky-300">?</span>
          <div className="min-w-0 flex-1"><h3 className="text-base font-semibold text-slate-100">Guide</h3><p className="text-[11px] text-slate-500">What everything on this screen means, and where to start</p></div>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search the guide…" className="hidden w-48 rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs outline-none placeholder:text-slate-500 focus:border-sky-500 sm:block" />
          <button onClick={onClose} aria-label="Close guide" className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white">✕</button>
        </div>
        <div className="flex min-h-0 flex-1">
          <nav className="hidden w-48 shrink-0 space-y-0.5 overflow-auto border-r border-slate-800 p-2 sm:block">
            {all.map(x => <button key={x.id} onClick={() => { setQ(''); setCur(x.id) }} className={`w-full rounded-md px-2.5 py-1.5 text-left text-xs ${!hits && cur === x.id ? 'bg-sky-500/15 font-medium text-sky-200' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}>{x.label}</button>)}
          </nav>
          <div ref={body} className="min-w-0 flex-1 overflow-auto p-5 text-xs leading-relaxed">
            <select value={cur} onChange={e => { setQ(''); setCur(e.target.value) }} className="mb-4 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 sm:hidden">{all.map(x => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
            {hits && hits.length === 0 && <p className="text-slate-500">Nothing in the guide matches “{q}”. Try asking the chat instead.</p>}
            {shown.map(x => <section key={x.id} className="mb-8 last:mb-0"><h3 className="mb-3 text-sm font-semibold text-slate-100">{x.label}</h3>{x.body}</section>)}
          </div>
        </div>
      </div>
    </div>
  )
}

export function Empty({ title, text, more }) {
  const { openHelp } = useHelp()
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center text-xs">
      <div className="mb-1 font-medium text-slate-300">{title}</div>
      <p className="max-w-[260px] leading-relaxed text-slate-500">{text}</p>
      {more && <button onClick={() => openHelp(more)} className="mt-3 text-sky-300 hover:text-sky-200">What am I looking at? →</button>}
    </div>
  )
}
