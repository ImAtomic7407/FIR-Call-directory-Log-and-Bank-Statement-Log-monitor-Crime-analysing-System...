// Voice layer for the XEST investigator chat. Dependency-free ES module so it
// drops into ChatPanel.jsx later (import { speakable, createVoice } from './speech.js').

const HINGLISH_WORDS = /\b(ke|ki|ka|ko|se|me|mein|hai|hain|ho|tha|the|kya|kaun|kisne|kitne|kitna|kab|kahan|kaise|batao|bataiye|dikhao|dikha|dikhaiye|karo|kiya|wala|wali|unka|unki|inka|koi|sab|aur|nahi|nahin|pehle|baad|lekin|paise|paisa|rupaye|rupay)\b/i

/** 'hi' when the text reads as Hinglish/Hindi, otherwise 'en'. */
export function detectLang(text) {
  if (/[ऀ-ॿ]/.test(text)) return 'hi'
  const hits = (text.match(new RegExp(HINGLISH_WORDS, 'gi')) || []).length
  return hits >= 2 || (hits >= 1 && text.split(/\s+/).length <= 4) ? 'hi' : 'en'
}

/** 1234567 -> "12 lakh 34 thousand 567" (Indian grouping, spoken). */
export function rupeesSpoken(n) {
  n = Math.round(Number(n))
  if (!Number.isFinite(n)) return ''
  if (n === 0) return 'zero rupees'
  const parts = []
  const crore = Math.floor(n / 1e7); n %= 1e7
  const lakh = Math.floor(n / 1e5); n %= 1e5
  const thousand = Math.floor(n / 1e3); n %= 1e3
  if (crore) parts.push(`${crore} crore`)
  if (lakh) parts.push(`${lakh} lakh`)
  if (thousand) parts.push(`${thousand} thousand`)
  if (n) parts.push(String(n))
  return parts.join(' ') + ' rupees'
}

const digits = s => s.split('').join(' ')

/** Turn on-screen answer text into something a TTS voice reads naturally. */
export function speakable(text = '') {
  let t = String(text)
  // citation brackets like [FIR-007, C0123] are for the eyes, not the ears
  t = t.replace(/\[[^\]]*\b(?:FIR|ALR)-\d+[^\]]*\]|\[[^\]]*\b[CTEX]\d{3,}\b[^\]]*\]/g, '')
  // money: ₹50,000 / Rs. 1,20,000 / INR 5000
  t = t.replace(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)/gi, (_, n) => rupeesSpoken(n.replace(/,/g, '')))
  // record ids
  t = t.replace(/\bFIR-0*(\d+)\b/g, 'F I R $1')
  t = t.replace(/\bALR-0*(\d+)\b/g, 'alert $1')
  t = t.replace(/\bC0*(\d{2,})\b/g, 'call $1')
  t = t.replace(/\bT0*(\d{2,})\b/g, 'transfer $1')
  t = t.replace(/\b(call|transfer|alert) \1\b/gi, '$1')
  // phone numbers: read digit by digit
  t = t.replace(/(?<![\d,])(\+?91[\s-]?)?(\d{10})(?![\d,])/g, (_, cc, num) => (cc ? 'plus nine one ' : '') + digits(num))
  // markdown / bullets / newlines
  t = t.replace(/[*_`#>]+/g, '').replace(/^\s*[-•]\s+/gm, '').replace(/\s*\n+\s*/g, '. ')
  t = t.replace(/\s*->\s*|\s*→\s*/g, ' to ').replace(/&/g, ' and ')
  return t.replace(/\s{2,}/g, ' ').replace(/\.\s*\./g, '.').trim()
}

/** Split into sentence-sized chunks so the first audio can start early. */
export function chunkSentences(text, max = 220) {
  const out = []
  for (const sent of text.match(/[^.!?।]+[.!?।]*\s*/g) || [text]) {
    let s = sent.trim()
    while (s.length > max) {
      const cut = s.lastIndexOf(',', max) > 60 ? s.lastIndexOf(',', max) + 1 : s.lastIndexOf(' ', max)
      out.push(s.slice(0, cut).trim()); s = s.slice(cut).trim()
    }
    if (s) out.push(s)
  }
  return out
}

const SR = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

/** Pick the best installed voice: Indian voices first, matching the reply language. */
function pickVoice(lang) {
  const voices = window.speechSynthesis?.getVoices?.() || []
  const want = lang === 'hi' ? ['hi-IN', 'en-IN'] : ['en-IN', 'hi-IN', 'en-GB', 'en-US']
  for (const code of want) {
    const v = voices.find(x => x.lang.replace('_', '-') === code)
    if (v) return v
  }
  return voices[0] || null
}

/**
 * createVoice({ onTranscript, onInterim, onState, onError })
 *  - onSpoken(): called when an answer finished playing without being interrupted
 *  - listen(): start the mic; the final transcript is passed to onTranscript(text)
 *  - speak(text, lang?): read an answer aloud (lang auto-detected when omitted)
 *  - stop(): cancel listening and speaking
 */
export function createVoice({ onTranscript, onInterim, onState, onError, onSpoken, recogLang = 'en-IN' } = {}) {
  const canListen = !!SR
  const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window
  let rec = null
  let state = 'idle' // idle | listening | speaking
  const set = s => { state = s; onState?.(s) }

  function listen() {
    if (!canListen) return onError?.('unsupported')
    stopSpeaking()
    if (rec) { rec.stop(); return }
    rec = new SR()
    rec.lang = recogLang          // en-IN returns Hinglish in Roman letters, which the router understands
    rec.interimResults = true
    rec.maxAlternatives = 1
    let finalText = ''
    rec.onstart = () => set('listening')
    rec.onresult = e => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) finalText += r[0].transcript
        else interim += r[0].transcript
      }
      onInterim?.((finalText + interim).trim())
    }
    rec.onerror = e => onError?.(e.error === 'not-allowed' || e.error === 'service-not-allowed' ? 'denied' : e.error === 'no-speech' ? 'no-speech' : e.error)
    rec.onend = () => { rec = null; set('idle'); if (finalText.trim()) onTranscript?.(finalText.trim()) }
    rec.start()
  }

  // ---- neural voice (server.py /tts), sentence by sentence, all clips requested in parallel
  let session = 0, audioEl = null, voiceName = 'en-IN-NeerjaNeural', neuralOk = true
  const fetchClip = t => fetch(`/tts?voice=${encodeURIComponent(voiceName)}&text=${encodeURIComponent(t)}`)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.blob() }).then(b => URL.createObjectURL(b))

  function stopSpeaking() {
    session++
    if (audioEl) { audioEl.pause(); audioEl = null }
    if (canSpeak) window.speechSynthesis.cancel()
    if (state === 'speaking') set('idle')
  }

  function speakBrowser(clean, lang) {
    if (!canSpeak) return set('idle')
    const l = lang || detectLang(clean)
    const u = new SpeechSynthesisUtterance(clean)
    const v = pickVoice(l)
    if (v) { u.voice = v; u.lang = v.lang } else u.lang = l === 'hi' ? 'hi-IN' : 'en-IN'
    u.onstart = () => set('speaking')
    u.onend = () => { set('idle'); onSpoken?.() }
    u.onerror = () => set('idle')
    window.speechSynthesis.speak(u)
  }

  async function speak(text, lang) {
    const clean = speakable(text)
    if (!clean) return
    stopSpeaking()
    const my = session
    if (!neuralOk) return speakBrowser(clean, lang)
    const parts = chunkSentences(clean)
    try {
      const clips = parts.map(fetchClip)        // all sentences requested at once; played back-to-back in order
      clips.forEach(c => c.catch(() => {}))
      for (let i = 0; i < parts.length; i++) {
        const url = await clips[i]
        if (my !== session) return
        await new Promise(res => {
          const a = audioEl = new Audio(url)
          a.onplay = () => set('speaking')
          a.onended = a.onerror = () => { URL.revokeObjectURL(url); res() }
          a.play().catch(res)
        })
        if (my !== session) return
      }
      set('idle'); onSpoken?.()              // finished naturally (not interrupted)
    } catch {
      if (my !== session) return
      neuralOk = false                       // server/network down: use the browser voice from now on
      onError?.('neural-unavailable')
      speakBrowser(clean, lang)
    }
  }

  function setVoice(v) { voiceName = v }

  function stop() { if (rec) { rec.abort(); rec = null } stopSpeaking(); set('idle') }

  return { canListen, canSpeak, listen, speak, stop, setVoice, get state() { return state } }
}
