import { useEffect, useRef } from 'react'
import { api } from './api'

// Subscribes to the server-sent event stream for one station (or everything for the command centre).
export function useLive(station, on) {
  const cb = useRef(on); cb.current = on
  useEffect(() => {
    let es, last = null, dead = false, timer
    const open = () => {
      if (dead) return
      es = new EventSource(api.streamUrl(station || '', last || ''))
      cb.current({ type: 'status', ok: false })
      es.onopen = () => cb.current({ type: 'status', ok: true })
      es.onerror = () => { cb.current({ type: 'status', ok: false }); es.close(); timer = setTimeout(open, 2500) }
      for (const t of ['hello', 'fir.created', 'graph.updated', 'notification', 'notification.ack']) {
        es.addEventListener(t, e => {
          if (e.lastEventId) last = e.lastEventId
          let d = {}; try { d = JSON.parse(e.data) } catch { /* ignore */ }
          cb.current({ type: t, data: d })
        })
      }
    }
    open()
    return () => { dead = true; clearTimeout(timer); es?.close() }
  }, [station])
}
