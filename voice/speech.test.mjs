import test from 'node:test'
import assert from 'node:assert/strict'
import { speakable, detectLang, rupeesSpoken, chunkSentences } from './speech.js'

test('rupees use Indian grouping', () => {
  assert.equal(rupeesSpoken(50000), '50 thousand rupees')
  assert.equal(rupeesSpoken(120000), '1 lakh 20 thousand rupees')
  assert.equal(rupeesSpoken(25000000), '2 crore 50 lakh rupees')
})
test('citations dropped, ids spelled', () => {
  assert.equal(speakable('Bunty sent ₹50,000 [T0045, FIR-007] to Zubair.'), 'Bunty sent 50 thousand rupees to Zubair.')
  assert.equal(speakable('See FIR-007 and call C0123 and ALR-02'), 'See F I R 7 and call 123 and alert 2')
})
test('entity id brackets dropped', () => {
  assert.equal(speakable('Contacts are Jatin. [E038, E029, X012]'), 'Contacts are Jatin.')
})
test('phone numbers read digit by digit', () => {
  assert.equal(speakable('Number 9876543210 called'), 'Number 9 8 7 6 5 4 3 2 1 0 called')
})
test('markdown and newlines flattened', () => {
  assert.equal(speakable('**Top 3**\n- Bunty\n- Zubair'), 'Top 3. Bunty. Zubair')
})
test('language detection', () => {
  assert.equal(detectLang('Zubair ke contacts batao'), 'hi')
  assert.equal(detectLang('Koi suspicious pattern dikhao'), 'hi')
  assert.equal(detectLang('Who are the top 5 key persons?'), 'en')
  assert.equal(detectLang('इमरान कौन है'), 'hi')
})

test('sentence chunking', () => {
  assert.deepEqual(chunkSentences('Pehla. Dusra hai? Teesra!'), ['Pehla.', 'Dusra hai?', 'Teesra!'])
  assert.ok(chunkSentences('word '.repeat(100)).every(c => c.length <= 220))
})
