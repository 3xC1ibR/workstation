# Status sheet design contract

Before any UI change, read this contract and follow the interface-design skill.

## Reference and purpose

An auxiliary engineering sheet for the user supervising an agent or campaign:
what happened, what matters now, and what happens next. Borrow the system-drawings
workspace's 1970s IBM/NASA visual language: white paper, black line work, restrained
uppercase labels, monospace values, reference numbers, and a ruled title block.
Reference: `/opt/projects/system-drawings/DESIGN.md`.

Observations are attributes and records, so tables and text carry them. Reserve
three-dimensional geometry for explanations of system structure. A profile
changes questions, scope, and ordering; it does not invent another theme.

## Objects and hierarchy

Objects: report, subject, observation, source, notice, action, section.
Actions: read, expand supporting evidence, follow a source, print.

Opening hierarchy: subject and observation context; urgent notices; assessment;
requested observations; next actions; supporting sections and sources. Arbitrary
additional sections are first-class content. Material caveats remain visible.
Only background detail may start collapsed. Omit empty notice panels.

## Tokens and components

Visual tokens live in `assets/style.css`: white paper, #111 ink, #555 secondary
text, faint gray rules, a small typography scale, shared spacing, square edges.
Titles use compact uppercase Helvetica-style lettering; other text uses system
monospace. Metrics are open ruled rows, not decorative cards. Native details
disclose evidence; semantic tables have column headers and explicit empty states.
Wide tables scroll inside a labeled, keyboard-focusable region; the page fits a
phone. Long text wraps without clipping.

Compact tables display a horizontal-scroll cue and retain the first record
column while scrolling. Descriptive columns have enough width for sentences.
Long subject identifiers use an explicit expansion control; material findings
are never automatically collapsed.

No chromatic accents, gradients, shadows, icons, oversized numbers, rounded tiles,
animation, or fixed overlays. Light paper is intentional under dark system
preferences. Focus is a black outline; disclosure controls have generous touch
areas. Print output expands evidence.

## Decision record

- 2026-10-29: Reuse system-drawings visual language. Markdown profiles customize
  expected coverage; agents must add material findings beyond configured fields.
  Generated artifacts are offline snapshots with source observation times.
- 2026-10-30: Register completed reports in Ribbon Field's shared Status inbox.
  The inbox uses that application's auxiliary-page grammar; each retained report
  preserves this monochrome sheet. Dismissal is reversible and report-specific.
