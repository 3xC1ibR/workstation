---
name: phomemo-print
description: Set up, inspect, and print documents on Ronnie's Phomemo M832D thermal printer from macOS over USB. Includes paper-size checks, a calibration page, and print-job receipts. Use stoic-article-print for selecting and formatting Stoic bookmarks.
---

# Phomemo printing

Use the macOS CUPS queue and the exact model driver. The installed printer was identified as `M832D-Q769`, connected over USB. Recheck live state before printing; a saved queue is not proof the printer is present.

## Inspect the printer

```sh
lpstat -t
/usr/sbin/lpinfo -v
lpoptions -p M832D-Q769 -l
```

Use USB on macOS. The manufacturer's guide reserves Bluetooth for phones and tablets. Use thermal paper, power on the printer, close the cover, and confirm paper is loaded. If setup or troubleshooting is needed, read [the setup record](references/setup.md).

The queue's base setting is **Letter**, 300 dpi, grayscale, continuous media, and one-sided output. Letter output was physically verified on the included roll. Ronnie prefers a sideways scroll layout for rolled paper because loose pages curl up; use normal portrait pagination for straight folded sheets. On 2026-10-31 Ronnie confirmed **8.5 x 11 inch sheets** and approved the margins of a 9 pt portrait test, then selected **8 pt** for sheet articles. The 8 pt revision has been prepared but not physically tested. Confirm the actual stock when changing media; the roll's exact labeled width was not measured.

- Letter: 215.9 mm wide, 279.4 mm page length; often labeled 216 mm or 8.5 inches.
- A4: 210 mm wide, 297 mm page length.
- This is a full-width portable printer. Do not format its standard roll as an 80 mm receipt.
- For a different loaded width, inspect its driver setting and reformat the document. The submission helper supports Letter, A4, and bounded custom roll dimensions.

## Rolled paper: sideways scrolls

Use a horizontal reading surface: the roll's **length runs left to right**, each reading column runs top to bottom, and subsequent columns continue to the right. Ronnie approved this orientation and selected **9 pt body text** for articles after the 10 pt test. Keep comfortable line lengths. Do not create a single article-length line or make the user tear off individual Letter pages.

The physical PDF remains narrow and long, with its width matching the roll. Rotate the **content** 90 degrees; do not use the PDF rotation flag or an additional CUPS landscape rotation. The helper explicitly requests portrait physical media. This separates the feed geometry from the reading direction.

The first scroll test uses one 215.9 x 320 mm custom page, with three reading columns and 10 pt text. Source and preview details are in [the scroll test record](references/scroll_test.md). Generate the short test with:

```sh
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/phomemo-print/scripts/create_scroll_test.py ~/.local/state/phomemo-printer/scroll_test_2026-10-30/sideways_scroll_test.pdf
```

Preflight a prepared scroll PDF with:

```sh
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/phomemo-print/scripts/print_pdf.py /absolute/path/scroll.pdf --media Roll --roll-width-mm 215.9 --roll-length-mm 320
```

For an authorized physical print, add `--submit --receipt /absolute/path/to/an/unused_runtime_receipt.json`. Set the length from the actual PDF, not from this example. Custom roll media is a per-job option; the base Letter queue remains available for folded sheets. The installed PPD limits custom media to 613 x 5700 points (about 216.25 mm wide and 2010.83 mm long). Do not submit an arbitrary article-length page past that limit. Longer scrolls require separately validated segmentation and feed behavior.

The 320 mm custom setting completed as job M832D-Q769-3, and the user approved the physical orientation. The test used 10 pt; article text was then requested at 9 pt. Longer sections still need their own preflight and completion checks.

## Prepare a PDF

Use the PDF skill when creating or editing PDFs. Preserve the requested document's content. Use the loaded paper size, black text on white, and one-sided pages. Use **8 pt article body text with about 11 pt leading for sheets**, and **9 pt with about 12 pt leading for rolled scrolls**. Ronnie selected 8 pt after approving the margins of the 9 pt Letter test; do not describe 8 pt output as physically verified yet. Sheet margins are **10 mm left/right and 12 mm top/bottom**. For scrolls these margins run across the roll and at its feed ends; the approved scroll test includes an additional 4 mm text inset inside its border. Render and inspect the PDF before printing. Already formatted documents may need reflow; do not silently shrink a wide page until the text is unreadable.

Reusable helpers use an isolated environment outside the source repository:

```sh
uv venv ~/.local/state/phomemo-printer/venv --python 3.12
uv pip install --python ~/.local/state/phomemo-printer/venv/bin/python -r /opt/projects/workstation/skills/phomemo-print/requirements.txt
```

Only create that environment when absent; otherwise reuse it. The helpers are available from this skill directory's `scripts/` folder.

```sh
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/phomemo-print/scripts/create_calibration_page.py ~/.local/state/phomemo-printer/calibration_letter.pdf --media Letter
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/phomemo-print/scripts/print_pdf.py /absolute/path/document.pdf --media Letter
```

The second command is a preflight only: it reports page count, dimensions, checksum, and the proposed command. It rejects media mismatches and cropped PDFs. Inspect page content as well; dimensions do not establish that text fits the printer's imageable area.

## Submit and verify

Printing requires the user's request to print. A request to prepare or preview a PDF does not authorize a physical print. Do not print another test or article batch solely because a queue reports completion.

Submit an authorized document with an unused receipt path outside the repository:

```sh
~/.local/state/phomemo-printer/venv/bin/python /opt/projects/workstation/skills/phomemo-print/scripts/print_pdf.py /absolute/path/document.pdf --media Letter --submit --receipt ~/.local/state/phomemo-printer/print_receipt_2026-10-30_1307.json
```

Use the actual date/time or another distinct professional name for a new job. The helper prints one copy at actual size, saves a submission record before calling `lp`, and refuses to reuse an existing receipt. It does not automatically resubmit. A second receipt is not a substitute for checking whether the first attempt succeeded.

```sh
lpstat -W not-completed -l -o M832D-Q769
lpstat -W completed -l -o M832D-Q769
lpstat -p M832D-Q769 -l
```

Distinguish **accepted by CUPS**, **completed in CUPS**, and **physically printed correctly**. An idle queue or a completed job does not prove that marks appeared on paper. Ask for the physical result when calibrating. If no output appears, inspect the saved receipt, exact job, printer status, paper feed, and connection before considering another print. Cancel only the specific unwanted job with `cancel JOB_ID`.

Keep generated PDFs, renders, receipts, driver archives, logs, and environments under `~/.local/state/phomemo-printer/` or another runtime directory outside the repository. Commit only skill source and factual setup documentation.
