import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { KIND_LABEL, ago, band } from './util'

export const EXAMPLES = [
  'Who are the most connected people?',
  'Show the alerts',
  'Who is Bunty connected to?',
  'Bunty ke calls dikhao',
  'Which people have the highest risk?',
  'Show the gangs in the network',
]

export function Alerts({ alerts, sel, seen, onOpen, mine, stations = [], persons = [], draft, onDraft, onRaised }) {
  const list = mine ? alerts.filter(a => !a.geo?.stations?.length || a.geo.stations.some(s => s.station === mine && s.routed)) : alerts
  return <>
    <div className="hrow"><h2>Alerts raised</h2>
      {!draft && <button className="btn" onClick={() => onDraft({ entities: [], firs: [] })}>Raise an alert</button>}</div>
    {draft && <RaiseAlert viewer={mine} stations={stations} persons={persons} draft={draft} onCancel={() => onDraft(null)} onDone={a => { onDraft(null); onRaised(a) }} />}
    <p className="lede">{list.length} alerts{mine ? ' for your station' : ' across all stations'}. Open one to see who is involved and where.</p>
    {list.map((a, i) => (
      <button key={a.id} className={'noting' + (sel === a.id ? ' sel' : '')} onClick={() => onOpen(a.id)}>
        <span className="para">{i + 1}.</span>
        {a.custom ? <span className="stamp hand">By hand</span> : seen.has(a.id) && <span className="stamp">Seen</span>}
        {!a.custom && a.geo?.cross_station && <span className="stamp red">Cross-station</span>}
        <span className={'kind ' + a.severity}>{a.custom ? `${a.id} · raised by ${a.details.raised_by_name}` : a.type.replace(/_/g, ' ')} · {a.severity}</span>
        <b>{a.title}</b><p>{a.summary}</p>
      </button>
    ))}
    {!list.length && <div className="empty">No alerts for this view.</div>}
  </>
}

const FIR_RX = /^FIR-\d{3}$/i
function RaiseAlert({ viewer, stations, persons, draft, onCancel, onDone }) {
  const [by, setBy] = useState(viewer || ''), [title, setTitle] = useState(''), [sev, setSev] = useState('medium'), [note, setNote] = useState('')
  const [ents, setEnts] = useState(draft.entities || []), [firs, setFirs] = useState(draft.firs || []), [to, setTo] = useState([])
  const [pq, setPq] = useState(''), [fq, setFq] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { if (viewer) setBy(viewer) }, [viewer])
  const name = id => persons.find(p => p.id === id)?.label || persons.find(p => p.id === id)?.name || id
  const matches = pq.trim().length > 1 ? persons.filter(p => !ents.includes(p.id) && ((p.label || p.name || '') + ' ' + p.id).toLowerCase().includes(pq.trim().toLowerCase())).slice(0, 6) : []
  const addFir = () => { const f = fq.trim().toUpperCase(); if (!FIR_RX.test(f)) return setErr('FIR numbers look like FIR-012'); if (!firs.includes(f)) setFirs([...firs, f]); setFq(''); setErr('') }
  const submit = async e => {
    e.preventDefault(); setBusy(true); setErr('')
    try { onDone(await api.raiseAlert({ station: by, title, note, severity: sev, entities: ents, firs, to_stations: to })) } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return <form className="raise" onSubmit={submit}>
    <h3 className="sub">Raise an alert by hand</h3>
    {!viewer && <div className="fld"><label htmlFor="ra-by">Raised by</label><select id="ra-by" required value={by} onChange={e => setBy(e.target.value)}><option value="">Choose station…</option>{stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>}
    <div className="fld"><label htmlFor="ra-t">What is the alert</label><input id="ra-t" required maxLength="120" placeholder="Bunty seen with a new associate near the mandi" value={title} onChange={e => setTitle(e.target.value)} /></div>
    <div className="fld"><span className="lbl">How serious</span><div className="seg" role="group" aria-label="How serious">
      {['high', 'medium', 'low'].map(v => <button type="button" key={v} className={'tool sev-' + v} aria-pressed={sev === v} onClick={() => setSev(v)}>{v}</button>)}</div></div>
    <div className="fld"><label htmlFor="ra-p">People</label>
      <div className="chips">{ents.map(id => <span key={id} className="chip on">{name(id)}<button type="button" aria-label={'Remove ' + name(id)} onClick={() => setEnts(ents.filter(x => x !== id))}>×</button></span>)}</div>
      <input id="ra-p" placeholder="Type a name, alias or E-number" value={pq} onChange={e => setPq(e.target.value)} autoComplete="off"
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (matches[0]) { setEnts([...ents, matches[0].id]); setPq('') } } }} />
      {matches.length > 0 && <div className="sugg">{matches.map(p => <button type="button" key={p.id} onClick={() => { setEnts([...ents, p.id]); setPq('') }}>{p.label || p.name} <small>{p.id} · risk {p.risk ?? '–'}</small></button>)}</div>}</div>
    <div className="fld"><label htmlFor="ra-f">FIRs</label>
      <div className="chips">{firs.map(f => <span key={f} className="chip on">{f}<button type="button" aria-label={'Remove ' + f} onClick={() => setFirs(firs.filter(x => x !== f))}>×</button></span>)}</div>
      <div className="inl"><input id="ra-f" placeholder="FIR-012" value={fq} onChange={e => setFq(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addFir() } }} />
        <button type="button" className="tool" onClick={addFir} disabled={!fq.trim()}>Add</button></div></div>
    <div className="fld"><span className="lbl">Send to stations <small>(optional; your own station always sees it)</small></span>
      <div className="chips">{stations.filter(s => s.id !== by).map(s => <button type="button" key={s.id} className="tool" aria-pressed={to.includes(s.id)} onClick={() => setTo(to.includes(s.id) ? to.filter(x => x !== s.id) : [...to, s.id])}>{s.short || s.name}</button>)}</div></div>
    <div className="fld"><label htmlFor="ra-n">Note for other officers</label><textarea id="ra-n" rows="3" placeholder="What was seen, by whom, what to do" value={note} onChange={e => setNote(e.target.value)} /></div>
    {err && <div className="err" role="alert">{err}</div>}
    <div className="acts"><button className="btn red" disabled={busy || !by || !title.trim() || (!ents.length && !firs.length)}>{busy ? 'Raising…' : to.length ? `Raise and send to ${to.length}` : 'Raise alert'}</button>
      <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
      {!ents.length && !firs.length && <small className="hint">Add at least one person or FIR.</small>}</div>
  </form>
}

export function People({ top, persons, onOpen }) {
  const ps = [...persons].sort((a, b) => (b.risk || 0) - (a.risk || 0))
  return <>
    <h2>People, by risk</h2>
    <p className="lede">Risk out of 100 = importance in the network + involvement in alerts + money moved.</p>
    {ps.map((n, i) => (
      <button key={n.id} className="person-row" onClick={() => onOpen(n.id)}>
        <span className="no">{i + 1}.</span>
        <span><b>{n.label}</b><small>{n.role || 'person'} · {n.community ? 'Group ' + n.community : 'no group'}</small></span>
        <span className={'r tab ' + band(n.risk)}>{n.risk ?? '–'}</span>
      </button>
    ))}
  </>
}

export function Ask({ qa, onCmd, onSend, llm }) {
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [qa.length, qa.at(-1)?.a])
  return (
    <div className="ask-sheet">
      <div>
        <h2>Ask the records</h2>
        <p className="lede">English or Hinglish. Ask about people, calls, money, alerts and gangs. {llm?.reachable ? 'The AI reads your request; rules double-check it.' : 'The AI is offline, so simple rules are answering.'}</p>
        <div className="examples">{EXAMPLES.map(q => <button key={q} onClick={() => onSend(q)}>{q}</button>)}</div>
      </div>
      {qa.map((x, i) => (
        <div className="qa" key={i}>
          <div className="q">{x.q}</div>
          <div className="a">{x.a ?? 'Looking through the records…'}</div>
          {x.cmds?.length > 0 && <div className="acts">{x.cmds.filter(c => c.op !== 'highlight' && c.op !== 'fit').map((c, k) => <span key={k} className="act">{describe(c)}</span>)}
            <button className="act" onClick={() => onCmd(x.cmds)}>Run again</button></div>}
          {x.router && <div className="src"><span>{x.router === 'llm' ? 'Understood by AI, checked by rules' : 'Understood by rules'}{x.chat ? ` · ${Object.values(x.chat.evidence || {}).flat().length} records` : ''}</span></div>}
        </div>
      ))}
      <div ref={end} />
    </div>
  )
}

function describe(c) {
  switch (c.op) {
    case 'fly': return `Fly to ${c.target.name}`
    case 'filter': return c.reset ? 'Clear filters' : 'Filter: ' + Object.entries(c.set).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')
    case 'layers': return [c.show?.length && 'Show ' + c.show.join(', '), c.hide?.length && 'Hide ' + c.hide.join(', ')].filter(Boolean).join(' · ')
    case 'heat': return c.metric === 'off' ? 'Heat off' : 'Heat: ' + c.metric.replace('_', ' ')
    case 'camera': return 'Camera: ' + c.mode
    case 'tour': return `Tour (${c.stops.length} stops)`
    default: return c.op
  }
}

export function Inbox({ viewer, stations, refreshKey, onOpen, onChanged }) {
  const [dir, setDir] = useState('in'), [items, setItems] = useState([]), [err, setErr] = useState('')
  const [reply, setReply] = useState({}), [form, setForm] = useState(false)
  const [d, setD] = useState({ to: '', kind: 'request_assistance', title: '', body: '', severity: 'medium' }), [ok, setOk] = useState('')
  const load = () => api.notifications({ station: viewer, direction: viewer ? dir : '' }).then(r => setItems(Array.isArray(r) ? r : r.items || [])).catch(e => setErr(e.message))
  useEffect(() => { load() }, [viewer, dir, refreshKey])
  const name = id => stations.find(s => s.id === id)?.name || id
  const send = async e => {
    e.preventDefault(); setErr(''); setOk('')
    try { await api.send({ from_station: viewer, to_stations: [d.to], kind: d.kind, title: d.title, body: d.body, severity: d.severity }); setOk('Sent to ' + name(d.to)); setD({ ...d, title: '', body: '' }); setDir('out'); onChanged?.() }
    catch (e2) { setErr(e2.message) }
  }
  return <>
    <h2>Station inbox</h2>
    <p className="lede">{viewer ? `Messages for ${name(viewer)}. Alerts from other stations land here the moment a FIR is filed.` : 'You are viewing as the command centre, so every message is shown. Choose a station at the top to act as one.'}</p>
    {viewer && <div className="seg"><button aria-pressed={dir === 'in'} onClick={() => setDir('in')}>Received</button><button aria-pressed={dir === 'out'} onClick={() => setDir('out')}>Sent</button></div>}
    {viewer && <button className="btn ghost" style={{ marginLeft: 8 }} onClick={() => setForm(!form)}>{form ? 'Close' : 'Write to a station'}</button>}
    {form && viewer && <form onSubmit={send} style={{ margin: '4px 0 14px' }}>
      <div className="row2">
        <div className="fld"><label htmlFor="n-to">To</label><select id="n-to" required value={d.to} onChange={e => setD({ ...d, to: e.target.value })}><option value="">Choose…</option>{stations.filter(s => s.id !== viewer).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="fld"><label htmlFor="n-k">Type</label><select id="n-k" value={d.kind} onChange={e => setD({ ...d, kind: e.target.value })}><option value="request_assistance">Request help</option><option value="share_intel">Share intel</option><option value="bolo">Be on the lookout</option></select></div>
      </div>
      <div className="fld"><label htmlFor="n-t">Subject</label><input id="n-t" required value={d.title} onChange={e => setD({ ...d, title: e.target.value })} /></div>
      <div className="fld"><label htmlFor="n-b">Message</label><textarea id="n-b" rows="3" value={d.body} onChange={e => setD({ ...d, body: e.target.value })} /></div>
      <button className="btn">Send</button>
    </form>}
    {err && <div className="err">{err}</div>}{ok && <div className="okmsg">{ok}</div>}
    {items.map(n => (
      <div key={n.id} className={'note-card' + (n.status === 'new' && n.to_station === viewer ? ' new' : '')}>
        <div className="nh"><span className={'nk ' + n.severity}>{KIND_LABEL[n.kind] || n.kind}</span><span className="nm">{n.id} · {ago(n.ts)}</span></div>
        <div className="nt">{n.title}</div>
        <div className="nm">{n.from_name || name(n.from_station)} → {n.to_name || name(n.to_station)}{n.status === 'ack' ? ' · acknowledged' : ''}</div>
        {n.body && <p>{n.body}</p>}
        {n.responses?.map((r, i) => <div className="reply" key={i}>{r.from_name || r.from_station}: {r.text || r.body}</div>)}
        <div className="acts">
          {(n.refs?.alert_id || n.refs?.alert_sig) && <button className="btn ghost" onClick={() => onOpen(n)}>Look at it</button>}
          {viewer && n.to_station === viewer && n.status === 'new' && <button className="btn" onClick={() => api.ack(n.id, viewer).then(() => { load(); onChanged?.() })}>Acknowledge</button>}
          {viewer && n.to_station === viewer && n.kind !== 'reply' && <button className="btn ghost" onClick={() => setReply({ ...reply, [n.id]: reply[n.id] ?? '' })}>Reply</button>}
        </div>
        {reply[n.id] !== undefined && <form className="reply" onSubmit={e => { e.preventDefault(); api.respond(n.id, viewer, reply[n.id]).then(() => { setReply(({ [n.id]: _, ...r }) => r); load() }).catch(x => setErr(x.message)) }}>
          <input style={{ width: '100%' }} autoFocus aria-label="Reply" placeholder="Type a reply and press Enter" value={reply[n.id]} onChange={e => setReply({ ...reply, [n.id]: e.target.value })} /></form>}
      </div>
    ))}
    {!items.length && <div className="empty">Nothing here yet.</div>}
  </>
}

export function FileFir({ viewer, stations, onFiled }) {
  const [st, setSt] = useState(viewer || ''), [text, setText] = useState(''), [rep, setRep] = useState(''), [res, setRes] = useState(null), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { if (viewer) setSt(viewer) }, [viewer])
  const go = async fn => { setBusy(true); setErr(''); try { const r = await fn(); setRes(r); onFiled?.(r) } catch (e) { setErr(e.message) } setBusy(false) }
  return <>
    <h2>File a new FIR</h2>
    <p className="lede">Write it in plain words, naming people with their phone numbers. Other stations that share a person, area or pattern are alerted straight away.</p>
    <form onSubmit={e => { e.preventDefault(); go(() => api.fileFir({ station: st, text, reporter: rep || undefined })).then(() => setText('')) }}>
      <div className="fld"><label htmlFor="f-s">Station filing it</label><select id="f-s" required value={st} onChange={e => setSt(e.target.value)}><option value="">Choose…</option>{stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      <div className="fld"><label htmlFor="f-t">What happened</label><textarea id="f-t" rows="6" required minLength="20" placeholder="On 20 Sept 2026 at Okhla Phase 2, acting on a tip-off, officers searched a warehouse. Accused Bhuvan Rathore, phone 9810012345, was found with…" value={text} onChange={e => setText(e.target.value)} /></div>
      <div className="fld"><label htmlFor="f-r">Reporting officer (optional)</label><input id="f-r" value={rep} onChange={e => setRep(e.target.value)} /></div>
      <button className="btn" disabled={busy || !st || text.length < 20}>{busy ? 'Filing…' : 'File FIR'}</button>
    </form>
    {err && <div className="err">{err}</div>}
    {res?.fir && <div className="okmsg">Filed {res.fir.fir_id}. {res.summary} {res.notifications?.length ? `${res.notifications.length} station notice(s) sent.` : ''}</div>}
    <h2 style={{ marginTop: 24 }}>Live data</h2>
    <p className="lede">FIRs you file here are kept until you remove them.</p>
    <button className="btn ghost" disabled={busy} onClick={() => confirm('Remove all live FIRs and notifications?') && go(api.demoReset)}>Reset live data</button>
  </>
}

export function Stations({ stations, viewer, links, onMap, onOnly, onViewAs, onBack, onOpen }) {
  const [sort, setSort] = useState('alerts')
  const keyOf = { alerts: s => s.high_alerts * 100 + s.alerts, firs: s => s.firs, cross: s => s.cross_station_alerts, inbox: s => s.unread_notifications }
  const list = [...stations].sort((a, b) => keyOf[sort](b) - keyOf[sort](a))
  const maxA = Math.max(1, ...stations.map(s => s.alerts))
  const me = stations.find(s => s.id === viewer)
  const mine = viewer ? links.filter(l => l.a === viewer || l.b === viewer).sort((a, b) => b.weight - a.weight) : []
  const tot = stations.reduce((t, s) => ({ firs: t.firs + s.firs, cross: t.cross + (s.cross_station_alerts ? 1 : 0), unread: t.unread + s.unread_notifications }), { firs: 0, cross: 0, unread: 0 })
  return <>
    <h2>{me ? me.name : 'All police stations'}</h2>
    <p className="lede">{me
      ? `${me.district}, ${me.state} · ${me.firs} FIRs · ${me.alerts} alerts (${me.high_alerts} high) · ${me.unread_notifications} unread messages`
      : `${stations.length} stations · ${tot.firs} FIRs · ${tot.cross} stations share alerts with another station · ${tot.unread} unread messages`}</p>
    {me && <>
      <div className="stn-a"><button className="tool" onClick={onBack}>← Back to command centre (all stations)</button></div>
      <h3 className="sub">Stations linked to yours</h3>
      {!mine.length && <div className="empty">No shared people or alerts with other stations.</div>}
      {mine.map(l => {
        const other = l.a === viewer ? { id: l.b, name: l.b_name } : { id: l.a, name: l.a_name }
        return <div key={other.id} className="stn">
          <div className="stn-h"><b>{other.name}</b><span className="n">{l.weight} shared links</span></div>
          <p className="stn-p">{l.entities.slice(0, 4).map(e => e.name).join(', ')}{l.entities.length > 4 ? ` +${l.entities.length - 4} more` : ''}</p>
          <div className="stn-a">
            {l.alerts.slice(0, 6).map(a => <button key={a} className="chip" onClick={() => onOpen(a)}>{a}</button>)}
            <button className="tool" onClick={() => onMap(viewer)}>Show link on map</button>
          </div>
        </div>
      })}
      <h3 className="sub">Every station</h3>
    </>}
    <div className="sortbar" role="group" aria-label="Sort stations">
      <small>Sort by</small>
      {[['alerts', 'Alerts'], ['firs', 'FIRs'], ['cross', 'Cross-station'], ['inbox', 'Unread']].map(([k, v]) =>
        <button key={k} className="tool" aria-pressed={sort === k} onClick={() => setSort(k)}>{v}</button>)}
    </div>
    {list.map(s => (
      <div key={s.id} className={'stn' + (s.id === viewer ? ' me' : '')}>
        <div className="stn-h"><b>{s.name}</b><span className="d">{s.district}, {s.state}</span></div>
        <div className="stn-bar" aria-hidden="true"><i className="h" style={{ width: `${(s.high_alerts / maxA) * 100}%` }} /><i style={{ width: `${((s.alerts - s.high_alerts) / maxA) * 100}%` }} /></div>
        <div className="stn-n">
          <span><b>{s.firs}</b> FIRs{s.live_firs ? ` (${s.live_firs} new)` : ''}</span>
          <span className={s.high_alerts ? 'r' : ''}><b>{s.alerts}</b> alerts{s.high_alerts ? `, ${s.high_alerts} high` : ''}</span>
          <span><b>{s.cross_station_alerts}</b> cross-station</span>
          {s.unread_notifications > 0 && <span className="r"><b>{s.unread_notifications}</b> unread</span>}
        </div>
        <div className="stn-a">
          <button className="tool" onClick={() => onMap(s.id)}>Show on map</button>
          <button className="tool" onClick={() => onOnly(s.id)}>Only this station</button>
          {s.id !== viewer && <button className="tool" onClick={() => onViewAs(s.id)}>View as this station</button>}
        </div>
      </div>
    ))}
  </>
}
