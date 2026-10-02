import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import GraphView from './GraphView'
import MapView from './MapView'
import Slip from './Slip'
import { useLive } from './useLive'
import { Alerts, People, Ask, Inbox, FileFir, Stations } from './Pages'
import { KIND_LABEL } from './util'

const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d } catch { return d } },
  set: (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}
const MAP_OPS = new Set(['fly', 'camera', 'heat', 'layers', 'tour', 'filter', 'focus'])
const SESSION = store.get('chat-session', '') || (() => { const id = 'ui-' + Math.random().toString(36).slice(2, 8); store.set('chat-session', id); return id })()
const loadQa = () => { try { return JSON.parse(store.get('chat-qa', '[]')).filter(x => x.a) } catch { return [] } }

class Guard extends Component {
  state = { bad: null }
  static getDerivedStateFromError(e) { return { bad: e } }
  componentDidUpdate(p) { if (p.reset !== this.props.reset && this.state.bad) this.setState({ bad: null }) }
  render() { return this.state.bad ? <div className="err" role="alert">Could not show this item. Pick another one. <button className="tool" onClick={this.props.onClose}>Close</button></div> : this.props.children }
}

export default function App() {
  const [viewer, setViewer] = useState(store.get('viewer', ''))
  const [auto, setAuto] = useState(store.get('autopilot', '1') === '1')
  const [health, setHealth] = useState(null), [llm, setLlm] = useState(null)
  const [graph, setGraph] = useState(null), [alerts, setAlerts] = useState([]), [stations, setStations] = useState([]), [links, setLinks] = useState([])
  const [tab, setTab] = useState('alerts'), [view, setView] = useState('graph')
  const [sel, setSel] = useState(null), [seen, setSeen] = useState(new Set())
  const [highlight, setHighlight] = useState(null), [qa, setQa] = useState(loadQa)
  const [toasts, setToasts] = useState([]), [rk, setRk] = useState(0), [unread, setUnread] = useState(0), [live, setLive] = useState(false)
  const [draft, setDraft] = useState(null), [q, setQ] = useState(''), [busy, setBusy] = useState(false), [err, setErr] = useState('')
  const mapRef = useRef(null), graphRef = useRef(null)
  const S = useRef({}); S.current = { alerts, stations, auto, viewer }

  const loadAll = useCallback(() => {
    api.health().then(setHealth).catch(() => {})
    api.alertsGeo().then(setAlerts).catch(() => {})
    api.graph({ types: 'person', etypes: 'call,transfer,associate' }).then(setGraph).catch(e => setErr(e.message))
    api.mapStations({}).then(setStations).catch(() => {})
    api.mapLinks({}).then(setLinks).catch(() => {})
    setRk(k => k + 1)
  }, [])
  useEffect(() => { loadAll(); api.llm().then(setLlm).catch(() => {}); const t = setInterval(() => api.llm().then(setLlm).catch(() => {}), 30000); return () => clearInterval(t) }, [loadAll])
  useEffect(() => {
    if (!viewer) return setUnread(0)
    api.notifications({ station: viewer, direction: 'in', status: 'new' }).then(r => setUnread((Array.isArray(r) ? r : r.items || []).length)).catch(() => {})
  }, [viewer, rk])
  const chooseViewer = v => { setViewer(v); store.set('viewer', v) }

  // ------------------------------------------------------------ locating things for the map
  const locate = async (kind, id) => {
    const { alerts, stations } = S.current
    if (kind === 'station') { const s = stations.find(x => x.id === id); return s && { kind, id, name: s.name, lat: s.lat, lon: s.lon } }
    if (kind === 'alert') { const a = alerts.find(x => x.id === id); return a?.geo?.lat && { kind, id, name: a.title, lat: a.geo.lat, lon: a.geo.lon } }
    const r = await api.mapFeatures({ layers: kind === 'fir' ? 'firs' : 'entities', q: kind === 'fir' ? id : '' })
    const f = r.features.find(x => x.id === id)
    return f && { kind, id, name: f.name || id, lat: f.lat, lon: f.lon }
  }

  // ------------------------------------------------------------ command executor (also used by the AI)
  const execCmds = useCallback((cmds = []) => {
    const goMap = cmds.some(c => MAP_OPS.has(c.op))
    if (goMap) setView('map')
    const go = () => cmds.forEach(c => {
      if (c.op === 'highlight') setHighlight(c.ids?.length ? { nodes: c.ids } : null)
      else if (c.op === 'select') setSel(c.target || (c.kind && { kind: c.kind, id: c.id }))
      else mapRef.current?.exec(c)
    })
    goMap ? setTimeout(go, 120) : go()
  }, [])

  const pick = useCallback(p => {
    if (!p || !['entity', 'alert', 'fir', 'station'].includes(p.kind)) return
    setSel({ kind: p.kind, id: p.id })
    if (p.kind === 'alert') setSeen(s => new Set(s).add(p.id))
  }, [])

  const showOnMap = async (s, d) => {
    const t = await locate(s.kind, s.id)
    if (!t) return
    if (s.kind === 'alert' && d?.entities) setHighlight({ nodes: d.entities })
    if (s.kind === 'entity') setHighlight({ nodes: [s.id] })
    execCmds([{ op: 'fly', target: t, zoom: undefined }])
  }
  const showInNet = ids => {
    setView('graph'); setHighlight({ nodes: Array.isArray(ids) ? ids : [ids] })
  }
  const openNote = n => {
    const a = alerts.find(x => x.id === n.refs?.alert_id) || alerts.find(x => x.geo?.sig === n.refs?.alert_sig)
    if (a) { pick({ kind: 'alert', id: a.id }); if (a.geo?.lat) showOnMap({ kind: 'alert', id: a.id }, a) }
    else if (n.refs?.fir_id) pick({ kind: 'fir', id: n.refs.fir_id })
  }

  // ------------------------------------------------------------ live events
  const toast = t => {
    const id = Math.random().toString(36).slice(2)
    setToasts(x => [...x.slice(-3), { id, ...t }])
    setTimeout(() => setToasts(x => x.filter(y => y.id !== id)), 14000)
  }
  useLive(viewer, ev => {
    if (ev.type === 'status') return setLive(ev.ok)
    const d = ev.data || {}
    if (ev.type === 'hello') return
    if (ev.type === 'graph.updated') return loadAll()
    if (ev.type === 'fir.created') {
      const f = d.fir || {}
      toast({ title: `New FIR ${f.fir_id || ''}`, small: f.station || '', body: d.summary || '' })
      loadAll()
      if (S.current.auto && !S.current.viewer) locate('fir', f.fir_id).then(t => t && (setView('map'), setTimeout(() => mapRef.current?.exec({ op: 'fly', target: t }), 150), pick({ kind: 'fir', id: f.fir_id })))
      return
    }
    if (ev.type === 'notification.ack') { toast({ title: 'Acknowledged', small: d.to_name || '', body: d.title || '' }); return setRk(k => k + 1) }
    if (ev.type === 'notification') {
      const n = d.notification || d
      toast({ title: n.title, small: KIND_LABEL[n.kind] || n.kind, body: n.body, sev: n.severity, note: n })
      setRk(k => k + 1)
      if (S.current.auto) setTimeout(() => openNote(n), 400)
    }
  })

  // ------------------------------------------------------------ ask
  useEffect(() => { store.set('chat-qa', JSON.stringify(qa.filter(x => x.a).slice(-30).map(x => ({ q: x.q, a: x.a })))) }, [qa])
  const send = async text => {
    text = (text ?? q).trim(); if (!text || busy) return
    setQ(''); setBusy(true); setTab('ask')
    const i = qa.length
    setQa(x => [...x, { q: text }])
    try {
      const r = await api.chat(text, SESSION)
      setQa(x => x.map((y, k) => (k === i ? { ...y, a: r.answer } : y)))
    } catch (e) { setQa(x => x.map((y, k) => (k === i ? { ...y, a: 'Sorry, that did not work: ' + e.message } : y))) }
    setBusy(false)
  }

  const persons = useMemo(() => (graph?.nodes || []).filter(n => n.type === 'person'), [graph])
  const ai = llm?.enabled && llm?.reachable
  const nAlerts = alerts.length - seen.size
  const flags = [['stations', 'Stations'], ['alerts', 'Alerts', nAlerts > 0 ? nAlerts : ''], ['people', 'People'], ['ask', 'Ask AI'], ['inbox', 'Inbox', unread || ''], ['file', 'File FIR']]
  const vName = stations.find(s => s.id === viewer)?.name

  return (
    <div className="shell">
      <header className="top">
        <div className="cover"><b>Criminal Network Analysis</b><span>{health?.period ? `${String(health.period[0]).slice(0, 10)} → ${String(health.period[1]).slice(0, 10)}` : ''}</span></div>
        <div className="tally">
          <span>{health?.firs ?? '–'}<small>FIRs</small></span><span>{health?.entities ?? '–'}<small>people</small></span>
          <span>{health?.calls ?? '–'}<small>calls</small></span><span className="al">{alerts.length}<small>alerts</small></span>
        </div>
        <div className="hright">
          <label className="who">Viewing as
            <select value={viewer} onChange={e => chooseViewer(e.target.value)} aria-label="Viewing as">
              <option value="">Command centre</option>{stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select></label>
          <span className={'ai' + (ai ? '' : ' off')}>{ai ? 'AI online' : 'AI offline · rules'}</span>
          {viewer && <button className="hbtn back" onClick={() => chooseViewer('')} title="Leave this station's view and see every station">← Back to command centre</button>}
          <button className="hbtn" aria-pressed={auto} title="When on, the map flies to new alerts and FIRs by itself" onClick={() => { setAuto(!auto); store.set('autopilot', auto ? '0' : '1') }}>AI autopilot {auto ? 'on' : 'off'}</button>
          <span className={'live-dot' + (live ? ' on' : '')} title={live ? 'Live updates connected' : 'Reconnecting…'} />
        </div>
      </header>

      <main className="spread">
        <section className="page left" aria-label="Notes">
          <div className="flags" role="tablist">
            {flags.map(([k, v, n]) => <button key={k} role="tab" className="flag" aria-selected={tab === k} onClick={() => setTab(k)}>{v}{n ? <i>{n}</i> : null}</button>)}
          </div>
          <div className="flagline" />
          <div className="leaf">
            {err && <div className="err">{err}</div>}
            {tab === 'alerts' && <Alerts alerts={alerts} sel={sel?.kind === 'alert' ? sel.id : null} seen={seen} mine={viewer} stations={stations} persons={persons} draft={draft} onDraft={setDraft}
              onRaised={a => { setAlerts(x => [...x.filter(y => y.id !== a.id), a]); loadAll(); pick({ kind: 'alert', id: a.id }); toast({ title: `${a.id} raised`, small: 'Alert by hand', body: a.title }) }} onOpen={id => { pick({ kind: 'alert', id }) }} />}
            {tab === 'stations' && <Stations stations={stations} viewer={viewer} links={links}
              onMap={id => { const t = stations.find(x => x.id === id); if (t) execCmds([{ op: 'focus', station: id }, { op: 'fly', target: { kind: 'station', id, name: t.name, lat: t.lat, lon: t.lon }, zoom: 11.8 }]) }}
              onOnly={id => execCmds([{ op: 'filter', set: { station: id } }, { op: 'focus', station: id }])}
              onViewAs={chooseViewer} onBack={() => chooseViewer('')} onOpen={id => pick({ kind: 'alert', id })} />}
            {tab === 'ask' && <Ask qa={qa} llm={llm} onSend={send} onCmd={execCmds} />}
            {tab === 'people' && <People persons={persons} onOpen={id => pick({ kind: 'entity', id })} />}
            {tab === 'inbox' && <Inbox viewer={viewer} stations={stations} refreshKey={rk} onOpen={openNote} onChanged={() => setRk(k => k + 1)} />}
            {tab === 'file' && <FileFir viewer={viewer} stations={stations} onFiled={() => { loadAll() }} />}
          </div>
          {tab === 'ask' && <form className="ask" onSubmit={e => { e.preventDefault(); send() }}>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Who is the most connected person? / Bunty ke calls…" autoComplete="off" aria-label="Ask the records" />
            <button disabled={busy || !q.trim()}>{busy ? '…' : 'Ask'}</button></form>}
        </section>

        <section className="page right" aria-label="Network and map">
          <div className="rhead">
            <h2>{view === 'map' ? 'Map' : 'Network'}</h2>
            <span className="meta">{view === 'map' ? (vName ? `${vName} highlighted` : 'all stations') : `${persons.length} people`}</span>
            <div className="viewflags" role="tablist">
              <button role="tab" className="vflag" aria-selected={view === 'graph'} onClick={() => setView('graph')}>Network</button>
              <button role="tab" className="vflag" aria-selected={view === 'map'} onClick={() => setView('map')}>Map</button>
            </div>
            {view === 'graph' && <div className="tools"><button className="tool" onClick={() => graphRef.current?.fit()}>Fit</button></div>}
          </div>
          <div className={'stage' + (view === 'graph' ? '' : ' hidden')}>
            <GraphView ref={graphRef} graph={graph} highlight={highlight} selected={sel?.kind === 'entity' ? sel.id : null} visible={view === 'graph'} onSelect={id => pick({ kind: 'entity', id })} />
            <div className={'answer-tag' + (highlight ? ' show' : '')}><span>{highlight?.nodes?.length} highlighted</span><button onClick={() => setHighlight(null)}>Clear</button></div>
          </div>
          {view === 'graph' && <div className="key"><span><i />Calls</span><span><i className="m" />Money</span><span><i className="cr" />High risk</span><span><i className="c" />Person</span></div>}
          <div style={{ display: view === 'map' ? 'flex' : 'none', flexDirection: 'column', flex: 1, minHeight: 0 }}>
            <MapView ref={mapRef} viewer={viewer} refreshKey={rk} highlight={highlight} visible={view === 'map'} onPick={pick} />
          </div>
          <Guard reset={sel && sel.kind + sel.id} onClose={() => setSel(null)}><Slip sel={sel} alerts={alerts} viewer={viewer} onRaise={d => { setDraft(d); setTab('alerts') }}
            onWithdraw={id => api.withdrawAlert(id, viewer).then(() => { setSel(null); loadAll() }).catch(e => setErr(e.message))} onClose={() => setSel(null)} onPick={pick} onMap={showOnMap} onNet={showInNet} /></Guard>
        </section>
      </main>

      <div className="toasts" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={'toast' + (t.sev === 'high' ? ' high' : '')}>
            <small>{t.small}</small><b>{t.title}</b>{t.body && <p>{t.body.slice(0, 160)}</p>}
            <div className="acts">
              {t.note && <button className="btn" onClick={() => { openNote(t.note); setToasts(x => x.filter(y => y.id !== t.id)) }}>Look at it</button>}
              {t.note && viewer && <button className="btn ghost" onClick={() => api.ack(t.note.id, viewer).then(() => { setRk(k => k + 1); setToasts(x => x.filter(y => y.id !== t.id)) })}>Acknowledge</button>}
              <button className="btn ghost" onClick={() => setToasts(x => x.filter(y => y.id !== t.id))}>Dismiss</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
