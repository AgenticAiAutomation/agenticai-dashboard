/**
 * Blog Playbook v2 composer tests (web/lib/playbook.ts, the *V2 functions).
 *
 *   node tests/playbook/v2.test.mts
 *   node tests/playbook/v2.test.mts --write-fixture   (refresh sample-v2.md)
 *
 * sample-v2.md is read by tests/test_blog_playbook_v2.py, so the Python side
 * scores and renders the exact bytes the writer would save.
 */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  badLinks,
  blocksForBodyV2,
  compose,
  composeV2,
  countCallouts,
  emptyBlocksV2,
  isAllowedUrl,
  normaliseBlocksV2,
  parse,
  parseV2,
  playbookProblems,
  toV2,
  type PlaybookBlocksV2,
} from '../../web/lib/playbook.ts';
import { SAMPLE as V1_SAMPLE } from './compose.test.mts';

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(here, 'sample-v2.md');
const TITLE = 'WhatsApp Automation for Clinics: Cut No-Shows in 14 Days';

export const SAMPLE_V2: PlaybookBlocksV2 = {
  version: 2,
  tldr: [
    'WhatsApp automation for clinics sends confirmations and reminders without a receptionist typing them.',
    'Most clinics see fewer no-shows within two weeks.',
    'Setup takes about a week on the official WhatsApp Business API.',
  ],
  who: 'clinic owners handling 30 or more appointments a day.',
  sections: [
    {
      question: 'How does WhatsApp automation work in a clinic?',
      body: '**Short answer:** a booking triggers a message, a reminder and a token.\n\nRead the [Meta API docs](https://developers.facebook.com/docs/whatsapp) or our [pricing](/pricing).',
      items: [
        { type: 'flow', flow: ['Booking made', 'Confirmation sent', 'Reminder 24h before'] },
        { type: 'callout', label: 'Clinic hack', text: 'Keep your **old number** on the API.' },
      ],
    },
    {
      question: 'Which messages should a clinic automate first?',
      body: 'Start with the messages your front desk sends most.',
      items: [
        {
          type: 'table',
          header: ['Message', 'When'],
          rows: [['Confirmation', 'Right after booking']],
          caption: 'Table 1: the first two',
          below_text: 'Confirmations stop **double bookings**.',
        },
        {
          type: 'table',
          header: ['Message', 'When'],
          rows: [['Reminder', '24 hours before']],
          caption: '',
          below_text: 'Reminders cut no-shows the most.',
        },
        {
          type: 'table',
          header: ['Message', 'When'],
          rows: [['Running late', 'When the queue slips']],
          caption: '',
          below_text: 'See [our clinic guide](/industries/clinics).',
        },
        { type: 'image', url: '/static/blog/inline/abc-123.webp', alt: 'Reminder on a phone', caption: 'A reminder' },
      ],
    },
    {
      question: 'What does it cost, and what did a real clinic get?',
      body: 'Prices below are typical for one clinic in India.',
      items: [
        {
          type: 'real_example',
          client: 'a 3-doctor dental clinic.',
          before: '18% of patients did not turn up.',
          after: 'reminders went out on WhatsApp.',
          metrics: [
            { label: 'No-shows', value: '18% to 7% in 14 days' },
            { label: 'Reminder calls', value: '60 a day to 5 a day' },
          ],
          description: 'The clinic kept its number.',
        },
        {
          type: 'cost_table',
          columns: ['Item', 'Setup (₹)', 'Per month (₹)'],
          rows: [['Setup', '25,000', '—'], ['API', '—', '3,000']],
          below_text: 'Excludes GST.',
        },
      ],
    },
  ],
  cta: 'calendly',
  cta_text: 'Want to see it on your own booking flow?',
};

let passed = 0;
function test(name: string, fn: () => void) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (err) {
    console.log(`FAIL  ${name}`);
    throw err;
  }
}

const md = composeV2(SAMPLE_V2, TITLE);
if (process.argv.includes('--write-fixture')) {
  writeFileSync(FIXTURE, md, 'utf8');
  console.log(`wrote ${FIXTURE}`);
}

test('v2 round trip: composeV2(parseV2(md)) == md, stored blocks reopen as-is', () => {
  const parsed = parseV2(md);
  assert.ok(parsed, 'parseV2 returned null');
  assert.equal(composeV2(parsed!.blocks, TITLE), md);
  // A cost table with custom columns is the same Markdown as a table, so a
  // parse reads it back as 'table'; the saved blocks keep the real type.
  assert.deepEqual(blocksForBodyV2(md, TITLE, SAMPLE_V2), SAMPLE_V2);
});

test('3 tables with 3 below-texts compose in order', () => {
  const a = md.indexOf('Right after booking');
  const b = md.indexOf('double bookings');
  const c = md.indexOf('24 hours before');
  const d = md.indexOf('cut no-shows the most');
  const e = md.indexOf('When the queue slips');
  const f = md.indexOf('our clinic guide');
  assert.ok(a < b && b < c && c < d && d < e && e < f, md);
});

test('bold and links pass through the H2 body untouched', () => {
  assert.ok(md.includes('**Short answer:** a booking'));
  assert.ok(md.includes('[pricing](/pricing)'));
});

test('callout uses its free-text label', () => {
  assert.ok(md.includes('> **Clinic hack:** Keep your **old number** on the API.'));
});

test('cost table columns: add, rename, remove round-trip', () => {
  const blocks = structuredClone(SAMPLE_V2);
  const cost = blocks.sections[2].items[1] as any;
  cost.columns = ['Line item', 'One-off', 'Monthly', 'Lead time'];   // add + rename
  cost.rows = [['Setup', '25,000', '—', '5 days'], ['API', '—', '3,000', '1 day']];
  let out = composeV2(blocks, TITLE);
  assert.ok(out.includes('| Line item | One-off | Monthly | Lead time |'));
  assert.equal(composeV2(parseV2(out)!.blocks, TITLE), out);
  assert.deepEqual(blocksForBodyV2(out, TITLE, blocks), blocks);
  cost.columns = ['Line item', 'Monthly'];                            // remove
  cost.rows = [['Setup', '—'], ['API', '3,000']];
  out = composeV2(blocks, TITLE);
  assert.ok(out.includes('| Line item | Monthly |\n|---|---|\n| Setup | — |'));
  assert.equal(composeV2(parseV2(out)!.blocks, TITLE), out);
  assert.deepEqual(blocksForBodyV2(out, TITLE, blocks), blocks);
});

test('v1 data opens in v2 without changing a byte', () => {
  const v1md = compose(V1_SAMPLE, TITLE);
  const converted = toV2(V1_SAMPLE);
  assert.equal(composeV2(converted, TITLE), v1md);
  assert.deepEqual(normaliseBlocksV2(V1_SAMPLE), converted);
  assert.ok(blocksForBodyV2(v1md, TITLE, V1_SAMPLE));
  assert.ok(blocksForBodyV2(v1md, TITLE, null), 'parseV2 should read a v1 body');
});

test('v1 example and cost become items', () => {
  const converted = toV2(V1_SAMPLE);
  const types = converted.sections.flatMap((s) => s.items.map((i) => i.type));
  assert.ok(types.includes('real_example'));
  assert.ok(types.includes('cost_table'));
});

test('callout rule: 0 blocked, 2 blocked, 1 with custom label OK, reserved rejected', () => {
  const none = structuredClone(SAMPLE_V2);
  none.sections[0].items = none.sections[0].items.filter((i) => i.type !== 'callout');
  assert.ok(playbookProblems(none).includes('Add one callout before submitting.'));

  const two = structuredClone(SAMPLE_V2);
  two.sections[1].items.push({ type: 'callout', label: 'Note', text: 'x' });
  assert.equal(countCallouts(two), 2);
  assert.ok(playbookProblems(two).includes('Only one callout per article.'));

  assert.deepEqual(playbookProblems(SAMPLE_V2), []);

  const reserved = structuredClone(SAMPLE_V2);
  (reserved.sections[0].items[1] as any).label = 'Real example';
  assert.ok(playbookProblems(reserved).some((p) => p.includes('reserved')));
});

test('half-filled optional blocks are problems; empty ones are not', () => {
  const b = structuredClone(SAMPLE_V2);
  b.sections[1].items.push({ type: 'table', header: ['A', 'B'], rows: [['', '']], caption: '', below_text: '' });
  b.sections[1].items.push({ type: 'image', url: '/x.webp', alt: '', caption: '' });
  b.sections[2].items.push({
    type: 'real_example', client: 'a shop', before: 'slow', after: 'fast',
    metrics: [{ label: '', value: '' }], description: '',
  });
  b.sections[2].items.push({ type: 'table', header: ['', ''], rows: [['', '']], caption: '', below_text: '' });
  const problems = playbookProblems(b);
  assert.ok(problems.some((p) => p.includes('header but no rows')));
  assert.ok(problems.some((p) => p.includes('no alt text')));
  assert.ok(problems.some((p) => p.includes('no numbers')));
  assert.equal(problems.length, 3, problems.join('\n'));
});

test('link scheme filter', () => {
  assert.ok(isAllowedUrl('https://a.com/x'));
  assert.ok(isAllowedUrl('/blog/x'));
  assert.ok(!isAllowedUrl('javascript:alert(1)'));
  assert.ok(!isAllowedUrl('http://a.com'));
  assert.ok(!isAllowedUrl('//evil.com'));
  assert.deepEqual(badLinks('[x](javascript:alert(1)) ![img](data:x) [ok](/a)'), ['javascript:alert(1']);
  const bad = structuredClone(SAMPLE_V2);
  bad.sections[0].body += ' [click](javascript:alert(1))';
  assert.ok(playbookProblems(bad).some((p) => p.includes('not allowed')));
});

test('an empty v2 article still emits the TL;DR marker and placeholder', () => {
  const blank = composeV2(emptyBlocksV2(), '');
  assert.ok(blank.startsWith('> **TL;DR**'));
  assert.ok(blank.includes('[FROM AUTHOR: '));
});

test('a hand-written body still opens raw', () => {
  assert.equal(blocksForBodyV2('# Old\n\nIntro.\n\n## H\n\nText.\n', 'Old', null), null);
});

test('v1 parse() is unchanged for v1 bodies', () => {
  assert.deepEqual(parse(compose(V1_SAMPLE, TITLE))!.blocks, V1_SAMPLE);
});

test('the v2 fixture matches the composer', () => {
  assert.equal(readFileSync(FIXTURE, 'utf8').replace(/\r\n/g, '\n'), md);
});

console.log(`\n${passed} passed`);
