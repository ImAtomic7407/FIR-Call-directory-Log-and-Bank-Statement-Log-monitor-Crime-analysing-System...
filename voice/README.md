# XEST voice (standalone)

Speak in English or Hinglish, hear the answer. Built separately from `frontend/`; merge later.

## Run
```bash
# backend as usual (port 8000), then:
cd voice
python3 -m venv .venv && .venv/bin/pip install edge-tts   # first time only
.venv/bin/python server.py
# open http://localhost:5180  (Chrome/Edge; localhost is needed for mic access)
# Hands-free = ChatGPT-style loop: mic reopens after each spoken answer
```
Another backend: `?api=http://host:8000`.

## Files
- `server.py` – serves the page and `/tts` (neural voices via edge-tts; needs internet). Voice menu in the header; falls back to the browser voice if it is unreachable.
- `speech.js` – `createVoice()` (mic + speaker), `speakable()` (cleans answer text for TTS), `detectLang()`. No dependencies.
- `index.html` – demo chat page, same look as the XEST chat, calls `POST /chat`.
- `speech.test.mjs` – `node --test speech.test.mjs`

## Merging into `frontend/src/ChatPanel.jsx`
Copy `speech.js` to `frontend/src/`, then: `const voice = useMemo(() => createVoice({onTranscript: send, onInterim: setInput, ...}), [])`,
add a mic button beside Send, and call `voice.speak(r.answer)` after `setMsgs` in `send()`.
