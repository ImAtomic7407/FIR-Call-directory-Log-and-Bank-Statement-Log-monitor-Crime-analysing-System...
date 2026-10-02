# Map, stations and live-alert API

For the frontend. All paths are relative to the API root (`/api` through the Vite proxy). Station params accept an id (`okhla`) or a name (`Okhla PS`). There is no auth: "logging in as a station" is just passing `station=`.

Coordinates are approximate and jurisdictions are synthetic nearest-station cells. Everything is computed by the same analysis the graph uses, so the map and the graph never disagree.

## Static geography
| Endpoint | Returns |
|---|---|
| `GET /geo/meta` | `bbox`, `center`, `stations[]` (id, name, short, lat, lon, district, state, `areas[]`, `jurisdiction` = closed `[lon,lat]` ring for a polygon), `areas[]` (tower areas: id, name, lat, lon, station), `districts`, `states` |
| `GET /stations` | Same stations without polygons |
| `GET /map/filters` | Everything a filter bar needs: stations, districts, states, areas, `alert_types`, `severities`, `layers`, `date_range`, `risk_range` |

## Map view data (own filters, independent of the graph filters)
All of these share the same filter params: `station`, `district`, `state` (comma-separated ok), `area`, `start`, `end` (YYYY-MM-DD), `min_risk`, `q` (name / phone / FIR text).

| Endpoint | Notes |
|---|---|
| `GET /map/features?layers=firs,towers,entities,alerts` | Markers. Extra params: `severity`, `alert_type`, `source=base\|live`, `cross_station=true`. Each feature has `kind` (`fir`/`tower`/`entity`/`alert`), `id`, `lat`, `lon` plus props. Response: `{count, by_kind, features[]}` |
| `GET /map/stations` | One row per station with counters: `firs`, `live_firs`, `alerts`, `high_alerts`, `cross_station_alerts`, `people`, `high_risk_people`, `calls`, `unread_notifications` |
| `GET /map/heat?metric=calls\|night_calls\|firs\|alerts\|risk` | `{max, points[{lat, lon, weight, intensity 0-1, area}]}` |
| `GET /map/links` | Station-to-station lines: people who appear in FIRs of both, and alerts spanning both. `a_pos`/`b_pos` are `[lat,lon]` |
| `GET /stations/{id}` | Station panel: counters, `recent_firs`, `alerts`, `top_people`, `links`, `inbox` counts |
| `GET /alerts/geo` | Alerts plus `geo.stations[]` (each with `routed` and `reasons`), `geo.areas`, `geo.cross_station` |

Feature notes: FIRs are placed at the area their text is about (`located_by: "text"`), else at their station. Entities sit at their last-seen tower (`last_seen`) else home area. Alerts sit at the weighted centre of the towers their calls used. Positions of FIRs/people are jittered slightly so they do not stack.

## FIRs
- `GET /firs` : filters as above plus `source`, `limit`. Each row has a `geo` block.
- `POST /firs` `{station, text, date?, reporter?}` : files a live FIR. Takes about 0.1 s. It re-runs extraction, entity resolution, graph, alerts and risk, then notifies. Returns `{fir, entities[], new_alerts[], notifications[], summary}`. `400` on unknown station or text under 20 chars.
  - Works with free text. People already in the system are recognised by full name or phone; `accused|suspect|named|... First Last` creates new people, with a phone found in the next ~160 characters.

## Notifications between stations
Kinds: `cross_station_link` (a person in the new FIR already has FIRs at your station), `new_alert` (a detector fired and your area holds its evidence), `jurisdiction_notice` (a FIR mentions your area), `request_assistance` / `share_intel` / `bolo` (manual), `reply`.

- `GET /notifications?station=&direction=in|out&status=new|ack&kind=` : inbox/outbox. No station = command-centre view.
- `POST /notifications` `{from_station, to_stations[], kind, title, body, severity, refs?}` : manual dispatch.
- `POST /notifications/{id}/ack` `{station}`; `POST /notifications/{id}/respond` `{station, text}` (creates a `reply` back to the sender).

## Live push (Server-Sent Events)
`GET /stream?station=okhla` (omit `station` to see everything). Reconnect with `?since=<last id>` to replay missed events.

```js
const es = new EventSource('/api/stream?station=okhla')
es.addEventListener('notification', e => ...)   // only this station's
es.addEventListener('fir.created', e => ...)    // everyone: {fir, entities, summary}
es.addEventListener('graph.updated', e => ...)  // everyone: refetch graph/map/alerts
es.addEventListener('notification.ack', e => ...) // sender is told when the other side acknowledges
```
Each payload also carries `_ts` and `_station`.

## Demo helpers
- `GET /demo/next` previews, `POST /demo/fire` files a generated FIR (a known high-risk person, written up at a different station), `POST /demo/reset` drops all live FIRs and notifications.
- Live FIRs and notifications persist in `backend/cache/live_state.json`.
