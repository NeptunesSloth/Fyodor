"""Parse the Comprehensive Rules TXT into numbered rules, examples and glossary entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# "100.", "100.1.", "100.1a" (subrule letters skip l and o), "1." sections
_RULE = re.compile(r"^(?P<num>\d{3}\.\d+[a-z]?|\d{3})\.?\s+(?P<text>.+)$")
_SECTION = re.compile(r"^(?P<num>\d)\.\s+(?P<title>.+)$")
_EFFECTIVE = re.compile(r"These rules are effective as of (?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})")


@dataclass
class Rule:
    number: str  # "702.2", "702.2a", "702"
    text: str
    examples: list[str] = field(default_factory=list)

    @property
    def parent(self) -> str | None:
        if re.fullmatch(r"\d{3}\.\d+[a-z]", self.number):
            return self.number[:-1]
        if re.fullmatch(r"\d{3}\.\d+", self.number):
            return self.number.split(".")[0]
        return None

    @property
    def chapter(self) -> str:
        return self.number[:3]

    def full_text(self) -> str:
        return "\n".join([self.text, *self.examples])


@dataclass
class ComprehensiveRules:
    effective: date | None
    sections: dict[str, str]  # "7" -> "Additional Rules"
    rules: dict[str, Rule]  # in document order
    glossary: dict[str, str]

    def title(self, number: str) -> str:
        """The heading a rule belongs to: "704.5k" → "State-Based Actions"; keyword abilities and
        keyword actions use their own heading ("702.2a" → "Deathtouch")."""
        chapter = number[:3]
        if chapter in ("701", "702") and "." in number:
            head = self.rules.get(chapter + "." + re.sub(r"[a-z]$", "", number.split(".")[1]))
            if head is not None:
                return head.text
        head = self.rules.get(chapter)
        return head.text if head else ""


def _clean(line: str) -> str:
    return line.replace(" ", " ").strip()


def parse(text: str) -> ComprehensiveRules:
    text = text.lstrip("﻿")
    lines = [_clean(line) for line in text.splitlines()]
    m = _EFFECTIVE.search(text)
    effective = datetime.strptime(m.group("date"), "%B %d, %Y").date() if m else None
    # The body starts at the second "1. Game Concepts" (the first is the table of contents).
    starts = [i for i, line in enumerate(lines) if line == "1. Game Concepts"]
    body_start = starts[1] if len(starts) > 1 else (starts[0] if starts else 0)
    glossary_at = [i for i, line in enumerate(lines) if line == "Glossary" and i > body_start]
    credits_at = [i for i, line in enumerate(lines) if line == "Credits" and i > body_start]
    body_end = glossary_at[0] if glossary_at else len(lines)
    sections: dict[str, str] = {}
    rules: dict[str, Rule] = {}
    current: Rule | None = None
    for line in lines[body_start:body_end]:
        if not line:
            continue
        sec = _SECTION.match(line)
        if sec and not _RULE.match(line):
            sections[sec.group("num")] = sec.group("title")
            current = None
            continue
        rm = _RULE.match(line)
        if rm:
            current = Rule(rm.group("num"), rm.group("text").strip())
            rules[current.number] = current
        elif current is not None and line.startswith("Example:"):
            current.examples.append(line)
        elif current is not None:
            current.text += "\n" + line  # a continuation line
    glossary: dict[str, str] = {}
    if glossary_at:
        end = credits_at[0] if credits_at else len(lines)
        block: list[str] = []
        for line in [*lines[glossary_at[0] + 1:end], ""]:
            if line:
                block.append(line)
            elif block:
                glossary[block[0]] = " ".join(block[1:])
                block = []
    return ComprehensiveRules(effective=effective, sections=sections, rules=rules, glossary=glossary)
