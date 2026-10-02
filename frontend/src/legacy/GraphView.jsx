import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { commColor, ETYPE_COLORS } from './theme'

cytoscape.use(fcose)

const SHAPE = { person: 'ellipse', phone: 'round-rectangle', vehicle: 'diamond', org: 'hexagon', location: 'round-triangle' }

const STYLE = [
  { selector: 'node', style: {
      label: 'data(label)', 'font-size': 9, color: '#e2e8f0', 'text-valign': 'bottom', 'text-margin-y': 3,
      'text-outline-color': '#020617', 'text-outline-width': 2, 'background-color': 'data(color)', shape: 'data(shape)',
      width: 'data(size)', height: 'data(size)', 'border-width': 'data(bw)', 'border-color': 'data(bc)', 'min-zoomed-font-size': 6 } },
  { selector: 'node[type != "person"]', style: { 'font-size': 7, opacity: 0.9 } },
  { selector: 'node[status = "shared"]', style: { 'border-color': '#ef4444', 'border-width': 3 } },
  { selector: 'edge', style: {
      width: 'data(w)', 'line-color': 'data(color)', 'curve-style': 'bezier', opacity: 0.55,
      'target-arrow-shape': 'data(arrow)', 'target-arrow-color': 'data(color)', 'arrow-scale': 0.8 } },
  { selector: 'edge[etype = "uses_phone"], edge[etype = "frequents"], edge[etype = "works_with"], edge[etype = "uses_vehicle"]', style: { 'line-style': 'dotted', opacity: 0.35 } },
  { selector: 'edge[etype = "reported_use"]', style: { 'line-style': 'dashed', opacity: 0.8 } },
  { selector: '.dim', style: { opacity: 0.08, 'text-opacity': 0 } },
  { selector: 'edge.dim', style: { opacity: 0.03 } },
  { selector: 'node.hl', style: { 'border-color': '#fde047', 'border-width': 4, opacity: 1, 'text-opacity': 1, 'z-index': 20 } },
  { selector: 'edge.hl', style: { opacity: 1, width: 3.5, 'z-index': 15 } },
  { selector: 'node:selected', style: { 'border-color': '#ffffff', 'border-width': 4 } },
]

export default function GraphView({ graph, highlight, selected, onSelect, layoutKey }) {
  const el = useRef(null)
  const cy = useRef(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useEffect(() => {
    cy.current = cytoscape({ container: el.current, style: STYLE, wheelSensitivity: 0.25, minZoom: 0.15, maxZoom: 4 })
    cy.current.on('tap', 'node', e => onSelectRef.current(e.target.id()))
    cy.current.on('tap', e => { if (e.target === cy.current) onSelectRef.current(null) })
    // keep the graph centred when the panel size changes (window resize, narrow screens)
    let t, last = { w: 0, h: 0 }
    const ro = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect
      if (!cy.current || (Math.abs(w - last.w) < 40 && Math.abs(h - last.h) < 40)) return cy.current?.resize()
      last = { w, h }
      clearTimeout(t)
      t = setTimeout(() => { const c = cy.current; c.resize(); const hl = c.nodes('.hl'); c.fit(hl.length ? hl : undefined, hl.length ? 70 : 30) }, 120)
    })
    ro.observe(el.current)
    return () => { clearTimeout(t); ro.disconnect(); cy.current.destroy() }
  }, [])

  // (re)load data
  useEffect(() => {
    const c = cy.current
    if (!c || !graph) return
    const els = []
    for (const n of graph.nodes) {
      const person = n.type === 'person'
      els.push({ group: 'nodes', data: {
        id: n.id, label: n.label, type: n.type, status: n.status, community: n.community, risk: n.risk,
        color: person ? commColor(n.community) : n.type === 'phone' ? '#475569' : '#334155',
        shape: SHAPE[n.type] || 'ellipse',
        size: person ? 18 + Math.round((n.score || 0) * 30) : 12,
        bw: person && (n.risk || 0) >= 60 ? 3 : 1, bc: person && (n.risk || 0) >= 60 ? '#ef4444' : '#0f172a' } })
    }
    for (const e of graph.edges) {
      els.push({ group: 'edges', data: {
        id: e.id, source: e.source, target: e.target, etype: e.etype, label: e.label,
        color: ETYPE_COLORS[e.etype] || '#64748b', arrow: e.etype === 'transfer' ? 'triangle' : 'none',
        w: e.etype === 'call' ? Math.min(1 + Math.log2(e.count || 1) * 1.2, 7) : e.etype === 'transfer' ? Math.min(2 + Math.log10((e.amount || 1)) * 0.6, 7) : e.etype === 'associate' ? 2.5 : 1.2 } })
    }
    c.batch(() => { c.elements().remove(); c.add(els) })
    c.layout({ name: 'fcose', animate: false, randomize: true, nodeRepulsion: 9000, idealEdgeLength: 90, quality: 'default', padding: 30 }).run()
  }, [graph, layoutKey])

  // highlight
  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.batch(() => {
      c.elements().removeClass('dim hl')
      const ids = highlight?.nodes
      if (ids && ids.length) {
        const set = new Set(ids)
        const et = highlight.etypes && highlight.etypes.length ? new Set(highlight.etypes) : null
        c.nodes().forEach(n => n.addClass(set.has(n.id()) ? 'hl' : 'dim'))
        c.edges().forEach(e => {
          const ok = set.has(e.source().id()) && set.has(e.target().id()) && (!et || et.has(e.data('etype')))
          e.addClass(ok ? 'hl' : 'dim')
        })
        const hl = c.nodes('.hl')
        if (hl.length) c.animate({ fit: { eles: hl, padding: 70 }, duration: 350 })
      }
    })
  }, [highlight, graph])

  // selection
  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.nodes().unselect()
    if (selected) c.getElementById(selected).select()
  }, [selected, graph])

  return (
    <div className="absolute inset-0">
      <div ref={el} className="h-full w-full" />
      <div className="absolute bottom-3 left-3 flex overflow-hidden rounded-md border border-slate-700/80 bg-slate-900/90 text-xs text-slate-300 shadow-lg backdrop-blur">
        <button title="Zoom in" className="px-2.5 py-1.5 hover:bg-slate-800" onClick={() => cy.current.animate({ zoom: { level: cy.current.zoom() * 1.3, renderedPosition: { x: cy.current.width() / 2, y: cy.current.height() / 2 } }, duration: 150 })}>+</button>
        <button title="Zoom out" className="border-l border-slate-700/80 px-2.5 py-1.5 hover:bg-slate-800" onClick={() => cy.current.animate({ zoom: { level: cy.current.zoom() / 1.3, renderedPosition: { x: cy.current.width() / 2, y: cy.current.height() / 2 } }, duration: 150 })}>−</button>
        <button title="Show the whole graph" className="border-l border-slate-700/80 px-2.5 py-1.5 hover:bg-slate-800" onClick={() => cy.current.animate({ fit: { padding: 30 }, duration: 300 })}>Fit</button>
        <button title="Rearrange the dots" className="border-l border-slate-700/80 px-2.5 py-1.5 hover:bg-slate-800" onClick={() => cy.current.layout({ name: 'fcose', animate: true, randomize: true, nodeRepulsion: 9000, idealEdgeLength: 90 }).run()}>Re-layout</button>
      </div>
    </div>
  )
}
