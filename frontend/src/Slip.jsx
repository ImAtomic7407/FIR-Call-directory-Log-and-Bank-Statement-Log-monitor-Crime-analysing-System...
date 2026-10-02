import { useEffect, useState } from 'react'
import { api } from './api'
import { band, fmtDate } from './util'

const money = n => '₹' + Number(n || 0).toLocaleString('en-IN')

export default function Slip({ sel, alerts, viewer, onClose, onPick, onMap, onNet, onRaise, onWithdraw }) {
  const [got, setD] = useState(null), [err, setErr] = useState('')
  useEffect(() => {
    if (!sel) return
    setD(null); setErr('')
    const f = sel.kind === 'entity' ? api.entity(sel.id) : sel.kind === 'fir' ? api.record(sel.id) : sel.kind === 'station' ? api.station(sel.id)
      : Promise.resolve(alerts.find(a => a.id === sel.id))
    let live = true
    f.then(x => live && (x ? setD({ key: sel.kind + ':' + sel.id, x }) : setErr('Not found'))).catch(e => live && setErr(e.message))
    return () => { live = false }
  }, [sel?.kind, sel?.id])

  // only use data fetched for the current selection (avoids one render with the old record)
  const d = got && sel && got.key === sel.kind + ':' + sel.id ? got.x : null
  let title = '', sub = '', body = null
  if (sel && d) {
    if (sel.kind === 'entity') {
      const r = d.risk || { score: 0, level: 'unknown' }, b = r.breakdown || { centrality: 0, alert_involvement: 0, money_volume: 0 }
      title = d.name
      sub = `${d.aliases?.length ? 'Also called ' + d.aliases.join(', ') + ' · ' : ''}${d.role || 'person'} · Group ${d.metrics?.community ?? '–'}`
      const bar = (x, m) => <div><i style={{ width: `${(x / m) * 100}%` }} /></div>
      body = <>
        <div><h4>Risk</h4><div className="riskline"><b className={band(r.score)}>{r.score}</b><span>out of 100 · {r.level}</span></div>
          <div className="parts">{bar(b.centrality, 40)}{bar(b.alert_involvement, 40)}{bar(b.money_volume, 20)}</div>
          <div className="parts-l"><span>Importance {b.centrality}/40</span><span>Alerts {b.alert_involvement}/40</span><span>Money {b.money_volume}/20</span></div></div>
        {d.alerts?.length > 0 && <div><h4>Named in alerts</h4><div className="refs">{d.alerts.map(a => <button key={a.id} onClick={() => onPick({ kind: 'alert', id: a.id })}>{a.id} · {a.title}</button>)}</div></div>}
        <div><h4>Identity</h4>
          {d.phones?.map(p => <div className="line" key={p.number}><span className="ids">{p.number}</span><span>from {p.fir}</span></div>)}
          {d.vehicles?.map(v => <div className="line" key={v}><span>Vehicle</span><span className="ids">{v}</span></div>)}
          {d.accounts?.map(v => <div className="line" key={v}><span>Account</span><span className="ids">{v}</span></div>)}
          {d.orgs?.map(v => <div className="line" key={v}><span>Organisation</span><span>{v}</span></div>)}
          {d.locations?.length > 0 && <div className="line"><span>Seen at</span><span>{d.locations.join(', ')}</span></div>}</div>
        {d.connections?.length > 0 && <div><h4>Linked people</h4>{d.connections.slice(0, 8).map(c => <div className="line" key={c.id}>
          <button onClick={() => onPick({ kind: 'entity', id: c.id })}>{c.name}</button>
          <span>{c.calls ? `${c.calls} calls` : ''}{c.calls && c.transfers ? ' · ' : ''}{c.transfers ? `${c.transfers} transfers ${money(c.amount)}` : ''}{!c.calls && !c.transfers ? c.relation : ''}</span></div>)}</div>}
        {d.firs?.length > 0 && <div><h4>FIRs</h4>{d.firs.map(f => <div key={f.fir_id}><div className="line"><button onClick={() => onPick({ kind: 'fir', id: f.fir_id })}>{f.fir_id}</button><span>{f.station} · {fmtDate(f.date)}</span></div><div className="fir">{f.text}</div></div>)}</div>}
        <div className="slip-acts"><button className="btn" onClick={() => onMap(sel)}>Show on map</button><button className="btn ghost" onClick={() => onNet(d.id)}>Show in network</button><button className="btn ghost" onClick={() => onRaise({ entities: [d.id], firs: [] })}>Raise alert</button>
          <a className="btn ghost" href={api.reportUrl(d.id)} target="_blank" rel="noreferrer">PDF report</a></div>
      </>
    } else if (sel.kind === 'alert') {
      title = d.title; sub = `${d.id} · ${d.severity} severity`
      const g = d.geo || {}
      body = <>
        <div><h4>{d.custom ? `Raised by hand · ${d.details.raised_by_name}` : 'What was found'}</h4><p>{d.summary}</p></div>
        <div><h4>People involved</h4><div className="refs">{(d.entities || []).map(e => <button key={e} onClick={() => onPick({ kind: 'entity', id: e })}>{e}</button>)}</div></div>
        {g.stations?.length > 0 && <div><h4>Police stations that see this{g.cross_station ? ' (cross-station)' : ''}</h4>
          <div className="refs">{g.stations.map(s => <button key={s.station} className={'stn' + (s.routed ? ' routed' : '')} title={(s.reasons || []).join('; ')} onClick={() => onPick({ kind: 'station', id: s.station })}>{s.name || s.station}{s.routed ? ' · alerted' : ''}</button>)}</div></div>}
        {d.evidence?.firs?.length > 0 && <div><h4>Records behind it</h4><div className="refs">{d.evidence.firs.map(f => <button key={f} onClick={() => onPick({ kind: 'fir', id: f })}>{f}</button>)}</div></div>}
        <div className="slip-acts"><button className="btn" onClick={() => onMap(sel, d)}>Show on map</button><button className="btn ghost" onClick={() => onNet(d.entities)}>Show in network</button>
          {d.custom && viewer === d.details?.raised_by && <button className="btn ghost" onClick={() => confirm(`Withdraw ${d.id}? Other stations will no longer see it.`) && onWithdraw(d.id)}>Withdraw</button>}</div>
      </>
    } else if (sel.kind === 'fir') {
      title = d.fir_id || sel.id; sub = `${d.station || ''} · ${fmtDate(d.date)}`
      body = <><div className="fir">{d.text}</div><div className="slip-acts"><button className="btn" onClick={() => onMap(sel)}>Show on map</button><button className="btn ghost" onClick={() => onRaise({ entities: [], firs: [sel.id] })}>Raise alert about this</button></div></>
    } else if (sel.kind === 'station') {
      title = d.name; sub = `${d.district || ''}, ${d.state || ''}`
      body = <>
        <div className="riskline"><b className={d.high_alerts ? 'high' : ''}>{d.alerts.length}</b><span>alerts · {d.high_alerts} high · {d.cross_station_alerts} cross-station</span></div>
        <div className="parts-l"><span>{d.firs} FIRs ({d.live_firs} filed live) · {d.people} people · {d.high_risk_people} high-risk · {d.calls} calls</span><span>Inbox: {d.inbox?.new || 0} new of {d.inbox?.total || 0} · {d.sent || 0} sent</span></div>
        {d.alerts?.length > 0 && <div><h4>Alerts here</h4>{d.alerts.map(a => <div className="line" key={a.id}><button onClick={() => onPick({ kind: 'alert', id: a.id })}>{a.title}</button><span>{a.severity}</span></div>)}</div>}
        {d.top_people?.length > 0 && <div><h4>Top people</h4>{d.top_people.map(p => <div className="line" key={p.id}><button onClick={() => onPick({ kind: 'entity', id: p.id })}>{p.name}</button><span>risk {p.risk}{p.other_stations?.length ? ' · also ' + p.other_stations.join(', ') : ''}</span></div>)}</div>}
        {d.links?.length > 0 && <div><h4>Linked stations</h4>{d.links.map(l => { const o = l.a === d.id ? [l.b, l.b_name] : [l.a, l.a_name]; return <div className="line" key={o[0]}><button onClick={() => onPick({ kind: 'station', id: o[0] })}>{o[1]}</button><span>{l.entities?.length || 0} shared people · {l.alerts?.length || 0} alerts</span></div> })}</div>}
        {d.recent_firs?.length > 0 && <div><h4>Recent FIRs</h4>{d.recent_firs.map(f => <div className="line" key={f.fir_id}><button onClick={() => onPick({ kind: 'fir', id: f.fir_id })}>{f.fir_id}</button><span>{fmtDate(f.date)}</span></div>)}</div>}
        <div className="slip-acts"><button className="btn" onClick={() => onMap(sel, d)}>Show on map</button></div>
      </>
    }
  }
  return (
    <aside className={'slip' + (sel ? ' open' : '')} aria-live="polite">
      <div className="slip-h"><div><h3>{title || (sel && !err ? 'Loading…' : '')}</h3><p>{sub}</p></div><button className="x" aria-label="Close" onClick={onClose}>×</button></div>
      <div className="slip-b">{err ? <div className="err">{err}</div> : body}</div>
    </aside>
  )
}
