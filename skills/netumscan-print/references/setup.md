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
