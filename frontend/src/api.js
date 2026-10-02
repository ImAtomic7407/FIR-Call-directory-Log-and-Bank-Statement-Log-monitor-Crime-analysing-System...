const BASE = '/api'

async function j(path, opts) {
  const r = await fetch(BASE + path, opts)
  if (!r.ok) {
    let msg = `${path}: ${r.status}`
    try { const b = await r.json(); if (typeof b.detail === 'string') msg = b.detail } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json()
}
const post = (path, body) => j(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const qs = p => new URLSearchParams(Object.entries(p || {}).filter(([, v]) => v !== '' && v != null && v !== false)).toString()

export const api = {
  raiseAlert: b => post('/alerts/custom', b),
  withdrawAlert: (id, station) => j(`/alerts/custom/${id}?station=${encodeURIComponent(station)}`, { method: 'DELETE' }),
  health: () => j('/health'),
  llm: () => j('/llm/status'),
  metrics: () => j('/metrics'),
  alerts: () => j('/alerts'),
  entity: id => j(`/entity/${id}`),
  record: id => j(`/record/${id}`),
  graph: p => j('/graph?' + qs(p)),
  chat: (message, session_id) => post('/chat', { message, session_id }),
  mapAsk: (message, session_id) => post('/map/ask', { message, session_id }),
  reportUrl: id => (id ? `${BASE}/report/${id}.pdf` : `${BASE}/report.pdf`),
  // map + stations + live
  mapFilters: () => j('/map/filters'),
  mapStations: p => j('/map/stations?' + qs(p)),
  mapFeatures: p => j('/map/features?' + qs(p)),
  mapHeat: p => j('/map/heat?' + qs(p)),
  mapLinks: p => j('/map/links?' + qs(p)),
  station: id => j(`/stations/${id}`),
  alertsGeo: () => j('/alerts/geo'),
  notifications: p => j('/notifications?' + qs(p)),
  send: body => post('/notifications', body),
  ack: (id, station) => post(`/notifications/${id}/ack`, { station }),
  respond: (id, station, text) => post(`/notifications/${id}/respond`, { station, text }),
  fileFir: body => post('/firs', body),
  demoFire: () => post('/demo/fire', {}),
  demoReset: () => post('/demo/reset', {}),
  streamUrl: (station, since) => `${BASE}/stream?${qs({ station, since })}`,
}
