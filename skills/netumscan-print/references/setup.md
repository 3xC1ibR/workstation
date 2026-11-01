# NetumScan NS8360L setup record

Recorded 2026-10-31, America/Chicago.

## Verified configuration

- Purchased model: NetumScan NS8360L, 80 mm nominal thermal receipt printer, USB and Ethernet. Product: https://www.amazon.com/dp/B0CQJQ365Q .
- Mac: Apple Silicon arm64, macOS 26.0.1 (25A362).
- Live USB identity: `POS80 Printer USB`, manufacturer `Printer`, serial `83600000000`, vendor `0x0416`, product `0x5011`.
- Interface 0 is USB printer class 7, with 64-byte bulk endpoints OUT `0x01` and IN `0x81`.
- Homebrew `libusb 1.0.30` was already installed. Added `pyusb==1.3.1` to the isolated environment `~/.local/state/netumscan-printer/venv/`, using Python 3.12.10.
- No NetumScan CUPS queue or vendor filter was installed. The existing Phomemo queue was not changed.

Inspect live presence using:

```sh
/usr/sbin/ioreg -p IOUSB -w 0
/usr/libexec/cups/backend/usb
~/.local/bin/netumscan-print --status
```

The USB backend discovers `usb://PrinterCMD%3AESCPO/POS80%20Printer%20USB?serial=83600000000`. `system_profiler SPUSBDataType` produced no useful device listing on this Mac; IORegistry and the USB backend did identify it.

For reinstall, create the environment only when absent:

```sh
brew install libusb
uv venv ~/.local/state/netumscan-printer/venv --python 3.12
uv pip install --python ~/.local/state/netumscan-printer/venv/bin/python -r /opt/projects/workstation/skills/netumscan-print/requirements.txt
ln -s /opt/projects/workstation/skills/netumscan-print ~/.agents/skills/netumscan-print
ln -s /opt/projects/workstation/skills/netumscan-print/scripts/netumscan-print ~/.local/bin/netumscan-print
```

Inspect existing directories and symlinks before recreating them. The source launcher uses the installed skill symlink and the runtime environment; it does not rely on the interactive shell's Python packages. The full invocation is:

```sh
~/.local/state/netumscan-printer/venv/bin/python /opt/projects/workstation/skills/netumscan-print/scripts/print_receipt.py --status
```

## Driver investigation and failed queue approach

The official Netum support page explicitly lists its downloadable Mac package for NT-8330 / NT-8360L: https://support.netum.net/hc/en-us/articles/44800664000795--All-Models-Receipt-Printer-Software-Drivers .

Downloaded package: `NT-8330_NT-8360L-mac-POS1.8.pkg`, archived under `~/.local/state/netumscan-printer/setup/2026-10-31/`.

- Source: https://cdn.shopify.com/s/files/1/2144/8019/files/NT-8330_NT-8360L-mac-POS1.8.pkg .
- SHA-256: `2cc9364c2545ce94fee6ac60dfcf3522075fa138693f1444387512b9905d315a`.
- `pkgutil --check-signature`: no signature.
- Extracted `pos` filter: Mach-O x86_64. It is not a native arm64 filter.
- Its scripts copy filters into `/usr/libexec/cups/filter/`. The package was inspected, not installed.

`lpadmin -m raw` failed with `Raw queues are no longer supported on macOS.` No queue was created. The installed generic Epson drivers describe 9-pin and 24-pin printers, not this ESC/POS receipt model; they were not substituted. Direct USB required no administrator prompt, Rosetta, or driver installation.

## Protocol and print records

The manufacturer programmer manual documents status requests `DLE EOT n`, CP437 page 0, native text fonts, and `GS V 66 0` for feeding to the cutter and making a partial cut. The helper selects standard text mode, emits the wrapped text, and requests a single partial cut. It does not pulse the cash drawer, sound the buzzer, or change persistent printer configuration.

All three submissions returned status bytes `16 / 12 / 12 / 12` for printer / offline / error / paper, indicating online, closed cover, no reported error, and paper available. These status bytes did not detect the user's observed jam.

Runtime directories are under `~/.local/state/netumscan-printer/`:

1. `calibration_print_2026-10-31/`: 491-byte calibration at 2026-11-01 00:08:01 UTC. The user reported paper fed but no marks appeared. The user confirmed only one side darkens when scratched, then found a jammed roll. Reversed paper orientation was considered but was not confirmed as the cause.
2. `calibration_retry_2026-10-31/`: user-authorized 491-byte replacement at 00:09:37 UTC. USB transfer completed; this job's physical result was not separately reported.
3. `short_test_2026-10-31/`: user-authorized 136-byte test at 00:10:05 UTC. Text was `NETUMSCAN PRINT TEST`, a sentence confirming USB printing, and a 48-digit number line. SHA-256 `2c312b920df88fd2329d98030d7ab87e66768aaecc7940ad5bf14db15114a5c5`. The user confirmed “that worked!” after this submission. Visible printed text is physically verified; cutting and full-width legibility were not separately reported.

There are no queued CUPS jobs for these submissions; the direct USB transfer is immediate. USB-transfer receipts are distinct from physical print confirmation. No independent agent review was performed; validation uses actual USB responses, the user's physical result, and local negative-path checks.

## Manufacturer references

- Download index: https://netumscan.com/pages/software-drivers .
- Programmer manual: https://cdn.shopify.com/s/files/1/0591/6364/0002/files/80MM_Printer_Programmer_Manual.pdf?v=1718868030 .
- Operating manual: https://cdn.shopify.com/s/files/1/0591/6364/0002/files/80MM_Printer_Instruction_Manual.pdf?v=1718868045 . The roll-loading illustration is on PDF page 5; the built-in self-test instructions are on PDF page 3.

The built-in self-test can distinguish a physical print problem from host-command trouble: switch off, hold FEED while switching on, then release when the PAPER OUT indicator lights. Do not keep holding FEED for several seconds; the manual describes a different hexadecimal-dump mode for that sequence. A self-test is another physical print and should be requested only when needed and authorized.

## Experimental graphics, 2026-10-31

Ronnie clarified that the intended use is experimental output rather than sales receipts, and requested a paper equivalent of the `status` skill. Added `Pillow==12.0.0` and `--image` support for bounded, single-frame PNGs. Native `GS v 0` raster commands carry 128-row bands at one pixel per dot. Transparency is composited on white, dithering is disabled, and row padding stays unprinted. Images wider than 576 dots, taller than 4096 dots, or entirely blank are rejected before USB submission.

The first graphic is a four-workstream status strip, 576 x 2752 dots (72 x 344 mm of content), with 24-pixel monospace body text (about 8.5 pt), bold headings, and ruled sections. It summarizes saved Agent Coord reports for Canvas Browser, Ramble, the kernel campaign, and the printer experiment. Its older funding request is explicitly marked unverified; no live billing, judge, CI or deployment audit was performed. The full HTML was built by the unchanged status renderer, registered in the local Status inbox, and inspected at desktop and phone widths.

- Runtime report and artwork: `~/.local/state/agent-status/projects/thermal_status_2026-10-31/` (`status.json`, `status.html`, `status_strip.png`, `render_status_strip.py`, and verification screenshots).
- Status inbox report ID: `dd7fea3670e5439484a2c9f948c372ac1725f0d833e9d970e2c8679478d05ffe`.
- Submission record: `~/.local/state/netumscan-printer/status_raster_print_2026-10-31/receipt.json`.
- Sent once at 2026-11-01 00:18:48 UTC. All 198331 bytes transferred; hardware status was ready before and after. Payload SHA-256: `05043d20994f929ffc6402ee156ab44ff716fc109b51fa601588cdb646d508e5`.
- Ronnie confirmed the raster status strip was **clear and readable**. This physically verifies the graphics path and the 24-pixel (~8.5 pt) body layout. Cutter action was not separately confirmed.

Offline raster checks reconstructed an asymmetric 9 x 129 dot pattern from the emitted bands, verifying black/white polarity, white padding, row order, exact lengths, 128-row splitting, and a single final cut. Blank, overly wide, and overly long PNGs were rejected. These checks submitted no additional print.

## Two-page sideways article trial, 2026-10-31

Ronnie requested two article pages in the existing sideways scroll style and specified **7.5 pt**. Used the first two pages of the local 8 pt Letter edition of Emerson's *Self-Reliance* as the exact excerpt boundary. Its source PDF is `~/.local/state/phomemo-printer/article_editions/2026-10-31/self_reliance_letter_8pt/self_reliance.pdf`, SHA-256 `69b8642a87586621df6fe641ce1b04f7f9ab72be0cc2a6618bd1aaf9c0359040`. The article's cleaned HTML supplied paragraph boundaries, epigraph line breaks, and emphasis. Removed only the source edition's running furniture and title block, replacing them with concise scroll attribution. This is an excerpt, not the complete essay; source page 2 ends mid-sentence.

- 2634 words; 7.5 pt Bitstream Vera Sans (italics/bold retained), 10 pt leading. Fourfold supersampling before raster reduction preserves fractional font sizing.
- 15 reading columns, each 90 mm wide with a 6 mm gap, on a 72 x 1442 mm printable image (576 x 11536 dots). The reading canvas was rotated clockwise for the physical feed, matching the Phomemo's approved orientation.
- Exact non-whitespace character comparisons passed for source pages versus the HTML prefix and for the reflowed lines versus that prefix. Every column was inspected in reading order across five preview windows. Both epigraphs and all selected body text remain present.
- Artifact directory: `~/.local/state/netumscan-printer/article_scroll_7_5pt_2026-10-31/`. Contains `create_scroll.py` (run with the existing Phomemo environment), `excerpt.txt`, `manifest.json`, `reading_scroll.png`, `physical_scroll.png`, and reading-window previews.
- Added explicit `--maximum-length-mm`, capped at 2048 mm, while retaining the default 512 mm bound. Negative checks verified the unchanged default rejection and absolute ceiling, and successful preparation under an explicit longer bound.
- Submitted once using `--maximum-length-mm 1442` at 2026-11-01 00:30:21 UTC. All 831331 bytes transferred by 00:30:24 UTC; status ready before and after. Payload SHA-256 `c92fab785841ae1fe905748fdbed990dadf55f3f2d4cdf77a08ab00a58adc489`.
- Print record: `~/.local/state/netumscan-printer/article_scroll_7_5pt_print_2026-10-31/receipt.json`. One final partial-cut command; no cuts between columns. Ronnie called the physical output **perfect**, approving the 7.5 pt sideways layout. Cutting was not separately reported.

No Stoic state or Phomemo preferences were changed. No extra physical calibration strip was sent.

## Roll-paper economics

Ronnie purchased nominal 3 1/8 inch x 230 foot stock, paying $4.99 for one roll to get it quickly; cheaper options are available. The installed sample roll is much shorter and was already nearly exhausted. Treat the new stock as 70.104 m per full roll.

The 2634-word, 1442 mm trial consumes 2.057% of a nominal full roll before additional feed/cut margins. Theoretical capacity is 48.6 identical samples / 128054 words; use about 45-48 samples or 120000 words as an approximate usable allowance. Paper area is equivalent to 1.90 US Letter sheets, using the labeled 3 1/8 inch width. It matched two densely typeset 8 pt, two-column source pages. A calculated single-column Letter model (one-inch margins, Vera Sans, 6 pt paragraph gaps, title allowance) takes five pages at both 11 pt / 14 pt leading and 12 pt / 15 pt leading. The conventional page comparison is modeled, not physically printed.

For similar prose, the observed rate is about 0.547 m per 1000 words. At an illustrative $2 per roll, paper alone costs about 1.56 cents per 1000 words or 4.11 cents for the actual trial. Exclude the printer purchase, electricity, wear, tax/shipping and unusable ends from this figure. Denser typography accounts for much of the page-count difference; a normal printer can also use compact layouts and duplex printing. Do not claim the roll is always cheaper than a laser printer.

At Ronnie's actual $4.99 per roll, the trial costs about 10.26 cents in paper. Scaled prose estimates: 1000 words 3.90 cents, 2500 words 9.74 cents, 5000 words 19.48 cents, and 10000 words 38.97 cents, before feed/cut waste. These are marginal paper costs, not the total cost of printer ownership.

Calculations and page-model assumptions are saved in the trial's runtime `paper_economics.json`. No additional print was sent for this analysis.
