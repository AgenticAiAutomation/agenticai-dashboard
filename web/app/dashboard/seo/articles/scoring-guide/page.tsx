'use client';

import Link from 'next/link';
import Shell from '@/components/Shell';
import { Card } from '@/components/ui';

/**
 * The scoring SOP, in the dashboard rather than in a shared document.
 *
 * A writer who has to leave the tool to find out what "Target 60-75" means
 * usually doesn't bother, so the guide lives one click from the article list
 * and reads as plain English rather than as the scorer's own vocabulary.
 *
 * Every point value and threshold here is copied from
 * api/app/seo/services/scoring.py. If a check's weight changes there, this page
 * has to change with it — see REFERENCE below, which is the whole 100 points.
 */

/* A phrase the writer sees verbatim in the score panels. */
function Screen({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-line bg-raised px-1.5 py-0.5 font-mono text-[12px] text-slate-200">
      {children}
    </code>
  );
}

function Example({
  tone,
  label,
  children,
  note,
}: {
  tone: 'bad' | 'good';
  label: string;
  children: React.ReactNode;
  note?: string;
}) {
  const bad = tone === 'bad';
  return (
    <div
      className={`rounded-lg p-3 ${
        bad ? 'bg-danger/10' : 'bg-success/10'
      }`}
    >
      <p
        className={`mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.1em] ${
          bad ? 'text-danger' : 'text-success'
        }`}
      >
        {label}
      </p>
      <p className="text-sm leading-relaxed text-slate-200">{children}</p>
      {note && (
        <p className="mt-2 font-mono text-[11.5px] tabular-nums text-muted">{note}</p>
      )}
    </div>
  );
}

function Note({
  tone = 'accent',
  title,
  children,
}: {
  tone?: 'accent' | 'warn';
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`my-5 rounded-lg p-4 ${
        tone === 'warn' ? 'bg-warning/10' : 'bg-primary/10'
      }`}
    >
      <p
        className={`mb-2 text-[10.5px] font-bold uppercase tracking-[0.1em] ${
          tone === 'warn' ? 'text-warning' : 'text-primary'
        }`}
      >
        {title}
      </p>
      <div className="space-y-2 text-sm leading-relaxed text-slate-300">{children}</div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="relative border-l border-line pl-10 pb-5 last:border-l-transparent last:pb-0">
      <span className="absolute -left-[15px] -top-0.5 grid h-[30px] w-[30px] place-items-center rounded-full border border-line bg-surface font-mono text-[13px] text-primary">
        {n}
      </span>
      <span className="block font-semibold text-slate-100">{title}</span>
      <span className="text-sm leading-relaxed text-slate-300">{children}</span>
    </li>
  );
}

/* The full 100 points, grouped exactly as the scorer groups them. */
const REFERENCE: { group: string; total: number; rows: [string, number][] }[] = [
  {
    group: 'Content quality',
    total: 35,
    rows: [
      ['AI detection under 20%', 8],
      ['Word count 1,200–2,500', 5],
      ['Grammar', 5],
      ['Readability 60–75', 3],
      ['Sentence variety', 3],
      ['Active voice over 70%', 3],
      ['No repeated phrases', 3],
      ['H1–H2–H3 hierarchy', 3],
      ['Paragraph length variation', 2],
    ],
  },
  {
    group: 'On-page SEO',
    total: 30,
    rows: [
      ['Keyword in title, meta, H1, first 100 words', 8],
      ['Semantic coverage vs top 3 results', 6],
      ['Keyword density 0.8–2%', 3],
      ['Image alt tags', 3],
      ['Internal links (2+ out)', 3],
      ['External authoritative links (2+)', 3],
      ['Meta description 140–160 characters', 2],
      ['URL slug', 2],
    ],
  },
  {
    group: 'FAQ & experience',
    total: 20,
    rows: [
      ['FAQs sourced with proof URLs', 8],
      ['FAQ section, 5+ questions', 5],
      ['From Author section filled', 3],
      ['FAQ answers 30–80 words', 2],
      ['Author byline present', 2],
    ],
  },
  {
    group: 'Technical',
    total: 15,
    rows: [
      ['Schema markup', 5],
      ['No orphan (2+ inbound links)', 3],
      ['Mobile-friendly', 3],
      ['Canonical tag', 2],
      ['Featured image dimensions', 2],
    ],
  },
];

export default function ScoringGuidePage() {
  return (
    <Shell
      title="Scoring guide"
      subtitle="What the score panels are telling you, and exactly what to do about each one."
      actions={
        <Link href="/dashboard/seo/articles" className="btn-secondary">
          Back to articles
        </Link>
      }
    >
      <div className="max-w-3xl space-y-6">
        {/* ---------------- the short version ---------------- */}
        <Card title="The short version">
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Every article is marked out of <strong className="text-slate-100">100</strong> and
            cannot be published below <strong className="text-slate-100">80</strong>. The panels
            beside the editor are not a report card — they are a to-do list, sorted so the most
            valuable job sits at the top.
          </p>

          <ol className="ml-4 mt-6 list-none space-y-0 p-0">
            <Step n={1} title="Write the article first">
              Don&apos;t chase the score while drafting. Get the real story down, then score it.
            </Step>
            <Step n={2} title="Press Save & score">
              The panels only appear after this. Nothing is scored while you type.
            </Step>
            <Step n={3} title="Open Path to 80 and do only what is highlighted">
              It tells you how many points you need and which fixes get you there. Anything below
              the highlighted block is optional.
            </Step>
            <Step n={4} title="Re-score and repeat">
              Scores move as you edit. Two or three passes is normal.
            </Step>
            <Step n={5} title="Check Blocking publish is empty">
              Score and blockers are separate. An article can hit 85 and still be blocked — usually
              a missing image or alt text.
            </Step>
          </ol>

          <Note title="The single most common mistake">
            <p>
              Trying to fix every suggestion. You almost never need to. The{' '}
              <Screen>Path to 80</Screen> panel highlights the handful that actually close the gap
              — often just one or two. The rest are improvements you can make if you want, not
              requirements.
            </p>
          </Note>
        </Card>

        {/* ---------------- the two suggestion panels ---------------- */}
        <Card title="“Whole article · 16” — what is this?">
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Suggestions come in two kinds, and they are split into two panels for one practical
            reason: whether there is a line to jump to.
          </p>

          <p className="mb-1 font-semibold text-slate-100">In the text</p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Problems tied to <strong className="text-slate-100">one specific line</strong>. Click
            one and the editor jumps there. A passive sentence, a repeated phrase.
          </p>

          <p className="mb-1 font-semibold text-slate-100">Whole article</p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Problems that aren&apos;t tied to any single line, because they are about the piece as a
            whole. There is nowhere to jump to, so they are listed separately. The{' '}
            <Screen>· 16</Screen> is just how many there are.
          </p>

          <p className="text-sm leading-relaxed text-slate-300">
            “You only have one internal link” is not a problem with line 42 — it is a problem with
            the article. Same for word count, meta description, and how many FAQs you wrote. That is
            the whole distinction. It is{' '}
            <strong className="text-slate-100">not a severity ranking</strong>, and sixteen is not
            alarming: most are worth a quarter-point each.
          </p>

          <Note tone="warn" title="Read the numbers carefully">
            <p>
              Both panels show <Screen>+N</Screen>, but they don&apos;t always mean the same thing.
              In <Screen>Path to 80</Screen>, <Screen>+5.7</Screen> means{' '}
              <em>your score goes up by 5.7</em>. In <Screen>Whole article</Screen> the number is
              the check&apos;s own raw points, which only equals the score change when all 27 checks
              are running. Grammar and AI detection need outside services and are often skipped, and
              when they are, the raw number understates the real gain.
            </p>
            <p>
              <strong className="text-slate-100">
                Trust the numbers in Path to 80.
              </strong>{' '}
              Those are the ones converted into actual score points.
            </p>
          </Note>
        </Card>

        {/* ---------------- panel tour ---------------- */}
        <Card title="The four panels">
          <dl className="space-y-4 text-sm leading-relaxed">
            <div>
              <dt className="font-semibold text-slate-100">Path to 80</dt>
              <dd className="text-slate-300">
                Your gap and the shortest way to close it. Fixes are ranked by how much score they
                add, and the highlighted ones are enough to publish. If it says “these 2 fixes are
                enough to publish”, do those two and stop.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-100">
                On track · N passing <span className="text-success">✓</span>
              </dt>
              <dd className="text-slate-300">
                Everything you already got right. Click to expand. Split into house checks and Rank
                Math checks because the two systems measure different things and are meant to
                disagree. This exists so a 67 doesn&apos;t feel like failure — it usually means
                twenty-odd things are already correct.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-100">In the text / Whole article</dt>
              <dd className="text-slate-300">
                The full list of everything imperfect. Use these to push past 80, not to reach it.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-100">Blocking publish</dt>
              <dd className="text-slate-300">
                Hard stops, unrelated to score. Fix these or the publish button will not work.
              </dd>
            </div>
          </dl>
        </Card>

        {/* ---------------- fix guide ---------------- */}
        <Card title="Keyword placement · up to 8 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            Work &quot;OpenBots&quot; naturally into H1, first 100 words.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            Your main keyword has to appear in four places: the{' '}
            <strong className="text-slate-100">page title</strong>, the{' '}
            <strong className="text-slate-100">meta description</strong>, the{' '}
            <strong className="text-slate-100">H1</strong>, and somewhere in the{' '}
            <strong className="text-slate-100">first 100 words</strong>. Two points per slot. The
            message names only the ones you are missing.
          </p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Put it in the H1 and work it into the opening paragraph. “Naturally” is doing real work
            in that sentence — write something you would say out loud, don&apos;t bolt the keyword
            on.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Example tone="bad" label="Bolted on">
              OpenBots. In this article about OpenBots we look at OpenBots and what OpenBots does.
            </Example>
            <Example tone="good" label="Natural">
              Teams evaluating OpenBots usually arrive with one question: what does it cost to run
              twenty bots?
            </Example>
          </div>
        </Card>

        <Card title="Readability · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            Shorten sentences and replace multi-syllable jargon with plain words. Target 60-75.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            60–75 is a <strong className="text-slate-100">reading-ease score</strong>, not a word
            count. It is calculated from two things only:{' '}
            <strong className="text-slate-100">how long your sentences are</strong> and{' '}
            <strong className="text-slate-100">how many syllables your words have</strong>. The band
            is roughly “a smart adult reads this comfortably without re-reading”.
          </p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Break long sentences in two. Swap heavy words for short ones — <em>utilise</em> →{' '}
            <em>use</em>, <em>implementation</em> → <em>setup</em>, <em>prior to</em> →{' '}
            <em>before</em>, <em>necessitates</em> → <em>needs</em>. Past about 25 words, split it.
          </p>
          <div className="space-y-3">
            <Example
              tone="bad"
              label="Too heavy — scores 0 of 3"
              note="reading ease −99.4 · 26 words in one sentence"
            >
              “Organizations implementing intelligent document processing capabilities frequently
              encounter substantial impediments relating to the heterogeneity of their incoming
              documentation, which necessitates considerable configuration effort prior to
              operationalization.”
            </Example>
            <Example
              tone="good"
              label="In the band — scores 3 of 3"
              note="reading ease 74.7 · avg 9.5 words per sentence"
            >
              “Most teams hit the same wall with invoices. The documents arrive in too many
              different layouts. Every new layout needs setup before the bot can read it reliably.
              That is the hidden cost most buyers never budget for.”
            </Example>
          </div>
          <Note tone="warn" title="You can overshoot">
            <p>
              Above 75 loses points too, and{' '}
              <strong className="text-slate-100">no suggestion appears to tell you</strong> — the
              message only fires below 60. Chopping the good example into very short sentences
              scores 93.7, which earns <strong className="text-slate-100">0 of 3</strong>, the same
              as the jargon version. Aim for the band, not for maximum simplicity.
            </p>
          </Note>
        </Card>

        <Card title="No orphan · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            Add a link to this article from 2 other published article(s) so it is not orphaned.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            This one is about <strong className="text-slate-100">other</strong> articles, not this
            one. An orphan is a page nothing links to. Google finds pages by following links, so a
            page with no inbound links looks unimportant. You need{' '}
            <strong className="text-slate-100">two links pointing at this article</strong> from
            other published pieces.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            Open two published articles on a related topic, find a sentence where this one is
            genuinely relevant, and add a link with the link picker. Half the points come from a
            single link, so one is better than none.
          </p>
          <p className="text-sm leading-relaxed text-slate-300">
            <strong className="text-slate-100">Watch out:</strong> this is the check people forget,
            because it is the only one that needs you to edit a <em>different</em> article. It will
            not clear itself.
          </p>
        </Card>

        <Card title="Heading hierarchy · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            An article must have exactly one H1. Demote the extras to H2.
          </p>
          <p className="text-sm leading-relaxed text-slate-300">
            H1 is the article&apos;s title. There can only be one, the way a book has one title and
            many chapter names. Find the extra <Screen># Heading</Screen> lines and change them to{' '}
            <Screen>## Heading</Screen>. One <Screen>#</Screen> is H1, two is H2, three is H3.
            Sections go in H2; sub-points inside a section go in H3.
          </p>
        </Card>

        <Card title="External links · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            Cite 1 more authoritative external source(s) — vendor docs, standards bodies, or
            original research.
          </p>
          <p className="text-sm leading-relaxed text-slate-300">
            You need <strong className="text-slate-100">two links to reputable sites other than
            ours</strong>. Citing sources is a trust signal — it shows the claims came from
            somewhere. Link the actual source of any number or claim you made. Good: official vendor
            documentation, a standards body, a named research report. Weak: a competitor&apos;s
            blog, a listicle, an SEO content farm.
          </p>
        </Card>

        <Card title="From Author · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            The From Author section is 76 words. Target around 200 — a specific production story
            with numbers, not a summary.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            This is where you write first-hand experience. It is scored on length as a proxy for
            substance, and you get full marks at{' '}
            <strong className="text-slate-100">120 words</strong>.
          </p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Don&apos;t summarise the article. Tell one specific thing that happened on a real
            project — what the client had, what you tried, what broke, what the numbers were.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Example tone="bad" label="Summary — scores low">
              “In our experience, document automation delivers significant value and reduces manual
              effort for our clients.”
            </Example>
            <Example tone="good" label="Story — scores full">
              “A logistics client sent us 40,000 scanned bills of lading across 11 layouts. Our
              first pass read 62% cleanly. The failures were almost all one carrier&apos;s
              carbon-copy forms…”
            </Example>
          </div>
          <Note tone="warn" title="The on-screen message overstates this">
            <p>
              It says “target around 200”, but the scorer awards full marks at 120. Write to 120 and
              move on — anything beyond that earns nothing extra.
            </p>
          </Note>
        </Card>

        <Card title="Repeated phrases · up to 3 points">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            This phrase appears 4 times. Rewrite all but one.
          </p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            The tool looks for any run of{' '}
            <strong className="text-slate-100">three words in a row</strong> appearing{' '}
            <strong className="text-slate-100">three or more times</strong>. Each repeated run costs{' '}
            <strong className="text-slate-100">0.5 points</strong>. Your main keyword is exempt, so
            you are not punished for using it.
          </p>
          <Example tone="bad" label="Costs 0.5 points" note="“document processing automation” × 4">
            “Document processing automation reduces errors. Document processing automation also cuts
            cycle time. Most teams adopt document processing automation to remove manual keying. In
            practice, document processing automation pays back within a year.”
          </Example>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            Fix it by varying: “…it also cuts cycle time. Most teams adopt it to remove manual
            keying. In practice, the payback lands inside a year.”
          </p>
        </Card>

        <Card title="FAQ answer length · up to 2 points in total">
          <p className="mb-3 border-l-[3px] border-line bg-raised px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
            Answer is 19 words. Rewrite to land between 30 and 80 — that is the range Google pulls
            into featured snippets.
          </p>
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            Each FAQ answer should be{' '}
            <strong className="text-slate-100">30–80 words</strong>. This is why the list shows
            several near-identical entries: <strong className="text-slate-100">one per short
            answer</strong>. The 2 points are shared across all your FAQs, so each is worth a
            fraction.
          </p>
          <p className="mb-4 text-sm leading-relaxed text-slate-300">
            Add a second sentence to each short answer — the “so what”, or the trade-off. Under 30
            words is too thin for Google to lift into a snippet; over 80 gets cut off.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Example tone="bad" label="14 words — no points">
              “OpenBots is an open-source RPA platform. It has no per-bot licence fee.”
            </Example>
            <Example tone="good" label="64 words — full credit">
              “OpenBots is an open-source RPA platform, so there is no per-bot licence fee. You pay
              for support and the orchestrator instead of per robot. For a team running twenty
              unattended bots, that usually moves the cost from a per-seat line item to a flat
              platform cost. The trade-off is that you own more of the setup and maintenance work
              yourself.”
            </Example>
          </div>
          <Note title="Do these last">
            <p>
              Eight of these together are worth <strong className="text-slate-100">2 points</strong>
              . That is a lot of rewriting for very little score. Skip them unless{' '}
              <Screen>Path to 80</Screen> has highlighted them.
            </p>
          </Note>
        </Card>

        {/* ---------------- where the points are ---------------- */}
        <Card title="Where the points really are">
          <p className="mb-3 text-sm leading-relaxed text-slate-300">
            Four checks carry <strong className="text-slate-100">30 of the 100 points</strong>: AI
            detection (8), keyword placement (8), FAQs with proof URLs (8), and semantic coverage
            (6). At the other end, seven checks are worth 2 points each —{' '}
            <strong className="text-slate-100">14 points between all seven</strong>.
          </p>
          <p className="text-sm leading-relaxed text-slate-300">
            So if an article is stuck in the sixties, the problem is almost always one of the big
            four — not the eight FAQ answers sitting at a quarter-point each.{' '}
            <Screen>Path to 80</Screen> already sorts by this, which is why working it top-down is
            faster than grinding through the full list.
          </p>
          <Note title="A worked example">
            <p>
              An article at <strong className="text-slate-100">73</strong> needs 7 points and shows
              sixteen suggestions. But the top entry — expanding a thin section to reach word count
              — is worth <strong className="text-slate-100">+14.6</strong> on its own. The panel
              highlights that one and marks everything else optional. One fix, publishable. Working
              the list bottom-up instead would mean rewriting eight FAQ answers for a combined{' '}
              <strong className="text-slate-100">+2</strong>, and still falling short.
            </p>
          </Note>
        </Card>

        {/* ---------------- reference table ---------------- */}
        <Card title="All 27 checks">
          <p className="mb-4 text-xs text-muted">
            Checks needing an outside service are skipped when it is unavailable. Skipped checks
            leave the total, so the score is always out of what actually ran.
          </p>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th className="bg-raised px-3.5 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.09em] text-muted">
                    Check
                  </th>
                  <th className="bg-raised px-3.5 py-2 text-right text-[11px] font-semibold uppercase tracking-[0.09em] text-muted">
                    Points
                  </th>
                </tr>
              </thead>
              {/* One tbody per group: a group heading row inside a table has to be
                  a real row, not a wrapper around rows. */}
              {REFERENCE.map((section) => (
                <tbody key={section.group}>
                  <tr>
                    <td
                      colSpan={2}
                      className="bg-raised px-3.5 py-1.5 text-[11.5px] font-bold uppercase tracking-[0.05em] text-slate-300"
                    >
                      {section.group} · {section.total}
                    </td>
                  </tr>
                  {section.rows.map(([label, points]) => (
                    <tr key={label} className="border-b border-line/60">
                      <td className="px-3.5 py-2 text-slate-300">{label}</td>
                      <td className="px-3.5 py-2 text-right font-mono tabular-nums text-slate-200">
                        {points}
                      </td>
                    </tr>
                  ))}
                </tbody>
              ))}
            </table>
          </div>
        </Card>

        {/* ---------------- quirks ---------------- */}
        <Card title="Two quirks worth knowing">
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-300">
            <li>
              <strong className="text-slate-100">
                The From Author message says 200, but 120 earns full marks.
              </strong>{' '}
              Write to 120 and move on.
            </li>
            <li>
              <strong className="text-slate-100">
                Readability punishes overshooting, silently.
              </strong>{' '}
              Below 60 you get a warning. Above 75 you lose the same points with no message at all.
              If readability shows 0 points and no suggestion, you have gone too simple, not too
              complex.
            </li>
          </ul>
        </Card>

        <p className="pb-4 text-xs text-muted">
          Publish threshold 80 of 100. Point values and thresholds on this page are taken from the
          live scoring code, and the readability scores shown were computed with it.
        </p>
      </div>
    </Shell>
  );
}
