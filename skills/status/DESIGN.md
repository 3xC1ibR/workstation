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

Objects: report, subject, observation, source, notice, action, section, response
field, saved response.
Actions: read, expand supporting evidence, follow a source, print. The shared
collection adds filter, dismiss, and restore; dismissal applies to one report.
Agents may attach response fields to a report. The collection adds an inline
Responses disclosure with labeled controls and Save responses. Saving records
user input separately from observations; it does not execute the next action.

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

## Shared collection page

The Status collection is part of this skill and runs independently of any agent
application. It imports the same `assets/style.css` as the generated sheets.
Keep the same page width, ruled title block, typography, whitespace, square
controls, and light paper under every system theme. Collection controls use
these existing tokens; do not introduce an application theme.

Use numbered, openly ruled rows with a report title, full assessment, origin,
generation time, and a quiet Dismiss or Restore button. The title opens the
retained HTML document in a separate tab. Filters and search operate on the
collection; Undo restores the last dismissal. Empty, loading, and failed states
are plain text in the sheet. No nested report viewer or overlay is needed.

Filter menus use the sheet's paper, ink, monospace type, square corners, and
one-pixel rules even while open. Enhance the native selects with labelled
combobox/listbox controls to avoid operating-system colors and shadows. Preserve
arrow-key navigation, Home/End, type-to-select, Enter/Space, Escape cancellation,
Tab traversal, and outside-click dismissal. Options wrap on narrow screens.

## Decision record

- 2026-11-21: Add report-specific response fields and durable user answers in the
  existing collection rows. Reuse the sheet's controls and filter pickers; keep
  portable snapshots inert, make save state explicit, and preserve unsaved input
  during collection refreshes. Detect competing edits before replacing answers.
- 2026-10-29: Reuse system-drawings visual language. Markdown profiles customize
  expected coverage; agents must add material findings beyond configured fields.
  Generated artifacts are offline snapshots with source observation times.
- 2026-10-30: Keep the shared collection independent of Ribbon Field, owned by
  the status skill and styled exactly like its HTML sheets. This supersedes the
  mistaken application integration. Retained reports and reversible dismissal
  remain available regardless of the generating agent or workspace.
- 2026-10-30: Style open filter menus as part of the report sheet; native macOS
  popup styling was inconsistent with the requested monochrome design.
