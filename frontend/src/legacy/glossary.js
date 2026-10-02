// One place for every technical term the UI shows, in plain words.
// [title, plain text, help-guide section it links to]
export const GLOSSARY = {
  group: ['Group', 'People who interact mostly with each other (calls, money, FIRs). The graph colours each group differently.', 'graph'],
  importance: ['Importance score', 'How central a person is: many contacts, links between separate people, quick reach to everyone. 0 to 1, higher = more important.', 'scores'],
  risk: ['Risk score', 'Out of 100. Adds up: how important the person is in the network (max 40), how many alerts involve them (max 40) and how much money they moved (max 20).', 'scores'],
  alert: ['Alert', 'A suspicious pattern the system found in the data. Every alert lists the FIR, call and transaction records behind it.', 'alerts'],
  fir: ['FIR', 'First Information Report: the police complaint text. Click an FIR chip to read it.', 'records'],
  cdr: ['Call record', 'One line of the phone call log (who called whom, when, how long, which tower). IDs look like C0123.', 'records'],
  txn: ['Transaction', 'One money transfer between two accounts. IDs look like T0123.', 'records'],
  resolution: ['Same-person matching', 'The same person is written differently in different FIRs (nickname, initials, phone number). This shows why mentions were treated as one person.', 'matching'],
  shared: ['Shared phone', 'A number tied to several different names. We do NOT merge those people, because that could blame the wrong person.', 'matching'],
  timeWindow: ['Time window', 'Only show calls, transfers and FIRs inside this date range. Drag the two handles.', 'graph'],
  show: ['Show', 'Which kinds of things appear as dots on the graph. Each kind has its own shape.', 'graph'],
  connections: ['Connections', 'Which kinds of lines appear between dots. Colours match the legend on the graph.', 'graph'],
  filters: ['Filters', 'Narrow what the graph shows. Nothing is deleted, only hidden.', 'graph'],
  keyPersons: ['Key persons', 'The five most important people in the network, with plain reasons. The number is the importance score as a percentage.', 'scores'],
}

export const IMPORTANCE_LABEL = {
  degree: 'Most contacts',
  betweenness: 'Links separate people',
  closeness: 'Reaches everyone fastest',
  pagerank: 'Tied to important people',
  strength: 'Most activity',
}

// How the same-person matcher decided (rule code -> plain sentence)
export const RULE_TEXT = {
  exact_full_name: 'Full name written exactly the same',
  'alias+phone': 'Nickname and phone number both match',
  phone_match: 'Same phone number',
  unique_alias: 'Nickname belongs to only this person',
  initial_surname: 'Initial + surname matches only this person',
  phone_only_new_identity: 'No name known; grouped by phone number only',
  stated_in_fir: 'Phone number stated in the FIR',
}
export const sure = c => (c >= 0.95 ? 'certain' : c >= 0.85 ? 'very likely' : c >= 0.7 ? 'likely' : 'weak match')

export const ALERT_TYPE = {
  burst_calling: 'Sudden burst of calls', circular_transfer: 'Money going in a circle', layering: 'Money split and re-joined',
  shared_phone: 'One phone, many names', shared_vehicle: 'Vehicle shared across groups', sudden_contact: 'Separate groups suddenly in contact',
  co_location: 'People together at the same place and time',
}

export const ALERT_HELP = {
  burst_calling: 'Many calls from one phone in a few minutes, far above its normal rate.',
  circular_transfer: 'Money leaves one person and comes back to them through intermediaries, usually a way to hide its source.',
  layering: 'One account splits a sum across several accounts that then pass it to one receiver.',
  shared_phone: 'One number is linked to several different people (could be a throwaway SIM).',
  shared_vehicle: 'The same vehicle is used by people who otherwise belong to different groups.',
  sudden_contact: 'Two groups that never interacted suddenly start contacting each other.',
  co_location: 'Several suspects were near the same phone tower at the same time.',
}
