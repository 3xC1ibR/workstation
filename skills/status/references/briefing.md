# Write a briefing, not a wall of text

A report is read by someone who runs several operations at once. They open the
review page in the morning (or after a meeting, often on a phone) and go through
each operation's report in turn, giving each **under a minute**. The page is HTML:
use it. Every fact belongs in the block made for its shape, so the reader can
find it by position without reading prose. For the full decision-packet
criteria, posture selection, and before/after rewrites, read
[decision-packet.md](decision-packet.md).

## The opening questions, in order

The renderer places blocks in this order; fill them so each answer comes first.

| # | The reader asks | Answer with | Rule |
| --- | --- | --- | --- |
| 1 | Where does this stand, and how sure are you? | `state` and `summary` | `state.level` is the honest one-word verdict; `state.label` is its reason in under 12 words; optional `confidence` (`high`, `moderate`, `low`) and `confidence_basis` rate evidence quality separately from outcome probability. The summary is at most 60 words; its first sentence is the headline the review list shows. |
| 2 | What must I decide? | `decisions` | Completed staff work: `question`, `recommendation`, contrastive `why`, 2–6 `options` (`upside`/`downside`), `reversibility`, `confidence`, plus `assumptions` and `if_wrong` for costly/irreversible calls. Omit when no choice is waiting. |
| 3 | What tasks wait on me, by when? | `needs_you` | Pure execution steps only (never hide a choice here), starting with a verb: effort, deadline (`due`), what it unblocks, and a link or ask number. Nothing for the reader: omit the block and say so in the summary. |
| 4 | What changed since I last looked? | `changes` | 2 to 6 items, each one line, marked `better`, `worse`, `new`, `resolved`, or `unchanged`. Measures also show their previous value automatically. |
| 5 | What happens next, and when? | `timeline`, `actions` | Scheduled checks, deadlines, and windows go in the timeline with times; owners and commitments go in actions. |

Then the shape of the work: `metrics` (the rail), `phases`, `workstreams`,
`charts`. Then evidence: `sections` (background collapsed) and `sources`.

## Choose the block by the shape of the content

| The content is | Use | Not |
| --- | --- | --- |
| A verdict on the whole operation | `state` (with optional `confidence`) | An adjective buried in the summary |
| A choice the reader must make (options, tradeoffs, spend, risk) | `decisions` | A vague `"Choose X"` line in `needs_you` |
| A pure execution task only the reader can perform (login, key, signature) | `needs_you` | A notice or summary bullet |
| A number with a goal ("$0 of $1,000", "48 of 50 checks") | a metric with `current` and `target` (draws a bar) | A sentence |
| A number you report every version | a metric with `current` and the **same label** each time (draws its trend and "Was ...") | Re-describing the change in prose |
| A number over time you observed | a `line` chart, or a metric `series` for a small trend | A table of times and values |
| A comparison across categories | a `bar` chart | Prose with numbers |
| Stages the work passes through | `phases` (one `active`) | "We are now in phase 3" |
| Dated events, scheduled checks, deadlines, a time window | `timeline` (+ `timeline_window` for a fixed window, such as a 24-hour campaign) | Clock times scattered through prose |
| Parallel lanes, agents, or streams, each with a state | `workstreams` | A table with a State column |
| Records to compare across several attributes | a section table | Workstreams or prose |
| Interpretation, a reason, a judgment call | prose: summary, a notice, or a section `text` | A table |
| Something to filter, adjust, or explore (hundreds of rows, scenarios, a plan to edit) | an interactive document (`--interactive`; the data-visualization skill for data) | A 40-row table |

Start from [briefing-example.json](briefing-example.json): it uses every block
on an illustrative subject. Field definitions are in
[report-format.md](report-format.md).

## Writing rules

- **Lead with the judgment and the change**, not chronology. "Revenue is $0 of
  $1,000 with 11 h left; replies are the bottleneck" beats "At 12h 07m into the
  window, net-new collected revenue is...".
- **Say each fact once, in its block.** Do not restate `needs_you` in the
  summary or a notice; the summary may say "Two things need you by 12:30."
- **Name things; never show raw identifiers in prose.** Write "the ads lead",
  not "Codex 01a205d9"; "the Bridge offer", not "acct_1Ue...". Put identifiers
  in `sources`, links, or a collapsed section.
- **Numbers carry their denominator, period, and unit**, and the reader's
  timezone (`timezone`). Missing is "No value", never 0.
- **Keep metric labels stable across versions.** The label is how the page finds
  last version's value and draws the trend.
- **Owners are roles a reader recognizes** ("database agent", "you",
  "migration lead").
- **At most three notices**, each a material exception: a failed assumption, a
  broken limit, a changed plan. Routine progress is not a notice.
- **Omit empty blocks.** Do not write "No blockers" sections.
- **Choose the state honestly.** `on_track`: the goal and dates hold.
  `at_risk`: a target or date is in doubt. `off_track`: it will be missed
  without a change of plan. `blocked`: progress waits on something outside the
  agent's control, often the reader. `paused`, `done` as written.

## Before and after

A wall of text (the pattern agents fall into):

> End of night (00:15). All agent work that doesn't need you is done and the
> agents (a3f9c2d1, 7be04412) are idle. 7 offers are live, 3 tools are staged,
> sales: 0. What turns offers into tests is your list: the API key, the ad
> account, the public business name, and identity verification. Checks run at
> 09:00, 13:00 and 18:00.

The same content as a briefing:

```json
{"state": {"level": "blocked", "label": "Agents idle until four account steps are done"},
 "summary": "Seven offers are live with no sales yet. Four account steps of yours, about 45 minutes, unlock paid tests.",
 "needs_you": [{"action": "Add the API key", "effort": "5 min", "unblocks": "Launch of the staged tools"},
               {"action": "Create the ad account", "effort": "20 min", "unblocks": "Paid tests"}],
 "metrics": [{"label": "Live offers with a sale", "value": "0 of 7", "current": 0, "target": 7, "better": "higher"}],
 "timeline": [{"at": "2026-11-23T09:00:00-06:00", "title": "Sales check", "kind": "scheduled"}]}
```

## Verify by looking, with a judge who is not you

The build prints **Report checks**: advice on walls of text, raw identifiers,
missing state, dates without a timeline, and progress without a target. Fix
each one or have a reason.

For the first report of an operation, and whenever its structure changes:

1. Capture it: `python3 -B <skill-directory>/scripts/capture_report.py report.html --out /tmp/report-shots`
   (desktop and phone, light and dark).
2. Open the images yourself, then give **only the images** to a fresh-context
   subagent (no JSON, no reasoning) with this prompt, unchanged each time:
   *"You run several projects and give this report under a minute. How many
   seconds does it take to answer: where does it stand, what changed, what
   must I do and by when, what happens next? Name the three biggest obstacles
   and one thing to remove."*
3. Fix what you agree with. Then remove one element that does not earn its
   place. Rebuild.

Routine versions with an unchanged structure need only the build checks.
Do not grade your own report: you see what you meant, not what is on screen.
