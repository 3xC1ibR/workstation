---
name: netumscan-print
description: Inspect and print text receipts on Ronnie's NetumScan NS8360L 80 mm thermal printer over USB on macOS, with hardware status checks and saved print receipts. Use phomemo-print for the full-width Phomemo printer.
---

# NetumScan receipt printing

The NS8360L is physically verified over USB on this Mac. Use the native USB helper, not a CUPS queue. Its serial is `83600000000`, USB vendor/product `0416:5011`, interface 0, bulk OUT `01` and IN `81`. The printer reports `POS80 Printer USB`.

```sh
~/.local/bin/netumscan-print --status
~/.local/bin/netumscan-print --text 'Receipt text'
~/.local/bin/netumscan-print --file /absolute/path/receipt.txt
```

The last two commands prepare and preview only. For a user-authorized physical print, add `--submit`. Each submission prints one copy, feeds to the cutter, and requests one partial cut. `--test` prepares a short calibration receipt; it also needs `--submit` to print.

The helper wraps text at 48 columns in the 12 x 24 dot font. The roll is 80 mm nominal; the documented printable width is 72 mm (576 dots at 203.2 dpi). It converts common typographic punctuation and encodes CP437. Unsupported characters, embedded control commands, empty text, and receipts exceeding 120 lines are rejected. PDF, images, and arbitrary Unicode require a separate rendering workflow; do not send them as receipt text or silently discard content.

The helper saves `preview.txt`, `payload.escpos`, and `receipt.json` under `~/.local/state/netumscan-printer/jobs/` before sending print data. An explicit `--output-directory` must name a new directory. It checks live printer status and serial identity, and does not retry an uncertain transfer. Inspect the existing record and physical output before deciding on another submission. A completed USB transfer and healthy status do not prove marks appeared on paper.

Blank output occurred during setup even though USB status was healthy; Ronnie found a jammed roll. After clearing it, a later test printed successfully. Check for a jam, correct loading, and the thermal side before changing software or printing repeatedly. Scratching loose thermal paper darkens its coated side. The manufacturer loading diagram shows paper unwinding underneath the roll. Keep the coated side against the print head. Cutter action and the complete 48-column width have not been separately confirmed by the user.

The command uses an isolated Python environment and Homebrew libusb. If missing, restore them using [the setup record](references/setup.md). Keep generated state outside the skill repository. Do not install the archived Intel-only vendor package or assume ordinary macOS application print dialogs are configured; this setup is for the receipt helper.
