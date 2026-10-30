# Sideways scroll orientation test

Requested 2026-10-30 after the first article job was canceled. The user explained that the roll curls up and is inconvenient to flatten and tear into pages. They want to hold the paper lengthwise and read it as a scroll. Straight folded sheets are expected tomorrow, 2026-10-31; ordinary page printing should be used once those are loaded.

## Geometry

- One physical custom page: 215.9 mm wide across the printer, 320 mm in the paper-feed direction.
- PDF MediaBox: 612 x 907.0866 points, PDF rotation 0.
- Content transform: translate to the leading edge, then rotate -90 degrees.
- Reading surface after turning the strip: 320 mm left to right by 215.9 mm high.
- Three numbered columns, read top to bottom within each and then left to right.
- 10 pt body text, 13.5 pt leading, 8 mm column gaps.
- Physical cross-roll margins 10 mm; leading/trailing margins 12 mm.
- One 100 mm scale line along the unrolling direction, an outer border, and explicit start/finish marks.
- Original test prose only; no article batch or previously canceled job was resumed.

## Submission

The installed `M832D-Q769` PPD advertises custom sizes up to 613 x 5700 points, with `HWMargins: 0 0 0 0`. Conservative physical margins are retained in the test despite that zero-margin declaration.

CUPS documents custom media as `Custom.WIDTHxLENGTHmm`: https://www.cups.org/doc/options.html . The submitted test uses `media=Custom.215.9x320mm`, `orientation-requested=3`, 300 dpi, grayscale, continuous media, one side, one copy, and no scaling. Its sideways reading direction is part of the PDF's content rather than a second printer rotation.

Source helper: `scripts/create_scroll_test.py`. Runtime files: `~/.local/state/phomemo-printer/scroll_test_2026-10-30/`:

- `sideways_scroll_test.pdf`: physical print PDF.
- `physical_orientation.png`: unrotated render in the printer's feed orientation.
- `reading_orientation.png`: render turned to the intended scroll-reading orientation.
- `print_receipt.json`: exact submission, checksum, job ID, and recorded result.
- `validation.json`: dimensions, content orientation, one-page check, and negative preflight checks.

The one-page PDF and reading preview passed visual review. Preflight accepted the exact custom geometry and refused an oversized 2100 mm length and a mismatched Letter request without submitting them. Physical feed length, orientation, and reading comfort still require the user's observation; record that separately from spooler completion.

Submitted once as `M832D-Q769-3` at 13:52:09 CDT. The printer returned to idle at 13:53:06 CDT; the exact CUPS terminal state is retained in the runtime receipt. No second strip has been submitted. Physical orientation is awaiting the user's response to the test.
