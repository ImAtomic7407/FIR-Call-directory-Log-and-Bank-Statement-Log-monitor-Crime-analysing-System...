import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import GraphView from './GraphView'
import ChatPanel from './ChatPanel'
import { Filters, AlertsPanel, KeyPersons, EntityPanel, AlertDetail, RecordModal } from './components'
import { HelpContext, HelpPanel, Info, Empty } from './Help'
import { commColor, ETYPE_COLORS, ETYPE_LABEL } from './theme'

const ALL_TYPES = ['person', 'phone', 'vehicle', 'org', 'location']
const ALL_ET = Object.keys(ETYPE_LABEL)

export default function App() {
  const [health, setHealth] = useState(null)
  const [llm, setLlm] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [graph, setGraph] = useState(null)
  const [err, setErr] = useState(null)
  const [f, setF] = useState({ from: 0, to: 9999, types: ['person'], etypes: ['call', 'transfer', 'associate', 'reported_use'], community: '', minRisk: 0 })
  const [selected, setSelected] = useState(null)
  const [activeAlert, setActiveAlert] = useState(null)
  const [highlight, setHighlight] = useState(null)
  const [tab, setTab] = useState('chat')
  const [record, setRecord] = useState(null)
  const [help, setHelp] = useState(null) // null = closed, otherwise section id
  const [pendingAsk, setPendingAsk] = useState(null)
  const [legend, setLegend] = useState(() => window.innerWidth >= 1536)
  const [guideSeen, setGuideSeen] = useState(() => { try { return localStorage.getItem('guideSeen') === '1' } catch { return true } })

  useEffect(() => {
    Promise.all([api.health(), api.metrics(), api.alerts()]).then(([h, m, a]) => {
      setHealth(h); setMetrics(m); setAlerts(a)
      const days = Math.round((new Date(h.period[1]) - new Date(h.period[0])) / 864e5)
      setF(x => ({ ...x, to: days }))
    }).catch(e => setErr(String(e)))
    api.llm().then(setLlm).catch(() => {})
  }, [])

  const names = useMemo(() => Object.fromEntries((graph?.nodes ?? []).map(n => [n.id, n.label || n.name])), [graph])
  const period = health?.period
  const query = useMemo(() => {
    if (!period) return null
    const t0 = new Date(period[0]).getTime()
    const iso = d => new Date(t0 + d * 864e5).toISOString().slice(0, 19)
    return { start: iso(f.from), end: iso(f.to + 1), types: f.types.join(','), etypes: f.etypes.join(','), min_risk: f.minRisk, ...(f.community ? { community: f.community } : {}) }
  }, [f, period])

  useEffect(() => {
    if (!query) return
    const t = setTimeout(() => api.graph(query).then(setGraph).catch(e => setErr(String(e))), 150)
    return () => clearTimeout(t)
  }, [query])

  const pick = useCallback(id => { setSelected(id); if (id) { setTab('entity'); setHighlight(id.includes(':') ? null : { nodes: [id] }) } else setHighlight(null) }, [])
  const pickAlert = a => {
    setActiveAlert(a); setSelected(null); setTab('alert')
    const extra = []
    if (a.details?.phone) extra.push('ph:' + a.details.phone)
    if (a.details?.plate) extra.push('veh:' + a.details.plate)
    setF(x => ({ ...x, types: [...new Set([...x.types, ...(a.details?.phone ? ['phone'] : []), ...(a.details?.plate ? ['vehicle'] : [])])], etypes: [...new Set([...x.etypes, ...(a.details?.phone ? ['reported_use', 'uses_phone'] : []), ...(a.details?.plate ? ['uses_vehicle'] : [])])] }))
    setHighlight({ nodes: [...a.entities, ...extra] })
  }
  const onChatHighlight = h => { setHighlight(h); setSelected(null) }
  // alert IDs have no /record entry: open the alert itself instead
  const openRecord = id => {
    const a = id.startsWith('ALR-') && alerts.find(x => x.id === id)
    if (a) { setHelp(null); pickAlert(a) } else setRecord(id)
  }
  const openRecordRef = useRef(openRecord)
  openRecordRef.current = openRecord

  const openHelp = useCallback(section => {
    setHelp(section || 'start')
    if (!guideSeen) { setGuideSeen(true); try { localStorage.setItem('guideSeen', '1') } catch { /* private mode */ } }
  }, [guideSeen])
  const closeHelp = useCallback(() => setHelp(null), [])
  const closeRecord = useCallback(() => setRecord(null), [])
  const helpCtx = useMemo(() => ({
    openHelp,
    ask: q => { setHelp(null); setTab('chat'); setPendingAsk({ q, n: Date.now() }) },
    openRecord: id => openRecordRef.current(id),
  }), [openHelp])

  useEffect(() => {
    const k = e => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '?') { e.preventDefault(); openHelp() }
      else if (e.key === '/') { e.preventDefault(); setTab('chat'); setTimeout(() => document.getElementById('chat-input')?.focus(), 0) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [openHelp])

  if (err) return <div className="p-8 text-red-300">Cannot reach the API ({err}). Start it with <code>uvicorn main:app --port 8000</code> in backend/.</div>

  const llmBadge = llm?.reachable ? ['AI online', 'bg-emerald-500', 'The AI model reads questions and words answers. Every ID and number it writes is checked against the data.']
    : llm?.enabled ? ['AI offline · rules mode', 'bg-amber-500', 'The AI model is not reachable, so keyword rules and template answers are used. Everything still works.']
    : ['Rules mode', 'bg-slate-500', 'No AI model configured: keyword rules and template answers are used. Everything still works.']
  const groups = graph?.communities ?? []
  return (
    <HelpContext.Provider value={helpCtx}>
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-800 bg-slate-900 px-4 py-2.5">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-slate-100">Criminal Network Analysis <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-normal text-slate-400">synthetic data</span></h1>
        {health && <div className="hidden items-center gap-1.5 text-[11px] text-slate-400 xl:flex">
          {[[health.firs, 'FIRs'], [health.calls, 'calls'], [health.transactions, 'transfers'], [health.entities, 'people']].map(([n, l]) => <span key={l} className="rounded-md bg-slate-800/70 px-2 py-0.5"><b className="font-semibold tabular-nums text-slate-200">{n}</b> {l}</span>)}
          <span className="rounded-md bg-rose-500/15 px-2 py-0.5 text-rose-300"><b className="font-semibold tabular-nums">{health.alerts}</b> alerts</span>
        </div>}
        <div className="ml-auto flex items-center gap-2">
          <span className="flex items-center text-[11px] text-slate-400"><i className={`mr-1.5 inline-block h-2 w-2 rounded-full ${llmBadge[1]}`} />{llmBadge[0]}<Info text={llmBadge[2]} section="chat" /></span>
          <button onClick={() => openHelp()} title="Open the guide (?)" className="relative flex items-center gap-1.5 rounded-md border border-slate-600 px-2.5 py-1 text-xs text-slate-200 hover:border-sky-500 hover:bg-slate-800">
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-semibold text-sky-300">?</span>Guide
            {!guideSeen && <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-400" /></span>}
          </button>
          <a href={api.reportUrl()} target="_blank" rel="noreferrer" className="rounded-md bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500">Case report PDF</a>
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto lg:grid-cols-[260px_minmax(0,1fr)_360px] lg:overflow-hidden 2xl:grid-cols-[290px_minmax(0,1fr)_400px]">
        <aside className="order-2 space-y-3 border-slate-800 p-3 lg:order-none lg:overflow-auto lg:border-r">
          {health && metrics && <Filters f={f} setF={setF} period={period} communities={graph?.communities ?? metrics.communities} />}
          <AlertsPanel alerts={alerts} activeId={activeAlert?.id} onPick={pickAlert} />
          {metrics && <KeyPersons top5={metrics.top5} onPick={pick} selected={selected} />}
        </aside>
        <main className="relative order-1 h-[60vh] min-w-0 lg:order-none lg:h-auto">
          <GraphView graph={graph} highlight={highlight} selected={selected} onSelect={pick} />
          {!graph && <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">Loading network…</div>}
          {graph && graph.nodes.length === 0 && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-xs text-slate-400">Nothing matches the current filters.<span className="text-slate-500">Widen the time window or lower the risk threshold.</span></div>}
          <div className="absolute right-3 top-3 w-52 rounded-lg border border-slate-800 bg-slate-900/90 text-[11px] text-slate-400 shadow-lg backdrop-blur">
            <div className="flex items-center justify-between px-2.5 py-1.5">
              <button onClick={() => setLegend(!legend)} className="flex items-center gap-1 font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"><span className="w-2.5">{legend ? '▾' : '▸'}</span>Legend</button>
              <button onClick={() => openHelp('graph')} className="text-sky-300/80 hover:text-sky-200">How to read</button>
            </div>
            {legend && <div className="max-h-[50vh] space-y-2 overflow-auto border-t border-slate-800 px-2.5 py-2">
              {groups.length > 0 && <div className="space-y-1">{groups.map(c => <div key={c.id} className="flex items-center gap-1.5"><i className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: commColor(c.id) }} /><span className="truncate">{c.label}</span></div>)}</div>}
              {f.etypes.length > 0 && <div className="space-y-1 border-t border-slate-800 pt-2">{f.etypes.map(e => <div key={e} className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 shrink-0" style={{ background: ETYPE_COLORS[e] }} />{ETYPE_LABEL[e]}</div>)}</div>}
              <div className="space-y-1 border-t border-slate-800 pt-2">
                <div className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 shrink-0 rounded-full border-2 border-red-500" />Risk 60+</div>
                <div className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 shrink-0 rounded-full border border-slate-500 bg-slate-700" />Bigger dot = more central</div>
              </div>
            </div>}
          </div>
          {highlight?.nodes?.length > 0 && (
            <button onClick={() => { setHighlight(null); setSelected(null) }} className="absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-yellow-400 px-3 py-1 text-xs font-medium text-slate-900 shadow-lg hover:bg-yellow-300">Showing {highlight.nodes.length} highlighted · Clear ✕</button>
          )}
        </main>
        <aside className="order-3 flex h-[75vh] min-h-0 flex-col border-slate-800 bg-slate-900/40 lg:order-none lg:h-auto lg:border-l">
          <nav className="flex border-b border-slate-800 text-xs">
            {[['chat', 'Investigator chat'], ['entity', 'Person details'], ['alert', 'Alert details']].map(([k, v]) => (
              <button key={k} onClick={() => setTab(k)} className={`flex-1 border-b-2 px-3 py-2.5 ${tab === k ? 'border-sky-500 text-sky-300' : 'border-transparent text-slate-400 hover:text-slate-200'}`}>{v}</button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-auto">
            <div className={tab === 'chat' ? 'h-full' : 'hidden'}><ChatPanel onHighlight={onChatHighlight} onOpen={openRecord} pendingAsk={pendingAsk} /></div>
            {tab === 'entity' && <EntityPanel id={selected} onOpen={openRecord} onPick={pick} />}
            {tab === 'alert' && (activeAlert ? <AlertDetail alert={activeAlert} onOpen={openRecord} onPick={pick} names={names} /> : <Empty title="No alert selected" text="Pick an alert in the left column to see what was found and the records behind it." more="alerts" />)}
          </div>
        </aside>
      </div>
      {help && <HelpPanel section={help} onClose={closeHelp} health={health} llm={llm} groups={groups} ask={helpCtx.ask} openRecord={helpCtx.openRecord} />}
      <RecordModal id={record} onClose={closeRecord} />
    </div>
    </HelpContext.Provider>
  )
}

