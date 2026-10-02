import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Chip, Linkified } from './components'

const SUGGEST = [
  'Who are the top 5 key persons?',
  'Show transactions above ₹50,000 between Group 1 members',
  'Who is Bunty?',
  'How is he connected to Jatin Singhal?',
  'Koi suspicious pattern dikhao',
  'Zubair ke contacts batao',
]
const SID = 'ui-' + Math.random().toString(36).slice(2, 8)

export default function ChatPanel({ onHighlight, onOpen, pendingAsk }) {
  const [msgs, setMsgs] = useState([{ role: 'bot', text: 'Ask about people, calls, money, connections, risk or alerts. English / Hinglish both work. Every answer cites FIR, call or transaction IDs and highlights the relevant sub-graph.' }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }) }, [msgs, busy])
  useEffect(() => { if (pendingAsk) send(pendingAsk.q) }, [pendingAsk])

  async function send(q) {
    q = (q ?? input).trim()
    if (!q || busy) return
    setInput(''); setBusy(true)
    setMsgs(m => [...m, { role: 'user', text: q }])
    try {
      const r = await api.chat(q, SID)
      setMsgs(m => [...m, { role: 'bot', ...r, text: r.answer }])
      onHighlight(r.highlight, r)
    } catch (e) {
      setMsgs(m => [...m, { role: 'bot', text: 'Backend not reachable. Is the API running on :8000?' }])
    }
    setBusy(false)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-auto p-3">
        {msgs.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
            <div className={`max-w-[95%] rounded-lg px-3 py-2 text-xs leading-relaxed ${m.role === 'user' ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-200'}`}>
              <div className="whitespace-pre-wrap"><Linkified text={m.text} onOpen={onOpen} /></div>
              {m.role === 'bot' && m.evidence && <Evidence m={m} onOpen={onOpen} />}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-1.5 text-xs text-slate-500"><span className="flex gap-0.5">{[0, 1, 2].map(i => <i key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-500" style={{ animationDelay: `${i * 150}ms` }} />)}</span>Looking through the records…</div>}
        <div ref={end} />
      </div>
      <div className="flex flex-wrap gap-1 border-t border-slate-800 px-3 pt-2.5"><span className="mb-1 w-full text-[10px] font-semibold uppercase tracking-wider text-slate-500">Try asking</span>
        {SUGGEST.map(s => <button key={s} onClick={() => send(s)} className="mb-1 rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400 hover:border-sky-500 hover:text-sky-300">{s}</button>)}
      </div>
      <form className="flex gap-2 p-3 pt-1" onSubmit={e => { e.preventDefault(); send() }}>
        <input id="chat-input" value={input} onChange={e => setInput(e.target.value)} placeholder="Ask in English or Hinglish…  ( / )" className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-sky-500" />
        <button disabled={busy || !input.trim()} className="rounded-md bg-sky-600 px-4 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40">Send</button>
      </form>
    </div>
  )
}

const TOOL_TEXT = { top_central: 'Who are the key people', entity_profile: 'Profile of one person', neighbors: 'Who is connected to someone', transactions: 'Money transfers', shortest_path: 'How two people are connected', calls: 'Phone calls', alerts: 'Suspicious patterns', risk: 'Risk score', communities: 'Groups' }

function Evidence({ m, onOpen }) {
  const [open, setOpen] = useState(false)
  const ev = m.evidence
  const all = [...ev.alerts, ...ev.firs, ...ev.txns.slice(0, 12), ...ev.calls.slice(0, 8)]
  return (
    <div className="mt-2 border-t border-slate-700 pt-1.5">
      {all.length > 0 && <div><span className="mr-1 text-[10px] uppercase text-slate-500">Evidence</span>{all.map(i => <Chip key={i} id={i} onOpen={onOpen} />)}</div>}
      <button onClick={() => setOpen(!open)} className="text-[10px] text-slate-500 hover:text-slate-300">{open ? '▾' : '▸'} how was this answered?</button>
      {open && (
        <div className="mt-1 space-y-0.5 text-[11px] text-slate-400">
          <div>Question understood as: <b className="text-slate-300">{TOOL_TEXT[m.trace.tool] || m.trace.tool}</b>{Object.keys(m.trace.args || {}).length > 0 && <span className="font-mono text-slate-500"> {JSON.stringify(m.trace.args)}</span>}</div>
          <div>Question read by: {m.trace.router === 'llm' ? 'the AI model' : 'simple keyword rules'} · Wording written by: {m.answer_source?.startsWith('llm') ? 'the AI model (every ID and number checked against the data)' : 'a fixed template (no AI)'}</div>
          {m.answer_template && m.answer_template !== m.answer && <div className="whitespace-pre-wrap text-slate-500">Plain data answer: {m.answer_template.slice(0, 300)}</div>}
        </div>
      )}
    </div>
  )
}
