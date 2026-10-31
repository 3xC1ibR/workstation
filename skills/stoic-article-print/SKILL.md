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

**Use the layout for the loaded paper.** On 2026-10-30 Ronnie reported that rolled output curls into itself and requested sideways scroll reading. They approved the physical three-column test and selected **9 pt** article text. With rolled stock, lay out successive upright reading columns along the roll's length, so it can be unrolled left to right and kept whole. Use `phomemo-print` for physical custom-media dimensions. Reflow source text and figures into the scroll's reading height rather than shrinking whole portrait pages. A single line extending for the article's entire length is not the intended layout.

On 2026-10-31 Ronnie confirmed 8.5 x 11 inch sheets and approved the physical portrait test's margins. The test used 9 pt text; Ronnie then corrected the requested sheet body text size to **8 pt**. Use normal portrait pages and continuous multi-page feeding for sheets, with 8 pt article text and about 11 pt leading. The 8 pt revision is prepared but has not been physically tested. Confirm the loaded stock when changing media. The normal-page defaults below apply to sheets; rolled scrolls retain 9 pt text. Custom roll limits and the approved first scroll test are documented in `phomemo-print/references/scroll_test.md`.

For **normal page printing**, inspect an existing source PDF before rebuilding it. Measure its actual body type size, page dimensions, printable bounds, and figure readability. If it already meets the user's reading preference and fits the loaded media, preserve that layout when reflow would add pages or damage figures. The first article trial found that the government-services paper's original Letter PDF already uses 10 pt body text and 17 pages; its reflowed draft grew to 24 pages. Publisher margins can be retained for such an existing edition. That 17-page job was canceled after 8 reported pages; do not resume it without a new request. See [the first article record](references/first_article.md).

Use these starting parameters, then adjust from the physical calibration result:

| Property | Starting layout |
| --- | --- |
| Page | Portrait Letter 215.9 x 279.4 mm, or A4 210 x 297 mm to match loaded media |
| Margins | 10 mm left/right; 12 mm top/bottom |
| Available width | 195.9 mm on Letter; 190 mm on A4 |
| Body | 8 pt, approximately 11 pt leading; choose columns for comfortable line lengths |
| Color | Black text on white; figures converted thoughtfully for monochrome thermal output |
| Graphics | Sharp at the printer's 300 dpi, readable labels, distinguishable line styles |
| Delivery | One-sided; logical pages rather than an untested article-length custom sheet |

Ronnie initially selected 10 pt after the physical calibration on 2026-10-30, then requested 9 pt for the article after approving the sideways scroll. The Letter sheet test on 2026-10-31 used 9 pt in two columns with an 8 mm gap; Ronnie approved its margins and subsequently selected 8 pt. See `phomemo-print/references/setup.md` for the physical test record. The approved scroll uses the revised 10/12 mm margins with a 4 mm content inset. For normal article pages, no visible border is required. The photograph suggests that mid-gray shades may reproduce quite dark, so inspect essential figure distinctions carefully.

Keep prose lines comfortable to follow. At 8 pt, full-width sheet lines can become long; use two columns with an approximately 8 mm gap when that improves a prose article, allowing wide figures or tables to span the page. Preserve reading order and the selected size for the loaded stock rather than reducing type to fit dense content.

Extract semantic article content, not screenshots of the webpage. Remove navigation, ads, promotions, cookie banners, and comments unless requested. Preserve original wording, headings, essential images and captions, tables, code, footnotes, and references. Include title, author, publication date when available, and source URL.

Reflow wide tables and code at the content level; split tables or wrap code without changing meaning. Prefer readable text to shrinking a whole source PDF. Preserve correct reading order when converting a two-column paper to one column. For figures, avoid pale labels, dense gray backgrounds, and color-only distinctions. Use black lines, dashes, patterns, and explicit labels where conversion would otherwise lose meaning; preserve scientific values and explain any material editorial change.

Use actual fonts and rendered page widths to check fit. Keep headings with their following paragraph, avoid orphaned lines, and add unobtrusive article/page identifiers. Avoid a large cover or contents page for a single short article. Do not assume a roll has unlimited capacity: report page count and estimated paper length (`pages x page length`) before an article batch. The purchased bundle's “23 pieces” is not a measured remaining-paper count.

## Build and print a complete scroll

`scripts/create_article_scroll.py` accepts a **complete cleaned article element** with local image assets. It retains original wording, uses embedded fonts, 9 pt text with 12 pt leading, reading columns about 90.7 mm wide, and wider panels for tables and wide figures. It does not fetch articles or establish reproduction permission. Install `requirements.txt` into the existing Phomemo runtime environment if needed.

```sh
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/stoic-article-print/scripts/create_article_scroll.py /absolute/path/cleaned_article.html /absolute/path/new_runtime_edition --title 'Article title' --author 'Author names' --date 'Publication date' --source-url https://example.com/article --license 'Applicable license' --license-url https://example.com/license --font-size 9
```

The output directory must be empty. The builder creates `article_scroll.pdf` for review, individual `article_scroll_section_NN.pdf` files for printing, and a manifest with exact custom dimensions, source checksum, tables, figures, column count, and total paper length. Each section stays within the driver's custom-length limit. The combined review PDF can contain different page lengths; **print individual section files with their manifest lengths**, rather than forcing the combined file to one common media size.

Validate text completeness against the cleaned source, inspect every reading column and wide panel, and preflight every section through `phomemo-print`. For an authorized full-article print, submit sections in order, retaining a separate receipt for each. Wait for a section's successful terminal state before starting the next; stop on cancellation, error, or missing paper. Keep the paper uncut between sections. Small leading/trailing margins at driver section boundaries are expected; do not describe an article-length scroll beyond the driver limit as a single custom page.

The first full 9 pt scroll edition is recorded in [the scroll article record](references/scroll_article.md).

## Verify before submission

Save a source manifest with exact URLs, retrieval times, inclusion/exclusion reasons, source endings, figure/table inventory, output page ranges, total pages, media dimensions, and PDF checksum. Store source copies, PDFs, manifests, renders, and receipts outside the skill repository, for example `~/.local/state/phomemo-printer/article_editions/`.

Compare extracted article text against the final PDF and check the beginning, ending, figure captions, tables, and footnotes. Render and inspect every page for clipping, missing glyphs, omitted content, unreadable figures, bad breaks, and excessive blank space. Keep text selectable and fonts embedded. A successful extraction or matching page count alone is insufficient.

Present the edition and included/excluded sources when review is requested. If printing is authorized, preflight and submit through `phomemo-print`, retaining its exact job receipt. Start a new layout with one representative page only when that calibration print is authorized; do not send a second job as an automatic retry.

## Record the actual result

Track prepared, submitted, completed-in-CUPS, physically-confirmed, and failed results separately in the runtime manifest. A completed queue entry is not proof of readable paper output. Do not mark a failed or uncertain job as printed.

If the user authorizes recording print status in Stoic, read the current bookmarks again and append a separate paragraph beginning `#printed` to the existing `note`, including the edition/date and actual outcome. Check for an existing equivalent marker first. Use the current documented `PATCH /api/bookmarks/{id}` contract with only `note`; preserve all old text, titles, read state, and archive state. Do not describe a hashtag in notes as a native bookmark tag. Re-read to verify the change and refresh assistant context afterward.

Do not create a recurring print job, assistant schedule, or new program unless requested. A future recurring workflow can use the live assistant-job or program API once the user has chosen its trigger, selection policy, and print authorization.
