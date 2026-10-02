# Criminal Network Analysis (hackathon prototype, synthetic data)

Reads police complaint text (FIRs), phone call logs and bank transfers, works out who is who, draws one connected map of the network, flags suspicious patterns, and lets an investigator ask questions in plain English or Hinglish. All data is synthetic.

## Run

Two terminals, from the project root.

```bash
# 1. backend (http://127.0.0.1:8000)
cd backend && source .venv/bin/activate && uvicorn main:app --port 8000
```

```bash
# 2. frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open http://localhost:5173. Click **? Guide** in the header (or press `?`) for a short walkthrough, a visual legend and the glossary. Every small `?` next to a label explains that term and links to the matching part of the guide.

Run the backend from a normal terminal. A server started from an app's preview pane may be blocked from reaching the AI laptop on your network.

Regenerate data: `python backend/data/generate_dataset.py` (seeded; `truth.json` is only for scoring, the app never reads it).
Score the same-person matching: `python backend/eval_resolution.py` (precision 1.00, recall 0.97).

## The AI model (optional)

The AI runs on another laptop on the same network, reached through a LiteLLM proxy. With it off, everything still works using keyword rules and fixed answer templates.

Create `backend/.env` (never commit it):

```
LLM_API_BASE=http://<AI-laptop-IP>:4000/v1
LLM_MODEL=openai/qwen3-4b
LLM_API_KEY=<key from the AI laptop's litellm .env>
LLM_TIMEOUT=25
```

Restart the backend after editing it. The header shows **LLM online / offline**; `GET /llm/status` shows details.

What the AI is allowed to do: (1) pick which question type the investigator is asking and for whom, (2) put the already-computed result into words. All counting, ranking and path-finding is done by Python/NetworkX. If the AI's wording contains an ID or number that is not in the computed result, or a placeholder like `FIR-xxx`, it is thrown away and a fixed template answer is shown. Click **how was this answered?** under any chat reply to see which was used.

## Plain-language guide to the terms

| You see | It means |
|---|---|
| **FIR** (`FIR-007`) | Police complaint text. |
| **Call** (`C0123`) | One line of the phone call log. |
| **Transfer** (`T0123`) | One money transfer. |
| **Group** | People who interact mostly with each other. Found automatically (Louvain method). |
| **Importance score** (0 to 1) | How central a person is: contacts, links between separate people, reach, ties to other important people. |
| **Risk score** (0 to 100) | Importance (max 40) + involvement in alerts (max 40) + money moved (max 20). |
| **Same-person matching** | Deciding that "Jatinbhai", "J. Singhal" and "Jatin Singhal" are one person, with the reason and how sure we are. People who merely share a phone number are never merged. |
| **Alert** | A suspicious pattern, with the records behind it (see below). |

### Alerts

| Alert | Plain meaning |
|---|---|
| Sudden burst of calls | Many calls from one phone within minutes. |
| Money going in a circle | Money leaves someone and returns to them via intermediaries. |
| Money split and re-joined | One account splits a sum across several accounts that pass it to one receiver. |
| One phone, many names | One number tied to several people, so likely a shared or throwaway SIM. |
| Vehicle shared across groups | One vehicle used by people from different groups. |
| Separate groups suddenly in contact | Two groups that never interacted start contacting each other. |
| People at the same place and time | Several suspects near the same tower together. |

## How it works

FIR text → mentions → same-person matching → one graph (people, phones, vehicles, organisations, places; lines are calls, transfers, FIR links) → importance, groups and alerts → chat, dashboard and PDF.

The person-to-person strength of a link is `calls + 3 × transfers + 2 × FIR links`. Importance combines four standard network measures (direct contacts, linking separate people, reach, ties to important people) with fixed weights.

## Files

| File | Role |
|---|---|
| `backend/extract.py` | FIR text → people, relations, events |
| `backend/resolve.py` | same-person matching rules R1 to R5, with evidence and confidence |
| `backend/graph.py` | the connected graph, importance scores, groups, top 5 with reasons |
| `backend/patterns.py` | the seven alert detectors |
| `backend/risk.py` | 0 to 100 risk score |
| `backend/chat.py` | question types (tools), person-name finder, AI/keyword router, answer checker, session memory |
| `backend/llm.py` | LiteLLM client; never raises, callers fall back to rules |
| `backend/report.py` | PDF (`/report.pdf`, `/report/{entity}.pdf`) |
| `frontend/src/glossary.js` | every technical term and its plain-language text, in one place |
| `frontend/src/Help.jsx` | the `?` popovers and the Guide window |
| `frontend/src` | React + Tailwind + Cytoscape dashboard |

## Map and stations (2D)

- **Stations tab** (left page): every police station with its FIRs, alerts, cross-station alerts and unread messages, sortable. Buttons: *Show on map*, *Only this station*, *View as this station*. When viewing as a station, it first lists the stations linked to yours (shared people and alerts).
- **Map**: street base map from OpenFreeMap (needs internet; falls back to a plain view and says so in the map key). Click a station to show only its links; click a link line for the people and alerts behind it.
- **Map keys** (when the map is showing): `F` fit all, `H` home view, `M` my station, `+`/`-` zoom, `Esc` show all links.

## Custom alerts (officer flag)
An officer can raise an alert by hand: **Alerts → Raise an alert**, or **Raise alert** on a person or FIR card. Pick the people and FIRs, a title, a severity and a note, and choose which stations receive it. It shows in the Alerts list (stamped "By hand"), on the map, and in the inboxes of the chosen stations. Only the station that raised it can **Withdraw** it. Custom alerts do not change risk scores.
- `POST /alerts/custom` `{station, title, note, severity, entities, firs, to}`
- `DELETE /alerts/custom/{id}?station=`
