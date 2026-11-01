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

Image mode accepts one PNG up to **576 x 4096 pixels**, printed at one pixel per hardware dot (8 dots/mm, 203.2 dpi). The roll is 80 mm nominal; its documented printable width is 72 mm. Prepare artwork at the intended size instead of shrinking an ordinary page. A 24-pixel font is about 8.5 pt on paper. Composite transparency on white; the helper converts to black and white without dithering, pads to complete bytes, and sends 128-row `GS v 0` raster bands. It saves the exact monochrome `preview.png`; inspect it before submission. PDF and arbitrary Unicode text require rendering into a correctly sized PNG first.

Ronnie confirmed the first 72 x 344 mm raster status strip was **clear and readable**. Its body used 24-pixel Monaco (~8.5 pt), section headings 32 pixels (~11.3 pt), and title 46 pixels (~16.3 pt). These are verified starting sizes, not a fixed preference for every artifact. Raster rendering can use installed fonts and supported Unicode glyphs, mix sizes and styles, rotate or mirror the whole layout, and place text and diagrams freely. Font size in dots is approximately points x 203.2 / 72. The 4096-row limit is a helper bound, not an established hardware maximum roll length. Native text additionally supports documented 12 x 24 / 9 x 17 dot fonts, 1-8x independent width/height scaling, and 90-degree rotation; those variants have not been physically calibrated here.

The helper saves `preview.txt`, `payload.escpos`, and `receipt.json` under `~/.local/state/netumscan-printer/jobs/` before sending print data. An explicit `--output-directory` must name a new directory. It checks live printer status and serial identity, and does not retry an uncertain transfer. Inspect the existing record and physical output before deciding on another submission. A completed USB transfer and healthy status do not prove marks appeared on paper.

Blank output occurred during setup even though USB status was healthy; Ronnie found a jammed roll. After clearing it, a later test printed successfully. Check for a jam, correct loading, and the thermal side before changing software or printing repeatedly. Scratching loose thermal paper darkens its coated side. The manufacturer loading diagram shows paper unwinding underneath the roll. Keep the coated side against the print head. Cutter action and the complete 48-column width have not been separately confirmed by the user.

The command uses an isolated Python environment and Homebrew libusb. If missing, restore them using [the setup record](references/setup.md). Keep generated state outside the skill repository. Do not install the archived Intel-only vendor package or assume ordinary macOS application print dialogs are configured; this setup is for the receipt helper.
