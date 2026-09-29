"""Fetch the current official Comprehensive Rules and record what changed (development only).

    python -m tools.rules_research.update                 # online: the official rules page
    python -m tools.rules_research.update --file CR.txt   # offline: a TXT you downloaded
    python -m tools.rules_research.update --no-bulletins  # skip update bulletin / release notes discovery

Stores ``data/rules/comprehensive_rules/<effective date>/`` (text, ``source.json``, SHA-256),
writes ``data/reports/rules_changes.md`` against the previous stored version, and records
newly discovered update bulletins and release notes in ``data/rules/bulletins.json``. Never
run by the app: game night works offline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from app.rules.research import RULES_DIR
from tools.rules_research import cr as crmod
from tools.rules_research import diff as diffmod
from tools.rules_research import store

RULES_PAGE = "https://magic.wizards.com/en/rules"
NEWS_PAGES = ("https://magic.wizards.com/en/news/announcements", "https://magic.wizards.com/en/news/feature")
USER_AGENT = "Fyodor-dev-rules-research/0.1 (offline Commander tabletop; developer tool)"
_TXT_LINK = re.compile(r"https://media\.wizards\.com/[^\"'<>]+?\.txt")
_NEWS_LINK = re.compile(r"/en/news/[a-z-]+/[a-z0-9-]*(?:update-bulletin|release-notes)[a-z0-9-]*")


def fetch(url: str, timeout: float = 60.0) -> bytes:
    quoted = urllib.parse.quote(url, safe=":/?&=%")
    req = urllib.request.Request(quoted, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - fixed official hosts
        data: bytes = res.read()
        return data


def find_txt_link(page_html: str) -> str | None:
    links = sorted(set(_TXT_LINK.findall(page_html)))
    return links[-1] if links else None  # names carry the date: the last is the newest


def discover_bulletins(pages: dict[str, str]) -> list[dict[str, str]]:
    found = {}
    for html in pages.values():
        for path in _NEWS_LINK.findall(html):
            slug = path.rsplit("/", 1)[-1]
            kind = "update_bulletin" if "update-bulletin" in slug else "release_notes"
            found[path] = {"url": "https://magic.wizards.com" + path, "kind": kind,
                           "title": slug.replace("-", " ").title()}
    return sorted(found.values(), key=lambda b: b["url"])


def record_bulletins(new: list[dict[str, str]], path: Path = store.BULLETINS) -> list[dict[str, str]]:
    known: list[dict[str, str]] = json.loads(path.read_text("utf-8")) if path.is_file() else []
    urls = {b["url"] for b in known}
    added = [dict(b, discovered=time.strftime("%Y-%m-%d")) for b in new if b["url"] not in urls]
    if added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known + added, indent=2) + "\n", "utf-8")
    return added


def ingest(text: str, *, source_url: str, root: Path = RULES_DIR, reports: Path = store.REPORTS_DIR,
           min_rules: int = 1000) -> dict[str, Any]:
    """Store a rules text if it is new and write the change report. Returns a summary."""
    parsed = crmod.parse(text)
    if parsed.effective is None or len(parsed.rules) < min_rules:
        raise ValueError("That doesn't look like the Comprehensive Rules text")
    digest = store.sha256(text)
    previous = store.latest(root)
    if previous and previous.get("sha256") == digest:
        return {"status": "unchanged", "effective_date": previous["effective_date"]}
    meta = {
        "source": "Wizards of the Coast — Magic: The Gathering Comprehensive Rules",
        "source_url": source_url, "rules_page": RULES_PAGE, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "effective_date": str(parsed.effective), "sha256": digest, "rules": len(parsed.rules),
        "glossary_terms": len(parsed.glossary), "previous": previous["effective_date"] if previous else None,
    }
    folder = store.save(text, meta, root)
    summary: dict[str, Any] = {"status": "stored", "effective_date": meta["effective_date"], "folder": str(folder)}
    if previous:
        old = crmod.parse((root / previous["dir"] / store.TEXT_NAME).read_text("utf-8"))
        d = diffmod.compare(old, parsed)
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "rules_changes.md").write_text(diffmod.markdown(d), "utf-8")
        summary.update(changes=len(d.changes), affected=sorted(d.affected_components()))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, help="use a downloaded Comprehensive Rules TXT instead of fetching")
    parser.add_argument("--url", help="fetch this TXT URL instead of discovering it on the rules page")
    parser.add_argument("--no-bulletins", action="store_true")
    args = parser.parse_args(argv)
    pages: dict[str, str] = {}
    if args.file:
        text, source = args.file.read_text("utf-8"), f"file:{args.file.name}"
    else:
        url = args.url
        if url is None:
            pages[RULES_PAGE] = fetch(RULES_PAGE).decode("utf-8", "replace")
            url = find_txt_link(pages[RULES_PAGE])
            if url is None:
                print("Couldn't find the TXT link on the rules page; pass --url or --file", file=sys.stderr)
                return 1
        text, source = fetch(url).decode("utf-8"), url
    summary = ingest(text, source_url=source)
    print(json.dumps(summary, indent=2))
    if not args.no_bulletins and not args.file:
        for page in NEWS_PAGES:
            try:
                pages[page] = fetch(page).decode("utf-8", "replace")
            except OSError as exc:
                print(f"(skipped {page}: {exc})", file=sys.stderr)
        added = record_bulletins(discover_bulletins(pages))
        for b in added:
            print(f"new {b['kind'].replace('_', ' ')}: {b['title']} — {b['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
