"""Advisory checks of a report against the briefing guidance (references/briefing.md).

The checks never block a build. They print what a reader catching up on several
operations would trip over, so the author can fix it before publishing.
"""
from __future__ import annotations

import re

SUMMARY_WORDS = 60
TEXT_WORDS = 120
CLOCK = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b\d{1,2}\s?(?:AM|PM|am|pm)\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b")
IDENTIFIER = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b")
FRACTION = re.compile(r"\d[\d,.]*\s*(?:/|of)\s*\$?\d")


def words(text):
    return len(text.split())


def check(document, *, operation=False):
    """Return advice as a list of sentences; an empty list means nothing to flag."""
    advice = []
    summary = document["summary"]
    if words(summary) > SUMMARY_WORDS:
        advice.append(f"summary has {words(summary)} words; keep it to {SUMMARY_WORDS} or fewer: where things stand, in one or two "
                      "sentences. Move the rest into blocks.")
    if "state" not in document:
        advice.append("no state: add state.level (on_track, at_risk, off_track, blocked, paused, done) and a short label so the "
                      "review list shows how the operation stands.")
    texts = [("summary", summary)] + [(f"notice '{n['title']}'", n["text"]) for n in document.get("notices", [])] + \
            [(f"section '{s['title']}'", s.get("text", "")) for s in document.get("sections", [])]
    for where, text in texts[1:]:
        if words(text) > TEXT_WORDS:
            advice.append(f"{where} has {words(text)} words of prose; turn lists into needs_you, workstreams, a table, or a "
                          "timeline, and keep prose for interpretation.")
    times = sum(len(CLOCK.findall(text)) for _, text in texts)
    if times >= 3 and not document.get("timeline"):
        advice.append(f"prose mentions {times} dates or clock times but there is no timeline; put dated events and scheduled "
                      "checks in timeline.")
    if any(label in (n["title"].lower()) for n in document.get("notices", []) for label in ("needs you", "for you", "your list")) \
            and not document.get("needs_you"):
        advice.append("a notice lists what the reader must do; move each item into needs_you with its effort and deadline.")
    identifiers = sorted({match for _, text in texts for match in IDENTIFIER.findall(text)})
    if identifiers:
        advice.append(f"prose contains raw identifiers ({', '.join(identifiers[:4])}{'…' if len(identifiers) > 4 else ''}); name "
                      "the thing instead and put identifiers in sources or a link.")
    for metric in document.get("metrics", []):
        if isinstance(metric.get("value"), str) and FRACTION.search(metric["value"]) and "target" not in metric:
            advice.append(f"metric '{metric['label']}' reads as progress toward a target; add current and target numbers to draw "
                          "its bar and its trend across versions.")
    for section in document.get("sections", []):
        columns = section.get("columns") or []
        lowered = [column.lower() for column in columns]
        if columns and any(word in lowered for word in ("state", "status")) and any(word in lowered for word in ("owner", "agent", "lane")):
            advice.append(f"section '{section['title']}' is a table of lanes with owners and states; use workstreams so each "
                          "state is marked.")
    if operation and not document.get("changes"):
        advice.append("no changes: say what moved since the last version, so a returning reader starts there.")
    if not document.get("needs_you") and not document.get("actions"):
        advice.append("neither needs_you nor actions: state what happens next and who does it, or say plainly that nothing is "
                      "needed from the reader.")
    return advice
