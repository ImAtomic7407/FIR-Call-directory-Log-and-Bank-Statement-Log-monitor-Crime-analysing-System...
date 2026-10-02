export const band = r => (r >= 60 ? 'high' : r >= 30 ? 'medium' : 'low')
export const fmtDate = s => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '')
export const ago = ts => {
  if (!ts) return ''
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  return s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : fmtDate(ts)
}
export const KIND_LABEL = {
  cross_station_link: 'Same person, other station', new_alert: 'New pattern in your area', jurisdiction_notice: 'FIR mentions your area',
  request_assistance: 'Help requested', share_intel: 'Intel shared', bolo: 'Be on the lookout', reply: 'Reply',
}
export const ID_RX = /\b(FIR-\d{3}|C\d{4}|T\d{4}|ALR-\d{2})\b/g
