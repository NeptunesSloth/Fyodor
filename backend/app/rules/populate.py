"""Populate and per-object token copies (wave 5J), researched against CR 2026-09-25.

* **Populate** (701.36): "To populate means to choose a creature token you control and create a token
  that's a copy of that creature token." (701.36a). The choice is made as the instruction is carried
  out; it doesn't target (hexproof doesn't matter). With no creature token, nothing is created
  (701.36b). Rootborn Defenses, Sundering Growth ("…, then populate"), Trostani, Selesnya's Voice,
  Growing Ranks, Horncaller's Chant ("Create a 4/4 … token, then populate": the new token may be
  chosen). The copy itself is the copy system's (app/rules/copying.py: copiable values 707.2, a copy
  of a copy 707.3, the token choke point and its 616.1 order).
* **"For each <permanent>, create a token that's a copy of that <permanent>"** (Second Harvest, Rhys
  the Redeemed, Multiversal Incursion, Clone Legion, Parallel Evolution "its controller creates"):
  one copy of each object the phrase names as the instruction resolves, all created at once (one
  instruction: ``copying.token_copy`` over every object, one creation batch). -- token copies (wave 31C) -- also "… a copy of it"
  (Saheeli, the Gifted) and "for each other nonland permanent you control" (other than the source: Oko, the Ringleader); "Those tokens gain
  haste. Exile those tokens at the beginning of the next end step." name all of them (``_Introducer.number`` is open for a group).

"Populate. The token enters tapped and attacking." (Ghired, wave 46A) is "populate tapped and attacking": the copy is created attacking (508.4).

Refused (left manual, unknown wording): "Populate X times", "for each of them" in a "one or more" trigger (Kambal), a phrase with a target
the copy text doesn't name.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import CopyRecipe, DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

# "a creature token you control" (701.36a)
CREATURE_TOKENS_KEY = 'sel:{"controller":"you","token":true,"types":["Creature"]}'

# the noun "that …" names, and the card type each object counted must have for it to fit
_NOUNS = {"permanent": None, "creature": "Creature", "artifact": "Artifact", "enchantment": "Enchantment", "token": None}
FOR_EACH = re.compile(r"for each (?P<what>[^,]+), (?:(?P<their>its controller creates)|create) (?:a|one) (?P<tapped>tapped )?"
                      r"token that's a copy of (?:that (?P<noun>permanent|creature|artifact|enchantment|token)|it)"  # (wave 31C: "of it", Saheeli, the Gifted)
                      r"(?:, except (?P<exc>.+))?")


def parse_for_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    """"For each <selector>, [its controller creates | create] a token that's a copy of that <noun>
    [, except …]" → one token_copy over every object the selector names, or None (manual)."""
    from app.rules import copying, selectors

    what, target = m["what"].strip(), None
    tm = re.fullmatch(r"(?P<sel>.+?) target player controls", what)
    if tm is not None:  # (Clone Legion: "each creature target player controls")
        what, target = tm["sel"] + " on the battlefield", "player"
    if what.startswith("another ") or " target " in f" {what} ":
        return None
    sel = selectors.parse(what.removesuffix(" on the battlefield") if what.endswith(" on the battlefield") else what)
    # (-- most-played cards II (wave 45A) -- "for each token you control that entered this turn" (Ocelot Pride): read of this turn's log, selectors.candidates)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None or set(sel.extras) - {"entered_this_turn"}:
        return None  # (wave 31C: "for each other nonland permanent you control" — other than the source, ``selectors.candidates``: Oko, the Ringleader)
    need = _NOUNS[m["noun"]] if m["noun"] else None
    if need is not None and sel.types != (need,):
        return None  # ("that creature" must be what each counted object is)
    if m["noun"] == "token" and sel.token is not True:
        return None
    if target is not None and (sel.controller is not None or m["their"]):
        return None
    if m["their"] and (sel.controller is not None or target is not None):
        return None  # ("its controller creates": every such object on the battlefield, each controller their own)
    ex = copying.parse_excepts(m["exc"])
    if ex is None:
        return None
    effect: dict[str, Any] = {"do": "token_copy", "n": 1, **copying._dump(ex),
                              "who": f"controlled:target|{sel.key()}" if target else sel.key()}
    if m["tapped"]:
        effect["tapped"] = True
    if m["their"]:
        effect["their"] = True  # (each copy is created by the copied object's controller)
    return [effect], target


# -- populate (701.36) ---------------------------------------------------------------------------
def populate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.36a-b: choose a creature token you control (the controller's choice when there are
    several), then create a token that's a copy of it."""
    from app.rules import selectors
    from app.rules.plan import decide

    pid = ctx["controller"]
    mine = [c for c in selectors.candidates(plan, selectors.from_key(CREATURE_TOKENS_KEY), pid, ctx.get("source_card"))
            if plan.state.cards[c].zone.endswith(":battlefield")]
    if not mine:
        plan.note("Populate: no creature token to copy (701.36b)", actor=pid)
        return True
    if len(mine) == 1:
        return _copy(plan, ctx, mine[0], bool(e.get("attacking")))
    decide(plan, player=pid, kind="choose_cards", prompt="Populate: choose a creature token you control to copy",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Token", card_id=c) for c in mine],
           resume={"step": "populate_choose", "ctx": ctx, "attacking": bool(e.get("attacking"))})
    return False


def _copy(plan: Plan, ctx: Context, cid: str, attacking: bool = False) -> bool:
    """The copy, as the instruction being resolved: it takes populate's place in the resolution (a
    616.1 order prompt then runs this copy again, not the choice)."""
    from app.rules import copying

    k = int(ctx.get("next") or 0) - 1
    effects = list(ctx.get("effects") or [])
    # (-- cant restrictions (wave 46A) -- "Populate. The token enters tapped and attacking." (Ghired): 508.4, the copy's controller chooses what it attacks)
    e = {"do": "token_copy", "n": 1, "who": f"object:{plan.oid(cid)}", **({"attacking": True, "tapped": True} if attacking else {})}
    if 0 <= k < len(effects) and effects[k].get("do") == "populate":
        effects[k] = e
        ctx["effects"] = effects
    return copying.token_copy(plan, ctx, e)


def resume_populate(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, selectors

    ctx = d.resume["ctx"]
    card = plan.state.cards.get(chosen[0]) if chosen else None
    if card is None or not card.zone.endswith(":battlefield") or not selectors.matches(
            plan, selectors.from_key(CREATURE_TOKENS_KEY), card, plan.ch(card), d.player, ctx.get("source_card")):
        raise ActionError("Choose a creature token you control")
    if _copy(plan, ctx, card.id, bool(d.resume.get("attacking"))):
        effects.continue_effects(plan, ctx)


# -- a copy of an object that left the battlefield (608.2h, 111.12) -----------------------------------
def gone_refs(plan: Plan, ctx: Context, who: str) -> list[Any]:
    """The objects "event" / "ref:<name>" names that were on the battlefield and are no longer that object there (400.7)."""
    from app.rules import context

    if who != "event" and (not who.startswith(context.PREFIX) or "|" in who):
        return []
    name = context.EVENT if who == "event" else who[len(context.PREFIX):]
    return [r for r in context._object_refs(ctx, name, was=True) if (r.zone or "").endswith("battlefield") and context._same(plan, r) is None]


def left_battlefield(plan: Plan, ctx: Context, who: str, their: bool) -> list[tuple[Any, str]]:
    """"Create a token that's a copy of it / of ~" when "it" (the trigger's object) or the source left the
    battlefield before the instruction: 608.2h — the effect uses the object's last known information, its
    copiable values as it last existed (111.12: a copy of a nonexistent object is made only through last known
    information). Each entry: (recipe, the player who creates it), or (why it's left to the players, "")."""
    from app.rules import context, copying

    snaps: list[Any] = []
    if who == "event" or who.startswith(context.PREFIX):  # -- review 32 -- or what an earlier instruction moved off the battlefield ("Exile
        # target creature. … create a token that's a copy of it", Kaya, Intangible Slayer; Identity Thief): as it last existed there (608.2h)
        for ref in gone_refs(plan, ctx, who):
            snaps.append(context.snapshot(plan, ref))
    elif who == "self":
        oid = ctx.get("source_object")
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if oid and (src is None or plan.oid(src) != oid or not src.zone.endswith(":battlefield")):
            snap = plan.rules.lki.get(oid)
            if snap is not None and snap.zone.endswith("battlefield"):
                snaps.append(snap)
    elif who == "host":  # "a copy of enchanted artifact" (Mechanized Production) whose host is gone: by hand
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
            host = src.attached_to
        else:
            was = plan.rules.lki.get(ctx.get("source_object") or "")
            host = was.attached_to if was is not None else None
        card = plan.state.cards.get(host or "")
        if host and (card is None or not card.zone.endswith(":battlefield")):
            return [("a copy of the permanent it was attached to, which left the battlefield (608.2h)", "")]
    out: list[tuple[Any, str]] = []
    for snap in snaps:
        if snap is None:
            continue  # (nothing is known of it: no token, 111.12)
        maker = snap.controller if their else ctx["controller"]
        name = snap.name or "it"
        if snap.face_down:
            out.append((f"a copy of {name} (a face-down object, 707.2)", ""))
            continue
        recipe = snap.copy_recipe.model_copy(deep=True) if snap.copy_recipe is not None else None
        if recipe is None and snap.printing and plan.info.get(snap.printing) is not None:
            recipe = CopyRecipe(printing=snap.printing, face=snap.face, source=name[:200])
        if recipe is None and snap.is_token and not snap.printing and snap.token_type_line:  # -- review 32 -- a token's copiable values:
            # what the effect that created it defined (707.2, 111.3; copying.base_recipe), as it last existed
            recipe = CopyRecipe(token={"name": snap.name, "power": snap.token_power, "toughness": snap.token_toughness,
                                       "colors": list(snap.token_colors), "type_line": snap.token_type_line, "text": snap.text,
                                       "mana_cost": snap.token_mana_cost}, source=name[:200])
        if recipe is None:
            out.append((f"a copy of {name} as it last existed (608.2h: its text isn't recorded)", ""))
            continue
        layout = (plan.info.get(recipe.printing) or {}).get("layout") if recipe.printing else None
        ch = copying.characteristics(recipe, plan.info)
        if (layout == "meld" and recipe.face) or (layout in copying.DOUBLE_FACED and layout not in copying.TWO_FACED_TOKENS):
            out.append((f"a copy of {name} (a double-faced or melded object, 707.8a)", ""))
        elif "Aura" in ch.subtypes or "Room" in ch.subtypes:
            out.append((f"a copy of {name} (an Aura or a Room: 303.4f, 709.5)", ""))
        else:
            out.append((recipe, maker))
    return out


# -- "Then if you control eight or more artifacts with the same name as one another, you win the game." -------------
_WIN_SAME_NAME = re.compile(r"if you control (?P<n>\w+) or more artifacts with the same name as one another, you win the game")


def win_sentence(text: str) -> dict[str, Any] | None:
    """Mechanized Production's last sentence (a condition checked as the instruction is carried out, 608.2c)."""
    from app.rules import token_grammar

    m = _WIN_SAME_NAME.fullmatch(text)
    if m is None:
        return None
    n = token_grammar.NUMBERS.get(m["n"].lower()) if not m["n"].isdigit() else int(m["n"])
    return {"do": "win_same_name", "n": n} if isinstance(n, int) and n > 1 else None


def win_same_name(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """104.2b: an effect says its controller wins the game, if they control N or more artifacts that share a name
    (201.2: a face-down object has no name, so it shares a name with nothing; 708.2). A permanent saying that a
    player "can't win the game" (104.2b: an effect that stops a win isn't modelled) leaves the win to the players."""
    from app.rules import characteristics as chars
    from app.rules.replace import _win

    pid = ctx["controller"]
    names: dict[str, int] = {}
    for c in plan.state.cards.values():
        if c.zone.endswith(":battlefield") and c.controller == pid and plan.in_game(c) and not c.face_down:
            ch = plan.ch(c)
            if "Artifact" in ch.types and ch.name:
                names[ch.name] = names.get(ch.name, 0) + 1
    if max(names.values(), default=0) < int(e["n"]):
        return True
    blockers = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.face_down
                and "can't win the game" in " ".join(ab.text for ab in chars.of(c, plan.info).abilities)]
    if blockers:
        plan.note(f"{plan.name(pid)} would win the game, but {blockers[0].name} says a player can't: resolve it by hand")
        return True
    _win(plan, pid)
    return True


PRIMITIVES = {"populate": populate, "win_same_name": win_same_name}
RESUME = {"populate_choose": resume_populate}
