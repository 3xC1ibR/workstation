"""Render a conservative Markdown subset to escaped HTML with the standard library.

Supported: headings, paragraphs, nested lists, pipe tables, fenced code, block
quotes, rules, and inline code, emphasis, and links. Raw HTML is never passed
through. Link targets are resolved by the caller, which decides what is safe.
"""
from __future__ import annotations

import html
import re

FENCE = re.compile(r"\s{0,3}(```|~~~)")
HEADING = re.compile(r"\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"\s{0,3}([-*_])(\s*\1){2,}\s*$")
ITEM = re.compile(r"(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
TABLE_DIVIDER = re.compile(r"\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
INLINE = re.compile(
    r"(?P<code>`+)(?P<code_text>.+?)(?P=code)"
    r"|\[(?P<label>[^\]\n]+)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    r"|<(?P<auto>https?://[^>\s]+)>"
    r"|(?P<bare>(?:https?|agentcoord)://[^\s<>\"')\]]+)"
    r"|\*\*(?P<strong>[^*\n]+?)\*\*"
    r"|(?<![\w*])\*(?P<emphasis>[^*\n]+?)\*(?![\w*])"
    r"|(?<![\w_])_(?P<underscore>[^_\n]+?)_(?![\w_])")


def default_link(target):
    """Allow web addresses and Ribbon Field links; everything else stays text."""
    return target if re.match(r"(https?|agentcoord)://[^\s]+\Z", target) else None


def inline(text, resolve=default_link):
    output, position = [], 0
    for match in INLINE.finditer(text):
        output.append(html.escape(text[position:match.start()], quote=False))
        position = match.end()
        if match["code"]:
            output.append("<code>" + html.escape(match["code_text"].strip(), quote=False) + "</code>")
        elif match["label"] is not None:
            address = resolve(match["target"])
            label = inline(match["label"], lambda _target: None)
            output.append(f'<a href="{html.escape(address, quote=True)}" rel="noreferrer">{label}</a>' if address
                          else f'{label} <code>{html.escape(match["target"], quote=False)}</code>')
        elif match["auto"] or match["bare"]:
            address = (match["auto"] or match["bare"]).rstrip(".,;:")
            position -= len(match["bare"] or "") - len(address) if match["bare"] else 0
            escaped = html.escape(address, quote=True)
            label = "Open in Ribbon Field" if address.startswith("agentcoord://") else escaped
            output.append(f'<a href="{escaped}" rel="noreferrer">{label}</a>')
        elif match["strong"] is not None:
            output.append("<strong>" + inline(match["strong"], resolve) + "</strong>")
        else:
            output.append("<em>" + inline(match["emphasis"] or match["underscore"], resolve) + "</em>")
    output.append(html.escape(text[position:], quote=False))
    return "".join(output)


def cells(line):
    line = line.strip()
    line = line[1:] if line.startswith("|") else line
    line = line[:-1] if line.endswith("|") and not line.endswith("\\|") else line
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]


def render(text, resolve=default_link):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n")
    output, index = [], 0

    def paragraph(buffer):
        if buffer:
            output.append("<p>" + "<br>".join(inline(line.strip(), resolve) for line in buffer) + "</p>")
            buffer.clear()

    def list_block(start):
        """Render consecutive list items; deeper indentation nests a list."""
        stack, position = [], start      # entries: (indent, tag)
        while position < len(lines):
            match = ITEM.match(lines[position])
            if not match:
                if lines[position].strip() and stack and len(lines[position]) - len(lines[position].lstrip()) > stack[-1][0]:
                    output.append(" " + inline(lines[position].strip(), resolve))     # continuation line
                    position += 1
                    continue
                if (not lines[position].strip() and position + 1 < len(lines) and ITEM.match(lines[position + 1])
                        and stack and len(ITEM.match(lines[position + 1])[1]) >= stack[0][0]):
                    position += 1
                    continue
                break
            indent, tag = len(match[1]), "ul" if match[2] in "-*+" else "ol"
            while stack and indent < stack[-1][0]:
                output.append(f"</li></{stack.pop()[1]}>")
            if stack and indent == stack[-1][0]:
                output.append("</li>")
            if not stack or indent > stack[-1][0]:
                stack.append((indent, tag))
                output.append(f"<{tag}>")
            output.append("<li>" + inline(match[3].strip(), resolve))
            position += 1
        while stack:
            output.append(f"</li></{stack.pop()[1]}>")
        return position

    buffer = []
    while index < len(lines):
        line = lines[index]
        fence = FENCE.match(line)
        if fence:
            paragraph(buffer)
            index += 1
            code = []
            while index < len(lines) and not lines[index].strip().startswith(fence[1]):
                code.append(lines[index])
                index += 1
            index += 1
            output.append("<pre><code>" + html.escape("\n".join(code), quote=False) + "</code></pre>")
        elif not line.strip():
            paragraph(buffer)
            index += 1
        elif HEADING.match(line):
            paragraph(buffer)
            match = HEADING.match(line)
            level = min(len(match[1]) + 1, 6)       # the page title owns <h1>
            output.append(f"<h{level}>{inline(match[2], resolve)}</h{level}>")
            index += 1
        elif RULE.match(line):
            paragraph(buffer)
            output.append("<hr>")
            index += 1
        elif "|" in line and index + 1 < len(lines) and TABLE_DIVIDER.match(lines[index + 1]) and "-" in lines[index + 1]:
            paragraph(buffer)
            heading = cells(line)
            index += 2
            output.append('<div class="table-region" tabindex="0" role="region" aria-label="Table"><table><thead><tr>'
                          + "".join(f'<th scope="col">{inline(cell, resolve)}</th>' for cell in heading) + "</tr></thead><tbody>")
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                row = (cells(lines[index]) + [""] * len(heading))[:len(heading)]
                output.append("<tr>" + "".join(f"<td>{inline(cell, resolve)}</td>" for cell in row) + "</tr>")
                index += 1
            output.append("</tbody></table></div>")
        elif line.lstrip().startswith(">"):
            paragraph(buffer)
            quoted = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            output.append("<blockquote>" + render("\n".join(quoted), resolve) + "</blockquote>")
        elif ITEM.match(line):
            paragraph(buffer)
            index = list_block(index)
        else:
            buffer.append(line)
            index += 1
    paragraph(buffer)
    return "\n".join(output)
