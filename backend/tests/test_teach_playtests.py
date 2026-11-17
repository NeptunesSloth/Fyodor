"""-- Teach Fyodor -- play tests of the expressiveness sweep (docs/TEACH_FYODOR_COVERAGE.md): for each mechanic, a card with the taught
name ("Neoprowess", taught as tests/teach_coverage.py rebuilds it) and a card with the native keyword play the same scenario on two
tables, and the tables must end the same (life, zones, counters, power and toughness, what was legal). Each table is also replayed
and saved and loaded (``check``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from app.game.errors import ActionError
from app.rules import coverage, sba, taught
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.teach_coverage import ROWS, S, T, b
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

ROW = {r.name: r for r in ROWS}


@dataclass
class Case:
    id: str  # the test id ("Menace (two blockers)")
    row: str  # the mechanic's row in tests/teach_coverage.py
    native: str  # the reference card's Oracle text
    play: Callable[[Any, Any], dict[str, Any]]  # the scenario: (table, the probe card) → what to compare besides the table
    n: int = 2  # the number after a numbered keyword
    taught_text: str | None = None  # (default: the made-up keyword, with its number)
    entry: dict[str, Any] | None = None  # (default: the row's entry)
    type_line: str = "Creature — Merfolk"
    cost: str = "{1}{G}"
    pt: tuple[str, str] | None = ("2", "2")
    mine: tuple[str, ...] = ()
    theirs: tuple[str, ...] = ()
    expect: Callable[[dict[str, Any]], bool] = lambda r: True  # (what the native card does here: the scenario isn't idle)


def _entry(case: Case) -> dict[str, Any]:
    return case.entry or ROW[case.row].entry()  # type: ignore[return-value]


def _taught_text(case: Case) -> str:
    if case.taught_text is not None:
        return case.taught_text
    row = ROW[case.row]
    return f"{row.made_up} {case.n}" if row.param else row.made_up


# -------------------------------------------------------------------------------------------------------------------- helpers
def answer(s, d, *, yes: bool = True, prefer: tuple[str, ...] = ()) -> None:
    """Answer one question: with the first offered of ``prefer`` (card names, labels or ids), else "yes" to an optional choice
    (``yes``) or no to it, else the first options it needs; damage to divide goes all it can to the first."""
    if d.kind == "divide":
        total, least, k = int((d.resume or {}).get("total", 0)), int((d.resume or {}).get("least", 1)), len(d.options)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[], amounts=[total - least * (k - 1)] + [least] * (k - 1))
        return
    names = {o.id: (s.state.cards[o.card_id].name if o.card_id in s.state.cards else "") for o in d.options}
    want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, names[o.id])]
    yes_ids = [o.id for o in d.options if o.label.lower().startswith(("yes", "pay", "kick", "sacrifice"))]
    no_ids = [o.id for o in d.options if o.label.lower().startswith(("no", "don't", "decline", "skip")) or o.id in ("no", "decline", "sacrifice")]
    if want:
        pick = want[: max(1, d.min_choices)]
    elif yes and yes_ids:
        pick = yes_ids[:1]
    elif not yes and no_ids:
        pick = no_ids[:1]
    else:
        pick = [o.id for o in d.options][: d.min_choices]
    try:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    except ActionError as exc:
        raise AssertionError(f"{d.kind} {d.prompt!r}: {[(o.id, o.label) for o in d.options]} -> {pick}") from exc


def settle(s, *, yes: bool = True, prefer: tuple[str, ...] = (), limit: int = 60) -> None:
    """Resolve everything (each question answered by ``answer``)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            answer(s, d, yes=yes, prefer=prefer)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_turn(s, phase: str, turn: int, *, attackers: Callable[[Any], list[dict[str, str]]] | None = None,
            blocks: Callable[[Any], list[dict[str, str]]] | None = None, yes: bool = True, limit: int = 300) -> dict[str, Any]:
    """Play on to ``phase`` of turn ``turn``; Alice declares ``attackers(d)`` on turn ``turn`` and Bob ``blocks(d)`` (each falls back to
    none when the engine refuses it: ``seen["refused"]`` says which)."""
    seen: dict[str, Any] = {}
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and s.state.turn.number == turn and d is None and not s.state.zones.get("stack"):
            return seen
        if d is not None and d.kind == "declare_attackers":
            want = attackers(d) if attackers and s.state.turn.number == turn and d.player == "p1" else []
            seen.setdefault("attack_options", sorted(o.id.split(":")[0] + (":probe" if _is_probe(s, o.card_id) else "") for o in d.options))
            try:
                act(s, d.player, type="declare_attackers", attackers=want)
            except ActionError:
                seen["refused"] = "attack"
                act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            want = blocks(d) if blocks and s.state.turn.number == turn else []
            try:
                act(s, d.player, type="declare_blockers", blocks=want)
                seen["blocked"] = bool(want)
            except ActionError:
                seen["refused"] = "block"
                act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            answer(s, d, yes=yes)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


def _is_probe(s, card_id: str | None) -> bool:
    c = s.state.cards.get(card_id) if card_id else None
    return c is not None and c.name.endswith(" Probe")


def _name(c) -> str:
    return "PROBE" if c.name.endswith(" Probe") else c.name


def table(s) -> dict[str, Any]:
    """What the two tables must agree on (the probe card's own name read as PROBE)."""
    st = s.state
    plan = Plan(st, "p1", s.cards, None)
    out: dict[str, Any] = {"turn": (st.turn.number, st.turn.phase), "stack": len(st.zones.get("stack", []))}
    for pid in ("p1", "p2"):
        p = st.players[pid]
        side: dict[str, Any] = {"life": p.life, "library": len(st.zones.get(f"{pid}:library", []))}
        for z in ("hand", "graveyard", "exile"):
            side[z] = sorted(_name(st.cards[i]) for i in st.zones.get(f"{pid}:{z}", []))
        field_ = []
        for i in st.zones.get(f"{pid}:battlefield", []):
            c = st.cards[i]
            ch = plan.ch(c)
            pt_ = (sba.power(c, ch), sba.toughness(c, ch)) if ch is not None and "Creature" in ch.types else None
            field_.append((_name(c), c.tapped, sorted((k, v) for k, v in c.counters.items() if v), pt_))
        side["battlefield"] = sorted(field_, key=repr)
        out[pid] = side
    return out


def attack_alone(d) -> list[dict[str, str]]:
    probe = next(o.card_id or o.id.split(":", 1)[1] for o in d.options if o.id.startswith("a:") and o.label and "Probe" in o.label) \
        if any("Probe" in (o.label or "") for o in d.options) else None
    return [{"card_id": probe, "target": "p2"}] if probe else []


def attackers_named(*names: str) -> Callable[[Any], list[dict[str, str]]]:
    def pick(d):
        return [{"card_id": o.id.split(":", 1)[1], "target": "p2"} for o in d.options
                if o.id.startswith("a:") and any(n in (o.label or "") for n in names)]
    return pick


def blockers(s, *names: str) -> Callable[[Any], list[dict[str, str]]]:
    """Bob blocks the probe with his creatures of these names (one each)."""
    def pick(d):
        probe = next(c.id for c in s.state.cards.values() if c.name.endswith(" Probe") and c.zone == "p1:battlefield")
        used: list[str] = []
        for n in names:
            used.append(next(c.id for c in s.state.cards.values() if c.name == n and c.owner == "p2" and c.zone == "p2:battlefield"
                             and c.id not in used))
        return [{"blocker_id": i, "attacker_id": probe} for i in used]
    return pick


def theirs(s, name: str):
    return put(s, name, "p2")


def bolt(s, target_id: str, pid: str = "p1") -> None:
    """``pid`` casts Lightning Bolt at ``target_id``."""
    c = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target_id])
    settle(s)


def cast_probe(s, probe, **kw) -> None:
    to_hand(s, probe.name)
    act(s, "p1", type="cast_spell", card_id=probe.id, **kw)
    settle(s)


def tried(fn: Callable[[], Any]) -> bool:
    try:
        fn()
    except ActionError:
        return False
    return True


# ------------------------------------------------------------------------------------------------------------------ scenarios
def sc_attack(*block: str, attackers: tuple[str, ...] = (), lands: tuple[str, ...] = ()):
    """On the battlefield from turn 1; on turn 3 it attacks (with ``attackers``) and Bob blocks it with ``block`` (Bob has ``lands``)."""
    def run(s, probe):
        put(s, probe.name)
        for n in lands:
            theirs(s, n)
        for n in attackers:
            put(s, n)
        for n in block:
            theirs(s, n)
        pick = attackers_named("Probe", *attackers)
        return to_turn(s, "main2", 3, attackers=pick, blocks=blockers(s, *block) if block else None)
    return run


def sc_defender(s, probe):
    put(s, probe.name)
    return to_turn(s, "main2", 3, attackers=attackers_named("Probe"))


def sc_bolted(s, probe):
    """Alice bolts her own creature."""
    put(s, probe.name)
    bolt(s, probe.id)
    return {}


def sc_opp_bolts(s, probe):
    """Bob bolts it in his own turn (he has only the {R} for the Bolt)."""
    put(s, probe.name)
    to_turn(s, "main1", 2)
    c = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    ok = tried(lambda: act(s, "p2", type="cast_spell", card_id=c.id, targets=[probe.id]))
    settle(s, yes=False)
    return {"cast": ok}


def sc_cycle(s, probe):
    to_hand(s, probe.name)
    mana(s, "p1", C=2)
    ok = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    return {"activated": ok}


def sc_echo(s, probe):
    to_hand(s, probe.name)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=probe.id)
    settle(s)
    return to_turn(s, "main1", 3, yes=False)  # (it isn't paid for in the upkeep)


def sc_kicked(s, probe):
    to_hand(s, probe.name)
    mana(s, "p1", G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=probe.id, kicker=1)
    settle(s)
    return {}


def sc_flashback(s, probe):
    act(s, "p1", type="move", card_ids=[probe.id], to={"zone": "graveyard"})
    mana(s, "p1", C=2)
    ok = tried(lambda: act(s, "p1", type="cast_spell", card_id=probe.id))
    settle(s)
    return {"cast": ok}


def sc_cheaper(*artifacts: str, pay: dict[str, int]):
    def run(s, probe):
        for n in artifacts:
            put(s, n)
        to_hand(s, probe.name)
        mana(s, "p1", **pay)
        ok = tried(lambda: act(s, "p1", type="cast_spell", card_id=probe.id))
        settle(s)
        return {"cast": ok}
    return run


def sc_noncreature_spell(s, probe):
    put(s, probe.name)
    opt = to_hand(s, "Opt")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    settle(s)
    return {}


def sc_extort(s, probe):
    put(s, probe.name)
    opt = to_hand(s, "Opt")
    mana(s, "p1", U=1, B=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    settle(s)
    return {}


def sc_outlast(s, probe):
    put(s, probe.name)
    to_turn(s, "main1", 3)
    mana(s, "p1", C=2)
    ok = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    return {"activated": ok}


def sc_escape(s, probe):
    act(s, "p1", type="move", card_ids=[probe.id], to={"zone": "graveyard"})
    lib = s.state.zones["p1:library"][:3]
    act(s, "p1", type="move", card_ids=list(lib), to={"zone": "graveyard"})
    mana(s, "p1", C=2)
    ok = tried(lambda: act(s, "p1", type="cast_spell", card_id=probe.id))
    settle(s)
    return {"cast": ok}


def sc_boast(s, probe):
    put(s, probe.name)
    to_turn(s, "main1", 3)
    mana(s, "p1", C=1)
    early = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    seen = to_turn(s, "main2", 3, attackers=attackers_named("Probe"))
    mana(s, "p1", C=2)
    late = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    again = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    return {"early": early, "late": late, "again": again, **seen}


def sc_cast(s, probe):
    to_hand(s, probe.name)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=probe.id)
    settle(s)
    return {}


def sc_connive_land(s, probe):
    """It connives with a Forest on top of the library: it draws the Forest and discards it (a land: no counter)."""
    forest = next(i for i in s.state.zones["p1:library"] if s.state.cards[i].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "library"}, position="top")
    return sc_cast(s, probe)


def sc_exploit(s, probe):
    put(s, "Grizzly Bears")
    return sc_cast(s, probe)


def sc_landfall(s, probe):
    put(s, probe.name)
    forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    return {}


def sc_raid(attack: bool):
    def run(s, probe):
        put(s, probe.name)
        to_turn(s, "main1", 3)
        before = len(s.state.zones["p1:hand"])
        seen = to_turn(s, "main2", 3, attackers=attackers_named("Probe") if attack else None)
        to_turn(s, "main1", 4)
        return {**seen, "drawn": len(s.state.zones["p1:hand"]) - before}
    return run


def sc_morbid(s, probe):
    put(s, probe.name)
    bears = theirs(s, "Grizzly Bears")
    bolt(s, bears.id)
    before = len(s.state.zones["p1:hand"])
    to_turn(s, "main1", 2)
    return {"drawn": len(s.state.zones["p1:hand"]) - before}


def sc_hellbent(s, probe):
    to_hand(s, probe.name)
    others = [i for i in s.state.zones["p1:hand"] if i != probe.id]
    if others:
        act(s, "p1", type="move", card_ids=others, to={"zone": "graveyard"})
    return sc_cast(s, probe)


def sc_threshold(s, probe):
    put(s, probe.name)
    lib = s.state.zones["p1:library"][:7]
    act(s, "p1", type="move", card_ids=list(lib), to={"zone": "graveyard"})
    settle(s)
    return {}


def sc_alliance(s, probe):
    put(s, probe.name)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    return {}


def sc_renew(s, probe):
    act(s, "p1", type="move", card_ids=[probe.id], to={"zone": "graveyard"})
    put(s, "Grizzly Bears")
    mana(s, "p1", C=1)
    ok = tried(lambda: act(s, "p1", type="activate_ability", card_id=probe.id, ability=0))
    settle(s)
    return {"activated": ok}


# -------------------------------------------------------------------------------------------------------- what the native card did
def probe_of(r: dict[str, Any]) -> tuple | None:
    return next((c for c in r["p1"]["battlefield"] if c[0] == "PROBE"), None)


def counters_of(r: dict[str, Any], kind: str = "+1/+1") -> int:
    c = probe_of(r)
    return dict(c[2]).get(kind, 0) if c else -1


def refused(r: dict[str, Any]) -> bool:
    return r["seen"].get("refused") == "block"


def blocked(r: dict[str, Any]) -> bool:
    return "refused" not in r["seen"] and bool(r["seen"].get("blocked"))


# ---------------------------------------------------------------------------------------------------------------------- cases
KICKER = {"kind": "keyword", "name": "Neokicker", "param": True, "abilities": [
    S("kicker", mana="{N}"), T("etb", b("if_kicked"), b("draw"))]}
FLASHBACK = {"kind": "keyword", "name": "Rekindle", "param": True, "abilities": [S("flashback", mana="{N}")]}

CASES: list[Case] = [
    # -- statics: evasion and combat rules --
    Case("Defender", "Defender", "Defender", sc_defender, expect=lambda r: "a:probe" not in r["seen"].get("attack_options", []) and r["p2"]["life"] == 40),
    Case("Flying (a ground blocker)", "Flying", "Flying", sc_attack("Grizzly Bears"), expect=lambda r: refused(r) and r["p2"]["life"] == 38),
    Case("Flying (a flying blocker)", "Flying", "Flying", sc_attack("Atraxa, Praetors' Voice"), expect=blocked),
    Case("Menace (one blocker)", "Menace", "Menace", sc_attack("Grizzly Bears"), expect=refused),
    Case("Menace (two blockers)", "Menace", "Menace", sc_attack("Grizzly Bears", "Llanowar Elves"), expect=blocked),
    Case("Fear (a green blocker)", "Fear", "Fear", sc_attack("Grizzly Bears"), expect=refused),
    Case("Fear (an artifact blocker)", "Fear", "Fear", sc_attack("Perilous Myr"), expect=blocked),
    Case("Skulk (a bigger blocker)", "Skulk", "Skulk", sc_attack("Grizzly Bears"), pt=("1", "1"), expect=refused),
    Case("Skulk (a smaller blocker)", "Skulk", "Skulk", sc_attack("Llanowar Elves"), pt=("1", "1"), expect=blocked),
    Case("Landwalk", "Landwalk", "Islandwalk", sc_attack("Grizzly Bears", lands=("Island",)), expect=refused),
    Case("Landwalk (no Island)", "Landwalk", "Islandwalk", sc_attack("Grizzly Bears"), expect=blocked),
    Case("Hexproof", "Hexproof", "Hexproof", sc_opp_bolts, expect=lambda r: not r["seen"]["cast"]),
    # -- triggers --
    Case("Ward", "Ward", "Ward {2}", sc_opp_bolts, expect=lambda r: r["seen"]["cast"] and probe_of(r) is not None and "Lightning Bolt" in r["p2"]["graveyard"]),
    Case("Prowess", "Prowess", "Prowess", sc_noncreature_spell, expect=lambda r: probe_of(r)[3] == (3, 3)),
    Case("Exalted", "Exalted", "Exalted", sc_attack(), expect=lambda r: r["p2"]["life"] == 37),
    Case("Battle Cry", "Battle Cry", "Battle cry", sc_attack(attackers=("Grizzly Bears",)), expect=lambda r: r["p2"]["life"] == 35),
    Case("Bushido", "Bushido", "Bushido 1", sc_attack("Grizzly Bears"), n=1, expect=lambda r: blocked(r) and probe_of(r) is not None and "Grizzly Bears" in r["p2"]["graveyard"]),
    Case("Afflict", "Afflict", "Afflict 2", sc_attack("Grizzly Bears"), expect=lambda r: blocked(r) and r["p2"]["life"] == 38),
    Case("Renown", "Renown", "Renown 1", sc_attack(), n=1, expect=lambda r: counters_of(r) == 1),
    Case("Extort", "Extort", "Extort", sc_extort, expect=lambda r: r["p1"]["life"] == 41 and r["p2"]["life"] == 39),
    Case("Exploit", "Exploit", "Exploit\nWhen this creature exploits a creature, draw a card.", sc_exploit, expect=lambda r: "Grizzly Bears" in r["p1"]["graveyard"] and len(r["p1"]["hand"]) == 1),
    # -- dying --
    Case("Undying", "Undying", "Undying", sc_bolted, expect=lambda r: counters_of(r) == 1),
    Case("Persist", "Persist", "Persist", sc_bolted, expect=lambda r: counters_of(r, "-1/-1") == 1),
    Case("Afterlife", "Afterlife", "Afterlife 1", sc_bolted, n=1, expect=lambda r: any("Spirit" in c[0] for c in r["p1"]["battlefield"]) and "PROBE" in r["p1"]["graveyard"]),
    # -- costs, casting and activating --
    Case("Echo", "Echo", "Echo {2}", sc_echo, expect=lambda r: "PROBE" in r["p1"]["graveyard"]),
    Case("Cycling", "Cycling", "Cycling {2}", sc_cycle, expect=lambda r: r["seen"]["activated"] and "PROBE" in r["p1"]["graveyard"] and len(r["p1"]["hand"]) == 1),
    Case("Outlast", "Outlast", "Outlast {2}", sc_outlast, expect=lambda r: counters_of(r) == 1),
    Case("Boast", "Boast", "Boast — {1}: Draw a card.", sc_boast, n=1, expect=lambda r: (r["seen"]["early"], r["seen"]["late"], r["seen"]["again"]) == (False, True, False)),
    Case("Affinity", "Affinity", "Affinity for artifacts", sc_cheaper("Sol Ring", pay={"G": 1, "C": 1}), cost="{2}{G}", mine=("Sol Ring",), expect=lambda r: r["seen"]["cast"] and probe_of(r) is not None),
    Case("Undaunted", "Undaunted", "Undaunted", sc_cheaper(pay={"G": 1, "C": 1}), cost="{2}{G}", expect=lambda r: r["seen"]["cast"] and probe_of(r) is not None),
    Case("Kicker", "Kicker", "Kicker {2}\nWhen this creature enters, if it was kicked, draw a card.", sc_kicked, entry=KICKER,
         taught_text="Neokicker 2", expect=lambda r: probe_of(r) is not None and len(r["p1"]["hand"]) == 1),
    Case("Flashback", "Flashback", "Draw a card.\nFlashback {2}", sc_flashback, entry=FLASHBACK, taught_text="Draw a card.\nRekindle 2",
         type_line="Sorcery", cost="{U}", pt=None, expect=lambda r: r["seen"]["cast"] and r["p1"]["exile"] == ["PROBE"]),
    Case("Escape", "Escape", "Escape—{2}, Exile three other cards from your graveyard.", sc_escape, expect=lambda r: r["seen"]["cast"] and probe_of(r) is not None),
    # -- keyword actions --
    Case("Investigate", "Investigate", "When this creature enters, investigate.", sc_cast,
         taught_text="When this creature enters, it neoinvestigates.", expect=lambda r: any(c[0] == "Clue" for c in r["p1"]["battlefield"])),
    Case("Connive (discarding a land)", "Connive", "When this creature enters, it connives.", sc_connive_land,
         taught_text="When this creature enters, it neoconnives.", expect=lambda r: "Forest" in r["p1"]["graveyard"] and counters_of(r) == 0),
    Case("Adapt", "Adapt", "When this creature enters, adapt 2.", sc_cast, taught_text="When this creature enters, neoadapt 2.", expect=lambda r: counters_of(r) == 2),
    # -- ability words --
    Case("Landfall", "landfall", "Landfall — Whenever a land you control enters, draw a card.", sc_landfall, expect=lambda r: len(r["p1"]["hand"]) == 1),
    Case("Raid (attacked)", "raid", "Raid — At the beginning of your end step, if you attacked this turn, draw a card.", sc_raid(True), expect=lambda r: r["seen"]["drawn"] == 1 and r["p2"]["life"] == 38),
    Case("Raid (didn't attack)", "raid", "Raid — At the beginning of your end step, if you attacked this turn, draw a card.", sc_raid(False), expect=lambda r: r["seen"]["drawn"] == 0),
    Case("Morbid", "morbid", "Morbid — At the beginning of your end step, if a creature died this turn, draw a card.", sc_morbid,
         theirs=("Grizzly Bears",), expect=lambda r: r["seen"]["drawn"] == 1),
    Case("Hellbent", "hellbent", "Hellbent — When this creature enters, if you have no cards in hand, draw a card.", sc_hellbent, expect=lambda r: len(r["p1"]["hand"]) == 1),
    Case("Enrage", "enrage", "Enrage — Whenever this creature is dealt damage, draw a card.", sc_bolted, pt=("2", "4"), expect=lambda r: probe_of(r) is not None and len(r["p1"]["hand"]) == 1),
    Case("Alliance", "alliance", "Alliance — Whenever another creature you control enters, put a +1/+1 counter on this creature.",
         sc_alliance, mine=("Grizzly Bears",), expect=lambda r: counters_of(r) == 1),
    Case("Threshold", "threshold", "Threshold — As long as seven or more cards are in your graveyard, this creature gets +1/+1.",
         sc_threshold, expect=lambda r: probe_of(r)[3] == (3, 3)),
    Case("Channel", "channel", "Channel — {2}, Discard this card: Draw a card.", sc_cycle, expect=lambda r: r["seen"]["activated"] and len(r["p1"]["hand"]) == 1),
    Case("Renew", "renew", "Renew — {1}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. Activate only as a "
         "sorcery.", sc_renew, n=1, mine=("Grizzly Bears",), expect=lambda r: r["seen"]["activated"] and "PROBE" in r["p1"]["exile"]),
]

PLAYED = sorted({c.row for c in CASES})
_COMMON = ("Lightning Bolt", "Opt", "Grizzly Bears", "Llanowar Elves", "Perilous Myr")
_THEIRS = ("Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Perilous Myr", "Atraxa, Praetors' Voice")


def _probe_card(case: Case, i: int, side: str) -> dict[str, Any]:
    text = _taught_text(case) if side == "taught" else case.native
    extra = {"power": case.pt[0], "toughness": case.pt[1]} if case.pt else {}
    return card(f"Case {i} {side.capitalize()} Probe", set_code="tst", number=f"TP-{i}-{side}", mana_cost=case.cost,
                cmc=float(sum(int(x) if x.isdigit() else 1 for x in case.cost.strip("{}").split("}{"))), type_line=case.type_line,
                oracle_text=text, colors=["G"], color_identity=["G"], keywords=[], **extra)


EXTRA = [_probe_card(c, i, side) for i, c in enumerate(CASES) for side in ("taught", "native")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture(autouse=True)
def _clean_library():
    taught.set_library([])
    yield
    taught.set_library([])


def _play(cards, case: Case, i: int, side: str) -> dict[str, Any]:
    entries = [taught.clean_entry(_entry(case))] if side == "taught" else []
    taught.set_library(entries)
    name = f"Case {i} {side.capitalize()} Probe"
    s = build(cards, [name, *_COMMON, *case.mine], list(dict.fromkeys([*_THEIRS, *case.theirs])))
    probe = card_named(s, name)
    seen = case.play(s, probe)
    check(s)
    return {**table(s), "seen": seen}


@pytest.mark.parametrize("i", range(len(CASES)), ids=[c.id for c in CASES])
def test_taught_plays_like_native(cards, i):
    case = CASES[i]
    data = cards.resolve(f"Case {i} Taught Probe")
    applied = taught.apply(data, [taught.clean_entry(_entry(case))])
    assert applied is not data and coverage.of_card_data(applied).level == "FULL", applied and applied.get("oracle_text")
    assert coverage.of_card_data(cards.resolve(f"Case {i} Native Probe")).level == "FULL"
    native = _play(cards, case, i, "native")
    assert case.expect(native), native
    mine = _play(cards, case, i, "taught")
    assert mine == native
