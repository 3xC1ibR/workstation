"""Existing research reader presentation, independent of publication state."""
import html
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from markdown_it import MarkdownIt

BASE = "/reader/"

MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


CSS = """
:root{color-scheme:light dark;--bg:#faf9f6;--fg:#242424;--muted:#646462;--line:#deddd7;--panel:#f0efe9;--link:#1855b0}
@media(prefers-color-scheme:dark){:root{--bg:#18181b;--fg:#e9e8e4;--muted:#aaa9a3;--line:#39393d;--panel:#252529;--link:#97bfff}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:1rem}
body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
main{max-width:56rem;margin:auto;padding:1.5rem max(1.1rem,env(safe-area-inset-right)) 5rem max(1.1rem,env(safe-area-inset-left))}
a{color:var(--link);text-underline-offset:.16em;overflow-wrap:anywhere}a:focus-visible{outline:3px solid var(--link);outline-offset:4px}
nav{font-size:.93rem;display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1.5rem}nav a{padding:.3rem 0}
h1,h2,h3,h4{line-height:1.25;letter-spacing:-.025em;overflow-wrap:anywhere}h1{font-size:clamp(1.8rem,5vw,2.6rem);margin:.6rem 0 1rem}h2{font-size:1.5rem;margin-top:2.3rem}h3{font-size:1.2rem;margin-top:1.7rem}
p,li{overflow-wrap:anywhere}li+li{margin-top:.45rem}ul,ol{padding-left:1.5rem}
.meta,footer{color:var(--muted);font-size:.88rem}.cards{list-style:none;padding:0}.cards li{margin:.75rem 0}.cards a{display:block;padding:1rem 1.15rem;border:1px solid var(--line);border-radius:.75rem;text-decoration:none}.cards a:hover{background:var(--panel)}.cards strong{display:block;font-size:1.08rem}.cards span{display:block;margin-top:.3rem;color:var(--muted);font-size:.85rem}
table{border-collapse:collapse;font-size:.88rem;line-height:1.55;min-width:100%}.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:1.4rem 0;border:1px solid var(--line);border-radius:.4rem}.table-scroll:focus-visible{outline:2px solid var(--link)}th,td{text-align:left;vertical-align:top;padding:.7rem .8rem;border-bottom:1px solid var(--line);min-width:10rem}th{background:var(--panel)}tr:last-child td{border-bottom:0}
code{font: .86em ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--panel);padding:.12em .3em;border-radius:.2em;overflow-wrap:anywhere}pre{overflow:auto;padding:1rem;background:var(--panel);border-radius:.5rem;line-height:1.55}pre code{padding:0;white-space:pre;overflow-wrap:normal}
blockquote{border-left:3px solid var(--line);margin:1rem 0;padding:.1rem 1rem;color:var(--muted)}hr{border:0;border-top:1px solid var(--line);margin:2rem 0}img{max-width:100%;height:auto}details{border:1px solid var(--line);border-radius:.5rem;padding:.7rem 1rem}summary{cursor:pointer}details ol{font-size:.92rem}.local-reference{color:var(--muted)}footer{border-top:1px solid var(--line);margin-top:3rem;padding-top:1rem}
@media print{nav,details,footer{display:none}body{font-size:11pt;background:white;color:black}main{max-width:none}.table-scroll{overflow:visible}a{color:inherit}pre{white-space:pre-wrap}}
"""


def page(title, body, nav="", refresh=False):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            + ('<meta http-equiv="refresh" content="60">' if refresh else '')
            + f"<title>{html.escape(title)} · Research reader</title><style>{CSS}</style></head>"
            + f'<body><main id="top"><nav><a href="{BASE}">All research</a>{nav}</nav>{body}'
            + '<footer><a href="#top">Back to top</a></footer></main></body></html>')


def render(path, text, available):
    tokens = MD.parse(text)
    headings = []
    used = {}
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            label = tokens[i + 1].content
            slug = re.sub(r"[^\w\- ]", "", label.lower()).strip().replace(" ", "-") or "section"
            used[slug] = used.get(slug, 0) + 1
            anchor = slug + (f"-{used[slug]}" if used[slug] > 1 else "")
            token.attrSet("id", anchor)
            if token.tag in ("h2", "h3"):
                headings.append(f'<li><a href="#{anchor}">{html.escape(label)}</a></li>')
        for child in token.children or []:
            if child.type != "link_open":
                continue
            url = child.attrGet("href") or ""
            parts = urlsplit(url)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            local = (path.parent / unquote(parts.path)).resolve()
            if local in available:
                child.attrSet("href", urlunsplit(("", "", available[local], parts.query, parts.fragment)))
            elif parts.path.startswith("/opt/projects/") or parts.path.endswith(".md"):
                # Keep local citations legible without sending iPad readers to nonexistent web paths.
                child.tag = "span"
                child.type = "html_inline"
                child.content = '<span class="local-reference" title="Reference file on the Mac: ' + html.escape(str(local), quote=True) + '">'
                # The matching closing token must also become a span.
                depth = 0
                children = token.children
                for following in children[children.index(child) + 1:]:
                    if following.type == "link_open":
                        depth += 1
                    if following.type == "link_close":
                        if depth == 0:
                            following.type = "html_inline"
                            following.content = "</span>"
                            break
                        depth -= 1
    body = MD.renderer.render(tokens, MD.options, {})
    body = body.replace("<table>", '<div class="table-scroll" role="region" aria-label="Report table; swipe to scroll" tabindex="0"><table>')
    body = body.replace("</table>", "</table></div>")
    if headings:
        toc = '<details><summary>Contents</summary><ol>' + "".join(headings) + '</ol></details>'
        # Put the contents after the report title.
        closing = body.find("</h1>")
        body = body[:closing + 5] + toc + body[closing + 5:] if closing >= 0 else toc + body
    return body
