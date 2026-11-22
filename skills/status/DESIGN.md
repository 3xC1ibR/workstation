---
name: Status review page
colors:
  primary: "#2c50c8"        # --accent: unread marker, links, the one primary action
  bg: "#f6f5f1"             # --canvas
  surface: "#ffffff"        # --surface: lists and report sheets
  surface-quiet: "#efede8"  # --surface-quiet: hover, table headings, response panel
  fg: "#1b1b1f"             # --ink
  fg-muted: "#5c5c66"       # --ink-secondary
  fg-faint: "#6a6a73"       # --ink-tertiary: row metadata, at least 4.5:1 on every surface
  border: "#e3e1da"         # --rule
  border-strong: "#c9c6bd"  # --rule-strong: control outlines
  danger: "#b3261e"         # --critical: blocking asks, failures
  warning: "#a14a04"        # --attention: notices, stale or overdue, earlier version
  success: "#17693f"        # --positive: accepted
typography:
  title:   { fontFamily: system-ui, fontSize: 28px, fontWeight: 680, lineHeight: 1.3 }
  heading: { fontFamily: system-ui, fontSize: 19px, fontWeight: 600, lineHeight: 1.3 }
  lead:    { fontFamily: system-ui, fontSize: 18px, lineHeight: 1.5 }
  reading: { fontFamily: system-ui, fontSize: 16px, lineHeight: 1.62 }
  body:    { fontFamily: system-ui, fontSize: 15px, lineHeight: 1.5 }
  meta:    { fontFamily: system-ui, fontSize: 13px, lineHeight: 1.5 }
  value:   { fontFamily: system-ui, fontSize: 22px, fontWeight: 600, lineHeight: 1.3 }
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
often on a phone, to decide what to read, act on, or dismiss.

Feeling: a calm triage list. Posture: transient. It must read at a glance, so
chrome is minimal and every row leads with what the item is. Light and dark
themes follow the system. Reference applications, recorded as defaults the
owner has not yet confirmed: **Linear Inbox** for triage and **Things** for calm
lists.

## Colors

Colour carries state, never decoration. Most of every screen is ink on paper.

- **Accent** marks unread items, links, and the single primary action of a view.
- **Critical** marks a blocking ask and a failed request. Nothing else is red.
- **Attention** marks report notices, stale or overdue asks, stale observations,
  and the notice shown on an earlier version.
- **Positive** marks an accepted delivery. Dismissed is neutral, not red.
- A tint appears only behind the text whose state it marks.

## Typography

System sans-serif for everything; monospace only for code and file paths.
Numbers use tabular figures. Titles are the strongest element of a row;
metadata is one quiet style in every state. Unread raises the title's weight and
shows the marker; it never dims the rest. No uppercase tracked labels above
headings, and no reference numerals on sections.

## Layout

A single centred column of 800 px on every page, so edges do not move between
the list, a delivery, and a report. Spacing uses the 4 px scale. A row is a
marker column, the content, and its age at the right; at phone width the age
ends the metadata line instead. Row metadata holds at most three items: a
state word, a kind or category, and an origin. Delivery summaries clamp to two
lines, operation summaries to one, ask reasons to three. Row actions appear
over the age on hover or keyboard focus; a touch user responds on the item's
own page, where controls reach 44 px. Reading text is limited to about 70
characters. Wide tables scroll inside a labelled, focusable region, keep their
first column while scrolling at phone width, and announce that they scroll.

## Elevation & Depth

Flat. Layers, bottom to top: canvas; surfaces (lists, sheets); menus (version
history, response choices); one transient notice. No shadows; a one-pixel rule
separates a surface from the canvas.

## Shapes

Containers 10 px, controls 8 px, small insets 4 px. One-pixel rules. The unread
marker is an 8 px disc. Chevrons are drawn with two borders; there is no icon set.

## Components

| Component | Variants | Use for | Do not use for |
|---|---|---|---|
| Row | unread, read, blocking, waiting, closed | One operation, delivery, or ask in a list | Anything with more than two actions |
| Button | standard, primary, quiet | Primary: the one affirmative response on a delivery page. Quiet: dismiss, restore, undo, add a note | A primary button on every list row |
| Segmented control | - | Open / Done / All | Navigation between pages |
| Report sheet | portable, served | A status report and a delivery's detail | Lists |
| Notice | attention | Material exceptions inside a report | Routine information |
| Response panel | awaiting, accepted, dismissed | The owner's response to a delivery | Report response fields (those use the response editor) |
| Response editor | - | Agent-defined questions inside a report | Delivery responses |
| Version history | - | Earlier versions of an operation report | Anything else |
| Transient notice | with Undo | Confirming a change that removed a row from view | States the page already shows |

## Do's and Don'ts

- Never use eyebrow labels: no small uppercase or tracked label above a heading
  or value.
- One primary button per view, at most. List rows use standard and quiet buttons.
- Every reversible action offers Undo or Reopen instead of a confirmation.
- Omit an empty section. Say plainly when a source is unavailable; never show
  an unavailable source as an empty list.
- No gradients, shadows, glass effects, decorative icons, entrance animation, or
  cards inside cards.
- Do not copy Ribbon Field asks or answers into this store. Resolve them through
  Ribbon Field's own interface from the page; link to Ribbon Field when that is
  unavailable.
- Never truncate text without a way to read all of it: in place for asks, on the
  item's page for deliveries and operations.
- Material findings in a report are never collapsed. Only background detail may
  start collapsed, and print expands it.

## Conceptual model

### Objects

| Object | Key attributes | Actions | Appears in |
|---|---|---|---|
| Operation | title, latest summary, origin, version count, unread, open asks | open, dismiss until next version, restore | Review list, report page |
| Report version | observations, notices, metrics, actions, sections, response fields | read, answer response fields, open another version | Report page |
| Delivery | title, summary, recommended default, decision, links, document, attachments, category, agent | read, do it (default or an option), dismiss with a reason, discuss in Ribbon Field, reopen | Review list, delivery page |
| Ask (owned by Ribbon Field) | kind, title, full question, choices, blocking, what it unblocks, thread | read in full, resolve by kind with a note, snooze, dismiss, open the thread | Review list, report page of its operation |

### Lexicon

| Term | Means | Never call it |
|---|---|---|
| Operation | A long-running effort with one living report | campaign, project report |
| Version | One retained report of an operation | snapshot, copy |
| Delivery | Finished unrequested work handed to the owner | suggestion, notification |
| Ask | Something an agent needs from the owner, kept in Ribbon Field | decision, question, task |
| Dismiss | Remove from Open without acting | archive, delete |
| Do it | Accept the recommended default or a listed option | approve, submit |

## Motion

Only a 120 ms colour transition on controls. Nothing moves on load.

## States

- **Empty:** one heading and one sentence saying what will appear here.
- **Loading:** the counts line says "Loading…"; lists stay empty.
- **Failure:** a critical-tinted message above the lists; unsaved input stays.
- **Source unavailable:** "Asks unavailable" in the attention colour, with the
  reason, directly under the header and in the counts line.
- **Earlier version:** an attention notice with a link to the latest version.

## Signature details

1. The accent disc in the left margin is the only unread signal.
2. A delivery row leads its second line with "Recommended:" so the default is
   readable without opening the item.
3. Report sheets open with the assessment in lead type; notices follow it, and
   both precede any metric.
4. Rows are fully clickable; row actions sit above that target and stay hidden
   until hover or focus, so the resting list is titles, summaries, and ages.

## Decision record

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
