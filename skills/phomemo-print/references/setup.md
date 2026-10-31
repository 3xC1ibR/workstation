# Phomemo M832D macOS setup

Recorded 2026-10-30, America/Chicago.

## Verified equipment and driver

- Printer purchased: Phomemo M832D Touchscreen Portable Inkless Printer, bundle described as 23 pieces / one paper roll. User's product link: https://www.amazon.com/dp/B0DTH8MQ6M .
- Mac: Apple Silicon (`arm64`), macOS 26.0.1, build 25A362.
- Manufacturer download page: https://m832d.phomemo.com/ .
- User-supplied download: `~/Downloads/QY_Printer_Driver_Mac.zip`.
- ZIP SHA-256: `4865ce6d5a46c995c7fc6aceefe15d14b34957775616cbb236dd08d89b0d2f39`.
- Package selected from the archive: `QY_Printer-2.22.0-M-Series.pkg`. The bundled README explicitly selects this package for M-series Macs and the other package for Intel Macs.
- `pkgutil --check-signature` reported a trusted Apple distribution certificate and Apple notarization. Installer signer: `ZHUHAI QUYIN TECHNOLOGY CO.,LTD.`, team `J7DJ82QB95`. Trusted timestamp: 2026-09-22 07:19:44 UTC. Recheck the current package on a reinstall; these observations do not authenticate a later download.
- Installed package receipt: `com.quin.printer.qyprinter`, version `string 2.22.0`.
- USB discovery and queue name: `M832D-Q769`.
- Model PPD: `/Library/Printers/PPDs/Contents/Resources/M832D-Q769.ppd`.
- CUPS raster filter: `/usr/libexec/cups/filter/rastertoM08F`.

## Installation used

The archive was extracted and inspected under `~/.local/state/phomemo-printer/setup/2026-10-30/`. Both package variants were signed and notarized; only the M-series variant was installed.

Installation used `/usr/sbin/installer -pkg PACKAGE -target /`, through the normal macOS administrator authentication prompt. The command returned `The install was successful.` No password was read or stored by the assistant. The installer created the USB queue. No Rosetta installation was needed.

If reinstallation is necessary, confirm the architecture, package identity, signature, and live manufacturer instructions. Open the correct package in Installer or run the same installer command with normal macOS administrator authorization. Do not disable Gatekeeper or remove quarantine to avoid an authentication or signature failure.

The installed queue was configured using:

```sh
lpadmin -p M832D-Q769 -o printer-is-shared=false -o PageSize=Letter -o Resolution=300dpi -o ColorOption=GrayScale -o zeMediaTracking=Continuous
lpoptions -p M832D-Q769 -o media=Letter -o sides=one-sided -o print-scaling=none
```

No system default printer was selected. Network printer sharing was disabled for this queue.

## Paper and printable area

**Letter output is physically verified on the included roll and is the working default.** The exact labeled roll width has not been measured. The original Letter selection was inferred from the US purchase, then validated by successful output with intact borders. Check the label when replacing the roll; do not claim a measured 216 mm width from a driver setting or photograph.

The exact installed PPD defines:

| Setting | Page size, points | Imageable area, points | Safe starting margins |
| --- | --- | --- | --- |
| Letter | 612 x 792 | x=23..589, y=30..762 | 36 points / 12.7 mm on all sides |
| A4 | 595 x 842 | x=21..574, y=30..812 | 36 points / 12.7 mm on all sides |

At the initial safe margins, the content width is 190.5 mm for Letter and about 184.6 mm for A4. After the successful physical test, Ronnie requested extending the borders. The revised layout uses 10 mm left/right and 12 mm top/bottom: content width 195.9 mm for Letter or 190 mm for A4. Both settings are inside the PPD's imageable area. These margins were preview-only at the initial calibration; the later Letter sheet test below received physical approval.

The additional fixed sizes are 110, 80, and 53 mm wide. Custom width/height support is declared up to 613 x 5700 points. A later 215.9 x 320 mm sideways-scroll test was submitted as `M832D-Q769-3`; see [the scroll test record](scroll_test.md) for its outcome. Longer article-length custom pages remain untested.

Driver defaults were A4, 300 dpi, grayscale, continuous media, printer-default darkness, zero offsets, rotation 0, and line enhancement off. Only media was changed for the first calibration; darkness and recognition values remain at vendor defaults.

The printer uses direct thermal monochrome output and one-sided pages. The initial article job demonstrated multi-page feeding on the roll but was canceled after 8 reported pages. The user found that the output curls up and wants to read rolled stock as a sideways scroll. Folded sheets are expected 2026-10-31 and should use regular pagination once loaded. Do not assume an automatic cutter or duplex printing.

## First calibration

- PDF: `~/.local/state/phomemo-printer/calibration_letter.pdf`.
- Render: `~/.local/state/phomemo-printer/calibration_letter.png`.
- Receipt: `~/.local/state/phomemo-printer/calibration_print_receipt_2026-10-30.json`.
- SHA-256: `d672365cf8b83866e5c12002e2fdfcd9cad445c02e10bf2f8fa8518643be2c0e`.
- One page, Letter portrait, body sizes 10/11/12/14 points, 100 mm scale line, contrast patches, and a border at 12.7 mm.
- Visual PDF review passed; used text fonts are embedded Bitstream Vera Sans.
- Submitted once at 2026-10-30 13:07:24 CDT. CUPS accepted job `M832D-Q769-1`.
- CUPS Get-Job-Attributes returned job-state `9` (completed), one impression, and one media sheet completed at 13:08:10 CDT. The printer returned to idle.
- Ronnie confirmed “it printed” and supplied a photograph showing all four border edges and readable text. Physical output is confirmed. The paper is curled as expected for roll media; no clipped text or missing border is visible in the photograph.
- Ronnie initially selected **10 pt** as comfortable and requested extending the borders. The initial article defaults were 10 pt body / approximately 13.5 pt leading with the revised margins above; subsequent scroll and sheet preferences supersede them.
- Revised preview: `~/.local/state/phomemo-printer/calibration_letter_revised.pdf`; not submitted. The revised generator's article sample uses the selected 10 pt size.
- Source checks: both skill frontmatter validators passed; PDF preflight passed for Letter; an A4 mismatch and reuse of the existing print receipt were refused without submitting another job. Later article and scroll trials are recorded in their respective skill references. Validation was performed by the implementing agent, with no independent review.

## Letter sheet test, 2026-10-31

- Ronnie confirmed the new sheets are **8.5 x 11 inches (Letter)**.
- Printed only page 1 of the complete *Self-Reliance* edition: portrait, two columns with an 8 mm gap, **9 pt body / 12 pt leading**, black on white, one-sided, actual size, 300 dpi.
- Outer margins: **10 mm left/right and 12 mm top/bottom**. The text and rendered pixels of the extracted test page exactly matched the reviewed full edition.
- Job `M832D-Q769-7` was submitted at 16:37:36 UTC and completed in CUPS at 16:38:20 UTC. One impression and one sheet were reported; the queue returned to idle with no jobs pending.
- Runtime directory: `~/.local/state/phomemo-printer/article_editions/2026-10-31/self_reliance_letter_9pt/`. Test PDF: `first_page_test.pdf`; receipt: `test_print_receipt.json`; SHA-256: `343bd12955efbc49a982095257db4edc79debe62d3b1aff31939ef06a257e2f2`.
- Ronnie confirmed the physical output looks great and explicitly approved the margins. Physical output and margins are confirmed for the **9 pt test**.
- Ronnie then corrected the requested sheet font size to **8 pt**. Current sheet preference is **8 pt body / about 11 pt leading**, preserving the approved margins; rolled scrolls retain 9 pt / about 12 pt leading.
- The complete 8 pt sheet revision is prepared under `~/.local/state/phomemo-printer/article_editions/2026-10-31/self_reliance_letter_8pt/`. It has **not** been physically printed or approved at that size. No additional print was authorized by the font correction.

## Primary references

- M832D specifications (300 dpi, full-width Letter/A4 plus narrower media): https://phomemo.com/products/thermal-portable-printer-m832d-upgraded-direct-touchscreen .
- Manufacturer macOS guide (USB connection): https://help.phomemo.com/portal/en/kb/articles/m832-how-to-work-with-macos .
- Manufacturer paper sizes: https://help.phomemo.com/portal/en/kb/articles/m832-supported-print-sizes-and-print-demonstration .
- The downloaded `macOS_Installation_Must Read.pdf` also specifies USB for macOS; its text was inspected from the local archive.

## Failure diagnosis

If a job remains pending or produces no marks, inspect that exact job and the live printer first. Check power, cover, roll orientation, paper selection, and a data-capable USB connection. A blank sheet can mean the thermal side is reversed; a missing USB device can mean power or cable trouble. These are hypotheses, not diagnoses without a physical observation.

The help guide's paper-sensor reset and hardware-reset procedures are separate recovery actions. Do not perform them as routine setup or substitute them for checking the current error. Consult the current manufacturer instructions if a persistent corresponding fault is confirmed.
