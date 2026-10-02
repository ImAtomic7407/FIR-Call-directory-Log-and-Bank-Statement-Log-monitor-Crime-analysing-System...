import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { api } from './api'

maplibregl.setWorkerUrl(workerUrl)
const STREETS = 'https://tiles.openfreemap.org/styles/positron'
const OURS = new Set(['bg', 'zones-flat', 'zones-line', 'heat', 'towers', 'ents', 'links', 'links-hit', 'firs'])
const BLANK = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f1efe3' } }] }
const BOUNDS = [[76.55, 28.2], [77.75, 28.95]]
const HOME = { center: [77.16, 28.6], zoom: 9.7, pitch: 0, bearing: 0 }
const ZOOM = { station: 12.6, area: 13.6, entity: 14.6, alert: 13.8, fir: 14.6 }
const EMPTY_F = { station: '', district: '', state: '', area: '', start: '', end: '', min_risk: 0, severity: '', alert_type: '', source: '', cross_station: false, q: '' }
const LAYER_DEFS = [['zones', 'Zones'], ['firs', 'FIRs'], ['towers', 'Towers'], ['entities', 'People'], ['alerts', 'Alerts'], ['links', 'Links'], ['heat', 'Heat'], ['buildings', 'Streets']]
const HEATS = [['calls', 'Calls'], ['night_calls', 'Night calls'], ['firs', 'FIRs'], ['alerts', 'Alerts'], ['risk', 'High-risk people']]
const empty = { type: 'FeatureCollection', features: [] }

const sq = (lat, lon, d) => {
  const k = d / Math.cos((lat * Math.PI) / 180)
  return [[[lon - k, lat - d], [lon + k, lat - d], [lon + k, lat + d], [lon - k, lat + d], [lon - k, lat - d]]]
}
const arc = (a, b, n = 28) => {
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, dx = b[0] - a[0], dy = b[1] - a[1]
  const cx = mx - dy * 0.22, cy = my + dx * 0.22
  return Array.from({ length: n + 1 }, (_, i) => { const t = i / n; return [(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * cx + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * cy + t * t * b[1]] })
}
const wait = ms => new Promise(r => setTimeout(r, ms))

const loadStyle = () => {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 4000)
  return fetch(STREETS, { signal: ac.signal }).then(r => (r.ok ? r.json() : BLANK)).catch(() => BLANK).finally(() => clearTimeout(t))
}

const MapView = forwardRef(function MapView({ viewer, refreshKey, highlight, onPick, onExec, visible }, ref) {
  const box = useRef(null), map = useRef(null), ready = useRef(false), pending = useRef([])
  const markers = useRef([]), ping = useRef(null), tour = useRef({ run: 0 })
  const cbs = useRef({}); cbs.current = { onPick, onExec }
  const [opts, setOpts] = useState(null)
  const [F, setF] = useState(EMPTY_F)
  const [L, setL] = useState({ zones: true, firs: true, towers: true, entities: true, alerts: true, links: true, heat: false, buildings: true })
  const [heat, setHeat] = useState('calls')
    const [data, setData] = useState({ stations: [], feats: [], links: [], heat: null })
  const [tag, setTag] = useState('')
  const [tourState, setTourState] = useState(null)
  const [more, setMore] = useState(false)
  const [focus, setFocus] = useState('')
  const [streets, setStreets] = useState(null)
  const Fr = useRef(F); Fr.current = F

  useEffect(() => { api.mapFilters().then(setOpts).catch(() => {}) }, [])

  // ------------------------------------------------------------------ data
  useEffect(() => {
    const p = { station: F.station, district: F.district, state: F.state, area: F.area, start: F.start, end: F.end, min_risk: F.min_risk || '',
      severity: F.severity, alert_type: F.alert_type, source: F.source, cross_station: F.cross_station || '', q: F.q }
    const base = { station: F.station, district: F.district, state: F.state, start: F.start, end: F.end }
    const t = setTimeout(() => {
      Promise.all([api.mapStations(base), api.mapFeatures(p), api.mapLinks({ station: F.station, min_risk: F.min_risk || '' }),
        L.heat && heat !== 'off' ? api.mapHeat({ metric: heat, ...base }) : Promise.resolve(null)])
        .then(([stations, f, links, h]) => setData({ stations, feats: f.features, links, heat: h })).catch(() => {})
    }, 160)
    return () => clearTimeout(t)
  }, [F, refreshKey, L.heat, heat])

  // ------------------------------------------------------------------ map setup
  useEffect(() => {
    let dead = false, m
    loadStyle().then(style => {
      setStreets(style !== BLANK)
      if (dead) return
      m = map.current = new maplibregl.Map({ container: box.current, style, ...HOME, minZoom: 8.6, maxZoom: 17, maxBounds: BOUNDS, renderWorldCopies: false, maxPitch: 0, dragRotate: false, touchPitch: false, attributionControl: { compact: true } })
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      m.on('load', () => {
        m.addSource('zones', { type: 'geojson', data: empty });
        m.addLayer({ id: 'zones-flat', type: 'fill', source: 'zones', paint: { 'fill-color': ['interpolate', ['linear'], ['get', 'sev'], 0, '#dfe8cf', 0.5, '#f4d98b', 1, '#e8a193'], 'fill-opacity': 0.32 } }); m.addSource('towers', { type: 'geojson', data: empty }); m.addSource('ents', { type: 'geojson', data: empty })
        m.addSource('firs', { type: 'geojson', data: empty }); m.addSource('links', { type: 'geojson', data: empty }); m.addSource('heat', { type: 'geojson', data: empty })
        m.addLayer({ id: 'heat', type: 'heatmap', source: 'heat', maxzoom: 15, paint: { 'heatmap-weight': ['get', 'intensity'], 'heatmap-intensity': 1.3, 'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 38, 14, 90],
          'heatmap-opacity': 0.75, 'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.2, '#ffe9a8', 0.5, '#f4a340', 0.8, '#d6453a', 1, '#8f1710'] } })
        m.addLayer({ id: 'zones-line', type: 'line', source: 'zones', paint: { 'line-color': ['case', ['get', 'me'], '#0d6a3d', '#4a5078'], 'line-width': ['case', ['get', 'me'], 3, 1.2], 'line-dasharray': [3, 2], 'line-opacity': 0.85 } })
        m.addLayer({ id: 'towers', type: 'circle', source: 'towers', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['+', 3, ['*', ['sqrt', ['get', 'calls']], 0.6]], 14, ['+', 6, ['*', ['sqrt', ['get', 'calls']], 1.6]]],
          'circle-color': '#1c2453', 'circle-opacity': 0.28, 'circle-stroke-color': '#1c2453', 'circle-stroke-width': 1.4, 'circle-stroke-opacity': 0.8 } })
        m.addLayer({ id: 'ents', type: 'circle', source: 'ents', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['+', 3, ['*', ['get', 'risk'], 0.05]], 14, ['+', 6, ['*', ['get', 'risk'], 0.14]]],
          'circle-stroke-width': 1.6, 'circle-stroke-color': '#fff', 'circle-opacity': 0.95,
          'circle-color': ['case', ['get', 'dim'], '#d4d6ca', ['get', 'hl'], '#f3b800', ['>=', ['get', 'risk'], 60], '#b3261e', ['>=', ['get', 'risk'], 30], '#c77a00', '#5a3e98'] } })
        m.addLayer({ id: 'links', type: 'line', source: 'links', layout: { 'line-cap': 'round' }, paint: { 'line-color': ['case', ['get', 'on'], '#b3261e', '#7a6f66'], 'line-width': ['get', 'w'], 'line-opacity': ['case', ['get', 'on'], 0.85, 0.28], 'line-dasharray': [2, 1.4] } })
        m.addLayer({ id: 'links-hit', type: 'line', source: 'links', paint: { 'line-color': '#000', 'line-width': 12, 'line-opacity': 0 } })
        m.addLayer({ id: 'firs', type: 'circle', source: 'firs', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 8], 'circle-color': ['case', ['==', ['get', 'src'], 'live'], '#1f9d55', '#5a3e98'], 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } })
        for (const id of ['ents', 'towers', 'firs', 'links-hit']) {
          m.on('mouseenter', id, () => (m.getCanvas().style.cursor = 'pointer'))
          m.on('mouseleave', id, () => (m.getCanvas().style.cursor = ''))
        }
        const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 })
        m.on('mousemove', e => {
          const f = m.queryRenderedFeatures(e.point, { layers: ['ents', 'firs'] })[0]
          if (!f) return tip.remove()
          const pr = f.properties
          tip.setLngLat(e.lngLat).setHTML(f.layer.id === 'ents' ? `<b>${pr.name || pr.id}</b>risk ${pr.risk}` : `<b>${pr.id}</b>${pr.src === 'live' ? 'filed live' : 'original record'}`).addTo(m)
        })
        m.on('click', e => {
          const fs = m.queryRenderedFeatures(e.point, { layers: ['ents', 'firs', 'towers', 'links-hit', 'zones-flat'].filter(l => m.getLayer(l)) })
          const f = fs[0]
          if (!f) return
          const pr = f.properties
          if (f.layer.id === 'ents') cbs.current.onPick({ kind: 'entity', id: pr.id })
          else if (f.layer.id === 'firs') cbs.current.onPick({ kind: 'fir', id: pr.id })
          else if (f.layer.id === 'towers') new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat).setHTML(`<b>${pr.name}</b>${pr.calls} calls · ${pr.people} people · ${pr.night} at night`).addTo(m)
          else if (f.layer.id === 'links-hit') new maplibregl.Popup({ closeButton: true, maxWidth: '300px' }).setLngLat(e.lngLat).setHTML(pr.html).addTo(m)
          else { setFocus(pr.id); cbs.current.onPick({ kind: 'station', id: pr.id }) }
        })
        const zc = () => box.current?.classList.toggle('far', m.getZoom() < 10.3)
        m.on('zoom', zc); zc()
        ready.current = true
        setData(d => ({ ...d })) // draw what already arrived
        pending.current.splice(0).forEach(c => run(c))
      })
    })
    return () => { dead = true; ready.current = false; tour.current.run++; markers.current.forEach(x => x.remove()); m?.remove(); map.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { if (visible) setTimeout(() => map.current?.resize(), 30) }, [visible])

  // ------------------------------------------------------------------ drawing
  const hl = useMemo(() => new Set(highlight?.nodes || []), [highlight])
  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    const vis = (id, on) => m.getLayer(id) && m.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none')
    const { stations, feats, links, heat: h } = data
    const mine = viewer
    m.getSource('zones').setData({ type: 'FeatureCollection', features: stations.map(s => ({ type: 'Feature', properties: { id: s.id, me: s.id === mine, sev: Math.min(1, (s.high_alerts * 2 + s.alerts) / 8),
      h: 250 + s.alerts * 380 + s.firs * 60 }, geometry: { type: 'Polygon', coordinates: [s.jurisdiction] } })) })
    m.getSource('towers').setData({ type: 'FeatureCollection', features: feats.filter(f => f.kind === 'tower').map(f => ({ type: 'Feature', properties: { name: f.name, calls: f.calls, people: f.people, night: f.night_calls }, geometry: { type: 'Point', coordinates: [f.lon, f.lat] } })) })
    m.getSource('ents').setData({ type: 'FeatureCollection', features: feats.filter(f => f.kind === 'entity').map(f => ({ type: 'Feature', properties: { id: f.id, name: f.name, risk: f.risk || 0, hl: hl.has(f.id), dim: hl.size > 0 && !hl.has(f.id) }, geometry: { type: 'Point', coordinates: [f.lon, f.lat] } })) })
    m.getSource('firs').setData({ type: 'FeatureCollection', features: feats.filter(f => f.kind === 'fir').map(f => ({ type: 'Feature', properties: { id: f.id, src: f.source }, geometry: { type: 'Point', coordinates: [f.lon, f.lat] } })) })
    const fx = focus || F.station || mine
    const shown = fx ? links.filter(l => l.a === fx || l.b === fx) : [...links].sort((a, b) => b.weight - a.weight).slice(0, 12)
    const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
    m.getSource('links').setData({ type: 'FeatureCollection', features: shown.map(l => ({ type: 'Feature', properties: { on: !!fx, w: Math.min(fx ? 5 : 3, 0.8 + l.weight * 0.25),
      html: `<b>${esc(l.a_name)} ↔ ${esc(l.b_name)}</b>${l.weight} shared links · ${l.entities.length} people<br>${l.entities.slice(0, 5).map(x => esc(x.name)).join(', ')}${l.entities.length > 5 ? '…' : ''}<br>Alerts: ${l.alerts.join(', ') || 'none'}` }, geometry: { type: 'LineString', coordinates: arc([l.a_pos[1], l.a_pos[0]], [l.b_pos[1], l.b_pos[0]]) } })) })
    m.getSource('heat').setData({ type: 'FeatureCollection', features: (h?.points || []).map(p => ({ type: 'Feature', properties: { intensity: p.intensity }, geometry: { type: 'Point', coordinates: [p.lon, p.lat] } })) })
    vis('zones-flat', L.zones); vis('zones-line', L.zones); vis('towers', L.towers); vis('ents', L.entities); vis('firs', L.firs); vis('links', L.links); vis('links-hit', L.links); vis('heat', L.heat && heat !== 'off')
    for (const ly of m.getStyle().layers) if (!OURS.has(ly.id)) m.setLayoutProperty(ly.id, 'visibility', L.buildings ? 'visible' : 'none')

    markers.current.forEach(x => x.remove()); markers.current = []
    const add = (el, lon, lat, onClick) => { el.addEventListener('click', ev => { ev.stopPropagation(); onClick() }); markers.current.push(new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(m)) }
    if (L.zones) for (const s of stations) {
      const el = document.createElement('div'); el.className = 'mk-station' + (s.id === mine ? ' me' : '') + (s.id === fx ? ' focus' : ''); el.title = s.name
      el.innerHTML = `${s.firs}${s.unread_notifications ? `<span class="bd">${s.unread_notifications}</span>` : ''}<span class="mk-label">${s.short}</span>`
      add(el, s.lon, s.lat, () => { setFocus(s.id); cbs.current.onPick({ kind: 'station', id: s.id }) })
    }
    if (L.alerts) for (const f of feats.filter(x => x.kind === 'alert')) {
      const el = document.createElement('div'); el.className = 'mk-alert ' + f.severity; el.textContent = f.id.slice(-2); el.title = f.title
      add(el, f.lon, f.lat, () => cbs.current.onPick({ kind: 'alert', id: f.id }))
    }
  }, [data, L, heat, hl, viewer, focus, F.station])

  // ------------------------------------------------------------------ commands
  const setPing = (lon, lat) => {
    const m = map.current; if (!m) return
    ping.current?.remove()
    const el = document.createElement('div'); el.className = 'mk-ping'
    ping.current = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(m)
    const mine = ping.current
    setTimeout(() => { if (ping.current === mine) { mine.remove(); ping.current = null } }, 6000)
  }
  const flyTo = (t, zoom) => {
    const m = map.current; if (!m) return
    setPing(t.lon, t.lat)
    m.flyTo({ center: [t.lon, t.lat], zoom: zoom || ZOOM[t.kind] || 13, speed: 0.85, curve: 1.5, essential: true })
  }
  const setCamera = useCallback(mo => {
    const m = map.current; if (!m) return
    if (mo === 'top' || mo === '3d' || mo === 'stop') m.easeTo({ bearing: 0, duration: 600 })
  }, [])
  const stopTour = () => { tour.current.run++; setTourState(null) }
  const runTour = async cmd => {
    const id = ++tour.current.run
    for (let i = 0; i < cmd.stops.length; i++) {
      if (tour.current.run !== id) return
      const s = cmd.stops[i]
      setTourState({ i: i + 1, n: cmd.stops.length, label: s.label })
      flyTo({ kind: s.kind, lat: s.lat, lon: s.lon }, ZOOM[s.kind] || 13)
      cbs.current.onPick({ kind: s.kind, id: s.id })
      await wait(cmd.dwell_ms || 4500)
    }
    if (tour.current.run === id) setTourState(null)
  }
  const run = c => {
    const m = map.current
    switch (c.op) {
      case 'fly': flyTo(c.target, c.zoom); setTag(`Flying to ${c.target.name}`); cbs.current.onPick({ kind: c.target.kind, id: c.target.id, quiet: c.target.kind === 'area' }); break
      case 'fit': { const pts = c.points || []; if (!pts.length) break
        const b = new maplibregl.LngLatBounds(); pts.forEach(p => b.extend([p[1], p[0]]))
        m.fitBounds(b, { padding: 90, maxZoom: 14, duration: 1400 }); break }
      case 'filter': setF(c.reset ? EMPTY_F : f => ({ ...f, ...c.set })); setTag(c.reset ? 'Filters cleared' : 'Filtered: ' + Object.entries(c.set).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')); break
      case 'layers': setL(l => { const n = { ...l }; c.show?.forEach(k => (n[k] = true)); c.hide?.forEach(k => (n[k] = false)); return n }); break
      case 'heat': if (c.metric === 'off') setL(l => ({ ...l, heat: false })); else { setHeat(c.metric); setL(l => ({ ...l, heat: true })) } setTag(c.metric === 'off' ? 'Heat off' : `Heat: ${c.metric.replace('_', ' ')}`); break
      case 'camera': setCamera(c.mode); break
      case 'tour': runTour(c); break
      case 'focus': setFocus(c.station || ''); break
      default: break
    }
  }
  useImperativeHandle(ref, () => ({
    exec: c => { if (ready.current) run(c); else pending.current.push(c) },
    focus: (lat, lon, kind) => flyTo({ lat, lon, kind }),
    setTag,
  }))

  // first time we know who the viewer is, show their patch
  const welcomed = useRef(null)
  useEffect(() => {
    if (!viewer || !data.stations.length || welcomed.current === viewer) return
    const s = data.stations.find(x => x.id === viewer); if (!s) return
    welcomed.current = viewer
    if (ready.current) flyTo({ kind: 'station', lat: s.lat, lon: s.lon }, 11.6)
    else pending.current.push({ op: 'fly', target: { kind: 'station', id: s.id, name: s.name, lat: s.lat, lon: s.lon }, zoom: 11.6 })
  }, [viewer, data.stations])

  const fitAll = useCallback(() => {
    const m = map.current; if (!m) return
    const pts = [...data.feats.map(f => [f.lon, f.lat]), ...(F.station || F.district || F.state ? [] : data.stations.map(x => [x.lon, x.lat]))]
    if (!pts.length) return m.flyTo({ ...HOME })
    const b = new maplibregl.LngLatBounds(); pts.forEach(p => b.extend(p))
    m.fitBounds(b, { padding: 70, maxZoom: 13.5, duration: 900 })
  }, [data, F.station, F.district, F.state])
  const area = `${F.station}|${F.district}|${F.state}|${F.area}`, fitted = useRef(area)
  useEffect(() => { if (fitted.current !== area && ready.current) { fitted.current = area; setTimeout(fitAll, 450) } }, [area, data.feats])

  const myStation = useCallback(() => {
    const s = data.stations.find(x => x.id === viewer); if (!s) return
    setFocus(s.id); flyTo({ kind: 'station', lat: s.lat, lon: s.lon }, 12)
  }, [data.stations, viewer])
  useEffect(() => {
    if (!visible) return
    const k = e => {
      if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return
      const m = map.current; if (!m) return
      if (e.key === 'f') fitAll()
      else if (e.key === 'h') m.flyTo({ ...HOME, speed: 0.9 })
      else if (e.key === 'm' && viewer) myStation()
      else if (e.key === '+' || e.key === '=') m.zoomIn()
      else if (e.key === '-') m.zoomOut()
      else if (e.key === 'Escape') { setFocus(''); setTag('') }
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [visible, fitAll, myStation, viewer])

  const set = (k, v) => setF(f => ({ ...f, [k]: v }))
  const nF = Object.entries(F).filter(([, v]) => v && v !== 0).length
  const counts = useMemo(() => { const c = {}; data.feats.forEach(f => (c[f.kind] = (c[f.kind] || 0) + 1)); return c }, [data.feats])
  const areas = (opts?.areas || []).filter(a => !F.station || a.station === F.station)

  return (
    <>
      <div className="fbar">
        <div className="f"><label htmlFor="mf-st">Police station</label>
          <select id="mf-st" value={F.station} onChange={e => set('station', e.target.value)}><option value="">All stations</option>{opts?.stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-st2">State</label>
          <select id="mf-st2" value={F.state} onChange={e => set('state', e.target.value)}><option value="">All</option>{opts?.states.map(s => <option key={s}>{s}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-d">District</label>
          <select id="mf-d" value={F.district} onChange={e => set('district', e.target.value)}><option value="">All</option>{opts?.districts.map(s => <option key={s}>{s}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-a">Area</label>
          <select id="mf-a" value={F.area} onChange={e => set('area', e.target.value)}><option value="">All areas</option>{areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-r">Risk ≥ <span className="pill">{F.min_risk}</span></label>
          <input id="mf-r" type="range" min="0" max="90" step="10" value={F.min_risk} onChange={e => set('min_risk', +e.target.value)} /></div>
        <div className="f"><label htmlFor="mf-q">Search</label><input id="mf-q" type="text" placeholder="name, phone, FIR…" value={F.q} onChange={e => set('q', e.target.value)} /></div>
        <button className="tool" aria-pressed={more} onClick={() => setMore(!more)}>{more ? 'Fewer filters' : 'More filters'}</button>
        {nF > 0 && <button className="tool" onClick={() => setF(EMPTY_F)}>Clear {nF}</button>}
      </div>
      {more && <div className="fbar">
        <div className="f"><label htmlFor="mf-s">From</label><input id="mf-s" type="date" min={opts?.date_range?.[0]} max={opts?.date_range?.[1]} value={F.start} onChange={e => set('start', e.target.value)} /></div>
        <div className="f"><label htmlFor="mf-e">To</label><input id="mf-e" type="date" min={opts?.date_range?.[0]} max={opts?.date_range?.[1]} value={F.end} onChange={e => set('end', e.target.value)} /></div>
        <div className="f"><label htmlFor="mf-t">Alert type</label>
          <select id="mf-t" value={F.alert_type} onChange={e => set('alert_type', e.target.value)}><option value="">Any</option>{opts?.alert_types.map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-v">Severity</label>
          <select id="mf-v" value={F.severity} onChange={e => set('severity', e.target.value)}><option value="">Any</option>{opts?.severities.map(a => <option key={a}>{a}</option>)}</select></div>
        <div className="f"><label htmlFor="mf-o">FIRs</label>
          <select id="mf-o" value={F.source} onChange={e => set('source', e.target.value)}><option value="">All</option><option value="base">Original records</option><option value="live">Filed live</option></select></div>
        <label className="chk"><input type="checkbox" checked={F.cross_station} onChange={e => set('cross_station', e.target.checked)} />Cross-station only</label>
      </div>}
      <div className="layerbar">
        <small>Layers</small>
        {LAYER_DEFS.map(([k, v]) => <button key={k} className="tool" aria-pressed={L[k]} onClick={() => setL(l => ({ ...l, [k]: !l[k] }))}>{v}</button>)}
        {L.heat && <select aria-label="Heat metric" className="tool" value={heat} onChange={e => setHeat(e.target.value)}>{HEATS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
        <span className="sep" />
        {viewer && <button className="tool" title="Shortcut: M" onClick={myStation}>My station</button>}
        {focus && <button className="tool" title="Shortcut: Esc" onClick={() => setFocus('')}>Show all links</button>}
        <button className="tool" title="Shortcut: F" onClick={() => fitAll()}>Fit all</button>
        <button className="tool" title="Shortcut: H" onClick={() => map.current?.flyTo({ ...HOME, speed: 0.9 })}>Reset view</button>
      </div>
      <div className="stage">
        <div className="canvas" ref={box} />
        <div className={'answer-tag' + (tag ? ' show' : '')}><span>{tag}</span><button onClick={() => setTag('')}>Clear</button></div>
        <div className={'tourbar' + (tourState ? ' show' : '')}>{tourState && <><span>Stop {tourState.i}/{tourState.n}</span><b>{tourState.label}</b><button className="tool" onClick={stopTour}>Stop tour</button></>}</div>
        <div className="mapkey" aria-label="Map key">
          <span><i className="st" />Police station (FIR count)</span><span><i className="hi" />High-risk person</span><span><i className="md" />Medium risk</span>
          <span><i className="fr" />FIR</span><span><i className="ln" />{focus || F.station || viewer ? 'Links to this station' : 'Strongest station links'}</span>
          {streets === false && <span className="off">Street map offline: plain view</span>}
        </div>
        <div className="mapcount">{counts.fir || 0} FIRs · {counts.entity || 0} people · {counts.alert || 0} alerts · {data.stations.length} stations</div>
      </div>
    </>
  )
})
export default MapView
