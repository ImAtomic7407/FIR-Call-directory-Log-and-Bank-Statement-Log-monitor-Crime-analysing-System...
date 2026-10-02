# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary audience right now: hackathon judges watching a live demo of a few minutes. It has to read as a real deployed police investigation system, not a prototype. The audience it is designed for: investigating officers and crime analysts in Indian police who work cases at a desk.

## Product Purpose
The app reads police complaint text (FIRs), phone call logs and bank transfers, and works out who is who across them. It draws one connected map of the criminal network, flags suspicious patterns as alerts that point to the records behind them, and answers investigator questions in English or Hinglish. A session serves three jobs equally: triaging alerts, exploring the network around a person, phone or FIR, and asking the AI questions.

## Positioning
Every claim can be traced to a record. Python/NetworkX does all the counting, ranking and path-finding. The AI only classifies the question and puts the computed result into words, and any answer containing an ID or number not in the computed result is replaced by a fixed template. Same-person matching shows its reason and confidence, and never merges people just because they share a phone number.

## Operating Context
- Data: 49 FIRs, 445 calls, 102 transfers, 42 entities, 9 alerts, July to September 2026. All of it is synthetic.
- Record IDs: FIR-007, C0123, T0123, ALR-01.
- Entity types: people, phones, vehicles, organisations, places.
- Alert types: call bursts, circular money, split and re-joined money, one phone with many names, vehicles shared across groups, separate groups suddenly in contact, people at the same place and time.
- The AI runs through a LiteLLM proxy on another laptop. When it is offline, answers come from rules and templates.

## Capabilities and Constraints
- The FastAPI backend and its API stay exactly as they are. Only the frontend changes.
- Stack: React 19, Vite, Tailwind 4, Cytoscape (fcose).
- Risk score runs 0–100: importance (max 40), alert involvement (max 40) and money moved (max 20). High is 60 or more, medium is 30 or more.
- Groups are found with Louvain community detection.
- The user says the current UI, and especially the graph, is not good enough. Both need a full redesign.

## Evidence on Hand
Synthetic dataset under backend/data. Precision and recall figures for same-person matching come from backend/eval_resolution.py. There are no real cases, agencies, officers or deployments, and none may be implied.

## Product Principles
- Every claim links to the record behind it.
- Show the network first: the map is the product.
- An answer is more credible when it shows its reasoning (rules vs AI, confidence).
- Must be legible to a non-expert in seconds and still feel like an operational tool.
