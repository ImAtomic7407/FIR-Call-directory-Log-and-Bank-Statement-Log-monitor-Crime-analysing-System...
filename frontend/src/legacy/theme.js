export const COMM_COLORS = ['#38bdf8', '#f472b6', '#facc15', '#4ade80', '#fb923c', '#a78bfa', '#2dd4bf', '#f87171']
export const commColor = c => (c ? COMM_COLORS[(c - 1) % COMM_COLORS.length] : '#64748b')
export const ETYPE_COLORS = {
  call: '#64748b', transfer: '#f59e0b', associate: '#a78bfa', uses_phone: '#475569', reported_use: '#ef4444',
  uses_vehicle: '#14b8a6', works_with: '#0ea5e9', frequents: '#94a3b8',
}
export const ETYPE_LABEL = {
  call: 'Phone calls', transfer: 'Money transfers', associate: 'Linked in FIR', uses_phone: 'Uses phone',
  reported_use: 'Shared phone', uses_vehicle: 'Vehicle', works_with: 'Organisation', frequents: 'Location',
}
export const TYPE_LABEL = { person: 'People', phone: 'Phones', vehicle: 'Vehicles', org: 'Organisations', location: 'Locations' }
export const SEV = { high: 'bg-red-500/20 text-red-300 border-red-500/40', medium: 'bg-amber-500/20 text-amber-300 border-amber-500/40', low: 'bg-sky-500/20 text-sky-300 border-sky-500/40' }
