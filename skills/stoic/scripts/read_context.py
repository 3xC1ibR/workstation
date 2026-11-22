"""Read the current Stoic account instructions, context and API reference."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ORIGIN = "https://tryblume.ai"
LOADING_PATH = "/api/agent-instructions/loading/text"
TOPICS = {
    "evidence": "behavior, health, habits, priorities, plans and retrospectives",
    "sources": "finding or interpreting personal data and checking coverage",
    "memory": "saving, correcting or forgetting shared personal context",
    "projects": "project strategy, outcomes, decisions and milestones",
    "programs": "continuing responsibilities, schedules and follow-ups",
    "writes": "note and record authorship, admin tools, timers and insights",
    "health": "health reporting, sharing and consent",
    "health-client": "implementing a health integration client",
    "execution": "implementing an external job executor",
    "events": "implementing an event listener",
}

# Identify reviewed paragraphs of the published loading_v1.md by hashing their
# heading, a newline and the verbatim paragraph. Live text is always the source.
# An edit to the paragraph or its heading makes it visible in full at startup.
PARAGRAPH_TOPICS = {
    "f43f1a7726938b2156034a54121ee9a61af316392829f6c16e5fbbab19215ef4": "start",
    "24a1541d25053be05c2a580cc8fecb6b12d462ed2979901ec25893ceeb3fb2f2": "start",
    "1d3d6bd24f1d44a487a3b5d50262ec2f367cbf0a8f55de3dbcd73dd265bba1d7": "start",
    "9b0e47885a7d3d577ebeb2b753694efe881072a26ee499f848c14d40d5ae4753": "evidence",
    "a156f152d40b51006919ee451b36b281c50d4d082ad02c5f9f19744721138c20": "evidence",
    "7dbaa710a230b1e03ebd5ee5414609c3b867db08de58ed73a9acf8005f728ba7": "sources",
    "f9e14f9af140d566c7394c00b85c48821e2fb152e8e92b8c8f0d8b6c785c35eb": "memory",
    "71e839337272ff40a7d8056b62ff6488febb703eac5fc43badb345abeb48ef67": "projects",
    "5125cd05843f97b12fb82b7c683130fbdf3fcb2416211aa72498e6c12c5400f5": "projects",
    "af683443c39fca139fab721b360e3de8544cdf9762cd6e733c80424aeb33db8d": "programs",
    "cdd956f80f593abc9ddf37e3618ba622c7e3e97ace1a6ae74fcb096c0787c865": "writes",
    "53c498c608afcc7843774d65f35947ad2d9ffca561433216c5f7e6fad75b750f": "writes",
    "6d7001227da06b6d5338fb676009ea081eb25937f7cc1d3f68cff1ec582d9ceb": "health",
    "700ca9f34509c2fbc93bd088687836514ac1c90a3589875a399200e7e9bcf605": "health-client",
    "9b2f954a9bcf40c9af77382baaecc501103108d0eef19937ea293b5b89e67cec": "execution",
    "48c86d12ea153f97c48549dc18e700c2bd9fe3003be024afc38cc494482af63b": "events",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def agent_token():
    value = os.environ.get("STOIC_API_TOKEN")
    if not value:
        path = os.environ.get("STOIC_API_TOKEN_FILE") or "~/.config/stoic/codex-token"
        try:
            value = Path(path).expanduser().read_text()
        except FileNotFoundError:
            raise ValueError("Stoic agent credential is missing.") from None
    value = value.strip()
    if not value:
        raise ValueError("Stoic agent credential is empty.")
    if not re.fullmatch(r"[!-~]+", value):
        raise ValueError("Stoic agent credential contains invalid characters.")
    return value


def read_api(path, token=None, body=None):
    request = Request(ORIGIN + path, data=body)
    if token:
        request.add_header("Authorization", "Bearer " + token)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with build_opener(NoRedirect).open(request, timeout=20) as response:
        return response.read().decode("utf-8")


def select_instructions(document, requested):
    """Show owner additions and edits on startup and on subsequent topic reads."""
    visible = []
    available = set()
    parts = re.split(r"^(#{1,6} [^\n]+)$", document, flags=re.MULTILINE)
    active = requested or {"start"}
    for heading, body in zip(["", *parts[1::2]], parts[::2]):
        selected = []
        for block in re.split(r"\n[ \t]*\n", body.strip("\n")):
            if not block:
                continue
            digest = hashlib.sha256((heading + "\n" + block).encode()).hexdigest()
            topic = PARAGRAPH_TOPICS.get(digest)
            if topic in TOPICS:
                available.add(topic)
            if topic is None or topic in active:
                selected.append(block)
        if selected or not body.strip():
            visible.extend(part for part in [heading, *selected] if part)
    if requested - available:
        visible.append("No separate instructions for " + ", ".join(sorted(requested - available)) + ".")
    if not requested and available:
        descriptions = [f"  {name} — {description}" for name, description in TOPICS.items() if name in available]
        visible.append("Read applicable instructions with topic NAME [NAME ...]\n" + "\n".join(descriptions))
    return "\n\n".join(visible)


def display_context(bundle):
    # The app embeds named JSON sections inside a string. Decode the envelope
    # before displaying it. Unknown formats and fields pass through intact.
    context = bundle.get("context")
    if isinstance(context, str):
        match = re.fullmatch(r"<context_sections>\s*(.*?)\s*</context_sections>", context, re.DOTALL)
        if match:
            try:
                sections = json.loads(match[1])
            except ValueError:
                sections = None
            if isinstance(sections, dict):
                memory = bundle.get("long_term_memory")
                content = memory.get("content") if isinstance(memory, dict) else None
                rendered = sections.get("long_term_memory")
                if isinstance(content, str) and content and isinstance(rendered, str) and content in rendered:
                    sections["long_term_memory"] = rendered.replace(content, "[see long_term_memory.content]", 1)
                bundle = {**bundle, "context": sections}
    return json.dumps(bundle, ensure_ascii=False, indent=2)


def guide_section(guide, query):
    headings = list(re.finditer(r"^## ([^\n]+)$", guide, re.MULTILINE))
    titles = [heading[1] for heading in headings]
    if not titles:
        raise ValueError("Guide headings unavailable. Read /llms.txt directly.")
    if not query:
        return "\n".join(titles)
    exact = [index for index, title in enumerate(titles) if query.casefold() == title.casefold()]
    matches = exact or [index for index, title in enumerate(titles) if query.casefold() in title.casefold()]
    if len(matches) != 1:
        raise ValueError("Choose one API section:\n" + "\n".join(titles[i] for i in matches or range(len(titles))))
    index = matches[0]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(guide)
    return guide[headings[index].start():end].strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start", help="read current instructions and personal context")
    commands.add_parser("topic", help="read instructions for a task").add_argument(
        "topics", nargs="+", choices=TOPICS
    )
    commands.add_parser("api", help="list or read API guide sections").add_argument("section", nargs="?")
    args = parser.parse_args()
    if args.command == "api":
        print(guide_section(read_api("/llms.txt"), args.section))
        return
    token = agent_token()
    instructions = read_api(LOADING_PATH, token)
    if args.command == "topic":
        print(select_instructions(instructions, set(args.topics)))
        return
    bundle = json.loads(read_api("/api/assistant/context", token, b"{}"))
    print(select_instructions(instructions, set()))
    print("\nPersonal context\n" + display_context(bundle))


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        hint = {401: " Check the credential and sign in again if expired.", 403: " Check account permissions."}
        sys.exit(f"Stoic returned HTTP {error.code}.{hint.get(error.code, '')}")
    except (OSError, URLError, ValueError) as error:
        sys.exit(f"Stoic read failed: {error}")
