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

The queue is set to **Letter**, 300 dpi, grayscale, continuous media, and one-sided output. Letter output was physically verified on the included roll and remains the working default. The roll's exact labeled width was not measured; check the label when changing media. Do not infer physical width from the driver's original default, which was A4.

- Letter: 215.9 mm wide, 279.4 mm page length; often labeled 216 mm or 8.5 inches.
- A4: 210 mm wide, 297 mm page length.
- This is a full-width portable printer. Do not format its standard roll as an 80 mm receipt.
- For a different loaded width, inspect its driver setting and reformat the document. The supplied helpers deliberately support portrait Letter and A4 only.

## Prepare a PDF

Use the PDF skill when creating or editing PDFs. Preserve the requested document's content. Use the loaded paper size, black text on white, and one-sided pages. On the first physical calibration Ronnie found **10 pt comfortable** and asked to extend the borders. The revised defaults are **10 mm left/right margins and 12 mm top/bottom margins**, with 10 pt body text at about 13.5 pt leading. These remain inside the driver's declared imageable area; the original 12.7 mm border was physically verified, while the revised margins have been checked in the PDF preview only. Render and inspect the PDF before printing. Already formatted documents may need reflow; do not silently shrink a wide page until the text is unreadable.

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
