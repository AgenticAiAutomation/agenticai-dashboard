/**
 * Blog Playbook composer tests (web/lib/playbook.ts). No framework — Node 22+
 * runs TypeScript directly:
 *
 *   node tests/playbook/compose.test.mts
 *   node tests/playbook/compose.test.mts --write-fixture   (refresh the .md)
 *
 * The composed sample is also written to tests/playbook/sample.md, which the
 * Python tests (tests/test_blog_playbook.py) score and render — so the two
 * languages are tested against the same bytes.
 */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  blocksForBody,
  compose,
  emptyBlocks,
  parse,
  sectionMarkdown,
  countWords,
  type PlaybookBlocks,
} from '../../web/lib/playbook.ts';

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(here, 'sample.md');
const KEYWORD = 'whatsapp automation for clinics';
const TITLE = 'WhatsApp Automation for Clinics: Cut No-Shows in 14 Days';

export const SAMPLE: PlaybookBlocks = {
  version: 1,
  tldr: [
    'WhatsApp automation for clinics sends booking confirmations, reminders and token updates without a receptionist typing them.',
    'Most clinics see fewer no-shows within two weeks because patients answer WhatsApp faster than calls.',
    'Setup takes about a week on the official WhatsApp Business API, and you keep your existing number.',
  ],
  who: 'clinic owners and practice managers handling 30 or more appointments a day.',
  sections: [
    {
      question: 'How does WhatsApp automation work in a clinic?',
      body:
        'A patient books on your website, by phone or at the desk. The booking lands in your calendar and a WhatsApp message goes out at once with the date, time and doctor. A day before, a reminder asks the patient to confirm or move the slot.\n\nOn the day, the patient gets their token number and a short message when the doctor is running late. Nobody at the front desk types any of it.',
      kind: 'flow',
      steps: [''],
      flow: ['Booking made', 'Confirmation sent', 'Reminder 24h before', 'Token on the day'],
      table: { header: ['', ''], rows: [['', '']] },
      image: { url: '', alt: '', caption: '' },
      callouts: [
        { tone: 'tip', text: 'Keep your old number. The API can run on the number patients already know.' },
      ],
    },
    {
      question: 'What do you need before you start?',
      body: 'You need three things in place. None of them takes long, but the approval step can stall if your business details do not match.',
      kind: 'steps',
      steps: [
        'A verified Meta Business account with your clinic name exactly as registered.',
        'A WhatsApp Business API number, either new or moved from the WhatsApp Business app.',
        'Approved message templates for confirmations, reminders and delays.',
      ],
      flow: ['', ''],
      table: { header: ['', ''], rows: [['', '']] },
      image: { url: '', alt: '', caption: '' },
      callouts: [
        { tone: 'warn', text: 'Moving a number off the WhatsApp Business app deletes its chat history on that phone. Export it first.' },
      ],
    },
    {
      question: 'Which messages should a clinic automate first?',
      body: 'Start with the messages your front desk sends most. For most clinics that order looks like this.',
      kind: 'table',
      steps: [''],
      flow: ['', ''],
      table: {
        header: ['Message', 'When it goes out', 'Why it matters'],
        rows: [
          ['Booking confirmation', 'Right after booking', 'Stops double bookings'],
          ['Reminder', '24 hours before', 'Cuts no-shows the most'],
          ['Running late', 'When the queue slips', 'Fewer angry calls at the desk'],
        ],
      },
      image: { url: '', alt: '', caption: '' },
      callouts: [
        { tone: 'pro', text: 'Add a one-tap "Reschedule" button to the reminder. Patients move slots instead of skipping them.' },
      ],
    },
  ],
  example: {
    heading: 'What does this look like for a real clinic?',
    client: 'a 3-doctor dental clinic with about 45 appointments a day.',
    before: 'two receptionists spent most mornings on reminder calls, and 18% of patients did not turn up.',
    after: 'reminders and confirmations went out on WhatsApp, and the front desk handled walk-ins instead.',
    metrics: [
      { label: 'No-shows', value: '18% to 7% in 14 days' },
      { label: 'Reminder calls', value: '60 a day to 5 a day' },
      { label: 'Setup time', value: '6 working days' },
    ],
  },
  cost: {
    heading: 'What does it cost and how long does it take?',
    intro: 'Prices below are typical for a single clinic in India and exclude GST.',
    rows: [
      { item: 'Setup and templates', one_time: '₹25,000', monthly: '—', time: '5–7 days' },
      { item: 'WhatsApp API and hosting', one_time: '—', monthly: '₹3,000', time: '1 day' },
      { item: 'Message charges', one_time: '—', monthly: 'About ₹0.15 each', time: '—' },
    ],
  },
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

const md = compose(SAMPLE, TITLE);

if (process.argv.includes('--write-fixture')) {
  writeFileSync(FIXTURE, md, 'utf8');
  console.log(`wrote ${FIXTURE}`);
}

/* ---- §6 test 2: the composer ---- */
test('exactly one H1', () => {
  assert.equal((md.match(/^# /gm) || []).length, 1);
});

test('at least three H2s', () => {
  assert.ok((md.match(/^## /gm) || []).length >= 3);
});

test('keyword inside the first 100 words (as the house scorer counts them)', () => {
  // Mirror of scoring.strip_markdown + its word regex.
  const text = md
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/[*_>~]/g, '');
  const first100 = (text.match(/[A-Za-z0-9']+/g) || []).slice(0, 100).join(' ').toLowerCase();
  assert.ok(first100.includes(KEYWORD), first100);
});

test('no HTML tags', () => {
  assert.equal(/<\/?[a-z][^>]*>/i.test(md), false);
});

test('every question section is 250 words or fewer', () => {
  for (const section of SAMPLE.sections) {
    assert.ok(countWords(sectionMarkdown(section)) <= 250, section.question);
  }
});

test('opens with the TL;DR block and keeps the author placeholder', () => {
  assert.ok(md.startsWith(`# ${TITLE}\n\n> **TL;DR**\n>\n> - `));
  assert.ok(md.includes('\n[FROM AUTHOR: '));
});

/* ---- §6 test 3: the round trip ---- */
test('parse(compose(x)) == x for the sample', () => {
  const parsed = parse(md);
  assert.ok(parsed, 'parse returned null');
  assert.equal(parsed!.title, TITLE);
  assert.deepEqual(parsed!.blocks, SAMPLE);
});

test('compose(parse(md)) == md', () => {
  assert.equal(compose(parse(md)!.blocks, TITLE), md);
});

/* ---- the "never silently rewrite" guarantee ---- */
test('an old, hand-written body opens in the raw editor', () => {
  const old = '# Old post\n\nSome intro.\n\n## A heading\n\nText.\n';
  assert.equal(parse(old), null);
  assert.equal(blocksForBody(old, 'Old post', null), null);
});

test('saved blocks are ignored once the body was edited by hand', () => {
  const edited = md.replace('Nobody at the front desk', 'No one at the front desk');
  const result = blocksForBody(edited, TITLE, SAMPLE);
  // Either raw (null) or blocks that compose to the edited body exactly.
  if (result !== null) assert.equal(compose(result, TITLE), edited);
});

test('saved blocks open when they match the body', () => {
  assert.deepEqual(blocksForBody(md, TITLE, SAMPLE), SAMPLE);
});

test('a new, empty Playbook still emits the TL;DR marker and placeholder', () => {
  const blank = compose(emptyBlocks(), '');
  assert.ok(blank.startsWith('> **TL;DR**'));
  assert.ok(blank.includes('[FROM AUTHOR: '));
});

test('pipes inside table cells survive the round trip', () => {
  const blocks = structuredClone(SAMPLE);
  blocks.sections[2].table.rows[0][2] = 'Stops A | B confusion';
  const out = compose(blocks, TITLE);
  assert.deepEqual(parse(out)!.blocks, blocks);
});

test('the sample fixture matches the composer', () => {
  // A Windows checkout (core.autocrlf) may hand the file back with CRLF.
  assert.equal(readFileSync(FIXTURE, 'utf8').replace(/\r\n/g, '\n'), md);
});

console.log(`\n${passed} passed`);
