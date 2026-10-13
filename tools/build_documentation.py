#!/usr/bin/env python3
"""Build/check START_HERE.html: a deterministic, fully offline Markdown handbook.

Markdown is canonical; docs/_site contains only the renderer's presentation.
Run: python tools/build_documentation.py [--check] [--root PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
import base64
from collections.abc import Callable
from html import escape, unescape
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import posixpath
import sys
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

ROOT = Path(__file__).resolve().parents[1]
AUDIENCES = ("user", "development", "reference", "archive")
ASSETS = ROOT / "docs" / "_site"


def slug(text: str) -> str:
    """GitHub heading anchors retain Unicode letters and duplicate suffixes."""
    return "".join(c for c in text.lower() if c in "-_ " or unicodedata.category(c)[0] in "LN").replace(" ", "-")


def inline_text(token: Token) -> str:
    if token.children is None:
        return token.content
    return "".join(child.content if child.type not in ("softbreak", "hardbreak") else " " for child in token.children if child.type in ("text", "code_inline", "image", "softbreak", "hardbreak"))


def route(path: str, anchor: str = "") -> str:
    return "#/" + quote(path, safe="/") + ("@" + quote(anchor, safe="") if anchor else "")


class HTMLProjection(HTMLParser):
    """Inspect rendered/raw HTML ids and rewrite links without losing markup."""

    def __init__(self, resolve: Callable[[str, bool], str] | None = None):
        super().__init__(convert_charrefs=False)
        self.resolve = resolve
        self.ids: set[str] = set()
        self.parts: list[str] = []
        self.text: list[str] = []

    ALLOWED_TAGS = frozenset("a p div span h1 h2 h3 h4 h5 h6 ul ol li pre code table thead tbody tfoot tr td th blockquote hr br img details summary em strong s del sup sub kbd samp b i dl dt dd section figure figcaption".split())
    ALLOWED_ATTRS = frozenset("id name href src alt title class colspan rowspan align start width height".split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.ALLOWED_TAGS:
            return
        updated = []
        for name, value in attrs:
            if name not in self.ALLOWED_ATTRS:
                continue
            if value and (name == "id" or (tag == "a" and name == "name")):
                self.ids.add(value)
            if self.resolve and ((tag == "a" and name == "href") or (tag == "img" and name == "src")) and value:
                value = self.resolve(value, tag == "img")
            updated.append(" " + name + (f'="{escape(value, quote=True)}"' if value is not None else ""))
        self.parts.append("<" + tag + "".join(updated) + ">")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.ALLOWED_TAGS:
            return
        self.handle_starttag(tag, attrs)
        self.parts[-1] = self.parts[-1][:-1] + " />"

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ALLOWED_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data, quote=False))
        self.text.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")
        self.text.append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")
        self.text.append(unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")


def collect_pages(root: Path) -> list[dict]:
    resolved_root = root.resolve()
    markdown = MarkdownIt("commonmark", {"html": True}).enable("table")
    files = sorted(p for audience in AUDIENCES for p in (root / "docs" / audience).rglob("*.md") if p.name != "FOLDER_DOCS_RU.md")
    # Root policies and any retained top-level guides remain readable inside the book.
    files += [root / name for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "LICENSE_RU.md") if (root / name).is_file()]
    if (root / "docs/README_RU.md").is_file():
        files.append(root / "docs/README_RU.md")
    pages = []
    ids = {}
    for path in files:
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError(f"Documentation source escapes repository: {path}")
        relative = path.relative_to(root).as_posix()
        audience = relative.split("/")[1] if relative.startswith("docs/") and relative.split("/")[1] in AUDIENCES else ("user" if path.name in ("README.md", "LICENSE_RU.md", "README_RU.md") else "development")
        tokens = markdown.parse(path.read_bytes().decode("utf-8"))
        title = path.stem
        toc = []
        seen = set()
        first_heading = True
        for index, token in enumerate(tokens):
            if token.type != "heading_open":
                continue
            text = inline_text(tokens[index + 1])
            base = slug(text)
            anchor = base
            suffix = 0
            while anchor in seen:
                suffix += 1
                anchor = f"{base}-{suffix}"
            seen.add(anchor)
            token.attrSet("id", anchor)
            if first_heading:
                title = text
                first_heading = False
            if token.tag != "h1":
                toc.append({"id": anchor, "title": text, "level": int(token.tag[1])})
        rendered = markdown.renderer.render(tokens, markdown.options, {})
        inspector = HTMLProjection()
        inspector.feed(rendered)
        ids[relative] = inspector.ids
        pages.append({"path": relative, "audience": audience, "title": title, "html": rendered, "text": "".join(inspector.text), "toc": toc})

    errors = []
    for page in pages:
        def resolve(link: str, image: bool = False) -> str:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                if image and parsed.scheme != "data":
                    errors.append(f"{page['path']}: remote image is not offline: {link}")
                if parsed.scheme.lower() not in ("http", "https", "mailto", "data"):
                    errors.append(f"{page['path']}: unsafe link {link}")
                return link
            target = posixpath.normpath(posixpath.join(posixpath.dirname(page["path"]), unquote(parsed.path))) if parsed.path else page["path"]
            anchor = unquote(parsed.fragment)
            if target.startswith("../") or target.startswith("/") or not (root / target).resolve().is_relative_to(resolved_root):
                errors.append(f"{page['path']}: link escapes repository: {link}")
                return "#"
            elif target in ids and not image:
                if anchor and anchor not in ids[target]:
                    errors.append(f"{page['path']}: missing anchor: {link}")
                return route(target, anchor)
            elif target == "START_HERE.html":
                start = "docs/user/START_RU.md" if "docs/user/START_RU.md" in ids else pages[0]["path"]
                return route(start)
            elif not (root / target).exists():
                errors.append(f"{page['path']}: missing file: {link}")
            if image and (root / target).is_file():
                mime = mimetypes.guess_type(target)[0] or "application/octet-stream"
                return f"data:{mime};base64," + base64.b64encode((root / target).read_bytes()).decode("ascii")
            return quote(target, safe="/") + ("?" + parsed.query if parsed.query else "") + ("#" + quote(anchor, safe="") if anchor else "")
        projection = HTMLProjection(resolve)
        projection.feed(page["html"])
        page["html"] = "".join(projection.parts)
    if errors:
        raise ValueError("Documentation link errors:\n" + "\n".join(errors))
    return pages


def build(root: Path = ROOT) -> str:
    pages = collect_pages(Path(root))
    # Never allow Markdown to terminate the inert JSON script element.
    data = json.dumps({"pages": pages}, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (ASSETS / "book.html").read_bytes().decode("utf-8")
    for marker, content in (
        ("/*__BOOK_CSS__*/", (ASSETS / "book.css").read_bytes().decode("utf-8")),
        ("/*__BOOK_JS__*/", (ASSETS / "book.js").read_bytes().decode("utf-8")),
        ("/*__BOOK_DATA__*/", data),
    ):
        template = template.replace(marker, content)
    return template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Canonical Markdown/project root")
    parser.add_argument("--output", type=Path, help="Output HTML (default: ROOT/START_HERE.html); file links remain relative to project root")
    parser.add_argument("--check", action="store_true", help="Fail if HTML is absent/stale; write nothing")
    args = parser.parse_args(argv)
    output = args.output or args.root / "START_HERE.html"
    try:
        content = build(args.root).encode("utf-8")
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.check:
        if not output.is_file() or output.read_bytes() != content:
            print(f"Stale offline handbook: {output}; run tools/build_documentation.py", file=sys.stderr)
            return 1
        print(f"Offline handbook is fresh: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    print(f"Built offline handbook: {output} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
