"""-- prohibitions (wave 22B) -- static "can't" lines checked where the event would happen. Researched against CR 2026-09-25.

* 614.17: an effect that says something can't happen isn't a replacement effect but follows similar rules; 614.17a: it must exist before
  the event; 614.17c: an event that can't happen can only be replaced by a self-replacement effect (614.15), so nothing replaces it and
  nothing triggers on it (603.2g). The line is read while its source is on the battlefield (611.3a), from the table as it is at that
  moment (the same scan as the cast limits: ``cast_limits._statics``).
* "Creature cards in graveyards and libraries can't enter the battlefield." (Grafdigger's Cage, Weathered Runestone, Soulless Jailer,
  Kunoros): checked for each card an effect puts onto the battlefield (``attachments.enter``, the one entry choke point): it stays where it
  is, as an Aura with nothing to enchant does (303.4g). A card in a hidden zone stays silently (a note would show that a card was found).
  Not read: "Lands can't enter the battlefield" (Worms of the Earth: whether a land play is then possible isn't settled).
* "Counters can't be put on artifacts, creatures, enchantments, or lands." (Solemnity), "This creature can't have counters put on it."
  (Tatterkite, Melira's Keepers): checked at the one counter choke point (``replace.plan_counters``) before any replacement is applied,
  for permanents on the battlefield and for one entering with counters (122.6: they are put as it enters; persist and undying returns
  too). A card that isn't a permanent (a suspended card in exile) is not "an artifact, creature, enchantment, or land" on the battlefield.
* "Players can't pay life or sacrifice creatures to cast spells or activate abilities." (Angel of Jubilation, Yasharn), "Players can't pay life to
  cast spells or to activate abilities that aren't mana abilities." (Karn's Sylex): 119.4 / 601.2h — a cost that can't be paid can't be begun, so the
  cost parts, the sacrifice candidates, Phyrexian mana's life and the mana abilities that pay life or sacrifice are all read (``life_banned``,
  ``sacrifice_banned``).
* "Spells and abilities your opponents control can't cause you to sacrifice permanents [or discard cards]." (Sigarda, Tajuru Preserver, Tamiyo):
  an edict or any other effect of an opponent's spell or ability does nothing to you here; a cost you pay yourself is no such effect.
* "Players can't search libraries." / "Your opponents can't search libraries." / "Players can't search libraries this turn." / "Spells and abilities
  your opponents control can't cause their controller to search their library." (Mindlock Orb, Stranglehold, Shadow of Doubt, Ashiok): the library
  is left out of the search (701.23); "then shuffle" is its own instruction and still happens.
Not read (stay by hand): "Lands can't enter the battlefield" / "Players can't play lands" (Worms of the Earth: whether a land play is then possible
isn't settled), "can't lose life" (Everybody Lives!, Courageous Resolve, Teferi's Protection: the life-loss events of damage, effects and costs have
no single choke point), "damage that would reduce your life total to less than 1 reduces it to 1 instead" (Angel's Grace: what it does at 0 life is
unsettled), cost increases by name (Disruptor Flute, Anointed Peacekeeper: cost_changes), protection from a name (Runed Halo), "any player may pay {2}
to ignore this" (Leonin Arbiter).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key
from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan

Definition = dict[str, Any]
KINDS = ("cant_enter", "cant_counters", "cant_pay", "cant_cause_sacrifice", "cant_search", "search_top", "draw_cap")

_ENTER = re.compile(r"^(?P<what>(?:nonland )?(?:permanent|creature) cards) in (?P<zones>graveyards|libraries|graveyards and libraries) "
                    r"can't enter the battlefield$")
_ZONES = {"graveyards": ("graveyard",), "libraries": ("library",), "graveyards and libraries": ("graveyard", "library")}
_COUNTERS = re.compile(r"^counters can't be put on (?P<sel>[a-z, ]+)$")
_SELF_COUNTERS = "~ can't have counters put on it"
_SEARCH_STATICS = {"players can't search libraries": "each", "your opponents can't search libraries": "opponents",
                   "spells and abilities your opponents control can't cause their controller to search their library": "caused"}
# "Players can't pay life or sacrifice creatures to cast spells or activate abilities." (Angel of Jubilation, Yasharn), "Players can't pay life to
# cast spells or to activate abilities that aren't mana abilities." (Karn's Sylex)
_PAY = re.compile(r"^players can't pay life(?: or sacrifice (?P<sac>[a-z ]+))? to cast spells(?P<act> or activate abilities"
                  r"| or to activate abilities that aren't mana abilities)$")


def static_definition(text: str) -> Definition | None:
    t = text.strip().rstrip(".")
    t = t[:1].lower() + t[1:] if t[:1].isupper() and not t.startswith("~") else t
    m = _ENTER.fullmatch(t)
    if m is not None:
        sel = selectors.parse(m["what"])
        if sel is None or sel.player is not None:
            return None
        return {"kind": "static", "static": "cant_enter", "sel": sel.key(), "zones": list(_ZONES[m["zones"]]), "effects": []}
    m = _COUNTERS.fullmatch(t)
    if m is not None:
        sel = selectors.parse(re.sub(r",? and ", ", or " if "," in m["sel"] else " or ", m["sel"]))
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras or sel.other:
            return None
        return {"kind": "static", "static": "cant_counters", "sel": sel.key(), "effects": []}
    m = _PAY.fullmatch(t)
    if m is not None:
        sel = selectors.parse(m["sac"]) if m["sac"] else None
        if m["sac"] and (sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras):
            return None
        return {"kind": "static", "static": "cant_pay", "sac": sel.key() if sel else None,
                "mana": m["act"] == " or activate abilities", "effects": []}
    if t == "if an opponent would search a library, that player searches the top four cards of that library instead":
        # -- most-played cards (wave 43B) -- 614.1a, 701.23 (Aven Mindcensor): the search sees only the top four cards; the whole library is shuffled afterwards if the text says so
        return {"kind": "static", "static": "search_top", "n": 4, "effects": []}
    m = re.fullmatch(r"(?P<who>each opponent|each player) can't draw more than one card each turn", t)
    if m:  # -- most-played cards (wave 43B) -- 101.2: Narset, Parter of Veils; Spirit of the Labyrinth; Leovold (see ``draw_allowed``)
        return {"kind": "static", "static": "draw_cap", "who": "opponents" if m["who"] == "each opponent" else "each", "n": 1, "effects": []}
    if t in _SEARCH_STATICS:  # (Mindlock Orb, Stranglehold, Ashiok, Dream Render)
        return {"kind": "static", "static": "cant_search", "who": _SEARCH_STATICS[t], "effects": []}
    if t == "spells and abilities your opponents control can't cause you to sacrifice permanents":  # (Sigarda, Tajuru Preserver)
        return {"kind": "static", "static": "cant_cause_sacrifice", "discard": False, "effects": []}
    if t == "spells and abilities your opponents control can't cause you to discard cards or sacrifice permanents":  # (Tamiyo, Collector of Tales)
        return {"kind": "static", "static": "cant_cause_sacrifice", "discard": True, "effects": []}
    if t == _SELF_COUNTERS:
        return {"kind": "static", "static": "cant_counters", "sel": None, "effects": []}
    if t == "players can't get counters":  # (122.1: a player gets counters; poison, energy, experience, rad)
        return {"kind": "static", "static": "cant_counters", "sel": None, "players": True, "effects": []}
    return None


def _statics(plan: Plan, kind: str) -> list[tuple[CardInstance, Definition]]:
    from app.rules import cast_limits

    return cast_limits._statics(plan.state, plan.info, kind)


def _label(src: CardInstance) -> str:
    return src.name or "a permanent"


def cant_enter(plan: Plan, card: CardInstance, controller: str) -> tuple[str, bool] | None:
    """(the permanent saying so, whether the card is in a public zone) if ``card`` can't enter the battlefield now (614.17)."""
    found = _statics(plan, "cant_enter")
    if not found:
        return None
    ch = plan.ch(card)
    types = {"Creature"} if card.face_down else ch.types  # (-- wave 24D -- 708.2 / 701.40a: a face-down object is a 2/2 creature card)
    for src, d in found:
        if not any(card.zone.endswith(f":{z}") for z in d["zones"]):
            continue
        sel = selectors.from_key(d["sel"])
        if sel.types and not set(sel.types) & types or set(sel.not_types) & types:
            continue
        return _label(src), not card.zone.endswith((":library", ":hand"))
    return None


def cant_get_counters(plan: Plan) -> str | None:
    """The permanent saying players can't get counters (614.17), or None."""
    return next((_label(src) for src, d in _statics(plan, "cant_counters") if d.get("players")), None)


def cant_counters(plan: Plan, card_id: str, entering_for: str | None) -> str | None:
    """The permanent saying counters can't be put on this card (614.17), or None. ``entering_for``: the controller it is entering
    under (it isn't on the battlefield yet: only other permanents' lines are read)."""
    found = _statics(plan, "cant_counters")
    card = plan.state.cards.get(card_id)
    if card is None or not found and entering_for is None:
        return None
    if entering_for is None and not card.zone.endswith(":battlefield"):
        return None  # (a card in exile with time counters is no permanent)
    probe = card.model_copy(update={"zone": zone_key(entering_for, "battlefield"), "controller": entering_for}) if entering_for else card
    ch = plan.ch(probe)
    if entering_for:  # -- review 22B -- 614.17d: its own "can't have counters put on it" applies as it enters (Tatterkite returned by undying)
        from app.rules.scripts import self_text

        if any(self_text(ab.text, ch.name).rstrip(".") == _SELF_COUNTERS for ab in ch.abilities):
            return _label(card)
    for src, d in found:
        if d.get("players"):
            continue
        if d["sel"] is None:
            if src.id == card_id and entering_for is None:
                return _label(src)
        elif selectors.matches(plan, selectors.from_key(d["sel"]), probe, ch, src.controller, src.id):
            return _label(src)
    return None


# -- cost payment (601.2h, 602.2b, 119.4) -- a cost that includes paying life or sacrificing something the line forbids can't be paid, so the
# spell or ability can't be begun (nothing is paid: 601.2h). Read from the table as it is (cast_limits._statics): ``mana_ability`` costs are
# only stopped by the lines that say "activate abilities" (Sylex: "that aren't mana abilities").
def cant_search(plan: Plan, searcher: str, by: str, library: str | None = None) -> str | None:
    """614.17 / 701.23: the permanent or effect keeping ``searcher`` from searching a library now, or None. ``by``: the controller of the spell or
    ability that has them search ("Spells and abilities your opponents control can't cause their controller to search their library":
    only a searcher who controls that spell or ability, and who is its static's controller's opponent). ``library``: whose library is
    searched (review 26A: "Search target opponent's library": not "their library", so the "caused" kind doesn't stop it)."""
    for src, d in _statics(plan, "cant_search"):
        mine = src.controller == searcher
        caused = d["who"] == "caused" and not mine and searcher == by and library in (None, searcher)
        if d["who"] == "each" or (d["who"] == "opponents" and not mine) or caused:
            return _label(src)
    turn = plan.state.turn.number
    return "an effect" if any(x["what"] == "search" and x["player"] == searcher and x["turn"] == turn for x in plan.rules.results) else None


def search_depth(plan: Plan, searcher: str) -> int | None:
    """-- most-played cards (wave 43B) -- 614.1a, 701.23: how many cards from the top of a library ``searcher`` may search (None: all of it): an opponent of the
    controller of "If an opponent would search a library, that player searches the top four cards of that library instead" (Aven Mindcensor). The cards
    outside the top are not seen and cannot be found, however they could be identified; the library is shuffled afterwards as the text says."""
    depths = [int(d["n"]) for src, d in _statics(plan, "search_top") if src.controller != searcher]
    return min(depths) if depths else None


def draw_left(plan: Plan, player: str) -> tuple[int, int] | None:
    """-- most-played cards (wave 43B) -- 101.2, 121.2: with "Each opponent can't draw more than one card each turn" (Narset, Parter of Veils) in play, how many more
    cards ``player`` may draw this turn and the limit (None: no limit): the limit less what they drew already this turn (the cards drawn before the permanent came
    count, the rulings). -- review 37 -- read one draw at a time (replace.draw_cards): a draw not allowed isn't made, so no replacement effect sees it; one a replacement
    effect replaced was not drawn and doesn't count (Narset and Leovold rulings: "if an opponent's first draw is replaced … Narset won't stop the next draw")."""
    caps = [int(d["n"]) for src, d in _statics(plan, "draw_cap") if d["who"] == "each" or src.controller != player]
    if not caps:
        return None
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    return max(0, min(caps) - (log.drew.get(player, 0) if log is not None else 0)), min(caps)


def note_search(plan: Plan, searcher: str, owner: str) -> None:
    """-- most-played cards (wave 43B) -- 701.23: ``searcher`` searches their own library (even when nothing is found): the event "Whenever an opponent
    searches their library" (Archivist of Oghma, Wan Shi Tong, Ob Nixilis, Unshackled) reads; a search of another player's library is not "their library"
    (the rulings), a search the searcher can't make (cant_search) never starts."""
    from app.game.rules_state import emit

    if searcher == owner:
        emit(plan.state, "designation", counter="search_library", player=searcher)


_SEARCH_EFFECT = re.compile(r"^players can't search libraries this turn$")


def _build_search(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "cant_search_turn", "who": "each_player"}], None


# -- most-played cards (wave 43B) -- 101.2, 701.6, 611.2a: "Spells you control can't be countered this turn." (Veil of Summer), "Creature spells you cast this turn can't
# be countered." (Domri, Anarch of Bolas): every such spell of that player for the rest of the turn, those already on the stack too (the rulings)
_UNCOUNTERABLE_EFFECT = re.compile(r"^(?:(?P<sel>[\w ,'-]+?) )?spells you (?:control|cast)(?P<mid> this turn)? can't be countered(?P<end> this turn)?$")


def _build_uncounterable(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import permissions
    from app.rules.scripts import _NoMatch

    key = permissions.spell_filter(m["sel"]) if m["sel"] else None
    if bool(m["mid"]) == bool(m["end"]) or (m["sel"] and key is None):
        raise _NoMatch
    return [{"do": "uncounterable_turn", "filter": key}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_SEARCH_EFFECT, _build_search), (_UNCOUNTERABLE_EFFECT, _build_uncounterable)]


def uncounterable_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The spells ``ctx["controller"]`` controls (matching the filter) can't be countered until the turn ends (permissions.spell_uncounterable reads it)."""
    r = plan.rules
    turn = plan.state.turn.number
    r.results = [x for x in r.results if x["turn"] == turn]
    r.results.append({"player": ctx["controller"], "what": "uncounterable", "turn": turn, "filter": e.get("filter")})
    return True


def cant_search_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """611.2a: "Players can't search libraries this turn." — the players in the game as it resolves, until the turn ends."""
    from app.rules.effects import _players

    r = plan.rules
    turn = plan.state.turn.number
    r.results = [x for x in r.results if x["turn"] == turn]
    for pid in _players(plan, ctx, e["who"]):
        r.results.append({"player": pid, "what": "search", "turn": turn})
    plan.note("Players can't search libraries this turn", actor=ctx["controller"])
    return True


def uncounterable_next(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"The next [creature] spell you cast this turn can't be countered.": waits for that spell (``bind_next_uncounterable``, as it is cast)."""
    r = plan.rules
    turn = plan.state.turn.number
    r.results = [x for x in r.results if x["turn"] == turn]
    r.results.append({"player": ctx["controller"], "what": "uncounterable_next", "turn": turn, "filter": e.get("filter")})
    return True


def bind_next_uncounterable(plan: Plan, card: Any, player: str) -> None:
    """A spell was just cast by ``player`` (601.2a): every waiting "next spell … can't be countered" of theirs that fits it now belongs to this very spell (400.7: a new
    object later is another spell), and is used up."""
    from app.rules import permissions

    r = plan.rules
    turn = plan.state.turn.number
    waiting = [x for x in r.results if x.get("what") == "uncounterable_next" and x["turn"] == turn and x["player"] == player]
    if not waiting:
        return
    ch = plan.ch(card)
    oid = r.object_id(card.id)
    for x in waiting:
        if not x.get("filter") or permissions.spell_matches(plan.state, player, card, ch, x["filter"], plan.info):
            x["what"], x["oid"] = "uncounterable", oid


PRIMITIVES = {"cant_search_turn": cant_search_turn, "uncounterable_turn": uncounterable_turn, "uncounterable_next": uncounterable_next}


def cant_cause_sacrifice(plan: Plan, victim: str, by: str) -> str | None:
    """614.17: the permanent saying a spell or ability controlled by ``by`` can't make ``victim`` sacrifice permanents ("Spells and abilities
    your opponents control can't cause you to sacrifice permanents": an edict of theirs does nothing to you; a cost you pay is no such effect)."""
    if victim == by:
        return None
    return next((_label(src) for src, _ in _statics(plan, "cant_cause_sacrifice") if src.controller == victim), None)


def cant_cause_discard(plan: Plan, victim: str, by: str) -> str | None:
    """614.17: the permanent saying a spell or ability controlled by ``by`` can't make ``victim`` discard cards (Tamiyo, Collector of Tales)."""
    if victim == by:
        return None
    return next((_label(src) for src, d in _statics(plan, "cant_cause_sacrifice") if src.controller == victim and d.get("discard")), None)


def life_banned(state: GameState, info: CardInfo | None, *, mana_ability: bool = False) -> str | None:
    from app.rules import cast_limits

    return next((_label(src) for src, d in cast_limits._statics(state, info, "cant_pay") if d["mana"] or not mana_ability), None)


def sacrifice_banned(state: GameState, info: CardInfo | None, card: CardInstance, *, mana_ability: bool = False) -> str | None:
    """The permanent saying ``card`` can't be sacrificed to pay a cost (a creature for Angel of Jubilation)."""
    from app.rules import cast_limits
    from app.rules.plan import Plan

    found = [(src, d) for src, d in cast_limits._statics(state, info, "cant_pay") if d["sac"] is not None and (d["mana"] or not mana_ability)]
    if not found or info is None:
        return None
    plan = Plan.view(state, card.controller, info)
    ch = plan.ch(card)
    return next((_label(src) for src, d in found if selectors.matches(plan, selectors.from_key(d["sac"]), card, ch, card.controller, src.id)), None)
