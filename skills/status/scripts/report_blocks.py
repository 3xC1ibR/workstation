"""Visual blocks of a status report: state, actions for the reader, changes, phases, timeline, workstreams, charts.

Each block is validated here and rendered as plain HTML and inline SVG. Nothing
needs a script: positions are SVG percentage coordinates, so a mark lands in the
same place at every width while its text keeps the page's type size, and the
served page's content policy (no inline styles) and the portable file's (only
its response script) both hold. Hover text is native SVG `<title>`; data behind
a chart opens in a native disclosure.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math

STATE_LEVELS = {
    "on_track": ("On track", "positive"),
    "at_risk": ("At risk", "attention"),
    "off_track": ("Off track", "critical"),
    "blocked": ("Blocked", "critical"),
    "paused": ("Paused", "quiet"),
    "done": ("Done", "positive"),
}
PHASE_STATES = {"done": "Done", "active": "Now", "upcoming": "Upcoming", "blocked": "Blocked", "skipped": "Skipped"}
# Marks say whether a change is good or bad, never which way a number moved (a falling error rate is better).
CHANGE_DIRECTIONS = {"better": ("+", "Better"), "worse": ("−", "Worse"), "new": ("•", "New"),
                     "resolved": ("✓", "Resolved"), "unchanged": ("=", "Unchanged")}
EVENT_KINDS = {"event", "scheduled", "deadline", "milestone"}
CHART_KINDS = {"line", "bar"}
CHANGED_SINCE = "Since the last version"

BLOCKS = {
    # collection: (required, optional)
    "needs_you": ({"action"}, {"effort", "due", "unblocks", "link", "ask"}),
    "changes": ({"text"}, {"direction"}),
    "phases": ({"name", "state"}, {"start", "end", "detail"}),
    "timeline": ({"at", "title"}, {"end", "detail", "kind", "owner"}),
    "workstreams": ({"name", "state", "now"}, {"owner", "next", "blocker", "link"}),
    "charts": ({"title", "kind", "series"}, {"unit", "y_label", "target", "target_label", "note", "source",
                                            "observed_at", "freshness_minutes"}),
}
METRIC_NUMBERS = {"current", "target", "better", "series"}
TOP_LEVEL = set(BLOCKS) | {"state", "timeline_window"}


def _timestamp(value, location):
    if not isinstance(value, str):
        raise ValueError(f"{location} must be an ISO 8601 timestamp with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{location} must be an ISO 8601 timestamp with a timezone") from error
    if parsed.utcoffset() is None:
        raise ValueError(f"{location} must include a timezone")
    return parsed


def _number(value, location, allow_null=False):
    if value is None and allow_null:
        return
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{location} must be a finite number{' or null' if allow_null else ''}")


def _record(record, required, optional, location):
    if not isinstance(record, dict):
        raise ValueError(f"{location} must be an object")
    missing, extra = required - record.keys(), record.keys() - required - optional
    if missing or extra:
        raise ValueError(f"{location}: missing {sorted(missing)}; unknown {sorted(extra)}.")


def _text(record, key, location):
    if key in record and (not isinstance(record[key], str) or not record[key].strip()):
        raise ValueError(f"{location}.{key} must be nonempty text")


def validate_blocks(document):
    """Validate the visual blocks; the core fields are validated by build_status."""
    if "state" in document:
        state = document["state"]
        _record(state, {"level"}, {"label"}, "state")
        if state["level"] not in STATE_LEVELS:
            raise ValueError(f"state.level must be one of {sorted(STATE_LEVELS)}")
        _text(state, "label", "state")
    if "timeline_window" in document:
        window = document["timeline_window"]
        _record(window, {"start", "end"}, {"label"}, "timeline_window")
        if _timestamp(window["start"], "timeline_window.start") >= _timestamp(window["end"], "timeline_window.end"):
            raise ValueError("timeline_window.start must precede timeline_window.end")
        _text(window, "label", "timeline_window")
    for collection, (required, optional) in BLOCKS.items():
        records = document.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(f"{collection} must be a list")
        for index, record in enumerate(records):
            location = f"{collection}[{index}]"
            _record(record, required, optional, location)
            for key in record.keys() - {"series", "target", "freshness_minutes"}:
                _text(record, key, location)
            for key in ("due", "start", "end", "at", "observed_at"):
                if key in record:
                    _timestamp(record[key], f"{location}.{key}")
            if collection == "changes" and record.get("direction", "new") not in CHANGE_DIRECTIONS:
                raise ValueError(f"{location}.direction must be one of {sorted(CHANGE_DIRECTIONS)}")
            if collection == "phases" and record["state"] not in PHASE_STATES:
                raise ValueError(f"{location}.state must be one of {sorted(PHASE_STATES)}")
            if collection == "workstreams" and record["state"] not in STATE_LEVELS:
                raise ValueError(f"{location}.state must be one of {sorted(STATE_LEVELS)}")
            if collection == "timeline":
                if record.get("kind", "event") not in EVENT_KINDS:
                    raise ValueError(f"{location}.kind must be one of {sorted(EVENT_KINDS)}")
                if "end" in record and _timestamp(record["end"], location) < _timestamp(record["at"], location):
                    raise ValueError(f"{location}.end must not precede at")
            if collection == "charts":
                _validate_chart(record, location)


def _validate_chart(chart, location):
    if chart["kind"] not in CHART_KINDS:
        raise ValueError(f"{location}.kind must be one of {sorted(CHART_KINDS)}")
    if "target" in chart:
        _number(chart["target"], f"{location}.target")
    if "freshness_minutes" in chart and (type(chart["freshness_minutes"]) is not int or chart["freshness_minutes"] < 0):
        raise ValueError(f"{location}.freshness_minutes must be a nonnegative integer")
    series = chart["series"]
    if not isinstance(series, list) or not 1 <= len(series) <= 4:
        raise ValueError(f"{location}.series must list 1 to 4 series")
    for number, line in enumerate(series):
        where = f"{location}.series[{number}]"
        _record(line, {"name", "points"}, set(), where)
        _text(line, "name", where)
        if not isinstance(line["points"], list) or not line["points"]:
            raise ValueError(f"{where}.points must be a nonempty list of [x, y] pairs")
        for position, point in enumerate(line["points"]):
            at = f"{where}.points[{position}]"
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{at} must be an [x, y] pair")
            _number(point[1], f"{at}[1]", allow_null=True)
            if chart["kind"] == "line":
                if isinstance(point[0], str):
                    _timestamp(point[0], f"{at}[0]")
                else:
                    _number(point[0], f"{at}[0]")
            elif not isinstance(point[0], str) or not point[0].strip():
                raise ValueError(f"{at}[0] must be a category label for a bar chart")
    if chart["kind"] == "line":
        kinds = {isinstance(point[0], str) for line in series for point in line["points"]}
        if len(kinds) > 1:
            raise ValueError(f"{location}: x values must be all timestamps or all numbers")


def validate_metric_numbers(metric, location):
    if "current" in metric:
        _number(metric["current"], f"{location}.current")
    if "target" in metric:
        _number(metric["target"], f"{location}.target")
        if "current" not in metric:
            raise ValueError(f"{location}.target needs current")
    if "better" in metric and metric["better"] not in ("higher", "lower"):
        raise ValueError(f"{location}.better must be higher or lower")
    if "series" in metric:
        series = metric["series"]
        if not isinstance(series, list) or len(series) < 2:
            raise ValueError(f"{location}.series must list at least two [timestamp, number] pairs")
        for position, point in enumerate(series):
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{location}.series[{position}] must be a [timestamp, number] pair")
            _timestamp(point[0], f"{location}.series[{position}][0]")
            _number(point[1], f"{location}.series[{position}][1]", allow_null=True)


# Rendering ---------------------------------------------------------------------------------------------------------


def format_number(value, unit=None):
    if value is None:
        return "No value"
    magnitude = abs(value)
    text = f"{value:,.0f}" if magnitude >= 100 or float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")
    if not unit:
        return text
    if unit in ("$", "€", "£", "¥"):
        return ("-" if value < 0 else "") + unit + text.lstrip("-")
    return text + unit if unit == "%" else f"{text} {unit}"


def percent(value):
    return f"{max(0.0, min(100.0, value)):.2f}%"


class Blocks:
    """Renders blocks with the report's own escaping, prose, and time formatting."""

    def __init__(self, document, *, escape, prose, time_text, provenance, link, generated, zone, previous=None):
        self.document, self.escape, self.prose, self.time_text = document, escape, prose, time_text
        self.provenance, self.link, self.generated, self.zone = provenance, link, generated, zone
        self.previous = previous or []           # earlier versions of this operation, newest first

    def clock(self, value):
        local = (value if isinstance(value, datetime) else _timestamp(value, "time")).astimezone(self.zone)
        return f"{local.hour % 12 or 12}:{local:%M} {local:%p}"

    def relative(self, moment):
        """How far a time lies from the report's generation, in the largest whole unit."""
        seconds = (moment - self.generated).total_seconds()
        minutes = abs(seconds) / 60
        amount = f"{minutes:.0f} min" if minutes < 90 else f"{minutes / 60:.0f} h" if minutes < 48 * 60 else f"{minutes / 1440:.0f} days"
        return f"in {amount}" if seconds >= 0 else f"{amount} ago"

    def state_word(self, level, extra_class=""):
        word, tone = STATE_LEVELS[level]
        return f'<span class="state-word tone-{tone}{extra_class}">{word}</span>'

    # The header's state line: the one word that says how the operation stands, then the author's reason.
    def state(self):
        state = self.document.get("state")
        if not state:
            return ""
        label = f' <span class="state-label">{self.escape(state["label"])}</span>' if state.get("label") else ""
        return f'<p class="sheet-state">{self.state_word(state["level"])}{label}</p>'

    def needs_you(self):
        items = self.document.get("needs_you", [])
        if not items:
            return ""
        rows = []
        for item in items:
            meta = []
            if item.get("due"):
                due = _timestamp(item["due"], "due")
                overdue = due < self.generated
                when = self.clock(due) if due.astimezone(self.zone).date() == self.generated.astimezone(self.zone).date() \
                    else self.time_text(item["due"], full=False)
                meta.append(f'<span class="todo-due{" tone-attention" if overdue else ""}">{"Overdue since" if overdue else "By"} '
                            f'{self.escape(when)}, {self.escape(self.relative(due))}</span>')
            if item.get("effort"):
                meta.append(self.escape(item["effort"]))
            if item.get("ask"):
                meta.append(f"Ask {self.escape(item['ask'])}")
            line = f'<p class="todo-meta">{" · ".join(meta)}</p>' if meta else ""
            unblocks = f'<p class="todo-unblocks">Unblocks: {self.escape(item["unblocks"])}</p>' if item.get("unblocks") else ""
            link = f'<p class="todo-link">{self.link(item["link"])}</p>' if item.get("link") else ""
            rows.append(f'<li><p class="todo-title">{self.escape(item["action"])}</p>{line}{unblocks}{link}</li>')
        return (f'<section class="block-needs-you" aria-labelledby="block-needs-you"><h2 class="block-heading" id="block-needs-you">'
                f'For you to do <span class="count">{len(items)}</span></h2><ol class="todo">{"".join(rows)}</ol></section>')

    def changes(self):
        items = self.document.get("changes", [])
        if not items:
            return ""
        since = ""
        if self.previous:
            since = f' <span class="count">since {self.escape(self.time_text(self.previous[0]["generated_at"], full=False))}</span>'
        rows = []
        for item in items:
            direction = item.get("direction", "new")
            mark, word = CHANGE_DIRECTIONS[direction]
            rows.append(f'<li data-direction="{direction}"><span class="change-mark" role="img" aria-label="{word}">{mark}</span>'
                        f'<span>{self.escape(item["text"])}</span></li>')
        return (f'<section class="block-changes"><h2 class="block-heading">{CHANGED_SINCE}{since}</h2>'
                f'<ul class="changes">{"".join(rows)}</ul></section>')

    def _date(self, value):
        local = _timestamp(value, "date").astimezone(self.zone)
        return f"{local:%b} {local.day}"

    def _span(self, start, end):
        """A start and an end; an end on the start's day gives its clock only."""
        if start and end:
            first, last = (_timestamp(value, "time").astimezone(self.zone) for value in (start, end))
            if first.date() == last.date():
                return f"{self.time_text(start, full=False)} – {last.hour % 12 or 12}:{last:%M} {last:%p}"
        return " – ".join(self.time_text(value, full=False) for value in (start, end) if value)

    def phases(self):
        phases = self.document.get("phases", [])
        if not phases:
            return ""
        current = next((index for index, phase in enumerate(phases) if phase["state"] in ("active", "blocked")), None)
        heading = "Phases"
        if current is not None:
            heading += f' <span class="count">{current + 1} of {len(phases)}</span>'
        rows = []
        for phase in phases:
            dates = " – ".join(self._date(value) for value in (phase.get("start"), phase.get("end")) if value)
            dates = f'<span class="phase-dates">{self.escape(dates)}</span>' if dates else ""
            detail = f'<span class="phase-detail">{self.escape(phase["detail"])}</span>' if phase.get("detail") else ""
            current_mark = ' aria-current="step"' if phase["state"] == "active" else ""
            rows.append(f'<li data-state="{phase["state"]}"{current_mark}><span class="phase-mark" aria-hidden="true"></span>'
                        f'<span class="phase-name">{self.escape(phase["name"])}</span>'
                        f'<span class="phase-state">{PHASE_STATES[phase["state"]]}</span>{dates}{detail}</li>')
        layout = "phases-long" if len(phases) > 5 else "phases-short"
        return f'<section class="block-phases"><h2 class="section-heading">{heading}</h2><ol class="phases {layout}">{"".join(rows)}</ol></section>'

    # Timeline: an axis from the window's start to its end with the present marked, then the events as a list.
    def timeline(self):
        events = sorted(self.document.get("timeline", []), key=lambda event: _timestamp(event["at"], "at"))
        if not events:
            return ""
        window = self.document.get("timeline_window")
        times = [_timestamp(event["at"], "at") for event in events] + [_timestamp(e["end"], "end") for e in events if e.get("end")]
        start = _timestamp(window["start"], "start") if window else min(times + [self.generated])
        end = _timestamp(window["end"], "end") if window else max(times + [self.generated])
        if end <= start:
            end = start + timedelta(hours=1)
        heading = "Timeline"
        if window and window.get("label"):
            heading += f' <span class="count">{self.escape(window["label"])}</span>'
        axis = self._axis(events, start, end) if window else ""
        return f'<section class="block-timeline"><h2 class="section-heading">{heading}</h2>{axis}{self._event_list(events)}</section>'


    def _position(self, moment, start, end):
        return (moment - start).total_seconds() / (end - start).total_seconds() * 100

    def _ticks(self, start, end):
        span = (end - start).total_seconds()
        steps = [900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800, 1209600, 2592000]
        step = next((s for s in steps if span / s <= 6), steps[-1])
        local = start.astimezone(self.zone)
        if step < 86400:
            first = local.replace(minute=0, second=0, microsecond=0)
            first += timedelta(seconds=-(first.hour * 3600) % step) if step >= 3600 else timedelta(0)
        else:
            first = local.replace(hour=0, minute=0, second=0, microsecond=0)
        ticks, moment = [], first
        while moment <= end:
            if moment >= start:
                ticks.append(moment)
            moment = (moment + timedelta(seconds=step)).astimezone(self.zone)
        def label(value):
            value = value.astimezone(self.zone)
            if step >= 86400:
                return f"{value:%b} {value.day}"
            clock = f"{value.hour % 12 or 12}{'' if value.minute == 0 else f':{value:%M}'} {value:%p}"
            return clock if value.hour or value.minute or span < 86400 else f"{value:%b} {value.day}"
        return [(tick, label(tick)) for tick in ticks]

    def _axis(self, events, start, end):
        now = self._position(self.generated, start, end)
        parts = ['<svg class="axis" width="100%" height="64" role="img" aria-label="'
                 + self.escape(f"Timeline from {self.time_text(start.isoformat(), full=False)} to {self.time_text(end.isoformat(), full=False)}")
                 + '">', '<rect class="axis-track" x="0" y="27" width="100%" height="4" rx="2"/>']
        if now > 0:
            parts.append(f'<rect class="axis-elapsed" x="0" y="27" width="{percent(now)}" height="4" rx="2"/>')
        # Only what the reader steers by is marked on the axis: deadlines and milestones. Everything is in the list.
        for event in events:
            kind = event.get("kind", "event")
            if kind not in ("deadline", "milestone"):
                continue
            x = self._position(_timestamp(event["at"], "at"), start, end)
            title = f'<title>{self.escape(self.time_text(event["at"], full=False))}: {self.escape(event["title"])}</title>'
            if kind == "deadline":
                parts.append(f'<line class="axis-deadline" x1="{percent(x)}" x2="{percent(x)}" y1="18" y2="40">{title}</line>')
            else:
                past = "past" if _timestamp(event["at"], "at") <= self.generated else "future"
                parts.append(f'<circle class="axis-mark axis-{past}" cx="{percent(x)}" cy="29" r="5">{title}</circle>')
        if 0 <= now <= 100:
            anchor = "start" if now < 6 else "end" if now > 94 else "middle"
            parts.append(f'<line class="axis-now" x1="{percent(now)}" x2="{percent(now)}" y1="14" y2="44"/>'
                         f'<text class="axis-now-label" x="{percent(now)}" y="10" text-anchor="{anchor}">Now</text>')
        ticks = self._ticks(start, end)
        for index, (tick, label) in enumerate(ticks):
            x = self._position(tick, start, end)
            anchor = "start" if x < 4 else "end" if x > 96 else "middle"
            parts.append(f'<text class="axis-label" x="{percent(x)}" y="60" text-anchor="{anchor}">{self.escape(label)}</text>')
        parts.append("</svg>")
        return "".join(parts)

    def _event_list(self, events):
        rows, now_placed, past = [], False, [e for e in events if _timestamp(e["at"], "at") <= self.generated]
        # Many past events: the last few stay in view, earlier ones wait behind a disclosure.
        hidden = past[:-4] if len(past) > 8 else []
        days = {_timestamp(e["at"], "at").astimezone(self.zone).date() for e in events}
        last_day = [None]
        def day_heading(event):
            day = _timestamp(event["at"], "at").astimezone(self.zone)
            if len(days) < 2 or day.date() == last_day[0]:
                return ""
            last_day[0] = day.date()
            return f'<li class="event-day">{day:%a}, {day:%b} {day.day}</li>'
        def row(event):
            moment = _timestamp(event["at"], "at")
            kind = event.get("kind", "event")
            when = self.clock(event["at"])
            if event.get("end"):
                end = _timestamp(event["end"], "end")
                when = (f"{when} – {self.clock(end)}" if end.astimezone(self.zone).date() == moment.astimezone(self.zone).date()
                        else f"{when} – {self.time_text(event['end'], full=False)}")
            word = {"deadline": "Deadline", "milestone": "Milestone", "scheduled": "Scheduled"}.get(kind)
            word = f'<span class="event-kind tone-{"attention" if kind == "deadline" else "quiet"}">{word}</span> ' if word else ""
            owner = f'<span class="event-owner">{self.escape(event["owner"])}</span>' if event.get("owner") else ""
            detail = f'<span class="event-detail">{self.escape(event["detail"])}</span>' if event.get("detail") else ""
            tense = "past" if moment <= self.generated else "future"
            return (f'<li data-tense="{tense}" data-kind="{kind}"><span class="event-time numeric">{self.escape(when)}</span>'
                    f'<span class="event-body"><span class="event-title">{word}{self.escape(event["title"])}</span>{owner}{detail}</span></li>')
        if hidden:
            earlier = "".join(day_heading(event) + row(event) for event in hidden)
            rows.append(f'<li class="event-earlier"><details><summary>{len(hidden)} earlier events</summary>'
                        f'<ol class="events">{earlier}</ol></details></li>')
        for event in events:
            if event in hidden:
                continue
            heading = day_heading(event)
            if not now_placed and _timestamp(event["at"], "at") > self.generated:
                rows.append(heading + f'<li class="event-now" aria-label="Now"><span class="event-time numeric">Now {self.clock(self.generated)}</span><span></span></li>')
                now_placed, heading = True, ""
            rows.append(heading + row(event))
        if not now_placed:
            rows.append(f'<li class="event-now" aria-label="Now"><span class="event-time numeric">Now {self.clock(self.generated)}</span><span></span></li>')
        return f'<ol class="events">{"".join(rows)}</ol>'

    def workstreams(self):
        items = self.document.get("workstreams", [])
        if not items:
            return ""
        counts = {}
        for item in items:
            counts[item["state"]] = counts.get(item["state"], 0) + 1
        tally = " · ".join(f"{count} {STATE_LEVELS[level][0].lower()}" for level, count in counts.items())
        rows = []
        for item in items:
            owner = f'<p class="ws-owner">{self.escape(item["owner"])}</p>' if item.get("owner") else ""
            following = f'<p><span class="ws-lead">Next</span> {self.escape(item["next"])}</p>' if item.get("next") else ""
            blocker = (f'<p class="ws-blocker"><span class="ws-lead">Blocked by</span> {self.escape(item["blocker"])}</p>'
                       if item.get("blocker") else "")
            link = f'<p class="ws-link">{self.link(item["link"])}</p>' if item.get("link") else ""
            rows.append(f'<li data-state="{item["state"]}"><p class="ws-head"><span class="ws-name">{self.escape(item["name"])}</span>'
                        f'{self.state_word(item["state"])}</p>{owner}<p><span class="ws-lead">Now</span> {self.escape(item["now"])}</p>'
                        f'{following}{blocker}{link}</li>')
        return (f'<section class="block-workstreams"><h2 class="section-heading">Workstreams <span class="count">{self.escape(tally)}</span></h2>'
                f'<ul class="workstreams">{"".join(rows)}</ul></section>')

    # Charts --------------------------------------------------------------------------------------------------------

    def charts(self):
        return "".join(self._chart(chart) for chart in self.document.get("charts", []))

    def _chart(self, chart):
        figure = self._line(chart) if chart["kind"] == "line" else self._bars(chart)
        legend = ""
        if len(chart["series"]) > 1:
            sample = ('<rect class="bar-fill series-{index}" x="0" y="1" width="24" height="8" rx="2"/>' if chart["kind"] == "bar"
                      else '<line class="series series-{index}" x1="0" x2="24" y1="5" y2="5"/>')
            legend = '<ul class="chart-legend">' + "".join(
                f'<li><svg width="24" height="10" aria-hidden="true">{sample.format(index=index)}</svg>'
                f'{self.escape(line["name"])}</li>' for index, line in enumerate(chart["series"])) + "</ul>"
        note = f'<p class="chart-note">{self.escape(chart["note"])}</p>' if chart.get("note") else ""
        return (f'<section class="block-chart"><h2 class="section-heading">{self.escape(chart["title"])}</h2>{note}{legend}'
                f'<figure class="chart">{figure}</figure>{self._data_table(chart)}{self.provenance(chart)}</section>')

    def _scale(self, values, target):
        values = [v for v in values if v is not None] + ([target] if target is not None else [])
        low, high = min(values + [0]), max(values + [0])
        if high == low:
            high = low + 1
        raw = (high - low) / 4
        power = 10 ** math.floor(math.log10(raw))
        step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
        return math.floor(low / step) * step, math.ceil(high / step) * step, step

    def _x_label(self, value, span_seconds):
        if isinstance(value, (int, float)):
            return format_number(value)
        local = _timestamp(value, "x").astimezone(self.zone)
        if span_seconds <= 2 * 86400:
            return f"{local.hour % 12 or 12}:{local:%M} {local:%p}"
        return f"{local:%b} {local.day}"

    def _line(self, chart):
        height, top, bottom = 216, 28, 184
        unit, target = chart.get("unit"), chart.get("target")
        def x_value(x):
            return _timestamp(x, "x").timestamp() if isinstance(x, str) else float(x)
        xs = [x_value(point[0]) for line in chart["series"] for point in line["points"]]
        x_low, x_high = min(xs), max(xs)
        if x_high == x_low:
            x_high = x_low + 1
        low, high, step = self._scale([p[1] for line in chart["series"] for p in line["points"]], target)
        def x_at(x):
            return 1 + (x_value(x) - x_low) / (x_high - x_low) * 98
        def y_at(y):
            return bottom - (y - low) / (high - low) * (bottom - top)
        parts = [f'<svg class="plot" width="100%" height="{height}" role="img" aria-label="{self.escape(chart["title"])}">']
        tick = low
        while tick <= high + step / 2:
            y = y_at(tick)
            parts.append(f'<line class="grid" x1="0" x2="100%" y1="{y:.1f}" y2="{y:.1f}"/>'
                         f'<text class="tick" x="0" y="{y - 4:.1f}">{self.escape(format_number(tick, unit))}</text>')
            tick += step
        if target is not None:
            y = y_at(target)
            label = chart.get("target_label") or f"Target {format_number(target, unit)}"
            parts.append(f'<line class="target" x1="0" x2="100%" y1="{y:.1f}" y2="{y:.1f}"/>'
                         f'<text class="tick target-label" x="100%" y="{y - 4:.1f}" text-anchor="end">{self.escape(label)}</text>')
        for index, line in enumerate(chart["series"]):
            points = sorted(line["points"], key=lambda point: x_value(point[0]))
            for first, second in zip(points, points[1:]):
                if first[1] is None or second[1] is None:
                    continue                                   # a missing value is a gap, never zero
                parts.append(f'<line class="series series-{index}" x1="{x_at(first[0]):.2f}%" x2="{x_at(second[0]):.2f}%" '
                             f'y1="{y_at(first[1]):.1f}" y2="{y_at(second[1]):.1f}"/>')
            for point in points:
                if point[1] is None:
                    continue
                label = f'{self._x_label(point[0], x_high - x_low)}: {format_number(point[1], unit)}'
                parts.append(f'<circle class="point series-{index}" cx="{x_at(point[0]):.2f}%" cy="{y_at(point[1]):.1f}" r="3">'
                             f'<title>{self.escape(line["name"])}, {self.escape(label)}</title></circle>')
        # Labels along the bottom at even steps of the clock (or of the numbers), never more than five.
        timed = isinstance(chart["series"][0]["points"][0][0], str)
        if timed:
            begin, finish = (datetime.fromtimestamp(value, self.zone) for value in (x_low, x_high))
            marks = [(tick.timestamp(), label) for tick, label in self._ticks(begin, finish)]
        else:
            marks = [(x_low + i * (x_high - x_low) / 2, format_number(x_low + i * (x_high - x_low) / 2)) for i in range(3)]
        for value, label in marks[:6]:
            x = 1 + (value - x_low) / (x_high - x_low) * 98
            anchor = "start" if x < 8 else "end" if x > 92 else "middle"
            parts.append(f'<text class="tick" x="{x:.2f}%" y="{height - 6}" text-anchor="{anchor}">{self.escape(label)}</text>')
        # The latest value, and the extreme one when it is elsewhere, carry their numbers.
        if len(chart["series"]) == 1:
            known = [p for p in sorted(chart["series"][0]["points"], key=lambda point: x_value(point[0])) if p[1] is not None]
            labelled = [known[-1]] + ([max(known, key=lambda point: point[1])] if max(known, key=lambda point: point[1]) is not known[-1] else [])
            for point in labelled:
                x = x_at(point[0])
                anchor = "end" if x > 85 else "start" if x < 15 else "middle"
                parts.append(f'<text class="point-label" x="{x:.2f}%" y="{y_at(point[1]) - 8:.1f}" text-anchor="{anchor}">'
                             f'{self.escape(format_number(point[1], unit))}</text>')
        parts.append("</svg>")
        return "".join(parts)

    def _bars(self, chart):
        unit, target = chart.get("unit"), chart.get("target")
        categories = []
        for line in chart["series"]:
            for label, _ in line["points"]:
                if label not in categories:
                    categories.append(label)
        values = {(index, label): value for index, line in enumerate(chart["series"]) for label, value in line["points"]}
        maximum = max([abs(v) for v in values.values() if v is not None] + ([abs(target)] if target is not None else []) + [0]) or 1
        rows = []
        for label in categories:
            bars = []
            for index, line in enumerate(chart["series"]):
                value = values.get((index, label))
                width = 0 if value is None else abs(value) / maximum * 100
                name = f'{self.escape(line["name"])}, ' if len(chart["series"]) > 1 else ""
                marker = (f'<line class="target" x1="{percent(abs(target) / maximum * 100)}" x2="{percent(abs(target) / maximum * 100)}" y1="0" y2="16"/>'
                          if target is not None else "")
                bars.append(f'<span class="bar-line"><svg class="bar" width="100%" height="16" role="img" aria-label="{name}{self.escape(label)}: '
                            f'{self.escape(format_number(value, unit))}"><rect class="bar-fill series-{index}" x="0" y="4" width="{percent(width)}" height="8" rx="2"/>{marker}</svg>'
                            f'<span class="bar-value numeric">{self.escape(format_number(value, unit))}</span></span>')
            rows.append(f'<li><span class="bar-label">{self.escape(label)}</span><span class="bar-group">{"".join(bars)}</span></li>')
        caption = ""
        if target is not None:
            caption = f'<p class="chart-note">{self.escape(chart.get("target_label") or "Target " + format_number(target, unit))}: the vertical rule</p>'
        return f'<ul class="bars">{"".join(rows)}</ul>{caption}'

    def _data_table(self, chart):
        unit = chart.get("unit")
        head = "".join(f'<th scope="col">{self.escape(line["name"])}</th>' for line in chart["series"])
        keys = []
        for line in chart["series"]:
            for x, _ in line["points"]:
                if x not in keys:
                    keys.append(x)
        values = {(index, x): y for index, line in enumerate(chart["series"]) for x, y in line["points"]}
        def shown(x):
            if isinstance(x, str) and chart["kind"] == "line":
                return self.time_text(x, full=False)
            return format_number(x) if isinstance(x, (int, float)) else x
        body = "".join(f"<tr><td>{self.escape(shown(x))}</td>" + "".join(
            f'<td class="numeric">{self.escape(format_number(values.get((index, x)), unit))}</td>' for index in range(len(chart["series"])))
            + "</tr>" for x in keys)
        return (f'<details class="chart-data"><summary>Data</summary><div class="table-region table-region-narrow">'
                f'<table class="table-pair"><thead><tr><th scope="col">{"Category" if chart["kind"] == "bar" else "At"}</th>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div></details>')

    # Measures: a bar toward the target, a line of earlier values, and the value it had in the last version.

    def metric_extras(self, metric):
        parts = []
        if "target" in metric and metric["target"]:
            share = metric["current"] / metric["target"] * 100
            parts.append(f'<svg class="meter" width="100%" height="6" role="img" aria-label="{share:.0f}% of target">'
                         f'<rect class="meter-track" x="0" y="0" width="100%" height="6" rx="3"/>'
                         f'<rect class="meter-fill" x="0" y="0" width="{percent(share)}" height="6" rx="3"/></svg>')
        history = self._metric_history(metric)
        if len([v for _, v in history if v is not None]) >= 3:
            parts.append(self._sparkline(metric["label"], history))
        delta = self._metric_change(metric)
        if delta:
            parts.append(delta)
        return f'<dd class="metric-visual">{"".join(parts)}</dd>' if parts else ""

    def _metric_history(self, metric):
        if metric.get("series"):
            return [(at, value) for at, value in metric["series"]]
        if "current" not in metric:
            return []
        history = []
        for version in reversed(self.previous):
            for earlier in version.get("metrics", []):
                if earlier.get("label") == metric["label"] and "current" in earlier:
                    history.append((version["generated_at"], earlier["current"]))
                    break
        return history + [(self.document["generated_at"], metric["current"])] if history else []

    def _sparkline(self, label, history):
        values = [v for _, v in history if v is not None]
        low, high = min(values), max(values)
        span = (high - low) or 1
        count = len(history)
        def x(index):
            return 2 + index / max(count - 1, 1) * 96
        def y(value):
            return 24 - (value - low) / span * 20
        parts = [f'<svg class="sparkline" width="100%" height="28" role="img" aria-label="{self.escape(label)}: '
                 f'{len(values)} observations from {self.escape(format_number(low))} to {self.escape(format_number(high))}">']
        for index in range(count - 1):
            first, second = history[index][1], history[index + 1][1]
            if first is None or second is None:
                continue
            parts.append(f'<line class="spark" x1="{x(index):.2f}%" x2="{x(index + 1):.2f}%" y1="{y(first):.1f}" y2="{y(second):.1f}"/>')
        for index, (at, value) in enumerate(history):
            if value is None:
                continue
            last = " spark-last" if index == count - 1 else ""
            parts.append(f'<circle class="spark-point{last}" cx="{x(index):.2f}%" cy="{y(value):.1f}" r="{2.5 if last else 1.5}">'
                         f'<title>{self.escape(self.time_text(at, full=False))}: {self.escape(format_number(value))}</title></circle>')
        parts.append("</svg>")
        return "".join(parts)

    def _metric_change(self, metric):
        if not self.previous:
            return ""
        earlier = next((m for m in self.previous[0].get("metrics", []) if m.get("label") == metric["label"]), None)
        if earlier is None or earlier.get("value") == metric.get("value"):
            return ""
        tone = ""
        if "current" in metric and "current" in earlier and metric.get("better") and metric["current"] != earlier["current"]:
            improved = (metric["current"] > earlier["current"]) == (metric["better"] == "higher")
            tone = " tone-positive" if improved else " tone-attention"
        was = "No value" if earlier.get("value") is None else earlier["value"]
        return f'<span class="metric-change{tone}">Was {self.escape(was)}</span>'
