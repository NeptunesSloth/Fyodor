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


def untap_hold(plan: Any, player: str, keep: list[str]) -> list[str]:
    """Bewitching Leechcraft (502.3, 614.1a): a tapped host that would untap loses a +1/+1 counter instead and untaps; with none (or if the
    counter can't come off) it stays tapped. Returns the ids to keep tapped; hosts already kept tapped are not "going to untap"."""
    from app.rules import counter_removal_results, permissions

    held: list[str] = []
    for aura, _i, d in permissions._table_statics(plan.state, plan.info, {"grant"}):
        if not d.get("untap_counter110h"):
            continue
        host = plan.state.cards.get(aura.attached_to or "")
        if host is None or not host.tapped or host.controller != player or host.id in keep or host.id in held:
            continue
        if not counter_removal_results.remove(plan, host.id, "+1/+1", 1, by=player):
            held.append(host.id)
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


BUILDERS = {
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


PRIMITIVES = {"episode110h": episode}
RESUME = {"episode110h": resume_episode}
