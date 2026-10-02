import { Fragment, useEffect, useState } from 'react'
import { api } from './api'
import { commColor, ETYPE_COLORS, ETYPE_LABEL, TYPE_LABEL, SEV } from './theme'
import { IMPORTANCE_LABEL, RULE_TEXT, ALERT_TYPE, ALERT_HELP, sure } from './glossary'
import { Info, Empty } from './Help'
export { Info }

export const ID_RX = /(FIR-\d{3}|C\d{4}|T\d{4}|ALR-\d{2})/g

export function Chip({ id, onOpen }) {
  const kind = id.startsWith('FIR') ? 'sky' : id.startsWith('C') ? 'slate' : id.startsWith('T') ? 'amber' : 'rose'
  const cls = { sky: 'bg-sky-500/15 text-sky-300', slate: 'bg-slate-500/20 text-slate-300', amber: 'bg-amber-500/15 text-amber-300', rose: 'bg-rose-500/15 text-rose-300' }[kind]
  return <button onClick={() => onOpen(id)} className={`mr-1 mb-1 rounded px-1.5 py-0.5 font-mono text-[11px] hover:brightness-125 ${cls}`}>{id}</button>
}

export function Linkified({ text, onOpen }) {
  return text.split(ID_RX).map((p, i) => (i % 2 ? <Chip key={i} id={p} onOpen={onOpen} /> : <span key={i}>{p}</span>))
}

export function Panel({ title, term, right, children, className = '' }) {
  return (
    <section className={`rounded-lg border border-slate-800 bg-slate-900/70 ${className}`}>
      <header className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <h3 className="flex items-center text-[11px] font-semibold uppercase tracking-wider text-slate-400">{title}{term && <Info term={term} />}</h3>{right}
      </header>
      <div className="p-3">{children}</div>
    </section>
  )
}

export function Filters({ f, setF, period, communities }) {
  const days = Math.max(1, Math.round((new Date(period[1]) - new Date(period[0])) / 864e5))
  const at = d => new Date(new Date(period[0]).getTime() + d * 864e5)
  const fmt = d => at(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  const toggle = (key, v) => setF({ ...f, [key]: f[key].includes(v) ? f[key].filter(x => x !== v) : [...f[key], v] })
  return (
    <Panel title="Filters" term="filters" right={<button onClick={() => setF({ ...f, from: 0, to: days, types: ['person'], etypes: ['call', 'transfer', 'associate', 'reported_use'], community: '', minRisk: 0 })} className="text-[11px] text-slate-500 hover:text-sky-300">Reset</button>}>
      <div className="space-y-3 text-xs">
        <div>
          <div className="mb-1 flex justify-between text-slate-400"><span className="flex items-center">Time window<Info term="timeWindow" /></span><span className="text-slate-200">{fmt(f.from)} → {fmt(f.to)}</span></div>
          <input type="range" min={0} max={days} value={f.from} onChange={e => setF({ ...f, from: Math.min(+e.target.value, f.to - 1) })} className="w-full accent-sky-400" />
          <input type="range" min={0} max={days} value={f.to} onChange={e => setF({ ...f, to: Math.max(+e.target.value, f.from + 1) })} className="w-full accent-sky-400" />
        </div>
        <div>
          <div className="mb-1 flex items-center text-slate-400">Show<Info term="show" /></div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(TYPE_LABEL).map(([k, v]) => (
              <button key={k} onClick={() => toggle('types', k)} className={`rounded border px-2 py-0.5 ${f.types.includes(k) ? 'border-sky-500 bg-sky-500/15 text-sky-200' : 'border-slate-700 text-slate-500'}`}>{v}</button>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1 flex items-center text-slate-400">Connections<Info term="connections" /></div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(ETYPE_LABEL).map(([k, v]) => (
              <button key={k} onClick={() => toggle('etypes', k)} className={`flex items-center gap-1 rounded border px-2 py-0.5 ${f.etypes.includes(k) ? 'border-slate-500 text-slate-200' : 'border-slate-800 text-slate-600'}`}>
                <i className="inline-block h-2 w-2 rounded-full" style={{ background: ETYPE_COLORS[k] }} />{v}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1 flex items-center text-slate-400">Group<Info term="group" /></div>
          <select value={f.community} onChange={e => setF({ ...f, community: e.target.value })} className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1">
            <option value="">All groups</option>
            {communities.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-slate-400"><span className="flex items-center">Hide people below risk<Info term="risk" /></span><span className="text-slate-200">{f.minRisk}</span></div>
          <input type="range" min={0} max={80} step={5} value={f.minRisk} onChange={e => setF({ ...f, minRisk: +e.target.value })} className="w-full accent-sky-400" />
        </div>
      </div>
    </Panel>
  )
}

export function AlertsPanel({ alerts, activeId, onPick }) {
  return (
    <Panel title={`Alerts (${alerts.length})`} term="alert">
      <ul className="space-y-1.5">
        {alerts.map(a => (
          <li key={a.id}>
            <button onClick={() => onPick(a)} className={`w-full rounded border px-2 py-1.5 text-left text-xs hover:bg-slate-800 ${activeId === a.id ? 'border-sky-500 bg-slate-800' : 'border-slate-800'}`}>
              <div className="flex items-center gap-1.5">
                <span className={`rounded border px-1 text-[10px] uppercase ${SEV[a.severity]}`}>{a.severity}</span>
                <span className="font-mono text-[10px] text-slate-500">{a.id}</span>
              </div>
              <div className="mt-0.5 text-slate-200">{a.title}</div>
              <div className="text-[10px] text-slate-500">{ALERT_TYPE[a.type] || a.type}</div>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

export function KeyPersons({ top5, onPick, selected }) {
  return (
    <Panel title="Key persons (top 5)" term="keyPersons">
      <ol className="space-y-1.5">
        {top5.map((t, i) => (
          <li key={t.id}>
            <button onClick={() => onPick(t.id)} className={`w-full rounded border px-2 py-1.5 text-left text-xs hover:bg-slate-800 ${selected === t.id ? 'border-sky-500' : 'border-slate-800'}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-100"><span className="mr-1 text-slate-500">{i + 1}.</span>{t.name}</span>
                <span className="flex items-center gap-1 text-slate-400"><i className="inline-block h-2 w-2 rounded-full" style={{ background: commColor(t.community) }} />Group {t.community} · {Math.round(t.score * 100)}</span>
              </div>
              <div className="mt-0.5 text-[11px] leading-snug text-slate-400">{t.reasons[0]}; {t.reasons[1]}</div>
            </button>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

export function EntityPanel({ id, onOpen, onPick }) {
  const [e, setE] = useState(null)
  const [tl, setTl] = useState([])
  const [showTl, setShowTl] = useState(false)
  useEffect(() => {
    setE(null); setTl([]); setShowTl(false)
    if (!id || id.includes(':')) return
    api.entity(id).then(setE).catch(() => {})
    api.timeline(id).then(setTl).catch(() => {})
  }, [id])
  if (!id) return <Empty title="No one selected" text="Click a dot in the graph, a name under Key persons, or a person in an alert to see their details here." more="start" />
  if (id.includes(':')) return <p className="p-4 text-sm text-slate-400">Non-person node <span className="font-mono">{id}</span>.</p>
  if (!e) return <p className="p-4 text-sm text-slate-500">Loading…</p>
  const r = e.risk
  const lvl = r.level === 'high' ? 'bg-red-500' : r.level === 'medium' ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="space-y-3 p-3 text-xs">
      <div>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-100">{e.name}</h2>
            <div className="text-slate-400">{e.aliases.length ? `a.k.a. ${e.aliases.join(', ')} · ` : ''}{e.role} · Group {e.metrics?.community ?? '–'}<Info term="group" /></div>
          </div>
          <a href={api.reportUrl(e.id)} target="_blank" rel="noreferrer" className="rounded bg-sky-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-sky-500">PDF report</a>
        </div>
        <div className="mt-2">
          <div className="mb-1 flex justify-between"><span className="flex items-center text-slate-400">Risk score<Info term="risk" /></span><span className="font-semibold text-slate-100">{r.score}/100 · {r.level}</span></div>
          <div className="h-2 overflow-hidden rounded bg-slate-800"><div className={`h-full ${lvl}`} style={{ width: `${r.score}%` }} /></div>
          <div className="mt-1 text-[11px] text-slate-500">Network importance {r.breakdown.centrality}/40 · Alerts {r.breakdown.alert_involvement}/40 · Money moved {r.breakdown.money_volume}/20</div>
        </div>
      </div>
      <Kv k="Phones">{e.phones.map(p => <div key={p.number}><span className="font-mono">{p.number}</span> <span className="text-slate-500">{RULE_TEXT[p.rule] || p.rule} · {sure(p.confidence)} <Chip id={p.fir} onOpen={onOpen} /></span></div>)}{!e.phones.length && '–'}</Kv>
      <Kv k="Accounts">{e.accounts.join(', ') || '–'}</Kv>
      <Kv k="Organisation">{e.orgs?.join(', ') || e.organisations?.join(', ') || '–'}</Kv>
      <Kv k="Vehicles">{e.vehicles.join(', ') || '–'}</Kv>
      <Kv k="Locations">{e.locations.join(', ') || '–'}</Kv>
      <Kv k="FIRs">{e.firs.map(f => <Chip key={f.fir_id} id={f.fir_id} onOpen={onOpen} />)}</Kv>
      {e.metrics && <Kv k="Standing">{Object.entries(e.metrics.ranks).map(([k, v]) => `${IMPORTANCE_LABEL[k] || k}: #${v}`).join(' · ')}</Kv>}
      <div>
        <div className="mb-1 flex items-center text-slate-400">Why these FIR mentions are one person<Info term="resolution" /></div>
        <ul className="space-y-1">
          {e.resolution.links.map((l, i) => (
            <li key={i} className="rounded bg-slate-800/60 px-2 py-1">
              <Chip id={l.fir_id} onOpen={onOpen} /> “{l.surface}” → <b>{RULE_TEXT[l.rule] || l.rule}</b> · {sure(l.confidence)}{l.note && <div className="text-slate-500">{l.note}</div>}
            </li>
          ))}
        </ul>
      </div>
      {e.alerts.length > 0 && (
        <div><div className="mb-1 text-slate-400">Alerts</div>{e.alerts.map(a => <div key={a.id} className="mb-1"><Chip id={a.id} onOpen={onOpen} /><span className="text-slate-300">{a.title}</span></div>)}</div>
      )}
      <div>
        <div className="mb-1 text-slate-400">Connections</div>
        <ul className="space-y-0.5">
          {e.connections.map(c => (
            <li key={c.id}>
              <button onClick={() => onPick(c.id)} className="text-sky-300 hover:underline">{c.name}</button>
              <span className="text-slate-500"> — {c.calls} calls, {c.transfers} transfers{c.amount ? ` ₹${c.amount.toLocaleString('en-IN')}` : ''}{c.relation ? `, ${c.relation}` : ''}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <button onClick={() => setShowTl(!showTl)} className="text-sky-300 hover:underline">{showTl ? 'Hide' : 'Show'} activity timeline ({tl.length})</button>
        {showTl && (
          <ul className="mt-1 max-h-72 space-y-0.5 overflow-auto border-l border-slate-700 pl-2">
            {tl.map(t => (
              <li key={t.id + t.ts}><span className="text-slate-500">{t.ts.slice(0, 16)}</span> <Chip id={t.id} onOpen={onOpen} />{t.text}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

const Kv = ({ k, children }) => (
  <div className="flex gap-2"><div className="w-24 shrink-0 text-slate-400">{k}</div><div className="min-w-0 flex-1 text-slate-200">{children}</div></div>
)

export function AlertDetail({ alert, onOpen, onPick, names }) {
  if (!alert) return null
  const ev = alert.evidence
  return (
    <div className="space-y-2 p-3 text-xs">
      <div className="flex items-center gap-2"><span className={`rounded border px-1 text-[10px] uppercase ${SEV[alert.severity]}`}>{alert.severity}</span><span className="font-mono text-slate-500">{alert.id}</span><span className="text-slate-500">{ALERT_TYPE[alert.type] || alert.type}</span></div>
      <h2 className="text-sm font-semibold text-slate-100">{alert.title}</h2>
      <p className="leading-relaxed text-slate-300">{alert.summary}</p>
      {ALERT_HELP[alert.type] && <p className="rounded bg-slate-800/60 p-2 text-slate-400"><b className="text-slate-300">What this means: </b>{ALERT_HELP[alert.type]}</p>}
      {alert.time?.start && <p className="text-slate-500">{alert.time.start} → {alert.time.end}</p>}
      <div><div className="mb-1 text-slate-400">People involved</div>{alert.entities.map(e => <button key={e} onClick={() => onPick(e)} className="mr-2 text-sky-300 hover:underline">{names?.[e] || e}</button>)}</div>
      {[['FIR records', ev.firs], ['Money transfers', ev.txns], ['Phone calls', ev.calls]].map(([k, v]) => v.length > 0 && (
        <div key={k}><div className="mb-1 text-slate-400">{k} ({v.length})</div>{v.slice(0, 30).map(i => <Chip key={i} id={i} onOpen={onOpen} />)}</div>
      ))}
    </div>
  )
}

export function RecordModal({ id, onClose }) {
  const [r, setR] = useState(null)
  useEffect(() => { setR(null); if (id) api.record(id).then(setR).catch(() => setR({ kind: 'error' })) }, [id])
  useEffect(() => { if (!id) return; const k = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [id, onClose])
  if (!id) return null
  const rows = r && r.kind !== 'error' ? Object.entries(r).filter(([k]) => k !== 'text' && k !== 'kind') : []
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[80vh] w-full max-w-xl overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl shadow-black/60 text-sm" onClick={e => e.stopPropagation()}>
        <div className="mb-2 flex items-center justify-between"><h3 className="font-mono text-base text-slate-100">{id}</h3><button onClick={onClose} className="text-slate-400 hover:text-white">✕</button></div>
        {!r && <p className="text-slate-500">Loading…</p>}
        {r?.kind === 'error' && <p className="text-red-300">Record not found.</p>}
        {r?.text && <p className="mb-3 rounded bg-slate-800 p-3 leading-relaxed text-slate-200">{r.text}</p>}
        <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-xs">
          {rows.map(([k, v]) => <Fragment key={k}><dt className="text-slate-400">{k.replace(/_/g, ' ')}</dt><dd className="break-words text-slate-200">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></Fragment>)}
        </dl>
      </div>
    </div>
  )
}
