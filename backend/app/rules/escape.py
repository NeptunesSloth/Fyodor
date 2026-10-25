"""-- escape (wave 5I) -- 702.138: "Escape—{G}{G}{U}{U}, Exile five other cards from your graveyard." (Uro), granted
escape ("Each nonland card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile
three other cards from your graveyard." — Underworld Breach, The Master of Keys), "escaped" and "escapes with".

Researched against the stored Comprehensive Rules (2026-09-25):

* 702.138a — escape is a static ability that functions while the card is in a player's graveyard: "You may cast this
  card from your graveyard by paying [cost] rather than paying its mana cost" — a permission (601.3) and an
  alternative cost together, paid by the rules for alternative costs (601.2b, 601.2f-h; 118.9: one alternative cost a
  spell, so never with flashback or "without paying its mana cost"; 118.9d: additional costs, increases and
  reductions still apply). The cast is offered only for a card in its owner's own graveyard ("your graveyard").
* 702.138b — a spell or permanent "escaped" if that spell (or the spell it was) was cast from a graveyard with an
  escape ability: the payment record's ``alternative`` ("escape"), which the permanent keeps (conditions._cast_holds).
* 702.138c — "~ escapes with [counters]": "If this permanent escaped, it enters with those counters" (a replacement,
  read as scripts reads "If …, ~ enters with …").
* 601.2a / 601.2h — the card is on the stack while its costs are paid, so "five other cards" never includes it.
* 400.7 — an escaped permanent that leaves the battlefield is a new object: escaping again is a new cast.

A granted escape's cost "is equal to the card's mana cost plus …": a card with no mana cost, with {X} in it, or with
two ways to be cast (split, Adventure, double-faced) isn't offered (which mana cost and X are UNVERIFIED here; the
players can still cast it by hand). Both a printed and a granted escape: each is its own way, offered separately
(the player picks, 601.2b). Nethergoyf's "any number of other cards with four or more card types among them" and
Lunar Hatchling's "Exile a land you control" stay manual.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.alt_costs import Offer
    from app.rules.characteristics import CardInfo, Characteristics

Definition = dict[str, Any]

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
PRINTED = re.compile(r"^escape—(?P<mana>(?:\{[^}]+\})+), exile (?P<n>[a-z]+) other cards from your graveyard$", re.IGNORECASE)
GRANT = re.compile(r"^each (?P<sel>[A-Za-z][A-Za-z -]*?) card in your graveyard has escape\. the escape cost is equal to "
                   r"the card's mana cost plus exile (?P<n>[a-z]+) other cards from your graveyard$", re.IGNORECASE)
# -- cost alt (wave 21F) -- "You may cast this card from your graveyard by paying {2}{W} rather than paying its mana cost." (Raffine's
# Guidance) / "... by paying {3}{R} and exiling four other cards from your graveyard ..." / "... and sacrificing two creatures ...": a
# graveyard cast for its own alternative cost (118.9, 601.3), offered as escape's is but not an escape (702.138b): tag "graveyard"
GY_COST = re.compile(r"^(?:as long as you control an? (?P<need>[A-Z][A-Za-z]+), )?you may cast (?:this card|this creature|~) from your graveyard by paying (?P<pay>(?:\{[^}X]+\})+)"
                     r"(?: and (?P<rest>(?:exil|sacrific)ing .+))? rather than paying its mana cost"
                     r"(?P<exile>\. if you cast this card this way and it would be put into your graveyard, exile it instead)?$", re.IGNORECASE)
ESCAPED = {"object": "self", "cast": {"escaped": True}}  # 702.138b, as a condition on the source (conditions._cast_holds)


def define_static(t: str) -> Definition | None:
    """A printed escape line or a static granting escape (``t``: the line, first letter lowercased, no period)."""
    from app.rules import mana as M
    from app.rules import selectors

    m = PRINTED.fullmatch(t)
    if m:
        n = _WORDS.get(m["n"].lower())
        cost = M.parse_cost(m["mana"])
        if n is None or cost.x or cost.unsupported:
            return None
        return {"kind": "static", "static": "escape", "mana": m["mana"], "exile": n, "effects": []}
    m = GY_COST.fullmatch(t)
    if m:
        from app.rules import alt_costs

        rest = re.sub(r"^(exil|sacrific)ing", r"\1e", m["rest"].lower()) if m["rest"] else ""
        text = f"pay {m['pay']}" + (f" and {rest}" if rest else "")
        # -- wave 110I -- Glimpse the Cosmos: "As long as you control a Giant, …" (need) and "… exile it instead" (614.1a, exile)
        return {"kind": "static", "static": "gy_cost", "cost": text, "effects": [], **({"need": m["need"]} if m["need"] else {}),
                **({"exile": True} if m["exile"] else {})} if alt_costs.parse_cost(text) else None
    m = GRANT.fullmatch(t)
    if m:
        n = _WORDS.get(m["n"].lower())
        sel = selectors.parse(f"{m['sel']} card in your graveyard")
        if n is None or sel is None or sel.player is not None or sel.zones != ("graveyard",) or not sel.card \
                or sel.zone_owner not in (None, "you"):
            return None
        return {"kind": "static", "static": "escape_grant", "filter": sel.key(), "exile": n, "effects": []}
    return None


def _cost_text(mana: str, n: int) -> str:
    word = next(w for w, k in _WORDS.items() if k == n)
    return f"pay {mana} and exile {word} other cards from your graveyard"


def offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Offer]:
    """The escape costs ``player`` could cast this card for now: its own escape ability and the ones permanents they
    control give it — only for a card in its owner's own graveyard (702.138a)."""
    from app.game.state import zone_key
    from app.rules import alt_costs, permissions, scripts, selectors
    from app.rules import mana as M
    from app.rules.graveyard_grants import _two_ways

    r = state.rules
    if r is None or card.owner != player or card.zone != zone_key(player, "graveyard") or not ch.types or ch.is_land \
            or r.card_mode(card.id) == "manual":
        return []
    out: list[Offer] = []
    for index, d in scripts.definitions(ch).items():
        if d.get("static") == "escape":
            alt = alt_costs.parse_cost(_cost_text(d["mana"], d["exile"]))
            if alt is not None:
                out.append(alt_costs.Offer(f"{card.id}:{index}", f"{ch.name}: escape ({d['mana']}, exile {d['exile']} other "
                                           "cards from your graveyard)", alt, escape=True))
        elif d.get("static") == "gy_cost" and (alt := alt_costs.parse_cost(d["cost"])) is not None:  # (wave 21F)
            if d.get("exile") and not ch.is_instant_or_sorcery:
                continue  # (the exile replacement is only applied to a spell leaving the stack, 614.1a)
            if d.get("need") and not any(c.controller == player and c.zone == zone_key(player, "battlefield") and d["need"] in permissions._view(state, player, info).ch(c).subtypes
                                         for c in state.cards.values()):
                continue
            out.append(alt_costs.Offer(f"{card.id}:{index}", f"{ch.name}: {d['cost']}", alt, escape=True, tag="graveyard", exile_gy=bool(d.get("exile"))))
    granted = permissions._table_statics(state, info, {"escape_grant"})
    if granted and ch.mana_cost and "//" not in ch.mana_cost and not _two_ways(card):
        cost = M.parse_cost(ch.mana_cost)
        if not cost.x and not cost.unsupported:
            view = permissions._view(state, player, info)
            for src, index, d in granted:
                if src.controller != player or not selectors.matches(view, selectors.from_key(d["filter"]), card, ch, player,
                                                                     src.id):
                    continue
                alt = alt_costs.parse_cost(_cost_text(ch.mana_cost, d["exile"]))
                if alt is not None:
                    out.append(alt_costs.Offer(f"{src.id}:{index}", f"{src.name}: escape ({ch.mana_cost}, exile {d['exile']} "
                                               "other cards from your graveyard)", alt, escape=True))
    from app.rules import (  # -- casting extras (wave 18E) -- 702.146a: cast transformed from the graveyard; 702.180a
        disturb,
        harmonize,
        mayhem,  # -- Marvel keywords (wave 25A) -- 702.187b
    )

    return out + disturb.offers(state, player, card, info) + harmonize.offers(state, player, card, ch, info) \
        + mayhem.offers(state, player, card, ch, info)


def escapes_with(text: str) -> str | None:
    """702.138c: "~ escapes with two +1/+1 counters on it." is "If ~ escaped, ~ enters with two +1/+1 counters on it.";
    the line rewritten so (``scripts.define_replacement``) reads it, or None."""
    m = re.fullmatch(r"~ escapes with (?P<rest>(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten) [^ ]+ counters? on it)\.?",
                     text)
    return f"If ~ escaped, ~ enters with {m['rest']}." if m else None
