---
name: netumscan-print
description: Print experimental status strips, text, and monochrome graphics on Ronnie's NetumScan NS8360L 80 mm thermal roll printer over USB on macOS, with hardware status checks and saved job records. Use phomemo-print for the full-width Phomemo printer.
---

# NetumScan experimental roll printing

The NS8360L is physically verified over USB on this Mac. Use the native USB helper, not a CUPS queue. Its serial is `83600000000`, USB vendor/product `0416:5011`, interface 0, bulk OUT `01` and IN `81`. The printer reports `POS80 Printer USB`.

```sh
~/.local/bin/netumscan-print --status
~/.local/bin/netumscan-print --text 'Receipt text'
~/.local/bin/netumscan-print --file /absolute/path/receipt.txt
~/.local/bin/netumscan-print --image /absolute/path/status_strip.png
```

Text, file, and image commands prepare and preview only. For a user-authorized physical print, add `--submit`. Each submission prints one copy, feeds to the cutter, and requests one partial cut. `--test` prepares a short calibration strip; it also needs `--submit` to print. Ronnie intends this printer for experimental artifacts, not sales receipts.

Text mode wraps at 48 columns in the 12 x 24 dot font, converts common typographic punctuation, and encodes CP437. Unsupported characters, embedded control commands, empty text, and prints exceeding 120 lines are rejected.

Image mode accepts one PNG up to **576 x 4096 pixels by default**, printed at one pixel per hardware dot (8 dots/mm, 203.2 dpi). For a longer authorized print, `--maximum-length-mm N` explicitly raises or lowers the length bound, up to 2048 mm / 16384 rows. The roll is 80 mm nominal; its documented printable width is 72 mm. Prepare artwork at the intended size instead of shrinking an ordinary page. A 24-pixel font is about 8.5 pt on paper. Composite transparency on white; the helper converts to black and white without dithering, pads to complete bytes, and sends 128-row `GS v 0` raster bands. It saves the exact monochrome `preview.png`; inspect it before submission. PDF and arbitrary Unicode text require rendering into a correctly sized PNG first.

Ronnie confirmed the first 72 x 344 mm raster status strip was **clear and readable**. Its body used 24-pixel Monaco (~8.5 pt), section headings 32 pixels (~11.3 pt), and title 46 pixels (~16.3 pt). These are verified starting sizes, not a fixed preference for every artifact. Raster rendering can use installed fonts and supported Unicode glyphs, mix sizes and styles, rotate or mirror the whole layout, and place text and diagrams freely. Font size in dots is approximately points x 203.2 / 72. The 4096-row limit is a helper bound, not an established hardware maximum roll length. Native text additionally supports documented 12 x 24 / 9 x 17 dot fonts, 1-8x independent width/height scaling, and 90-degree rotation; those variants have not been physically calibrated here.

For **sideways article scrolls**, retain the Phomemo reading model: hold the strip lengthwise, read each upright column top to bottom, then continue to the right. Reflow the text for the 72 mm reading height; do not shrink a whole Letter page. Render a horizontal reading canvas, then rotate it 90 degrees clockwise into the physical 576-dot-wide feed image. The first trial used the first two source pages of *Self-Reliance*, **7.5 pt** Vera Sans with 10 pt leading, 90 mm columns and 6 mm gaps, for 15 columns on one 1442 mm strip. Ronnie called this physical result **perfect**, approving the reading size and scroll layout. Use it as the verified NetumScan article starting layout; do not overwrite the Phomemo's separate preferences. Exact source, runtime generator, text audits, and print record are in [the setup record](references/setup.md).

Ronnie purchased nominal **3 1/8 inch x 230 foot rolls**. A full roll is 70.104 m. The verified 2634-word sample uses 1.442 m of content (about 2.06% of a full roll, plus feed/cut allowance), equivalent to two dense 8 pt source pages or approximately five conventional 11-12 pt, single-column Letter pages. For similar prose at the approved settings, estimate about **0.55 m per 1000 words**; actual headers, figures, and paragraph structure change this. Paper cost is total pack cost / roll count x printed metres / 70.104. The user's actual pack price and roll count are not yet known; do not present example prices as their purchase cost.

The helper saves `preview.txt`, `payload.escpos`, and `receipt.json` under `~/.local/state/netumscan-printer/jobs/` before sending print data. An explicit `--output-directory` must name a new directory. It checks live printer status and serial identity, and does not retry an uncertain transfer. Inspect the existing record and physical output before deciding on another submission. A completed USB transfer and healthy status do not prove marks appeared on paper.

Blank output occurred during setup even though USB status was healthy; Ronnie found a jammed roll. After clearing it, a later test printed successfully. Check for a jam, correct loading, and the thermal side before changing software or printing repeatedly. Scratching loose thermal paper darkens its coated side. The manufacturer loading diagram shows paper unwinding underneath the roll. Keep the coated side against the print head. Cutter action and the complete 48-column width have not been separately confirmed by the user.

The command uses an isolated Python environment and Homebrew libusb. If missing, restore them using [the setup record](references/setup.md). Keep generated state outside the skill repository. Do not install the archived Intel-only vendor package or assume ordinary macOS application print dialogs are configured; this setup is for the receipt helper.
