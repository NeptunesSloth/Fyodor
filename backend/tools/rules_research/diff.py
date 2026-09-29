"""Compare two Comprehensive Rules versions and say which parts of Fyodor they may affect."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from tools.rules_research.cr import ComprehensiveRules

# Which rules chapters (or single rules) the engine's modules implement. Used to point a rules
# change at the code and tests to review; kept here (a developer tool), not in engine code.
IMPACT: dict[str, list[str]] = {
    "106": ["app/rules/mana.py", "app/rules/casting.py"],
    "107": ["app/rules/mana.py", "app/rules/costs.py"],
    "110": ["app/game/rules_state.py (object identity)"],
    "113": ["app/rules/oracle.py", "app/rules/coverage.py"],
    "115": ["targeting (M16)"],
    "116": ["app/rules/engine.py (special actions: play_land)"],
    "117": ["app/rules/engine.py (priority, is_stop, advance)"],
    "118": ["app/rules/costs.py", "app/rules/casting.py (payment)"],
    "119": ["app/game/handlers/players.py (life)"],
    "120": ["app/rules/combat.py (damage)", "app/game/handlers/rules.py (rules_damage)"],
    "122": ["app/game/handlers/players.py (player counters)", "app/rules/sba.py"],
    "205": ["app/rules/characteristics.py (type line)"],
    "400": ["app/game/rules_state.py (zone changes, object identity, LKI)", "app/game/ops.py (move_card)"],
    "500": ["app/rules/engine.py (turn structure)"], "501": ["app/rules/engine.py"], "502": ["app/rules/engine.py (untap)"],
    "503": ["app/rules/engine.py (upkeep)"], "504": ["app/rules/engine.py (draw)"], "505": ["app/rules/engine.py (main)"],
    "506": ["app/rules/combat.py"], "507": ["app/rules/combat.py"], "508": ["app/rules/combat.py (attackers)"],
    "509": ["app/rules/combat.py (blockers)"], "510": ["app/rules/combat.py (combat damage)"],
    "511": ["app/rules/combat.py (end of combat)"], "513": ["app/rules/engine.py (end step)"],
    "514": ["app/rules/engine.py (cleanup)"],
    "601": ["app/rules/casting.py (casting)"], "602": ["app/rules/casting.py (activating)"],
    "603": ["triggers (M16)"], "605": ["app/rules/mana.py (mana abilities)", "app/rules/casting.py"],
    "608": ["app/rules/engine.py (resolving)"], "609": ["effects (M16)"], "611": ["continuous effects (M16)"],
    "613": ["layers (M16)"], "614": ["replacement effects (M16)"], "615": ["prevention (M16)"],
    "700": ["app/rules/oracle.py"], "701": ["keyword actions (M16)"], "702": ["keywords: app/rules/combat.py, coverage.SUPPORTED_KEYWORDS"],
    "704": ["app/rules/sba.py"], "706": ["copies (M16)"], "707": ["copies (M16)"], "708": ["face-down (app/game/ops.py)"],
    "709": ["app/rules/characteristics.py (split cards)"], "712": ["app/rules/characteristics.py (double-faced)"],
    "715": ["app/rules/characteristics.py (adventures)"],
    "800": ["app/rules/leave.py (leaving the game)", "app/rules/plan.py (turn order)"],
    "802": ["attack multiple players: app/rules/combat.py"], "903": ["commander: casting.py, sba.py, deck checks"],
}

CATEGORY_BY_CHAPTER = [
    (("702",), "KEYWORD"), (("701",), "KEYWORD ACTION"), (("903",), "COMMANDER CHANGE"),
    (("506", "507", "508", "509", "510", "511"), "COMBAT CHANGE"), (("118", "601", "602"), "COST CHANGE"),
    (("400", "401", "402", "403", "404", "405", "406", "407", "408"), "ZONE CHANGE"),
    (("704",), "STATE-BASED ACTION CHANGE"), (("613", "706", "707"), "COPY/LAYER CHANGE"),
]


def category(number: str) -> str:
    chapter = number[:3]
    for chapters, name in CATEGORY_BY_CHAPTER:
        if chapter in chapters:
            return name
    return "OTHER"


@dataclass
class Change:
    kind: str  # NEW RULE / REMOVED RULE / MODIFIED RULE (and NEW KEYWORD / NEW KEYWORD ACTION)
    number: str
    category: str
    heading: str
    before: str = ""
    after: str = ""


@dataclass
class RulesDiff:
    old_version: str
    new_version: str
    changes: list[Change] = field(default_factory=list)
    glossary_added: list[str] = field(default_factory=list)
    glossary_removed: list[str] = field(default_factory=list)

    def affected_components(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for c in self.changes:
            for comp in IMPACT.get(c.number[:3], []):
                out.setdefault(comp, []).append(c.number)
        return out


def _norm(text: str) -> str:
    return " ".join(text.split())


def compare(old: ComprehensiveRules, new: ComprehensiveRules) -> RulesDiff:
    """Rule-by-rule comparison. Renumbering shows up as a removal plus an addition; a rule whose
    text is identical after whitespace normalisation is not a change."""
    diff = RulesDiff(str(old.effective), str(new.effective))
    for num, rule in new.rules.items():
        heading = new.title(num)
        if num not in old.rules:
            kind = "NEW RULE"
            if num.count(".") == 1 and not num[-1].isalpha() and num[:3] in ("701", "702"):
                kind = "NEW KEYWORD ACTION" if num.startswith("701") else "NEW KEYWORD"
            diff.changes.append(Change(kind, num, category(num), heading, after=rule.full_text()))
        elif _norm(old.rules[num].full_text()) != _norm(rule.full_text()):
            diff.changes.append(Change("MODIFIED RULE", num, category(num), heading,
                                       before=old.rules[num].full_text(), after=rule.full_text()))
    for num, rule in old.rules.items():
        if num not in new.rules:
            diff.changes.append(Change("REMOVED RULE", num, category(num), old.title(num), before=rule.full_text()))
    diff.glossary_added = sorted(set(new.glossary) - set(old.glossary))
    diff.glossary_removed = sorted(set(old.glossary) - set(new.glossary))
    return diff


def markdown(diff: RulesDiff, *, card_counts: dict[str, int] | None = None, limit: int = 400) -> str:
    """``data/reports/rules_changes.md``. ``card_counts`` (keyword → Commander-legal cards) adds
    how many cards a keyword change may touch."""
    lines = [f"# Comprehensive Rules changes: {diff.old_version} → {diff.new_version}", ""]
    if not diff.changes and not diff.glossary_added and not diff.glossary_removed:
        return "\n".join([*lines, "No rule text changed.", ""])
    by_kind: dict[str, int] = {}
    for c in diff.changes:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    lines += ["| Change | Rules |", "|---|---|", *[f"| {k} | {n} |" for k, n in sorted(by_kind.items())], ""]
    affected = diff.affected_components()
    if affected:
        lines += ["## Rules update impact", "", "Engine components to review (and their tests):", ""]
        for comp, nums in sorted(affected.items()):
            lines.append(f"- **{comp}** — {', '.join(sorted(set(nums))[:15])}{' …' if len(set(nums)) > 15 else ''}")
        lines.append("")
    lines += ["## Changes", ""]
    for c in diff.changes[:limit]:
        count = ""
        if card_counts and c.category == "KEYWORD":
            n = card_counts.get(c.heading.lower())
            count = f" — Commander-legal cards with it: {n}" if n is not None else ""
        lines.append(f"### {c.kind}: {c.number} ({c.heading}) — {c.category}{count}")
        if c.kind == "MODIFIED RULE":
            delta = difflib.unified_diff(c.before.splitlines(), c.after.splitlines(), lineterm="", n=0)
            lines += ["```diff", *[d for d in delta if not d.startswith(("---", "+++", "@@"))], "```"]
        else:
            lines += ["", "> " + (c.after or c.before).replace("\n", "\n> ")]
        lines.append("")
    if len(diff.changes) > limit:
        lines.append(f"… and {len(diff.changes) - limit} more.")
    if diff.glossary_added or diff.glossary_removed:
        lines += ["## Glossary", "", f"Added: {', '.join(diff.glossary_added) or '—'}",
                  f"Removed: {', '.join(diff.glossary_removed) or '—'}", ""]
    return "\n".join(lines)
