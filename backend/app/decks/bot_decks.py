"""-- bot decks -- the decks a bot can be seated with besides one the host picks from their library (POST /games/{id}/bot, the
lobby's Add bot): a special ``deck_id`` token names where its deck comes from.

* ``@random``: a deck from the host's library, picked at random;
* ``@precon:<id>``: a bundled Commander precon (app/decks/precons.json); ``@precon`` alone: one at random;
* ``@generated``: a simple playable 100-card Commander deck generated from the card database for a random commander.

Every pick takes an ``rng`` (``random.Random``-like, as ``resolve.shuffle_data`` does): the API seeds it from the game and the seat
(:func:`seeded`), so the same request picks the same deck, and tests pass their own. The deck it resolves to is recorded on the seat's
action (``AddBot.cards`` / ``PlayerSetup.cards``), so a replay never picks again. Nothing here writes to the library.
"""

from __future__ import annotations

import functools
import hashlib
import json
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.cards.repository import CardRepository

RANDOM = "@random"
PRECON = "@precon"
GENERATED = "@generated"
BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
DECK_SIZE = 100
LANDS = 36
# the nonland slots and how many of each it aims for (the rest: creatures, then anything)
TARGETS = (("ramp", 10), ("removal", 8), ("draw", 5))
CREATURES = 30
MAX_MV = 7


def is_token(deck_id: str | None) -> bool:
    return bool(deck_id) and str(deck_id).startswith("@")


def seeded(*parts: object) -> random.Random:
    """A randomizer seeded from ``parts`` (the game, the seat …): the same parts, the same picks."""
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# -- the host's library -------------------------------------------------------------------------------------------------------


def pick_library_deck(decks: list[Any], rng: Any) -> Any | None:
    """One of ``decks`` (in a stable order: by id), or None when there are none."""
    pool = sorted(decks, key=lambda d: str(getattr(d, "id", d)))
    return rng.choice(pool) if pool else None


# -- precons ------------------------------------------------------------------------------------------------------------------


@functools.cache
def precons() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parent / "precons.json"
    return tuple(json.loads(path.read_text("utf-8"))) if path.is_file() else ()


def precon(precon_id: str | None, rng: Any) -> dict[str, Any] | None:
    """The precon with this id (None: one at random); None when there is no such precon."""
    pool = precons()
    if not precon_id:
        return rng.choice(sorted(pool, key=lambda p: p["id"])) if pool else None
    return next((p for p in pool if p["id"] == precon_id), None)


# -- a generated deck ---------------------------------------------------------------------------------------------------------


def _role(text: str, types: str) -> str:
    t = text.lower()
    if "add {" in t and "{t}" in t or "search your library for a basic land" in t or "search your library for up to two basic land" in t:
        return "ramp"
    if re.search(r"(destroy|exile) target (creature|artifact|enchantment|nonland permanent|permanent)", t) \
            or re.search(r"deals \d+ damage to (any target|target creature)", t):
        return "removal"
    if re.search(r"draw (a card|two cards|three cards|\w+ cards)", t):
        return "draw"
    if "Creature" in types:
        return "creature"
    return "other"


def _rows(cards: CardRepository) -> list[Any]:
    """Every commander-legal, non-digital, non-token card (its default printing): a few columns only."""
    sql = ("SELECT p.name, p.type_line, p.oracle_text, p.cmc, p.color_identity, p.legalities, p.edhrec_rank, p.mana_cost "
           "FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id "
           "WHERE d.is_token = 0 AND p.digital = 0 AND p.legalities LIKE '%\"commander\": \"legal\"%'")
    return cards._query(sql)  # noqa: SLF001 - (the repository's own read connection)


def _commander_ok(row: Any) -> bool:
    types = row["type_line"] or ""
    front = types.split("//")[0]
    return ("Legendary" in front and "Creature" in front) or "can be your commander" in (row["oracle_text"] or "")


def generate_commander_deck(cards: CardRepository, rng: Any) -> tuple[str, str] | None:
    """(deck text, commander name): a random legal commander, ~36 basic lands of its colours and 63 singleton cards in its colour
    identity (ramp, removal, card draw, creatures, a curve up to mana value 7, the most played first). A thin card pool is filled
    with more basic lands, so it is always 100 cards. None when the database has no commander."""
    rows = _rows(cards)
    commanders = sorted((r for r in rows if _commander_ok(r)), key=lambda r: r["name"])
    if not commanders:
        return None
    cmd = rng.choice(commanders)
    identity = set(json.loads(cmd["color_identity"] or "[]"))
    basic_names = {r["name"] for r in rows if (r["type_line"] or "").startswith("Basic Land")}
    pool: dict[str, list[Any]] = {"ramp": [], "removal": [], "draw": [], "creature": [], "other": []}
    for r in rows:
        types = r["type_line"] or ""
        if r["name"] == cmd["name"] or "Land" in types.split("//")[0] or r["name"] in basic_names:
            continue
        if not set(json.loads(r["color_identity"] or "[]")) <= identity or (r["cmc"] or 0) > MAX_MV:
            continue
        if any(w in types for w in ("Conspiracy", "Scheme", "Plane", "Phenomenon", "Vanguard", "Attraction", "Contraption")):
            continue
        pool[_role(r["oracle_text"] or "", types)].append(r)

    def best(rs: list[Any]) -> list[Any]:
        """Most played first (EDHREC rank), shuffled a little among neighbours so two decks differ."""
        ranked = sorted(rs, key=lambda r: (r["edhrec_rank"] is None, r["edhrec_rank"] or 0, r["name"]))
        keyed = [(i + rng.random() * 12, i) for i in range(len(ranked))]
        return [ranked[i] for _, i in sorted(keyed)]

    picked: list[str] = []
    for role, n in TARGETS:
        picked += [r["name"] for r in best(pool[role])[:n]]
    picked += [r["name"] for r in best(pool["creature"])[:CREATURES]]
    spells = DECK_SIZE - 1 - LANDS
    rest = best([r for role in ("other", "creature", "draw", "removal", "ramp") for r in pool[role] if r["name"] not in picked])
    picked += [r["name"] for r in rest[: max(0, spells - len(picked))]]
    picked = list(dict.fromkeys(picked))[:spells]
    lands = DECK_SIZE - 1 - len(picked)
    colors = [c for c in "WUBRG" if c in identity and BASICS[c] in basic_names]
    if not colors:
        colors = ["C"] if "Wastes" in basic_names else [c for c in "WUBRG" if BASICS[c] in basic_names][:1]
    if not colors:
        return None
    weights = {c: 1 for c in colors}  # (by the pips its cards ask for: more of the colour it needs most)
    for r in [cmd, *(x for role in pool.values() for x in role if x["name"] in picked)]:
        for sym in re.findall(r"\{([WUBRG])\}", r["mana_cost"] or ""):
            if sym in weights:
                weights[sym] += 1
    total = sum(weights.values())
    counts = {c: lands * w // total for c, w in weights.items()}
    for c in sorted(colors, key=lambda c: -weights[c])[: lands - sum(counts.values())]:
        counts[c] += 1
    lines = ["Commander", f"1 {cmd['name']}", "", "Deck"]
    lines += [f"{n} {'Wastes' if c == 'C' else BASICS[c]}" for c, n in counts.items() if n]
    lines += [f"1 {name}" for name in picked]
    return "\n".join(lines) + "\n", cmd["name"]


# -- a token, resolved ----------------------------------------------------------------------------------------------------------


class DeckSourceError(ValueError):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def resolve(deck_id: str, *, library: list[Any], cards: CardRepository | None, rng: Any) -> dict[str, Any]:
    """Where a bot's deck comes from: ``{"deck_id": …}`` (a deck of the host's library) or ``{"text", "name", "kind"}`` (a deck list to
    import, nothing saved). A real deck id is returned as it is."""
    if not is_token(deck_id):
        return {"deck_id": deck_id}
    if deck_id == RANDOM:
        picked = pick_library_deck(library, rng)
        if picked is None:
            raise DeckSourceError("There are no decks in this computer's library to pick from", 404)
        return {"deck_id": picked.id}
    if deck_id == PRECON or deck_id.startswith(PRECON + ":"):
        p = precon(deck_id[len(PRECON) + 1:] or None, rng)
        if p is None:
            raise DeckSourceError("No such precon", 404)
        return {"text": p["text"], "name": f"{p['name']} (precon)", "kind": "precon"}
    if deck_id == GENERATED:
        if cards is None or not cards.available:
            raise DeckSourceError("A generated deck needs the card database")
        made = generate_commander_deck(cards, rng)
        if made is None:
            raise DeckSourceError("The card database has no commander to build a deck around")
        return {"text": made[0], "name": f"Generated: {made[1]}", "kind": "generated"}
    raise DeckSourceError(f"Unknown deck source {deck_id!r}")
