import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { band } from './util'

cytoscape.use(fcose)
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()

function pairs(graph) {
  const by = new Map(), ids = new Set(graph.nodes.map(n => n.id))
  for (const e of graph.edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    const key = [e.source, e.target].sort().join('|')
    const p = by.get(key) || { source: e.source, target: e.target, calls: 0, txns: 0, amount: 0, fir: 0 }
    if (e.etype === 'call') p.calls += e.count || 1
    else if (e.etype === 'transfer') { p.txns += e.count || 1; p.amount += e.amount || 0 }
    else if (e.etype === 'associate') p.fir += 1
    by.set(key, p)
  }
  const out = []
  for (const [k, p] of by) {
    if (p.calls) out.push({ id: 'c' + k, source: p.source, target: p.target, kind: 'call', w: Math.min(4.5, 1.2 + p.calls / 8), label: `${p.calls} calls`, calls: p.calls, txns: p.txns })
    if (p.txns) out.push({ id: 'm' + k, source: p.source, target: p.target, kind: 'money', w: Math.min(4.5, 1.4 + p.amount / 300000), label: `₹${p.amount.toLocaleString('en-IN')}`, calls: p.calls, txns: p.txns })
    if (p.fir && !p.calls && !p.txns) out.push({ id: 'f' + k, source: p.source, target: p.target, kind: 'fir', w: 1.3, label: 'named together', calls: 0, txns: 0 })
  }
  return out
}

const GraphView = forwardRef(function GraphView({ graph, highlight, selected, onSelect, visible }, ref) {
  const box = useRef(null), cy = useRef(null), cb = useRef(onSelect)
  cb.current = onSelect
  useImperativeHandle(ref, () => ({ fit: () => cy.current?.animate({ fit: { padding: 30 } }, { duration: 300 }) }))

  useEffect(() => {
    const c = cy.current = cytoscape({
      container: box.current, wheelSensitivity: 0.25, minZoom: 0.2, maxZoom: 1.5,
      style: [
        { selector: 'node.group', style: { shape: 'round-rectangle', 'corner-radius': 28, 'background-opacity': 0, 'border-width': 1.4, 'border-style': 'dashed', 'border-dash-pattern': [7, 5], 'border-color': css('--green'), label: 'data(label)', 'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': -4, 'font-family': 'Source Serif 4', 'font-weight': 600, 'font-size': 15, color: css('--green'), padding: 22 } },
        { selector: 'node.person', style: { width: 'data(size)', height: 'data(size)', 'background-color': '#fff', 'border-width': 1.8, 'border-color': css('--ink'), label: 'data(label)', 'text-valign': 'bottom', 'text-margin-y': 4, 'font-family': 'Hind', 'font-weight': 600, 'font-size': 13, color: css('--ink'), 'text-background-color': css('--sheet'), 'text-background-opacity': 0.85, 'text-background-padding': 1 } },
        { selector: 'node.person[band="high"]', style: { 'border-color': css('--red'), 'border-width': 2.4, 'outline-width': 2, 'outline-color': css('--red'), 'outline-offset': 3, color: css('--red') } },
        { selector: 'node.person[band="medium"]', style: { 'background-color': '#fbe6c2' } },
        { selector: 'edge', style: { 'curve-style': 'bezier', 'control-point-step-size': 14, width: 'data(w)', 'line-color': css('--ink'), opacity: 0.78 } },
        { selector: 'edge.money', style: { 'line-color': css('--red') } },
        { selector: 'edge.fir', style: { 'line-style': 'dashed', 'line-dash-pattern': [5, 4], width: 1.3, 'line-color': css('--pencil') } },
        { selector: '.dim', style: { opacity: 0.12 } },
        { selector: 'node.group.dim', style: { opacity: 0.3 } },
        { selector: 'edge.lit', style: { opacity: 1, 'z-index': 9, 'underlay-color': '#f3d36b', 'underlay-opacity': 0.8, 'underlay-padding': 4 } },
        { selector: 'node.person.lit', style: { 'underlay-color': '#f3d36b', 'underlay-opacity': 0.9, 'underlay-padding': 6, 'underlay-shape': 'ellipse', 'z-index': 9 } },
      ],
    })
    c.on('tap', 'node.person', e => cb.current(e.target.id()))
    c.on('tap', e => { if (e.target === c) cb.current(null) })
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(box.current)
    return () => { ro.disconnect(); c.destroy() }
  }, [])

  useEffect(() => {
    const c = cy.current
    if (!c || !graph) return
    const persons = graph.nodes.filter(n => n.type === 'person')
    const els = (graph.communities || []).map(g => ({ data: { id: 'g' + g.id, label: g.label }, classes: 'group' }))
    for (const n of persons) els.push({ data: { id: n.id, label: n.label, parent: n.community ? 'g' + n.community : undefined, band: band(n.risk), size: 14 + (n.score || 0) * 22 }, classes: 'person' })
    for (const p of pairs({ nodes: persons, edges: graph.edges })) els.push({ data: p, classes: p.kind })
    c.elements().remove(); c.add(els)
    c.layout({ name: 'fcose', quality: 'proof', randomSeed: 7, animate: false, nodeRepulsion: 7000, idealEdgeLength: 95, nestingFactor: 0.5, gravity: 0.35, nodeSeparation: 80 }).run()
    c.fit(undefined, 30)
  }, [graph])

  useEffect(() => { if (visible) { cy.current?.resize(); cy.current?.fit(undefined, 30) } }, [visible])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.elements().removeClass('lit dim')
    const ids = highlight?.nodes?.filter(Boolean)
    if (!ids?.length) return
    const set = new Set(ids)
    const nodes = c.nodes('.person').filter(n => set.has(n.id()))
    if (!nodes.length) return
    const edges = c.edges().filter(e => set.has(e.data('source')) && set.has(e.data('target')))
    c.elements().not(nodes).not(edges).not('node.group').addClass('dim')
    c.nodes('.group').filter(g => !g.children().some(ch => set.has(ch.id()))).addClass('dim')
    nodes.addClass('lit'); edges.addClass('lit')
    if (visible) c.animate({ fit: { eles: nodes, padding: 110 } }, { duration: 420, easing: 'ease-out-cubic' })
  }, [highlight, graph, visible])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.nodes().unselect()
    if (selected) c.getElementById(selected).select()
  }, [selected])

  return <div id="cy" className="canvas" ref={box} />
})
export default GraphView
