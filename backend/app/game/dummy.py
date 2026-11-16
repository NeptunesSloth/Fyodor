"""-- target dummy -- the server answers for the table's target dummy (app/game/handlers/dummy.py) so it never holds the game up.

After each action a player sends, ``GameSession`` asks :func:`to_answer` what the dummy has to do now and performs it as the dummy,
again and again (at most ``MAX_ANSWERS`` times), until nothing is waiting for it:

* opening hands: it keeps (it holds no cards);
* rules automation running: it passes priority, declares no attackers, blocks as the host set it (``PlayerState.dummy_blocks``:
  never; chump the biggest attacker; or block with everything it can, each creature on the biggest attacker it can block), and
  answers any other choice with the smallest answer it allows, trying a few if the engine refuses one. Every decision kind the
  engine asks (``rules_state.DecisionKind``) has an answer here:

  - ``declare_attackers`` / ``declare_blockers``: their own intents (no attackers; blocks as set, then no blocks);
  - ``choose_one`` / ``choose_cards`` / ``confirm`` / ``manual_resolution``: none when it may choose nothing, else the first
    options it must choose, then each other option alone;
  - ``order``: everything, in the order offered; ``reconcile``: the first option of each question;
  - ``divide``: as evenly as it may (at least the least share each, the rest on the first target; combat damage only to the
    creatures blocking, never past them to what it attacks);
  - a typed answer (``card_names.is_free_text``): a card name (one it was shown, if it fits, then a common name of each card type
    that fits), the smallest number, "no cards" for a splice history. Not answerable: restoring the names of spells cast before an
    old save kept them (``historical spell names``: only the table knows them).

  The engine stays the judge of every answer: a refused one is followed by the next, and a question none of them answers is left to
  the table (the session says so once).

Each answer is an ordinary recorded action whose actor is the dummy, so history replays it like any other (deterministic under
undo, redo and a reload). Undo and redo treat the dummy's answers as part of the action they answered: one undo takes the
player's action back with them (``GameSession.undo``). Nothing is answered while automation is off or paused (no priority to
pass; the dummy's turns are skipped anyway), or once the game is over.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.game.control import decider_of
from app.game.handlers.dummy import dummy_of
from app.game.rules_state import Decision
from app.game.state import CardInstance, GameState

if TYPE_CHECKING:
    from app.rules.characteristics import CardInfo

log = logging.getLogger(__name__)

MAX_ANSWERS = 64  # answers in a row after one action (a full combat with triggers needs a handful)
MAX_TRIES = 6  # answers tried for one decision before giving up on it

# Card names it may name (201.4): one of each card type, kept to those that fit the question ("a nonland card name": 201.4a) and
# that the card database has; the engine judges the one sent (card_names.canonical). Single-faced names (201.4b).
NAMES = (("Sol Ring", "Artifact"), ("Grizzly Bears", "Creature — Bear"), ("Lightning Bolt", "Instant"),
         ("Rampant Growth", "Sorcery"), ("Pacifism", "Enchantment — Aura"), ("Gideon Jura", "Legendary Planeswalker — Gideon"),
         ("Command Tower", "Land"), ("Mountain", "Basic Land — Mountain"))


def is_dummy(state: GameState, pid: str | None) -> bool:
    p = state.players.get(pid) if pid else None
    return p is not None and p.dummy


def to_answer(state: GameState, info: CardInfo | None = None) -> tuple[str, list[dict[str, Any]]] | None:
    """The dummy and the answers to try in turn (the first the server accepts is the one), or None when it has nothing to do."""
    pid = dummy_of(state)
    if pid is None or state.players[pid].left:
        return None
    pregame = state.pregame
    if pregame is not None and not pregame.finished:
        seat = pregame.seats.get(pid)
        return (pid, [{"type": "mulligan_keep"}]) if seat is not None and seat.status == "deciding" else None
    r = state.rules
    if r is None or state.settings.automation == "off" or r.paused or r.winner is not None or r.draw_reason is not None:
        return None
    if pid in r.lost or pid in r.conceded:
        return None
    d = r.decision
    if d is not None:
        if decider_of(state, d) != pid:
            return None
        return pid, answers(d, state=state, info=info, blocks=state.players[pid].dummy_blocks)
    if r.priority == pid:
        return pid, [{"type": "pass_priority"}]
    return None


def answers(d: Decision, *, state: GameState | None = None, info: CardInfo | None = None,
            blocks: str = "never") -> list[dict[str, Any]]:
    """The dummy's answers to decision ``d``, the one it means first (see the module's list)."""
    if d.kind == "declare_attackers":
        return [{"type": "declare_attackers"}]
    if d.kind == "declare_blockers":
        tries = _blocks(d, state, info, blocks) if state is not None and blocks != "never" else []
        out: list[dict[str, Any]] = [{"type": "declare_blockers", "blocks": b} for b in tries]
        return [*out, {"type": "declare_blockers"}][-MAX_TRIES:]
    ids = [o.id for o in d.options if o.group != "seen"]  # (the cards a player looked at, shown beside the options, are not answers)

    def choose(picked: list[str], **more: Any) -> dict[str, Any]:
        return {"type": "choose", "decision_id": d.id, "option_ids": picked, **more}

    from app.rules import card_names  # (rules → game: imported late to stay acyclic)

    if card_names.is_free_text(d):
        return [choose([], name=n) for n in _typed(d, info)][:MAX_TRIES]
    if d.kind == "divide":
        return [choose([], amounts=a) for a in _divide(d)]
    out = []
    if d.kind == "order":  # (its triggers, in the order offered)
        out.append(choose(ids))
    if d.kind == "reconcile":  # one answer per question: the first offered for each
        firsts: dict[str | None, str] = {}
        for o in d.options:
            firsts.setdefault(o.group, o.id)
        out.append(choose(list(firsts.values())))
    if d.min_choices <= 0:
        out.append(choose([]))
    need = max(1, d.min_choices)
    if len(ids) >= need:
        out.append(choose(ids[:need]))
    if need == 1:
        out += [choose([i]) for i in ids[1:]]
    return out[:MAX_TRIES]


# -- blocking ------------------------------------------------------------------------------------------------------------------


def _blocks(d: Decision, state: GameState, info: CardInfo | None, mode: str) -> list[list[dict[str, str]]]:
    """The blocks to try for ``mode`` ("chump" / "all"), best first, from the decision's own blockers and attackers (what the engine
    offers) and the engine's own check of each pair (``combat.block_problem``); the engine judges the whole declaration when it is
    sent (menace, "can't block alone", block costs …), and a refused one is followed by the next."""
    try:
        return _plan_blocks(d, state, info, mode)
    except Exception:  # noqa: BLE001 - never fail the player's action over the dummy's blocks: it then blocks with nothing
        log.exception("The target dummy couldn't work out its blocks")
        return []


def _plan_blocks(d: Decision, state: GameState, info: CardInfo | None, mode: str) -> list[list[dict[str, str]]]:
    from app.game.resolve import NoCardInfo
    from app.rules import characteristics as chars  # (rules → game: imported late to stay acyclic)
    from app.rules import combat, layers, sba

    cards: Any = info if info is not None else NoCardInfo()

    def offered(prefix: str) -> list[CardInstance]:
        return [state.cards[o.id[2:]] for o in d.options if o.id.startswith(prefix) and o.id[2:] in state.cards]

    blockers, attackers = offered("b:"), offered("a:")
    ch = {c.id: layers.derive(state, c, chars.of(c, cards), cards) for c in blockers + attackers}

    def size(c: CardInstance) -> tuple[int, int]:
        return sba.power(c, ch[c.id]) or 0, sba.toughness(c, ch[c.id]) or 0

    biggest = sorted(attackers, key=lambda c: (-size(c)[0], -size(c)[1]))  # (stable: ties in the order offered)

    def can(b: CardInstance, a: CardInstance) -> bool:
        return combat.block_problem(state, b, ch[b.id], a, ch[a.id], cards) is None

    def pair(b: CardInstance, a: CardInstance) -> dict[str, str]:
        return {"blocker_id": b.id, "attacker_id": a.id}

    chumps: list[list[dict[str, str]]] = []  # one blocker (its smallest that can) on each attacker, from the biggest
    for a in biggest:
        able = [b for b in blockers if can(b, a)]
        if able:
            chumps.append([pair(min(able, key=size), a)])
    if mode == "chump":
        return chumps[:MAX_TRIES - 1]
    every = [pair(b, top) for b in blockers if (top := next((a for a in biggest if can(b, a)), None)) is not None]
    return [every, *chumps[:MAX_TRIES - 2]] if every else []


# -- dividing ------------------------------------------------------------------------------------------------------------------


def _divide(d: Decision) -> list[list[int]]:
    """601.2d: an amount per option adding up to the total, as even as it may (at least the least share each, the rest on the first);
    combat damage (``free``: what the attacker attacks, 702.19b) goes only to the creatures blocking it."""
    resume = d.resume or {}
    total, least, n = int(resume.get("total", 0)), int(resume.get("least", 1)), len(d.options)
    free = resume.get("free")
    shares = [i for i in range(n) if i != free] or list(range(n))  # (where the amount goes)
    if n == 0 or total < least * n:
        return []
    spare = total - least * (n - len(shares))  # (what the free target doesn't get: its least, 0 for combat damage)
    each = spare // len(shares)
    amounts = [least] * n
    for i in shares:
        amounts[i] = each
    amounts[shares[0]] += spare - each * len(shares)
    return [amounts] if all(a >= least for a in amounts) else []


# -- typed answers -------------------------------------------------------------------------------------------------------------


def _typed(d: Decision, info: CardInfo | None) -> list[str]:
    """What it types for a free-text decision (``card_names.is_free_text``); the engine judges each (``card_names.answer``)."""
    first = d.options[0]
    if first.id == "__number__":  # (group_choice.number_answer: a whole number, at least the label's "≥ N")
        return [first.label.rsplit("≥", 1)[-1].strip() if "≥" in first.label else "0"]
    if first.group == "historical splice names":
        return ["no cards"]
    if first.group == "historical spell names":
        return []  # (old-save history only the table knows: left to it)
    what = first.group or "card name"
    resolve = getattr(info, "resolve", None)

    def type_line(name: str) -> str | None:
        card = resolve(name) if resolve is not None else None
        return None if card is None else str(card.get("type_line") or "")

    seen = [o.label for o in d.options[1:] if o.group == "seen" and o.label]  # a card it was shown (looking at a hand), if it fits
    seen = [n for n in seen if (t := type_line(n)) is not None and "//" not in t and _fits(what, t)][:1]
    fits = [n for n, t in NAMES if _fits(what, t) and (resolve is None or type_line(n) is not None)]
    return list(dict.fromkeys([*seen, *fits]))


def _fits(what: str, type_line: str) -> bool:
    from app.rules import card_names

    try:
        return card_names._allowed(what, type_line)
    except Exception:  # noqa: BLE001 - an unexpected question: the engine judges it
        return True
