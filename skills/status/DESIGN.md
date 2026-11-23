---
name: Status review page
colors:
  primary: "#1c1c1e"        # --action: the one solid button of a panel
  accent: "#1f5fd6"         # --accent: unread marker, links, keyboard focus
  bg: "#ffffff"             # --canvas
  surface: "#ffffff"        # --surface: the page itself, menus and controls
  surface-quiet: "#f3f3f5"  # --surface-quiet: row hover, the chosen view, the search field in use, code
  fg: "#1c1c1e"             # --ink
  fg-muted: "#505057"       # --ink-secondary: secondary prose
  fg-faint: "#6c6c73"       # --ink-tertiary: row metadata and ages, at least 4.5:1 on every surface
  border: "#e7e7ea"         # --rule: hairlines
  border-strong: "#c8c8ce"  # --rule-strong: control outlines
  danger: "#c0341d"         # --critical: blocking asks, failures
  warning: "#9a5300"        # --attention: notices, stale or overdue, earlier version
  success: "#17693f"        # --positive: accepted
typography:
  title:   { fontFamily: system-ui, fontSize: 30px, fontWeight: 700, lineHeight: 1.25 }
  heading: { fontFamily: system-ui, fontSize: 20px, fontWeight: 700, lineHeight: 1.25 }
  reading: { fontFamily: system-ui, fontSize: 16px, lineHeight: 1.6 }
  table:   { fontFamily: system-ui, fontSize: 15px, lineHeight: 1.5 }
  meta:    { fontFamily: system-ui, fontSize: 13px, lineHeight: 1.5 }
layout:
  page: 1120px        # --page-width
  main: 640px         # --main-width, also --measure
  rail: 416px         # --rail-width
  gutter: 64px        # --gutter
rounded:
  sm: 4px
  control: 8px
  container: 10px
spacing:
  1: 4px
  2: 8px
  3: 12px
  4: 16px
  5: 24px
  6: 32px
  7: 48px
  8: 72px
components:
  list-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
---

# Status review page design contract

Before any UI change, read this contract and follow the interface-design skill.
Implementation values live in `assets/tokens.css`; this file mirrors them and
holds the rules. Add a token in both places.

## Overview

One standalone page where the owner reviews two kinds of agent work: **operations**
(long-running efforts with a living report) and **proactive work** (finished,
unrequested work an agent delivers). It also shows what agents are asking of
him in Ribbon Field, without owning those asks. He opens it a few times a day,
on a desktop and on a phone, to decide what to answer, read, or dismiss.

Direction: a **calm task list**. Ink on a white page; hairlines and space do the
grouping; colour only states something; the only outlined things are controls.
Posture: transient. It must read at a glance, so chrome is minimal and every
row is a title, one quiet line, and an age. Light and dark themes follow the
system. Reference applications: **Things** for calm lists and **Linear Inbox**
for triage.

## Colors

Colour carries state, never decoration. Most of every screen is ink on paper.

- **Ink** is also the action colour: the one solid button of a panel is ink on
  paper (paper on ink in the dark theme), not the accent.
- **Accent** marks unread items, links in text, and keyboard focus. Nothing else.
- **Critical** marks the word "Blocking", a failed request, and the state words
  "Off track" and "Blocked" with a worse change's mark. Nothing else is red.
- **Attention** marks stale or overdue asks, an inactive agent, stale
  observations, an unavailable source, and the notice on an earlier version.
- **Positive** marks an accepted delivery, the state words "On track" and
  "Done", and a better or resolved change. Dismissed is neutral, not red.
- **Attention** also marks "At risk", an overdue item for the reader, a
  deadline in a timeline, and a measure that moved the wrong way.
- **Charts are ink.** Series are told apart by dashes and a legend, never by
  hue, because hue on this page means state.
- A tint appears only behind the text whose state it marks (failure, earlier
  version). The quiet surface is the ground of a hovered row, the chosen view,
  the search field in use, and code.
- Every text colour is at least 4.5:1 on the canvas and on the quiet surface, in
  both themes.

## Typography

System sans-serif for everything; monospace only for code and file paths.
Five sizes: title 30 px (26 px at phone width), report headings 20 px, text
16 px, tables 15 px, metadata and desktop controls 13 px. Controls use 16 px at
phone width. List section headings ("Needs you", "Operations") are set at text
size in bold on a hairline, with a count in regular grey. Numbers use tabular
figures.

A row title is 16 px at 1.35: medium weight for an ask and for an unread item,
regular for a read one. Metadata is one grey in every state; only a state word
is coloured. An ask's title is the question itself and is shown whole at every
width. A delivery's or operation's title too long for its lines ends at a
whole word (the script fits it), never inside a figure, and the full title
stays in its tooltip and accessible name. A list title is shown without its closing full stop. No
uppercase tracked labels, and no reference numerals on sections.

Prose (the assessment, notices, section text, ask text) keeps the 640 px measure
at line height 1.6. A line that begins with a number is set as a step with its
number hanging; a web address in text is linked as written and may break after
a slash.

## Layout

The page is 1120 px wide: a **main column of 640 px**, a 64 px gutter, and a
**rail of 416 px**. Below 1000 px everything is one column; at phone width the
page inset is 24 px. Spacing uses the 4 px scale.

- **Review page.** What asks for a decision takes the main column (asks, then
  proactive work); the living reports take the rail, in every view. Each
  section is one list, newest first; asks keep Ribbon Field's order. Items with
  nothing new for seven days wait in one closed native "Older" group with a
  count at the end of their section; a search that matches inside opens it, and
  a section holding nothing newer shows its rows directly.
- **Row.** A title (a delivery's or operation's on one line, two at phone
  width; an ask's whole) with its age in a fixed right column ("now", "52m", "15h", then "Nov 9"), and one line beneath:
  state words, then what it costs (kind and effort, for an ask other than a
  decision), then the source or an excerpt. A delivery's excerpt is
  "Recommended: ..." while it is open. Rows bleed 20 px past the column so the
  hover tint and focus ring share one box while text stays on the column edge.
  At phone width the title takes the row's full width and the age ends the
  line beneath, which wraps: an ask's in full, an excerpt to two lines. The
  age never stands alone on a line. Row actions appear on hover or keyboard focus; a touch user responds
  on the item's page.
- **Margin mark.** One mark hangs left of the text column: an 8 px accent disc
  for an unread delivery or operation, a chevron for an ask (it opens in place).
- **Open ask.** It opens in place between two hairlines on the column. Order:
  title, the line beneath, what answering unblocks and the place to act, the
  response, then the whole question and its context, in ink. Nothing in it is
  boxed except its controls.
- **Report.** Navigation, title, one quiet line (subject, "As of ..."), then the
  opening: the operation's asks, the assessment and the notices in the main
  column, with the measures in the rail as rows (label, value at the right,
  particulars beneath). Sections follow at full width with prose at the
  measure. A table of two columns keeps the main column and wraps at phone
  width; every wider table takes the page's 1120 px and scrolls sideways under
  its first column, with edge shadows, only when that is not enough.
- **Delivery.** Title and one quiet line, then the summary in the main column with
  the response in the rail beside it (it follows the summary below 1000 px).
  A write-up of prose alone continues in the main column and the response stays
  in view beside it. Wide content (a write-up with tables, an interactive
  document, another application) takes the page's whole width below the rail.

## Elevation & Depth

Flat. Layers, bottom to top: canvas; row actions; menus (version history,
snooze, response choices); one transient notice. No shadows on surfaces; a
menu is outlined. The only gradient is the edge shadow of a scrolling table,
which states that the table continues.

## Shapes

Containers 10 px, controls 8 px, small insets 4 px. One-pixel rules. Chevrons
are drawn with two borders; the search glyph is the page's one drawn icon.

## Components

| Component | Variants | Use for | Do not use for |
|---|---|---|---|
| Row | ask (collapsed, open), unread, read, closed | One operation, delivery, or ask in a list | Anything with more than two row actions |
| Button | standard, primary, quiet | Primary: the one solid button of a panel, never greyed out. Standard: a second resolution (Decline, Not done). Quiet: snooze, dismiss, change, undo | A primary button on a list row |
| Choices | - | Options of an ask or a delivery as rows: one is chosen, then sent with the panel's primary button; choosing the chosen row clears it. A tag ("Recommended") takes its own line under the option's text | Sending on a single tap |
| Answer field | - | One outlined field for an answer or a note, a line tall (44 px at phone width), growing with what is written | A field ruled only underneath: it was a weak target |
| Action line | - | Primary at the left, quiet words at the right ending on the rule's edge; "Discuss" leads to the conversation | A second row of actions |
| View switch | - | Open / Done / All as three words, the chosen one on the quiet surface | Navigation between pages |
| Search | idle, in use | A glyph and a word until used; the glyph alone at phone width | A filter menu |
| Older group | - | Items with nothing new for seven days, as a native disclosure with a count | Hiding asks |
| Report sheet | portable, served | A status report and a delivery's detail | Lists |
| Notice | - | A material exception in a report: a strong first line and a paragraph directly under the assessment | Routine information |
| Measure | tile, rail row; with a bar toward its target, a trend line, and its last value | A metric with its provenance | Prose |
| State word | on track, at risk, off track, blocked, paused, done | How an operation or a lane stands: under a report's title, on its review row, beside a workstream | Decoration, or anything that is not a state |
| Report blocks | for you to do, since the last version, phases, timeline (axis for a fixed window, list by day with a Now rule), workstreams, line chart, bar chart | The four questions of a briefing and the shape of the work; drawn without script, positions in SVG percentages | Content that only one report needs: that is an interactive document |
| Response panel | awaiting, accepted, dismissed, earlier version | The owner's response to a delivery | Report response fields |
| Response editor | - | Agent-defined questions inside a report, with "Save responses" as its primary | Delivery responses |
| Version history | - | Earlier versions of an operation report or of a delivery | Anything else |
| Embedded document | retained document, application; unavailable on this address | Content an agent built, in a sandboxed frame inside an item's page or the embedded view. Its outline is the trust boundary: the one outlined region | Anything the page itself renders; agent markup is never written into a page |
| Response proposal | - | A response the embedded document proposes, inside the response panel with Confirm and Ignore | Recording a response without the owner's Confirm |
| Transient notice | with Undo | Confirming a change that removed a row from view | States the page already shows |

## Do's and Don'ts

- Never use eyebrow labels: no small uppercase or tracked label above a heading
  or value.
- One solid button per panel, and it is never greyed out: with nothing to send
  it leads to where an answer goes.
- Nothing is boxed except controls and an agent's embedded document.
- Every reversible action offers Undo or Reopen instead of a confirmation. An
  ask's resolution is not reversible, so a choice is chosen and then sent.
- Omit an empty section. Say plainly when a source is unavailable; never show
  an unavailable source as an empty list.
- No decorative gradients, shadows, glass effects, decorative icons, entrance
  animation, or cards inside cards.
- Do not copy Ribbon Field asks or answers into this store. Resolve them through
  Ribbon Field from the page, on both addresses.
- Never truncate text without a way to read all of it: in place for asks, on the
  item's page for deliveries and operations.
- Show an agent's text as written: titles, addresses and provenance are not
  rewritten, shortened to a domain, or hidden.
- Material findings in a report are never collapsed. Only background detail may
  start collapsed, and print expands it.
- Style values live only in `assets/tokens.css`; `drift_check.py diff` stays clean.

## Conceptual model

### Objects

| Object | Key attributes | Actions | Appears in |
|---|---|---|---|
| Operation | title, latest summary, origin, version count, unread, open asks | open, dismiss until next version, restore | Review list, report page |
| Report version | observations, notices, metrics, actions, sections, response fields | read, answer response fields, open another version | Report page |
| Delivery | title, summary, recommended default, decision, links, document, attachments, category, agent, key or series, latest version, version count, unread | read, do it (default or an option), dismiss with a reason, discuss in Ribbon Field, reopen | Review list, delivery page |
| Delivery version | one immutable publication of a delivery; number, received time | read, open another version; responses are given on the latest | Delivery page |
| Interactive document | kind (retained document or address of an application), the item version it belongs to | use inside the item's page; follow its links in the same tab | Report page, delivery page |
| Document state | the value the document saved, save time, revision, saving version | saved and loaded by the document through the page; read by agents | Not shown; `read_responses.py` |
| Embedded application | address on the tailnet host, the item it was opened from | read inside the page's frame, go back, open on its own | Embedded view |
| Ask (owned by Ribbon Field) | kind, title, full question, choices, blocking, what it unblocks, thread | answer in place (choose and send, or write), resolve by kind with a note, snooze, dismiss, discuss in the thread | Review list, report page of its operation |

### Lexicon

| Term | Means | Never call it |
|---|---|---|
| Operation | A long-running effort with one living report | campaign, project report |
| Version | One retained report of an operation, or one publication of a delivery | snapshot, copy |
| Interactive document | Content an agent built that runs inside an item's page, in a sandbox | widget, app, plugin |
| Propose | An interactive document suggesting a response that the owner confirms or ignores | submit, respond, record |
| Delivery | Finished unrequested work handed to the owner | suggestion, notification |
| Ask | Something an agent needs from the owner, kept in Ribbon Field | decision, question, task |
| Dismiss | Remove from Open without acting | archive, delete |
| Do it | Accept the recommended default or a listed option | approve, submit |

## Motion

Only a 120 ms transition on control colours, the search field's width, and the
ask chevron. Nothing moves on load.

## States

- **Empty:** one sentence in grey ("No reports or deliveries yet", "All
  reviewed", "No matches").
- **Loading:** the counts announcement says "Loading…"; lists stay empty.
- **Failure:** a critical-tinted message above the lists; unsaved input stays.
- **Source unavailable:** "Asks unavailable" in the attention colour, with the
  reason, under the header.
- **Earlier version:** an attention notice with a link to the latest version.
- **Counts:** the header's counts line is an announcement for assistive
  technology; sighted readers have the section counts.

## Signature details

1. Ink on a white page in a main column and a rail; hairlines and space do the
   grouping, and nothing is boxed but controls.
2. One answer form everywhere: choices as rows, an outlined field for words,
   one solid ink button, quiet words at the right.
3. An ask is answered where it is listed, between two hairlines, with the
   response directly under its title.
4. A delivery row leads its second line with "Recommended:" so the default is
   readable without opening the item.
5. The margin mark: an accent disc for unread, a chevron for an ask.

## Decision record

- 2026-11-23: **Reports become briefings.** The owner found reports "a giant
  wall of text": the format accepted only prose, tables, and metric tiles, so
  no instruction could produce a timeline or a chart. The report now has
  visual blocks in a fixed order that answers the reader's four questions
  (where it stands, what changed, what I must do by when, what happens next):
  a state word under the title and on the review row, "For you to do" with
  the deadline first, "Since the last version", phases, a timeline, workstreams,
  line and bar charts, and measures with a target bar, a trend across versions,
  and their previous value. Everything is drawn server-side as HTML and SVG
  with percentage coordinates, so neither page's content policy changes and
  the portable file needs no script. A blind critic scored a real report of
  the old format 3/10 and the example in the new one 7/10; its fixes were
  applied (timeline axis only for a fixed window with only deadlines and
  milestones marked, day headings in the list, change marks that say good or
  bad rather than up or down, bars without empty tracks, even clock ticks,
  labelled peak and latest values, one column of measures on phones).
  Declined: 24-hour times (the page writes "2:00 PM" everywhere), removing
  sparklines (they need three versions to appear, and they are the only
  cross-version trend), and removing per-measure provenance. The builder
  prints advisory checks (summary length, prose walls, raw identifiers, dates
  without a timeline) because guidance alone did not change what agents wrote.

- 2026-11-23: An ask takes a reply as well as a resolution. The owner said the
  offered answers are often not what he wants to say. The free-text line is
  always present; **Reply** sends his words to the asking conversation as a
  user message naming the ask, through Ribbon Field's own message queue (the
  local forwarding or the paired browser, as for resolutions), and leaves the
  ask open marked "Replied". The mark comes from the content-free event log,
  so no reply text is stored here. The quiet link is "Reply in conversation".
- 2026-11-22: **The page is rebuilt as a calm task list.** Direction: ink on a
  white page, no containers, a margin mark for state, one quiet line under each
  title, colour only for state. Why: of four directions it was the only one
  whose restraint matched Things and Linear Inbox, and it keeps every ask on
  one screen, which triage needs. Method: four directions were derived from
  random seeds and outside inspirations (a railway timetable, an editorial
  front page, a calm task list, a bookkeeper's ledger); one blind critic ranked
  them against Things and Linear Inbox and put the task list first among the
  four; then every iteration was judged by a fresh critic that saw screenshots
  only, with one fixed prompt, and was followed by a removal pass.
  Scores, each from a different critic, out of 10: iteration 1, 6.4; iteration
  2, 6.4; iteration 3, 6.8; iteration 4, 6.4; iteration 5, 6.4. The target of
  9 was not reached. The loop was stopped after iteration 5, at the owner's
  cost limit, because the scores were not converging; iterations 6 to 8 were
  not run.
  What was built across the iterations: the response directly under an open
  ask's title (owner's request); one list per section, newest first, with a
  closed "Older" group for items quiet for seven days (owner's request);
  printed links that lead with the tailnet address (owner's request); one row
  grammar with the age in a fixed right column and a margin chevron for asks;
  titles fitted at a whole word; one answer form (choices, line field, one
  solid button) on asks and deliveries; four then five type sizes and one
  control height; notices without a coloured bar; and, after the owner set the
  page to 1120 px, a main column with a rail on all three pages.
  After iteration 5's critic one change was made and not scored: the marks
  that gave each kind a shape (a square for a delivery, a circle for a report)
  were returned to the unread disc of iterations 2 to 4, because a hollow
  square beside a title read as a checkbox that cannot be ticked.
  Declined, with the reason: putting the question before the response in an
  open ask (the owner asked for the response first); removing the ask chevron
  (a collapsed ask must show that it opens, on touch too); relabelling "Do it"
  with a generated verb, showing addresses as domains, hiding provenance, and
  stripping the subject line (each rewrites or hides what the agent wrote);
  removing the outline of an embedded document (it is the trust boundary
  between the page's controls and agent-built content); renaming the sections
  (the owner's own vocabulary); a text grey lighter than 4.5:1.
  After the builder's blind comparison with the live page (the candidate was
  preferred, slightly; the live page was judged the better phone design), four
  faults were fixed without another critic: ask titles are shown whole in the
  list, a choice's tag sits under its text, the answer and note fields have a
  full outline, and the line under a title wraps at phone width. Table cells
  no longer hyphenate; columns have minimum widths instead. A second
  comparison found two more, both against owner requests, and they were fixed
  the same way: wide content on report and delivery pages spans the 1120 px
  page instead of the main column, and at phone width the age moved under the
  title so that titles use the full row.
  Open: critics disagree on the rail (the fourth asked for measures as rows,
  the fifth called the rows a wall of grey) and on the answer form (ruled
  line and dividers against a filled field); the report below its opening has
  full-width section rules over 640 px text; the embedded-address view is
  titled with a raw path; agent text repeats itself and prints raw addresses,
  which publishing guidance, not styling, would fix; and the page has no
  drawn signature of its own, which every critic from the third on noted.
- 2026-11-22: The page becomes a host for what agents build. The owner asked
  that reports be interactive when appropriate, that the page not limit what
  agents code or generate, and that links not open new pages. (1) Agent
  content runs in a sandboxed frame with an opaque origin (`allow-scripts
  allow-forms allow-modals allow-popups allow-downloads`, never
  `allow-same-origin`), and a retained document is served only with a
  `Content-Security-Policy` `sandbox` directive, because the tailnet origin is
  shared with Ribbon Field and a script with that origin could act as the
  owner there. Nothing else about the content is restricted. (2) An
  application on the host is framed directly at its own address and not
  proxied: a proxy would make the Status service a relay to local ports and
  still could not rewrite the absolute paths an application uses. Embeddable
  applications must therefore tolerate an opaque origin. (3) A document
  reaches the page only through a message bridge whose every message the page
  validates; it may propose a response but never record one, which takes the
  owner's Confirm in the page's own response panel. What a document saves is
  its own state, not an approval. (4) Deliveries have versions, published
  under a stable key or as a replacement; responses stay attached to the
  series and name the version they were given on, and a newer version makes
  the row unread again. (5) Everything on this host opens in the same tab with
  a way back; only another website opens a new tab.
- 2026-11-22: Replace the monochrome engineering-sheet contract with this
  review-page contract. The owner found the sheet "too minimalist and
  limiting" and asked for an opinionated design with clear visual priority,
  status colour used sparingly, real action controls, and phone readability.
  Colour now carries state; type is system sans-serif; dark theme follows the
  system. Linear Inbox and Things are the reference applications, as defaults
  the owner has not confirmed.
- 2026-11-22: First scoring round (design-hill-climb, two blind critics, Things
  and Linear Inbox as references) found faint metadata, up to seven metadata
  items per row, a column of twelve "Dismiss" labels, three page widths, and
  the attention colour carrying three meanings. Changes: metadata ink raised to
  4.5:1, three metadata items at most with the age right-aligned, row actions
  shown on hover or focus only, one 800 px column, "asks open" in ink instead
  of the attention colour, the assessment ahead of notices, finished actions
  quieted, and one date format.
- 2026-11-22: Asks are read in full and answered in place. A row leads with one
  line and opens to the whole question; text is never cut without a way to read
  it. Resolutions go from the page's script to Ribbon Field's browser interface
  on the shared tailnet origin, authenticated by the browser's Ribbon Field
  pairing, so Ribbon Field stays the only store. This supersedes "link to
  Ribbon Field" for asks; unpaired browsers and the local address still link.
- 2026-11-22: Second scoring round. Changes: at phone width the age moves into
  the metadata line so titles span the row; operation summaries clamp to one
  line and ask reasons to three; report provenance is source and time only,
  with the year and timezone stated once in the header and "Stale" as a single
  word; links and attachments form one list after a delivery's write-up.
  A third round was not run: the second gain (+0.15) was at the critics' noise
  level. Open for the owner: a "Mark all read" control for operations at phone
  width, and whether metric provenance belongs in the tile or under Sources.
  Declined: clamping a metric's detail text, grouping next actions by owner
  (owners are free text), and hiding a delivery document's opening paragraph,
  because each would hide or reinterpret content the agent wrote.
- 2026-11-22: Reports become versions of living operations. Identity is an
  explicit operation key, else workspace with agent name, else workspace with
  conversation, else workspace with title, so the 34 earlier snapshots group
  without rewriting them. Unread means a version newer than the last one
  opened. Dismissal applies to the latest version and lapses when a new version
  arrives, which preserves the earlier per-report dismissal records.
- 2026-11-22: Add proactive deliveries as a second item type with recorded
  responses (read, accepted, dismissed, discussed), each with its time. A
  delivery retains its Markdown document and text attachments so it is readable
  from a phone, where the Mac's file paths do not exist.
- 2026-11-22: Asks are read from Ribbon Field's command-line listing on demand
  and never stored. Ribbon Field offers no authenticated path for another page
  to resolve an ask, so each ask links to its thread. When the listing is
  unavailable the page states the reason.
- 2026-11-22: Remove the response editor from list rows; responses are edited
  in the report itself. Remove eyebrow labels, section reference numerals, the
  ruled title block, and the custom filter menus of the earlier collection.
- 2026-11-22: The service accepts one configured public address (a Tailscale
  serve path) besides loopback. Pages use a path prefix chosen from the request
  host, and writes accept that origin with the page token.
- 2026-11-22: Record content-free usage events (page opens, item opens,
  responses) to compare this page with Ribbon Field's overview.
- 2026-11-22: Put editing and saving inside the open report. Portable files use
  access restricted to their own report to reach the local answer store.
- 2026-11-21: Add report-specific response fields and durable user answers.
  Make save state explicit and detect competing edits before replacing answers.
- 2026-10-30: Keep the shared collection independent of Ribbon Field and owned
  by the status skill. Retained reports and reversible dismissal remain
  available regardless of the generating agent or workspace.
- 2026-10-29: Markdown profiles customize expected coverage; agents must add
  material findings beyond configured fields. Generated artifacts are offline
  snapshots with source observation times. (The system-drawings visual language
  adopted on this date was superseded on 2026-11-22.)
