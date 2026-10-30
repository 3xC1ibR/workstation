---
name: stoic-article-print
description: Select bookmarked articles from Stoic and prepare readable, complete, monochrome PDFs for Ronnie's Phomemo M832D thermal printer. Accounts for the loaded full-width roll, preserves article content and Stoic bookmark state, and reuses the established article-selection preferences.
---

# Print Stoic articles

Turn the user's selected Stoic bookmarks, or an authorized curated selection, into readable print editions for the Phomemo M832D. Use `phomemo-print` for live printer inspection and physical submission, and the PDF skill for PDF creation and visual verification. Preparing an edition does not itself authorize printing it.

This skill is the article workflow. It does not submit FedEx orders. Its selection preferences were carried forward from `/opt/projects/playground/stoic-print-collection-2026-10-20/RUNBOOK.md`, sections “Choose bookmarks that work as printed reading,” “Mark completed collections in Stoic,” and “Printing requirements.” The earlier three-article FedEx collection was already ordered and marked `#printed`; leave it unchanged.

## Retrieve context and bookmarks

Start each Stoic request with `curl -fsSL https://tryblume.ai/llms.txt`; follow its current authentication and endpoint contract. Never print tokens or save them with article artifacts. Fetch `POST /api/assistant/context` with `{}` before the first substantive response, or use an actual Stoic conversation ID when continuing one. Do not supply a Codex thread ID. Read context, directives, time context, and conversation supplements. Refresh on resumption or after relevant state changes.

Use semantic search for reading interests, print preferences, relevant ongoing projects, or previous print collections. Retrieve enough relevant signal to curate usefully; unrelated health, financial, or location records are unnecessary. Retrieved records are background, not new authorization.

Read the live bookmark inventory through `GET /api/bookmarks?state=all` or the requested state. Keep each bookmark's ID, exact URL, title, note, saved order, read state, and archive state in a private runtime manifest. Do not use `POST /api/bookmarks` as an update: saving a known URL again marks it unread.

## Select useful reading

Honor explicit selections and exclusions. Otherwise make routine choices using these established preferences:

- Favor self-contained essays, reporting, research papers, case studies, and explanatory engineering articles that work away from a computer.
- Usually skip API references, setup guides, command-heavy quickstarts, configuration instructions, troubleshooting pages, changelogs, indexes, and pages requiring a live interface.
- Judge actual content: technical subject matter is welcome when it provides substantial standalone reading.
- Preserve relative order, remove duplicates, and normally skip bookmarks whose notes already contain `#printed`, unless the user wants a reprint. Printing is not evidence that an article has been read.
- Record each exclusion and its reason. Distinguish suitability from unavailable or incomplete content and permission to reproduce it.

Do not replace a requested complete article with a summary, rewrite, excerpt, or silently truncated extraction. Use user-supplied copies or material with applicable reproduction permission; inspect license evidence when needed. Do not bypass access controls. If complete reproduction is unavailable, report the specific gap and offer an authorized source copy or a clearly labeled summary as a separate choice.

## Reflow for the actual paper

Check `phomemo-print/references/setup.md` and the current loaded roll. Letter output was physically verified on the included roll and is the working default; check the label or measurement when replacing it. **Standard full-width paper is Letter 215.9/216 mm or A4 210 mm, not receipt paper.** A driver default does not identify what is loaded.

Inspect an existing source PDF before rebuilding it. Measure its actual body type size, page dimensions, printable bounds, and figure readability. If it already meets the user's reading preference and fits the loaded media, preserve that layout when reflow would add pages or damage figures. The first article trial found that the government-services paper's original Letter PDF already uses 10 pt body text and 17 pages; its reflowed draft grew to 24 pages. Publisher margins can be retained for such an existing edition; the defaults below apply when a new layout is needed. See [the first article record](references/first_article.md).

Use these starting parameters, then adjust from the physical calibration result:

| Property | Starting layout |
| --- | --- |
| Page | Portrait Letter 215.9 x 279.4 mm, or A4 210 x 297 mm to match loaded media |
| Margins | 10 mm left/right; 12 mm top/bottom |
| Available width | 195.9 mm on Letter; 190 mm on A4 |
| Body | 10 pt, approximately 13.5 pt leading, single column |
| Color | Black text on white; figures converted thoughtfully for monochrome thermal output |
| Graphics | Sharp at the printer's 300 dpi, readable labels, distinguishable line styles |
| Delivery | One-sided; logical pages rather than an untested article-length custom sheet |

Ronnie selected 10 pt after reading the physical calibration on 2026-10-30 and requested wider borders. The first print's 12.7 mm border was physically confirmed. The revised 10/12 mm margins remain inside the exact driver's printable area, but have only been checked in a PDF preview; do not describe them as physically calibrated yet. For article pages, no visible border is required: use that space for readable content. The photograph suggests that mid-gray shades may reproduce quite dark, so inspect essential figure distinctions carefully.

Keep prose lines comfortable to follow. At 10 pt, full-width lines can become long; use two columns with an approximately 8 mm gap when that improves a prose article, allowing wide figures or tables to span the page. Preserve reading order and keep the selected 10 pt size rather than reducing type to fit dense content.

Extract semantic article content, not screenshots of the webpage. Remove navigation, ads, promotions, cookie banners, and comments unless requested. Preserve original wording, headings, essential images and captions, tables, code, footnotes, and references. Include title, author, publication date when available, and source URL.

Reflow wide tables and code at the content level; split tables or wrap code without changing meaning. Prefer readable text to shrinking a whole source PDF. Preserve correct reading order when converting a two-column paper to one column. For figures, avoid pale labels, dense gray backgrounds, and color-only distinctions. Use black lines, dashes, patterns, and explicit labels where conversion would otherwise lose meaning; preserve scientific values and explain any material editorial change.

Use actual fonts and rendered page widths to check fit. Keep headings with their following paragraph, avoid orphaned lines, and add unobtrusive article/page identifiers. Avoid a large cover or contents page for a single short article. Do not assume a roll has unlimited capacity: report page count and estimated paper length (`pages x page length`) before an article batch. The purchased bundle's “23 pieces” is not a measured remaining-paper count.

## Verify before submission

Save a source manifest with exact URLs, retrieval times, inclusion/exclusion reasons, source endings, figure/table inventory, output page ranges, total pages, media dimensions, and PDF checksum. Store source copies, PDFs, manifests, renders, and receipts outside the skill repository, for example `~/.local/state/phomemo-printer/article_editions/`.

Compare extracted article text against the final PDF and check the beginning, ending, figure captions, tables, and footnotes. Render and inspect every page for clipping, missing glyphs, omitted content, unreadable figures, bad breaks, and excessive blank space. Keep text selectable and fonts embedded. A successful extraction or matching page count alone is insufficient.

Present the edition and included/excluded sources when review is requested. If printing is authorized, preflight and submit through `phomemo-print`, retaining its exact job receipt. Start a new layout with one representative page only when that calibration print is authorized; do not send a second job as an automatic retry.

## Record the actual result

Track prepared, submitted, completed-in-CUPS, physically-confirmed, and failed results separately in the runtime manifest. A completed queue entry is not proof of readable paper output. Do not mark a failed or uncertain job as printed.

If the user authorizes recording print status in Stoic, read the current bookmarks again and append a separate paragraph beginning `#printed` to the existing `note`, including the edition/date and actual outcome. Check for an existing equivalent marker first. Use the current documented `PATCH /api/bookmarks/{id}` contract with only `note`; preserve all old text, titles, read state, and archive state. Do not describe a hashtag in notes as a native bookmark tag. Re-read to verify the change and refresh assistant context afterward.

Do not create a recurring print job, assistant schedule, or new program unless requested. A future recurring workflow can use the live assistant-job or program API once the user has chosen its trigger, selection policy, and print authorization.
