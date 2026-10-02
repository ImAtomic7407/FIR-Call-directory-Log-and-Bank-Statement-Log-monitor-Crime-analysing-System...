// Shared data helpers for the three prototypes. Data is a snapshot of the live API (data.js);
// chat goes to the running backend on :8000.
(function () {
  const D = window.XDATA
  const G = D.graph
  const byId = Object.fromEntries(G.nodes.map(n => [n.id, n]))
  const comms = Object.fromEntries(G.communities.map(c => [c.id, c]))
  const persons = G.nodes.filter(n => n.type === 'person')
  const alerts = D.alerts
  const PERSON_LINKS = new Set(['call', 'transfer', 'associate', 'works_with'])

  const ALERT_NAME = {
    shared_phone: 'One phone, many names',
    circular_transfer: 'Money going in a circle',
    burst_calling: 'Sudden burst of calls',
    co_location: 'Same place, same time',
    sudden_contact: 'Groups suddenly in contact',
    layering: 'Money split and re-joined',
    shared_vehicle: 'Vehicle shared across groups',
  }

  const riskBand = r => (r == null ? 'none' : r >= 60 ? 'high' : r >= 30 ? 'medium' : 'low')
  const inr = n => '₹' + Number(n).toLocaleString('en-IN')
  const shortDate = s => (s ? new Date(s.replace(' ', 'T')).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '')

  // One edge per person pair, carrying which kinds of link exist between them.
  function personPairs() {
    const m = new Map()
    for (const e of G.edges) {
      if (!PERSON_LINKS.has(e.etype)) continue
      if (byId[e.source]?.type !== 'person' || byId[e.target]?.type !== 'person') continue
      const k = [e.source, e.target].sort().join('|')
      const p = m.get(k) || { id: 'p:' + k, source: e.source, target: e.target, calls: 0, amount: 0, txns: 0, fir: 0, evidence: [] }
      if (e.etype === 'call') p.calls += e.count || 1
      else if (e.etype === 'transfer') { p.txns += e.count || 1; p.amount += e.amount || 0 }
      else p.fir += 1
      p.evidence.push(...(e.evidence || []))
      m.set(k, p)
    }
    for (const p of m.values()) {
      p.kind = p.txns ? 'money' : p.calls ? 'call' : 'fir'
      p.weight = p.calls + 3 * p.txns + 2 * p.fir
      const a = byId[p.source].community, b = byId[p.target].community
      p.cross = a != null && b != null && a !== b
      p.community = p.cross ? null : a
    }
    return [...m.values()]
  }

  function neighbours(id) {
    const out = new Set()
    for (const p of personPairs()) {
      if (p.source === id) out.add(p.target)
      if (p.target === id) out.add(p.source)
    }
    return [...out]
  }

  function alertsFor(id) { return alerts.filter(a => a.entities.includes(id)) }

  async function ask(message) {
    const r = await fetch('http://127.0.0.1:8000/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: 'proto' }),
    })
    if (!r.ok) throw new Error('The backend answered ' + r.status)
    return r.json()
  }

  const EXAMPLES = ['Bunty ke calls dikhao', 'Who are the top 5 suspects?', 'Show money circles', 'Jatin Singhal ka network batao']

  window.X = { D, G, byId, comms, persons, alerts, ALERT_NAME, riskBand, inr, shortDate, personPairs, neighbours, alertsFor, ask, EXAMPLES,
    entity: id => D.entities[id], metrics: D.metrics, health: D.health, llm: D.llm }
})()
