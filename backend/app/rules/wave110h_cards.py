"""Wave 110H one-card ability rewrites (exact Oracle text -> wording the grammar already reads)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

# Unscythe, Killer of Kings: the Scythe of the Wretched trigger (damage_death104) with another rider (702.6, 120.3, 603.10a).
_UNSCYTHE = ("Whenever a creature dealt damage by equipped creature this turn dies, you may exile that card. "
             "If you do, create a 2/2 black Zombie creature token.")


_LEECH = ('Enchanted creature has "If ~ would untap during your untap step, remove a +1/+1 counter from it instead. '
          'If you do, untap it."')


# Kosei, Penitent Warlord: a static grant with three conditions that must all hold (604.2, 611.3a): the one-condition grant, then the others added.
_KOSEI = ('As long as ~ is enchanted, equipped, and has a counter on it, ~ has "Whenever Kosei deals combat damage to an opponent, you draw that many '
          'cards and Kosei deals that much damage to each other opponent."')


# Immard: "put a counter on it or remove one" as the equal choice "you may remove one; if you don't, put one on" (608.2d); the reflexive
# trigger (603.12) still follows only the removal. ponytail: the put happens before the reflexive modes resolve; the modes don't read counters.
_IMMARD = ("Whenever ~ enters or attacks, put a charge counter on it or remove one from it. When you remove a counter this way, choose one \u2014")


def modal_header(ability: Any, ch: Any) -> Any:
    """Immard's header (the modes are read by modal_abilities.definitions): the rewritten text, else the ability unchanged."""
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != _IMMARD:
        return ability
    return replace(ability, text=ability.text[:ability.text.index(", put a charge")] + ", you may remove a charge counter from it. If you don't, "
                   "put a charge counter on it. When you do, choose one \u2014")


_PHOENIX = "When ~ dies, you may exile it and collect evidence 4. If you do, return this card to the battlefield tapped."
# The Spot, Living Portal: the card is put on the bottom (401.4); "If you do" holds only if it really got to the library (608.2c), then the linked exile returns.
# Wolverine, Fierce Fighter: a static read where damage is dealt (heal110h in replace.py): the damage marked earlier is removed as the new damage is marked.
_WOLVERINE = "If damage would be dealt to ~, instead that damage is dealt, but all other damage already dealt to him is healed."
_WINDS = "If a permanent with a wind counter on it would untap during its controller's untap step, remove all wind counters from it instead."
# Saproling Burst: the token's quoted CDA counts the counters on its creator (the permanent named in the quote, 111.2); the leaves trigger destroys the tokens that
# permanent made (its token_source), they can't be regenerated (701.19c).
_BURST_TOKEN = ("Remove a fade counter from ~: Create a green Saproling creature token. It has \"This token's power and toughness are each equal to the number of fade "
                "counters on ‹granter›.\"")
_BURST_LEAVES = "When ~ leaves the battlefield, destroy all tokens created with ~. They can't be regenerated."
_SPOT = "When ~ dies, put ~ on the bottom of ~'s owner's library. If you do, return the exiled cards to their owners' hands."
# Mysterious Limousine, in Oracle order (608.2c): exile the target (linked, 607.2a); if a creature really is in exile, return each OTHER linked card (not the one
# just exiled: exiled_with "other" skips cards exiled in this same resolution).
_LIMO = ("Whenever this Vehicle enters or attacks, exile up to one other target creature until this Vehicle leaves the battlefield. If a creature is put into "
         "exile this way, return each other card exiled with this Vehicle to the battlefield under its owner's control.")
# Stitcher Geralf: the controller picks up to two creature cards among the milled ones (any graveyard), exiles them, and the token is as big as their total power.
_GERALF = ("{2}{U}, {T}: Each player mills three cards. Exile up to two creature cards put into graveyards this way. Create an X/X blue Zombie creature "
           "token, where X is the total power of the cards exiled this way.")
_SCAPEGOAT = ("Whenever one or more other creatures you control enter, if this creature is suspected, you may suspect one of the other creatures. "
              "If you do, this creature is no longer suspected.")


_SPECTER = ("Whenever ~ deals combat damage to a player, you may pay {X}. If you do, that player reveals X cards from their hand and you choose one of "
            "them. That player discards that card.")
_AETHER = ("Whenever ~ blocks a creature, you may return ~ to its owner's hand. If you do, you may put a creature card from your hand onto the "
           "battlefield blocking that creature.")


def untap_hold(plan: Any, player: str, keep: list[str]) -> list[str]:
    """Bewitching Leechcraft (502.3, 614.1a): a tapped host that would untap loses a +1/+1 counter instead and untaps; with none (or if the
    counter can't come off) it stays tapped. Returns the ids to keep tapped; hosts already kept tapped are not "going to untap"."""
    from app.rules import counter_removal_results, permissions

    held: list[str] = []
    for aura, _i, d in permissions._table_statics(plan.state, plan.info, {"grant"}):
        if not d.get("untap_counter110h"):
            continue
        host = plan.state.cards.get(aura.attached_to or "")
        # 616.1/614.5: stun first -> stun counter lost, +1/+1 kept. Leechcraft first -> +1/+1 lost, then the modified untap event still meets the
        # stun replacement -> stun counter lost, stays tapped. Same outcome minus a +1/+1 counter, so the host controller's choice is always
        # stun first; no prompt needed (a stunned host is in ``keep`` already).
        if host is None or not host.tapped or host.controller != player or host.id in keep or host.id in held:
            continue
        if not counter_removal_results.remove(plan, host.id, "+1/+1", 1, by=player):
            held.append(host.id)
    # Freyalise's Winds (614.1a): an untapping permanent with wind counters loses them all instead and stays tapped. A stunned one has both
    # replacements (616.1): its controller chooses, and stun first dominates. Either order ends tapped this step, minus one counter. Stun first
    # leaves wind counters, wind first leaves the stun counter. A wind counter only matters while Freyalise's Winds is on the battlefield (its
    # replacement is that ability's), where it holds one untap exactly like the stun counter; a stun counter always holds one. So stun first is
    # never worse, no prompt needed (the stunned permanent is already in ``keep``).
    if permissions._table_statics(plan.state, plan.info, {"wind110h"}):
        for c in plan.state.cards.values():
            if c.tapped and c.controller == player and c.zone.endswith(":battlefield") and c.counters.get("wind") and c.id not in keep and c.id not in held:
                counter_removal_results.remove(plan, c.id, "wind", c.counters["wind"], by=player)
                held.append(c.id)
    return held


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == _UNSCYTHE:
        native = scripts.define(replace(ability, text=text.replace("equipped creature", "~")), ch)
        if native is None or "damaged_by_self" not in native.get("cond", {}):
            return None
        cond = {**native["cond"], "damaged_by_host104": True}
        cond.pop("damaged_by_self")
        return {**native, "cond": cond}
    if text == _KOSEI:
        native = scripts.define(replace(ability, text=text.replace("is enchanted, equipped, and has a counter on it", "is enchanted").replace("Kosei", "~")), ch)
        if native is None or native.get("conditions") != [{"static": "self", "test": "enchanted"}]:
            return None
        return {**native, "conditions": [*native["conditions"], {"static": "self", "test": "equipped"},
                                         {"static": "self_counter", "counter": None, "op": ">=", "n": 1}]}
    if text == _SCAPEGOAT.replace("this creature", "~") or text == _SCAPEGOAT:
        native = scripts.define(replace(ability, text="Whenever one or more other creatures you control enter, if this creature is suspected, draw a card."), ch)
        return None if native is None else {**native, "effects": [{"do": "scapegoat110h"}]}
    if text == _SPECTER.replace("~", ch.name) or text == _SPECTER:  # Hollow Specter: the paid X (107.3) sizes the reveal (701.20a), then Cabal Interrogator's chain
        native = scripts.define(replace(ability, text="Whenever ~ deals combat damage to a player, you may pay {X}. If you do, that player discards X cards."), ch)
        if native is None or native["effects"][-1].get("do") != "discard":
            return None
        paid = native["effects"][-1]["n"]
        chain = scripts.parse_effects("Target player reveals three cards from their hand and you choose one of them. That player discards that card.")
        if chain is None or len(chain[0]) != 3:
            return None
        reveal, pick, drop = chain[0]
        return {**native, "effects": [*native["effects"][:-1], {**reveal, "who": "event_player", "n": paid}, pick, drop]}
    if text == _AETHER:
        native = scripts.define(replace(ability, text=text.replace(" blocking that creature.", ".")), ch)
        if native is None or native["effects"][-1].get("do") != "put_from_hand":
            return None
        return {**native, "effects": [*native["effects"][:-1], {**native["effects"][-1], "blocking": True}]}
    if text == _PHOENIX:  # the card exiled as the cost is a new object (400.7); the return takes that exiled object (the cost's "pay0x" binding)
        native = scripts.define(replace(ability, text=text.replace("return this card", "return it")), ch)  # (the grammar's own reading)
        if native is None or native["effects"][-1].get("who") != "event.new":
            return None
        return {**native, "effects": [*native["effects"][:-1], {**native["effects"][-1], "who": "ref:pay0x"}]}
    if text == _BURST_TOKEN:
        return scripts.define(replace(ability, text="Remove a fade counter from this enchantment: Create a green Saproling creature token with \"This token's power "
                                      "and toughness are each equal to the number of fade counters on its creator.\""), ch)
    if text == _BURST_LEAVES:
        native = scripts.define(replace(ability, text="When ~ leaves the battlefield, destroy all Saprolings. They can't be regenerated."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["destroy", "no_regen"]:
            return None
        return {**native, "effects": [{"do": "made110h", "as": "made110h"}, {**native["effects"][0], "who": "ref:made110h"}, native["effects"][1]]}
    if text == _WINDS:
        return {"kind": "static", "static": "wind110h", "effects": []}
    if text == _WOLVERINE:
        return {"kind": "static", "static": "heal110h", "effects": []}
    if text == _SPOT:
        put = scripts.define(replace(ability, text="When ~ dies, put it on the bottom of its owner's library."), ch)
        back = scripts.define(replace(ability, text="When ~ dies, return each card exiled with ~ to its owner's hand."), ch)
        if put is None or back is None or put["effects"] != [{"do": "to_library", "who": "event.new", "place": "bottom"}]:
            return None
        return {**put, "effects": [{**put["effects"][0], "do": "bottom_did110h", "did": "spot110h"},
                                   {"do": "only_if", "cond": {"succeeded": "spot110h"}, "skip": len(back["effects"])}, *back["effects"]]}
    if text == _LIMO.replace("this Vehicle", "~"):
        until = scripts.define(replace(ability, text=_LIMO[:_LIMO.index(" If a creature")]), ch)
        if until is None or [e["do"] for e in until["effects"]] != ["exile_until"]:
            return None
        # (the linked exile, 607.2a: marked by hand, the sub-reading cannot see the card's other sentence)
        return {**until, "effects": [{**until["effects"][0], "link": True}, {"do": "limo_back110h"}]}
    if text == _GERALF:
        from app.rules import card_copy_sources as C

        native = scripts.define(replace(ability, text="{2}{U}, {T}: Each player mills three cards. Create a 3/3 blue Zombie creature token."), ch)
        token = scripts.parse_effects("Create an X/X blue Zombie creature token, where X is the number of cards in your hand.")
        if native is None or token is None or [e["do"] for e in native["effects"]] != ["mill", "create_token"]:
            return None
        made = {**token[0][0], "token": {**token[0][0]["token"], "power": {"total_power100e": "geralf"}, "toughness": {"total_power100e": "geralf"}}}
        pick = C.select(who="ref:geralf_milled", n=2, upto=True, filter=C.key("creature card in a graveyard"))
        pick["as"], pick["prompt"] = "geralf_pick", "Stitcher Geralf: exile up to two creature cards put into graveyards this way"
        return {**native, "effects": [{**native["effects"][0], "as": "geralf_milled"}, pick,
                                      {"do": "exile", "who": "ref:geralf_pick", "as": "geralf"}, made]}
    if text == _LEECH:  # the grant definition the staged untap model reads (tests/test_rules_untap_attempts45.py), marked: untap_hold carries it out
        return {"kind": "static", "static": "grant", "effects": [], "who": "attached", "attached_kind": "creature", "conditions": [], "p": 0, "t": 0,
                "base": None, "keywords": [], "grants": [text.split('"')[1]], "rules": [], "untap_counter110h": True}
    return None


# -- spell bodies -------------------------------------------------------------------------------------
def _binding_negotiation() -> Any:
    from app.rules import scripts
    from app.rules import static_spell100c as S

    base = scripts.parse_effects("Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it.")
    if base is None:
        return None
    effects, target, flag = base
    did = next(e["did"] for e in effects if e.get("did"))
    # "Otherwise" (608.2c): you didn't choose a card. Your choice of one or none of the face-up exiled cards that player owns (406.3), to their graveyard (400.3).
    yard = {"do": "return_choice", "who": f"{S.OWNED}target|{S._key(card=True, extras=('face_up',), zones=('exile',))}", "to": "graveyard",
            "n": 1, "upto": True, "random": False, "label": "face-up exiled card"}
    return [*effects, {"do": "only_if", "cond": {"not": {"succeeded": did}}, "skip": 1}, yard], target, flag


def _carom() -> Any:
    from app.rules import damage_redirection_effects as R

    # 614.9: the redirection of the shared 3-damage recipe, one damage
    return [{"do": R.STEP, "mode": "finite", "origin": "target:0", "destination": "target:1", "n": 1}], \
        [{"what": R.key("creature")}, {"what": R.key("creature"), "distinct_from": [0]}], False


def _episode() -> Any:
    return [{"do": "episode110h", "who": "target"}], "player", False


def _fold() -> Any:
    """Welcome to the Fold: toughness 2 or less normally; with madness paid the bound is X, the madness cost's X (107.3b). Both are the one native
    "gain control of target creature if its toughness is N or less" (608.2b: the target is checked as the spell resolves)."""
    from app.rules import scripts

    native = scripts.parse_effects("Gain control of target creature if its toughness is 2 or less.")
    if native is None or len(native[0]) != 2:
        return None
    (gate, grab), target, flag = native[0], native[1], native[2]
    madness = {"object": "self", "cast": {"alt": "madness"}}
    big = {**gate, "cond": {**gate["cond"], "n": {"count_value": {"x": 1}}}}
    return [{"do": "only_if", "cond": {"not": madness}, "skip": 2}, gate, grab,
            {"do": "only_if", "cond": madness, "skip": 2}, big, grab], target, flag


def _lava_burst() -> Any:
    """Lava Burst: the damage to a creature can't be prevented (615.12) or redirected (614.9): flags set per creature recipient in effects._deal."""
    from app.rules import scripts

    native = scripts.parse_effects("~ deals X damage to any target.")
    if native is None or [e.get("do") for e in native[0]] != ["damage"]:
        return None
    return [{**native[0][0], "creature_firm110h": True}], native[1], native[2]


def _firestorm() -> Any:
    """Temporal Firestorm: chosen as it resolves, not targeted (608.2d, 115.1): up to X of your creatures and/or planeswalkers (X = kicks) phase out (702.26)."""
    from app.rules import selectors

    key = selectors.parse("creatures and/or planeswalkers you control").key()  # type: ignore[union-attr]
    return [{"do": "player_chooses", "who": "you", "sel": key, "n": {"kicked": 1}, "label": "creature or planeswalker", "upto": True, "optional": True,
             "as": "gco"}, {"do": "phase_out", "who": "ref:gco"}], None, False


def _support_x() -> Any:
    """Support X (701.41a) on an instant/sorcery: "other" is every creature, so the X-sized group counter wording."""
    from app.rules import scripts

    return scripts.parse_effects("Put a +1/+1 counter on each of up to X target creatures.")


def _specter_mortality() -> Any:
    """Specter of Mortality: chosen as it resolves (not targeted, 608.2d): any number of your graveyard creature cards are exiled, then each other creature
    gets -X/-X for the number exiled. ponytail: the "When you do" reflexive (603.12) resolves inline; it has no targets, so only the stack timing is lost."""
    from app.rules import scripts

    native = scripts.parse_effects("Exile up to three target creature cards from your graveyard. Each other creature gets -X/-X until end of turn, "
                                   "where X is the number of cards exiled this way.")
    if native is None or [e.get("do") for e in native[0]] != ["exile", "pump"]:
        return None
    (_, pump), (spec,) = native[0], native[1]
    return [{"do": "player_chooses", "who": "you", "sel": spec["what"], "n": 99, "label": "creature card", "upto": True, "optional": True, "as": "gco"},
            {"do": "exile", "who": "ref:gco", "as": "e0"}, pump], None, False


def _time_reaper() -> Any:
    """Time Reaper: the damaged player's face-up exiled card goes to the bottom of its owner's library; "if you do" (the card reached the library), gain 3."""
    from app.rules import scripts

    native = scripts.parse_effects("Put target face-up card that player owns in exile on the bottom of its owner's library.")
    if native is None or [e.get("do") for e in native[0]] != ["to_library"]:
        return None
    effects, target, flag = native
    return [{**effects[0], "do": "bottom_did110h", "did": "pdid110h"}, {"do": "only_if", "cond": {"succeeded": "pdid110h"}, "skip": 1},
            {"do": "gain_life", "who": "you", "n": 3}], target, flag


def _outmaneuver() -> Any:
    from app.rules import scripts

    base = scripts.parse_effects("X target blocked creatures gain flying until end of turn.")
    return None if base is None else ([{"do": "assign_unblocked110h", "who": "target:0"}], base[1], base[2])


def _unleash() -> Any:
    from app.rules import scripts

    got = scripts.parse_effects("Destroy target artifact or enchantment an opponent controls with mana value less than or equal to that amount of excess damage.")
    if got is None:
        return None
    ability = {"kind": "triggered", "trigger": "reflexive", "effects": got[0], "optional": False, **scripts.target_fields(got[1])}
    return [{"do": "damage", "who": "target:0", "n": 7, "bind_excess": "excess_dealt"}, {"do": "excess_reflex110h", "ability": ability}], \
        [{"what": "creature_or_planeswalker", "min": 1, "max": 1}], False


def _revival() -> Any:
    from app.rules import scripts, selectors

    got = scripts.parse_effects("Return up to one permanent card from your graveyard to the battlefield. You lose 3 life for each card returned this way. Exile ~.")
    if got is None or [e["do"] for e in got[0]] != ["return_choice", "lose_life", "exile"]:
        return None
    # one card for each permanent type (205.2a): the answer is checked as a matching of cards to types (effects.check_total_power, "party"), an artifact
    # creature standing for one of its types only
    kinds = [selectors.parse(f"{t} card in your graveyard").key() for t in ("artifact", "battle", "creature", "enchantment", "land", "planeswalker")]
    lose = got[0][1]
    lose = {**lose, "n": {"times": [3, {**lose["n"]["times"][1], "this_way": "battlefield_put"}]}}  # (the grammar counts cards returned to a hand; these went to the battlefield)
    return [{**got[0][0], "n": 6, "label": "card of each permanent type", "party": kinds}, lose, *got[0][2:]], got[1], got[2]


def excess_reflex(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """603.12, 120.10: "When it deals excess damage this way, ..." triggers once if there was excess; the trigger's amount is that excess, and its target
    (chosen when it goes on the stack, 603.3d) is bounded by it."""
    from app.game.rules_state import TriggerEvent
    from app.rules import context
    from app.rules.triggers import _add

    excess = max((int(b.get("n") or 0) for k, b in context.refs(ctx).items() if k.endswith("excess_dealt")), default=0)  # (bound under a prefixed name)
    if excess >= 1:
        _add(plan, controller=ctx["controller"], source_card=ctx.get("source_card") or "", source_object=ctx.get("source_object") or "",
             name=str(ctx.get("name") or ""), index=7300, definition=e["ability"], event=TriggerEvent(kind="reflexive", amount=excess))
    return True


BUILDERS = {
    "For each permanent type, return up to one card of that type from your graveyard to the battlefield. You lose 3 life for each card returned this way. "
    "Exile ~.": _revival,
    "~ deals 7 damage to target creature or planeswalker. When it deals excess damage this way, destroy target artifact or enchantment an opponent controls "
    "with mana value less than or equal to that amount of excess damage.": _unleash,
    "X target blocked creatures assign their combat damage this turn as though they weren't blocked.": _outmaneuver,
    "put target face-up card they own in exile on the bottom of their library. If you do, you gain 3 life.": _time_reaper,
    "you may exile one or more creature cards from your graveyard. When you do, each other creature gets -X/-X until end of turn, where X is the "
    "number of cards exiled this way.": _specter_mortality,
    "Support X.": _support_x,
    "Choose up to X creatures and/or planeswalkers you control, where X is the number of times this spell was kicked. Those permanents phase out.":
        _firestorm,
    "~ deals X damage to any target. If ~ would deal damage to a creature, that damage can't be prevented or dealt instead to another permanent or "
    "player.": _lava_burst,
    "Gain control of target creature if its toughness is 2 or less. If this spell's madness cost was paid, instead gain control of that creature if "
    "its toughness is X or less.": _fold,
    "Target player reveals their hand and the top card of their library. You choose a card revealed this way. That player puts the chosen card "
    "on the bottom of their library.": _episode,
    "The next 1 damage that would be dealt to target creature this turn is dealt to another target creature instead.": _carom,
    "Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a face-up "
    "exiled card they own into their graveyard.": _binding_negotiation,
}


def parse(body: str) -> Any:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None


# -- Psychotic Episode ---------------------------------------------------------------------------------
def episode(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """701.20a: the target player reveals their hand and their top card; you choose one of the revealed cards; its owner puts it on the bottom."""
    from app.game.rules_state import DecisionOption
    from app.game.state import zone_key
    from app.rules import effects
    from app.rules.plan import decide

    players = effects._players(plan, ctx, e["who"])
    if not players:
        return True
    pid = players[0]
    effects.reveal_hand(plan, ctx, {"who": "target"})
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    if library:
        plan.do({"type": "reveal_top", "player": pid, "count": 1}, actor=pid)
    pool = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone == zone_key(pid, "hand")] + library[:1]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Choose a revealed card",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=1, max_choices=1, resume={"step": "episode110h", "ctx": ctx, "pid": pid, "pool": pool})
    return False


def resume_episode(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, pid, pool = d.resume["ctx"], d.resume["pid"], d.resume["pool"]
    chosen = [c for c in chosen[:1] if c in pool and c in plan.state.cards]
    effects._after_hand_choice(plan, ctx, chosen)  # the unchosen revealed hand cards stop being revealed
    for cid in chosen:
        plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[cid].name}", [cid], actor=d.player)
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"}, "position": "bottom"}, actor=pid)
    effects.continue_effects(plan, ctx)


# -- Frantic Scapegoat ---------------------------------------------------------------------------------
def scapegoat(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """701.60a, 603.4: you may suspect one of the other creatures that entered (this batch); if you do, this creature is no longer suspected."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    me = ctx["source_card"]
    pool = [c for c in dict.fromkeys([*context.objects(plan, ctx, context.EVENT_NEW), *context.objects(plan, ctx, context.EVENT)]) if c != me and plan.state.cards[c].zone.endswith(":battlefield")
            and plan.state.cards[c].controller == ctx["controller"] and plan.ch(plan.state.cards[c]).is_creature]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Suspect one of the other creatures?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in pool],
           min_choices=0, max_choices=1, resume={"step": "scapegoat110h", "ctx": ctx, "pool": pool})
    return False


def resume_scapegoat(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    chosen = [c for c in chosen[:1] if c in d.resume["pool"] and c in plan.state.cards]
    if chosen:
        context.bind_objects(plan, ctx, "_scapegoat", chosen)
        effects.PRIMITIVES["suspect"](plan, ctx, {"do": "suspect", "who": "ref:_scapegoat"})
        if plan.oid(chosen[0]) in plan.rules.suspected:  # (not when it can't become suspected: no "if you do")
            effects.PRIMITIVES["unsuspect100f"](plan, ctx, {"do": "unsuspect100f", "who": "self"})
    effects.continue_effects(plan, ctx)


def bottom_did(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """to_library that records "if you do": the target reached its owner's library (608.2c)."""
    from app.rules import context, effects

    cards = effects._cards(plan, ctx, e["who"])
    done = effects.PRIMITIVES["to_library"](plan, ctx, {**e, "do": "to_library"})
    context.bind_payment(ctx, e["did"], any(plan.state.cards[c].zone.endswith(":library") for c in cards))
    return done


def healed(plan: Any, creatures: dict[str, int]) -> list[str]:
    """Creatures dealt damage that carry the heal static (Wolverine, Fierce Fighter): their earlier marked damage is healed first."""
    from app.rules import permissions

    mine = {src.id for src, _, _ in permissions._table_statics(plan.state, plan.info, {"heal110h"})}
    return [c for c, n in creatures.items() if n > 0 and c in mine]


def limo_back(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import effects, exiled_with

    back = {"do": "return_card", "who": f"{exiled_with.WHO}:other", "to": "battlefield", "tapped": False, "under": "owner"}  # (built here: a stored WHO would read as its own pronoun)
    # "If a creature is put into exile this way" (608.2c): judged by what the exile really recorded (a replaced exile records nothing).
    return effects.PRIMITIVES["return_card"](plan, ctx, back) if ctx.get("exiled_now") else True


def assign_unblocked(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Outmaneuver (510.1c exception): the targets assign their combat damage this turn as though they weren't blocked (no choice: no "may")."""
    from app.rules import effects

    for c in effects._cards(plan, ctx, e["who"]):
        plan.rules.assign_forced110h[c] = plan.state.turn.number
    return True


def made(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """The battlefield tokens created with the source (token_source, 111.2), bound for the next effect."""
    from app.rules import context

    src = ctx.get("source_card")
    context.bind_objects(plan, ctx, e["as"], [c.id for c in plan.state.cards.values()
                                              if c.is_token and c.zone.endswith(":battlefield") and c.token_source is not None and c.token_source.source_id == src])
    return True


PRIMITIVES = {"assign_unblocked110h": assign_unblocked, "made110h": made, "limo_back110h": limo_back, "bottom_did110h": bottom_did, "episode110h": episode, "scapegoat110h": scapegoat, "excess_reflex110h": excess_reflex}
RESUME = {"episode110h": resume_episode, "scapegoat110h": resume_scapegoat}
