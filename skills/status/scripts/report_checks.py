"""Advisory checks for status reports and proactive deliveries against the decision-packet contract.

The checks never block a build or publication. They print what a busy principal
triaging several reports would trip over, so the author can fix it before
publishing.
"""
from __future__ import annotations

import re

SUMMARY_WORDS = 60
DELIVERY_SUMMARY_WORDS = 80
TEXT_WORDS = 120
CLOCK = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b\d{1,2}\s?(?:AM|PM|am|pm)\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b")
URL_PATTERN = re.compile(r"https?://\S+|agentcoord://\S+")
FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
IDENTIFIER = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    r"|\b(?:acct|cus|sub|pi|ch|evt|price|prod|si|pm|tok|sk|pk)_[A-Za-z0-9]{8,}\b"
    r"|\b(?:i|vol|sg|vpc|subnet|ami|snap|eni|igw|rtb|nat)-[0-9a-f]{8,}\b"
    r"|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b"
)
FRACTION = re.compile(r"\d[\d,.]*\s*(?:/|of)\s*\$?\d")
DECISION_VERB = re.compile(r"\b(?:choose|decide|pick|select between|whether to)\b", re.IGNORECASE)
SHELL_EATEN_DOLLAR = re.compile(r"\(\s*,|\b(?:The|the|a|an|for|at|of|to)  +[A-Za-z]")
CHAT_REPLY_RESIDUE = re.compile(r'\breply\s+["\'`\u201c]?[a-z0-9_-]{2,24}["\'`\u201d]?\s+to\b|\brespond\s+with\s+["\'`\u201c]', re.IGNORECASE)
REVERSE_DNS_LABEL = re.compile(r"\b(?:com|org|io|net)\.[a-z0-9-]+(?:\.[a-z0-9-]+)+\b")
STOPWORDS = {"a", "an", "and", "as", "at", "be", "by", "do", "for", "if", "in", "is", "it", "of", "on", "only", "or", "the", "to", "with"}


def words(text):
    return len(text.split())


def _plain(text):
    return URL_PATTERN.sub(" ", FENCED_CODE.sub(" ", text or ""))


def _significant_tokens(text):
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {token for token in tokens if len(token) > 1 and token not in STOPWORDS}


def _near_duplicate(first, second):
    left, right = _significant_tokens(first), _significant_tokens(second)
    if not left or not right:
        return False
    smaller = min(len(left), len(right))
    if smaller < 3:
        return left == right
    return len(left & right) / smaller >= 0.75


def _report_text_fields(document):
    fields = [("summary", document["summary"])]
    fields.extend((f"notice '{n['title']}'", n["text"]) for n in document.get("notices", []))
    fields.extend((f"section '{s['title']}'", s.get("text", "")) for s in document.get("sections", []))
    fields.extend((f"change {i + 1}", c["text"]) for i, c in enumerate(document.get("changes", [])))
    for i, item in enumerate(document.get("needs_you", [])):
        fields.append((f"needs_you[{i}]", " ".join(item.get(k, "") for k in ("action", "unblocks"))))
    for i, item in enumerate(document.get("decisions", [])):
        parts = [item.get(k, "") for k in ("question", "recommendation", "why", "if_wrong", "unblocks")]
        parts.extend(item.get("assumptions", []))
        for opt in item.get("options", []):
            parts.extend(opt.get(k, "") for k in ("label", "summary", "upside", "downside"))
        fields.append((f"decisions[{i}]", " ".join(parts)))
    for i, lane in enumerate(document.get("workstreams", [])):
        fields.append((f"workstream '{lane['name']}'", " ".join(lane.get(k, "") for k in ("now", "next", "blocker"))))
    for i, action in enumerate(document.get("actions", [])):
        fields.append((f"action {i + 1}", " ".join(action.get(k, "") for k in ("action", "reason", "status"))))
    return fields


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
    prose_blocks = [("summary", summary)] + [(f"notice '{n['title']}'", n["text"]) for n in document.get("notices", [])] + \
                   [(f"section '{s['title']}'", s.get("text", "")) for s in document.get("sections", [])]
    for where, text in prose_blocks[1:]:
        if words(text) > TEXT_WORDS:
            advice.append(f"{where} has {words(text)} words of prose; turn lists into decisions, needs_you, workstreams, a table, or a "
                          "timeline, and keep prose for interpretation.")
    times = sum(len(CLOCK.findall(text)) for _, text in prose_blocks)
    if times >= 3 and not document.get("timeline"):
        advice.append(f"prose mentions {times} dates or clock times but there is no timeline; put dated events and scheduled "
                      "checks in timeline.")
    if any(label in (n["title"].lower()) for n in document.get("notices", []) for label in ("needs you", "for you", "your list")) \
            and not document.get("needs_you"):
        advice.append("a notice lists what the reader must do; move each item into needs_you with its effort and deadline.")
    all_fields = _report_text_fields(document)
    identifiers = sorted({match for _, text in all_fields for match in IDENTIFIER.findall(_plain(text))})
    if identifiers:
        advice.append(f"prose contains raw identifiers ({', '.join(identifiers[:4])}{'…' if len(identifiers) > 4 else ''}); name "
                      "the thing instead and put identifiers in sources or a link.")
    eaten = [where for where, text in all_fields if SHELL_EATEN_DOLLAR.search(_plain(text))]
    if eaten:
        advice.append(f"possible missing dollar amount (shell-expanded $variable) in {', '.join(eaten[:3])}; verify every figure.")
    if not document.get("decisions"):
        for item in document.get("needs_you", []):
            if DECISION_VERB.search(item["action"]):
                advice.append(f"needs_you asks the reader to decide ('{item['action'][:60]}'); move decisions into the decisions "
                              "block with a recommendation, contrastive options, reversibility, and confidence.")
                break
    for index, decision in enumerate(document.get("decisions", [])):
        where = f"decisions[{index}]"
        if not decision.get("options"):
            advice.append(f"{where} has no options; list at least two options with upside and tradeoff so the reader sees why the "
                          "recommendation beats the realistic alternative.")
        if not decision.get("reversibility") or not decision.get("confidence"):
            advice.append(f"{where} is missing reversibility or confidence; state both so the reader can calibrate verification effort.")
        if decision.get("reversibility") == "irreversible" and (not decision.get("assumptions") or not decision.get("if_wrong")):
            advice.append(f"{where} is marked irreversible; state key assumptions and what changes if wrong.")
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
    if not document.get("decisions") and not document.get("needs_you") and not document.get("actions"):
        advice.append("neither decisions, needs_you, nor actions: state what happens next and who does it, or say plainly that "
                      "nothing is needed from the reader.")
    return advice


def check_delivery(document, body=None):
    """Return advisory checks for a proactive delivery and its Markdown document."""
    advice = []
    summary = document.get("summary", "")
    if words(summary) > DELIVERY_SUMMARY_WORDS:
        advice.append(f"summary has {words(summary)} words; keep it to {DELIVERY_SUMMARY_WORDS} or fewer (BLUF + bottom line). "
                      "Put evidence and option tradeoffs in --document.")
    recommended = document.get("recommended_default") or ""
    decision = document.get("decision") or {}
    options = decision.get("options") or []
    if decision and not recommended:
        advice.append("decision has no recommended_default; advise what to do rather than asking an open question.")
    if recommended and options:
        for option in options:
            if _near_duplicate(recommended, option):
                advice.append(f"decision option '{option[:60]}' duplicates recommended_default; list only distinct alternatives "
                              "(the page already shows recommended_default as the first choice).")
                break
    if (recommended or decision) and (not document.get("reversibility") or not document.get("confidence")):
        advice.append("delivery asks for a decision without reversibility or confidence; add both so the reader knows whether "
                      "this is a quick two-way door or a one-way commitment.")
    check_texts = [("summary", summary)]
    if recommended:
        check_texts.append(("recommended_default", recommended))
    if decision.get("question"):
        check_texts.append(("decision.question", decision["question"]))
    if body:
        check_texts.append(("document", body))
    identifiers = sorted({match for where, text in check_texts if where != "document"
                          for match in IDENTIFIER.findall(_plain(text))})
    if identifiers:
        advice.append(f"delivery header contains raw identifiers ({', '.join(identifiers[:4])}{'…' if len(identifiers) > 4 else ''}); "
                      "name the thing plainly and put raw IDs in the document or links.")
    eaten = [where for where, text in check_texts if SHELL_EATEN_DOLLAR.search(_plain(text))]
    if eaten:
        advice.append(f"possible missing dollar amount (shell-expanded $variable) in {', '.join(eaten[:3])}; verify every figure.")
    if body:
        if CHAT_REPLY_RESIDUE.search(_plain(body)):
            advice.append("document contains chat-reply instructions (e.g. 'Reply \"...\" to approve'); readers respond through "
                          "the page's response panel instead.")
        action_texts = [recommended] + list(options)
        body_lower = body.lower()
        unexplained = sorted({label for text in action_texts for label in REVERSE_DNS_LABEL.findall(text)
                              if label.lower() not in body_lower})
        if unexplained:
            advice.append(f"recommended_default or options reference targets absent from document ({', '.join(unexplained[:3])}); "
                          "every action the reader approves must be explained and verifiable in the write-up.")
    return advice
