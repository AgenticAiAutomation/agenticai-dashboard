# Writing an article in the block editor

For the SEO team. No code, no HTML, no JSON — you write in blocks, the page
builds itself.

## Where it is

Articles → the **Blocks** link on any article. (If you do not see the link,
the block editor is switched off on the server; use Edit as before.) The old
markdown editor still works for every article and nothing about it changed.

## The screen

Three columns:

1. **Left — your article.** Title, URL, keyword, meta title, meta description,
   then the blocks.
2. **Middle — the preview.** The exact page readers will see, updated a second
   or two after you stop typing. Switch it to *mobile* to see it on a phone.
3. **Right — publish, checks, score, history.**

It saves by itself five seconds after you stop typing (“Saved” at the top
right). Ctrl+S saves now. If you see “Not saved”, read the red message — it
names the block and the field.

## Blocks

Every article is a stack of blocks. A block is one thing: a paragraph, a
heading, a table, an image, a chart, a quote.

- **Add a block:** type `/` in an empty paragraph, or click **+ Add a block**
  at the bottom, or hover between blocks and click the **+**. Type to filter
  (“tab” finds Table), arrow keys to choose, Enter to insert.
- **Move a block:** drag the ⋮⋮ handle, or click it and press Alt+↑ / Alt+↓.
- **Duplicate / delete:** hover a block; the buttons are top right.
- **Change a paragraph into a heading, callout or quote** (and back): hover,
  use the dropdown top right. Your words are kept.
- **Enter** in a paragraph starts a new paragraph. **Backspace** in an empty
  block removes it.

### Text formatting

Select text and a small toolbar appears: **bold**, *italic*, underline,
strike, `code`, link, four **highlight** colours, four **emphasis** colours.
Ctrl+B / Ctrl+I / Ctrl+U / Ctrl+K (link) also work.

The colours are named — amber, mint, sky, rose — not a colour picker. That
is deliberate: sixty articles by six writers still look like one site.

**Limits, enforced when you save:** at most **4 highlights** and **2 gradient
headlines** per article, **1 lead paragraph** per section. Go over and you
get a warning and lose score. Two gradient headlines feel designed; six feel
like a slide deck.

### Pasting

Paste from Google Docs, Word or a web page. Headings stay headings, bullet
lists stay lists, bold and italic stay — and every font, colour and size the
source had is dropped. Plain text with blank lines between paragraphs becomes
separate paragraph blocks.

## The blocks, and when to use each

| block | use it for | remember |
|---|---|---|
| **Key takeaways** | 3–5 one-line facts, at the top | Required in the first four blocks. This is what Google lifts into a snippet. |
| **Paragraph** | body text | Tick *Lead paragraph* on the first one of a section — one per section. |
| **Heading** | section titles | H2 for sections, H3 inside a section. Never skip a level. The title is the H1. |
| **List** | bullets, numbers, checklists | |
| **Steps** | a how-to | 3 or more steps get HowTo structured data. Add a total time if you know it. |
| **Image** | a figure | Alt text is required, at least three words, describing what is in the picture. Not the filename. Not “image of”. Caption and credit optional. *Breakout* makes it wider than the text. |
| **Gallery** | 2–4 images | |
| **Before / after** | two versions of the same thing | Same framing, same size, or the comparison lies. |
| **Video** | YouTube or a clip | Title, description, upload date, duration and a poster image are all required — Google needs them. Nothing loads from YouTube until a reader clicks. |
| **Table** | numbers and comparisons | Caption is required. Right-align money and numbers. *Stack rows* on phones for wide tables. |
| **Callout** | a note, tip, warning or result | Result callouts are for the outcome — use one. |
| **Quote** | something a person said | Name required; role and company optional. |
| **Code** | code | Language label; readers get a copy button. |
| **Stat band** | 2–4 big numbers | Type the number as it should read (“1,240”, “62%”). |
| **Chart** | bar, line or donut | Fill the table; the chart draws itself. It must have a title. |
| **Process flow** | a pipeline, left to right | 2–7 steps; mark which are bots, humans, decisions and the result. |
| **FAQ** | questions and answers | Required. 30–80 words per answer is what Google shows. Feeds the FAQ table used by the scorer. |
| **Call to action** | a link to a service or the audit | |
| **Divider** | a section break | |
| **Embed** | a LinkedIn or X post | Shown as a link card; no tracking script loads. |

## The rhythm rule

The editor watches for walls of text:

- no more than **250 words** without a visual (image, table, chart, callout,
  quote, steps, code, stat band, flow);
- at least **one visual per 400 words**;
- key takeaways near the top; an FAQ block somewhere.

Break any of these and the Checks panel says so. It is a warning, not a
block — but it costs score, and it is the whole point of the new editor.

## Checks, score, publish

**Checks** (right column) lists everything the editor found. Click a message
to jump to the block. ⛔ blocks publishing; ⚠ is advice and costs score.

**Save & score** runs the same 27-check scorer and Rank Math checks as the
old editor. Publishing still needs **80**.

**Publish** is Jai's button. If a ⛔ check is still failing, the button
explains which; an admin can override with a reason, and the reason is
recorded.

**History** shows every save. Restore any earlier version; nothing is lost —
the current version is kept too.

## What the page does for you

You never write these; they come from your blocks:

- structured data for Google (article, breadcrumbs, FAQ, how-to, video);
- the table of contents from your H2/H3 headings;
- reading time, dates, the author box;
- image sizes, lazy loading, the mobile layout;
- the “Updated” date when you republish.

## Two habits that matter

**Alt text describes; it does not name.** “Whiteboard listing five invoice
failure causes, carbon-copy forms far ahead” — not “whiteboard.jpg” and not
“image”.

**Numbers go in tables and stat bands, not sentences.** A reader scans; a
table gives them the answer in a second, and Google can show it.
