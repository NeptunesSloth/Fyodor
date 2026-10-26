"""-- one-card wordings (wave 110D) --

Requiem Monolith: "{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life."
That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery." The second sentence is a choice of the TARGET's
controller (608.2d: the player who is told "may" decides); the Monolith is the damage source (120.3, 609.7)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MONOLITH = ('{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life." '
            "That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery.")


ZHALFIR = "I, II — Another target nonland permanent phases out. It can't phase in for as long as you control this Saga."
PARK = "I — For each opponent, up to one target noncreature artifact they control becomes a 0/4 Wall artifact creature with defender for as long as you control this Saga."
PURSUIT = ("When this enchantment enters, suspect target creature an opponent controls. As long as this enchantment remains on the battlefield, "
            "that creature is also goaded.")
PURSUIT2 = ("At the beginning of combat on your turn, if two or more players have lost the game, gain control of all goaded and/or suspected "
             "creatures until end of turn. Untap them. They gain haste until end of turn.")
OBLIG = ("Return target creature card from an opponent's graveyard to the battlefield under their control with a duty counter on it. For as long as that "
         "creature has a duty counter on it, it is goaded, can't attack you or a permanent you control, and can't block creatures you control.")
RAVAGER = ("Whenever this creature transforms into Ravager of the Fells, it deals 2 damage to target opponent or planeswalker and 2 damage to up to one "
           "target creature that player or that planeswalker's controller controls.")
WALL = ("You may have this creature enter as a copy of any creature on the battlefield, except it's a Wall in addition to its other types and has defender. "
        "When you do, tap the copied creature and it doesn't untap during its controller's untap step for as long as you control this creature.")
ULTIMA = ("Whenever Ultima attacks, put a blight counter on target land. For as long as that land has a blight counter on it, it loses all land types and "
          'abilities and has "{T}: Add {C}."')
SYMPOSIUM = "Target player creates a token that's a copy of target creature you control."
NUKA = ("Whenever equipped creature attacks, until the end of defending player's next turn, that player gets two rad counters whenever they cast a spell.")
DIVINER = ("Whenever one or more other creatures you control enter, if they entered or were cast from a graveyard, create a token that's a copy of one of them. "
           "This ability triggers only once each turn.")
JIN3 = ("III — You may cast any number of spells from your hand without paying their mana costs. Exile this Saga, then return it to the battlefield.")
KITESAIL = ("When this creature enters, for each player, choose up to one other target artifact or creature that player controls. For as long as this creature "
            'remains on the battlefield, the chosen permanents become Treasure artifacts with "{T}, Sacrifice this artifact: Add one mana of any color" and lose all other abilities.')
SHELOB = ("Whenever another creature dealt damage this turn by a Spider you controlled dies, create a token that's a copy of that creature, except it's a Food artifact "
          'with "{2}, {T}, Sacrifice this token: You gain 3 life," and it loses all other card types.')
DACK = "Whenever you cast a spell that targets one or more permanents, gain control of those permanents."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    if ability.text == PURSUIT:  # Hot Pursuit: 701.60a suspect, 611.2b goaded (by its controller, 701.15a) while the Enchantment stays
        d = scripts.define(replace(ability, text=PURSUIT.split(" As long")[0]), ch)
        if d is not None:
            d["effects"] += [{"do": "goad_while110i", "who": "target"}]
        return d
    if ability.text == PURSUIT2:  # 603.4 intervening if (checked again as it resolves); 800.4a lost players are the ones out of the game
        d = scripts.define(replace(ability, text=PURSUIT2.replace("if two or more players have lost the game, ", "").replace("goaded and/or suspected", "goaded")), ch)
        if d is not None:
            two_lost = {"value": {"players_lost": 1}, "op": ">=", "n": 2}
            d["effects"] = [{"do": "only_if", "cond": two_lost, "skip": len(d["effects"])},
                            {**d["effects"][0], "who": d["effects"][0]["who"].replace('"goaded"', '"goaded_or_suspected"')}, *d["effects"][1:]]
            d["if"] = two_lost
        return d
    if ability.kind == "spell" and ability.text.split(" (")[0] == OBLIG:  # 611.2b: all three last while it has a duty counter; "you" is the spell's controller
        from app.rules import selectors

        d = scripts.define(replace(ability, text="Return target creature card from an opponent's graveyard to the battlefield under its owner's control "
                                                 "with a duty counter on it."), ch)
        if d is not None:
            mine = selectors.Selector(types=("Creature",), controller="player:@you").key()
            d["effects"][0]["as"] = "duty110d"  # (400.7: "that creature" is the new object)
            d["effects"] += [{"do": "until", "duration": "while_counter:duty", "n": 3}, {"do": "goad", "who": "ref:duty110d"},
                             {"do": "restrict", "who": "ref:duty110d", "rules": ["cant_attack_player_pw:@you"], "locked": True},
                             {"do": "restrict", "who": "ref:duty110d", "rules": ["cant_block_sel:" + mine], "locked": True}]
        return d
    if ability.text == RAVAGER:  # 115.1, 120.3: "that player" is the opponent, or the controller of the planeswalker, the first target names (player_relative)
        d = scripts.define(replace(ability, text=RAVAGER.replace("that player or that planeswalker's controller", "that player")), ch)
        if d is not None:
            d["targets"][1] = {**d["targets"][1], "of": 0}  # (as multi100n._blaze: the second group is relative to the first target's player)
        return d
    if ability.text == PARK:  # per_opponent.py reads "that player controls" (115.1: one group per opponent); 611.2b duration
        return scripts.define(replace(ability, text=PARK.replace(" they control", " that player controls").replace("this Saga", "~")), ch)
    if ability.text == ZHALFIR:  # 702.26a, 610.3: phased out, held out for as long as its controller controls the Saga
        d = scripts.define(replace(ability, text="I, II — Another target nonland permanent phases out."), ch)
        if d is not None:
            d["effects"] = [{"do": "phase_hold110d", "who": "target"}]
        return d
    if ability.text == WALL:  # 707.5 enters as a copy; 603.12 the reflexive trigger (on the copied creature) is queued by :func:`wall_entered`
        d = scripts.define(replace(ability, text=WALL.split(" When you do")[0]), ch)
        parsed = scripts.parse_effects("Tap target creature. It doesn't untap during its controller's untap step for as long as you control ~.")
        if d is not None and parsed is not None:
            d["reflex110d"] = [{**x, "who": "event"} if x.get("who") == "target" else x for x in parsed[0]]
        return d
    if ability.text == ULTIMA:  # 305.7 (no land types), 613.1f; lasts while the land has a blight counter (611.2b-style until-wrapper)
        d = scripts.define(replace(ability, text=ULTIMA.split(" and abilities and")[0].replace("land types", "abilities").replace("Ultima", "~") + "."), ch)
        if d is not None:
            d["effects"] = [{**x, "no_land_types110d": True, "abilities": ["{T}: Add {C}."]} if x.get("do") == "become" else x for x in d["effects"]]
        return d
    if ability.kind == "spell" and ability.text == SYMPOSIUM:  # 111.2 the token's creator is the target player; 707.2 it copies the creature (two target groups, 115.1)
        d = scripts.define(replace(ability, text="Create a token that's a copy of target creature you control."), ch)
        if d is not None:
            d["effects"] = [{**d["effects"][0], "who": "target:1", "creator": "target:0"}]
            d.update(target=None, targets=[{"what": "player", "min": 1, "max": 1}, {**d["target"], "min": 1, "max": 1}])
        return d
    if ability.text == NUKA:  # 603.7 a turn-long watch of the defending player's casts (508.5), ending in the cleanup of THEIR next turn (514.2)
        d = scripts.define(replace(ability, text="Whenever equipped creature attacks, until your next turn, whenever an opponent casts a spell, they get two rad counters."), ch)
        if d is not None and d["effects"][0].get("do") == "delayed":
            first = {k: v for k, v in d["effects"][0].items() if k != "next_turn"}
            d["effects"][0] = {**first, "end_of_next_turn": True, "player_ref110d": "defending_player"}
        return d
    if ability.text == DIVINER:  # 603.2c one batch; its controller picks the copied creature (707.2) from all of them; 603.4 "if" as Celes (conditions._SOME_OF_THEM)
        d = scripts.define(replace(ability, text=DIVINER.replace("if they entered or were cast from a graveyard", "if one or more of them entered from a graveyard or "
                                                                 "was cast from a graveyard").replace("one of them", "target creature you control")), ch)
        if d is not None and d["effects"][-1].get("do") == "token_copy":  # (a target stand-in: the grammar refuses "that creature" for a batch)
            d["target"] = None
            d["effects"] = [*({**x, "skip": 2} if x.get("do") == "only_if" else x for x in d["effects"][:-1]), {"do": "choose_one_of", "who": "ref:event", "n": 1, "as": "copy110d"}, {**d["effects"][-1], "who": "ref:copy110d"}]
        return d
    if ability.text == JIN3:  # 701.20e-style cast for free, then 400.7 the Saga returns as a new object (front face up: 712.14a, the default entry face)
        d = scripts.define(replace(ability, text=JIN3.split(" Exile")[0]), ch)
        d2 = scripts.define(replace(ability, text="III — Exile this Saga, then return it to the battlefield."), ch)
        if d is not None and d2 is not None:
            d["effects"] += d2["effects"]
        return d
    if ability.text == KITESAIL:  # 205.1a Treasure artifact (creature type dropped), 613.1d-f; 611.2b until it leaves; 115.1 one group per player (per_opponent)
        d = scripts.define(replace(ability, text="When this creature enters, for each player, up to one other target artifact or creature that player controls loses all "
                                                  "abilities for as long as this creature remains on the battlefield."), ch)
        if d is not None:
            d["effects"] = [{**x, "types": ["Artifact"], "artifact_types": ["Treasure"], "abilities": ["{T}, Sacrifice this artifact: Add one mana of any color"]}
                            if x.get("do") == "become" else x for x in d["effects"]]
        return d
    if ability.text == SHELOB:  # 707.9b the copy is a Food artifact only (the quoted comma belongs to the sentence, not the ability); 700.4 look back (events.py)
        return scripts.define(replace(ability, text=SHELOB.replace("life,\"", "life\"")), ch)
    if ability.text == DACK:  # Dack Fayden's emblem (114.1): the cast event's targets (115.9b: departed ones are ignored), permanently
        cond = events.parse_condition("you cast a spell that targets one or more permanents")
        assert cond is not None
        return {"kind": "triggered", "trigger": "event", "cond": cond, "optional": False, "target": None,
                "effects": [{"do": "spell_permanents110d", "selector": cond["targets"], "as": "dack110d"},
                            {"do": "gain_control", "who": "ref:dack110d", "to": "you"}]}
    if ability.text != MONOLITH:
        return None
    d = scripts.define(replace(ability, text=MONOLITH.replace(" That creature's controller may have this artifact deal 1 damage to it.", "")), ch)
    if d is not None:
        d["effects"] += [{"do": "may_hit110d", "bind": "hit110d"}, {"do": "only_if", "cond": {"succeeded": "hit110d"}, "skip": 1},
                         {"do": "damage", "who": "target", "n": 1}]
    return d


def may_hit(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects

    cards = effects._cards(plan, ctx, "target")
    context.bind_payment(ctx, e["bind"], False)
    if not cards or not plan.state.cards[cards[0]].zone.endswith(":battlefield"):
        return True
    who = plan.state.cards[cards[0]].controller
    effects.decide(plan, player=who, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: have it deal 1 damage to {plan.state.cards[cards[0]].name}?",
                   options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
                   resume={"step": "may_hit110d", "ctx": ctx, "bind": e["bind"]})
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    if len(chosen) != 1 or chosen[0] not in ("yes", "no"):
        raise ActionError("Choose yes or no")
    context.bind_payment(d.resume["ctx"], d.resume["bind"], chosen[0] == "yes")
    effects.continue_effects(plan, d.resume["ctx"])


def spell_permanents(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, token_copy_sources

    refs = token_copy_sources.spell_targets(plan, ctx, e["selector"])
    context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in refs]}
    return True


def phase_hold(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import ObjectRef
    from app.rules import effects, phase_lifetimes43

    ids = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    source = ObjectRef(card=ctx["source_card"], object_id=ctx["source_object"])
    phase_lifetimes43.phase_out(plan, source, ids, ctx["controller"], control=ctx["controller"])
    return True


GIFT_UP = "turned_up_attach110d"


def attach_up(plan: Any, card: Any) -> None:
    """Gift of Doom: 702.37e, 303.4f "As this Aura is turned face up, you may attach it to a creature": its controller picks any creature it can
    legally enchant (protection counts, targeting does not: 303.4d) before state-based actions would put the unattached Aura into the graveyard (704.5m)."""
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects, scripts
    from app.rules.targets import label

    if plan.manual(card) or not any(d.get("replacement") == GIFT_UP for d in scripts.definitions(plan.ch(card)).values()):
        return
    hosts = [c.id for c in plan.state.cards.values()
             if c.zone.endswith(":battlefield") and plan.ch(c).is_creature and c.id != card.id and attachments.host_problem(plan, card, c.id) is None]
    if hosts:
        effects.decide(plan, player=card.controller, kind="choose_one", prompt=f"{card.name}: attach it to a creature?",
                       options=[DecisionOption(id=c, label=label(plan, c), card_id=c) for c in hosts] + [DecisionOption(id="none", label="Don't attach")],
                       resume={"step": GIFT_UP, "card": card.id})


def resume_attach(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments

    if len(chosen) != 1 or (chosen[0] != "none" and chosen[0] not in plan.state.cards):
        raise ActionError("Choose a creature or decline")
    card = plan.state.cards.get(d.resume["card"])
    if chosen[0] != "none" and card is not None and card.zone.endswith(":battlefield") and attachments.host_problem(plan, card, chosen[0]) is None:
        attachments.attach(plan, card.id, chosen[0], d.player)


PRIMITIVES: dict[str, Any] = {"phase_hold110d": phase_hold, "may_hit110d": may_hit, "spell_permanents110d": spell_permanents}
RESUME: dict[str, Any] = {"may_hit110d": resume, GIFT_UP: resume_attach}


CALL = "Choose up to two. Return those cards from your graveyard to your hand."


def modal_lines(lines: list[Any]) -> list[Any]:
    """Call Damage Control: "Choose up to two. Return those cards from your graveyard to your hand. • Target artifact card. • ..." is up to two modes
    (700.2), each returning its one targeted card (the common instruction acts on each target on its own, 608.2b), as "Choose up to two — • Return
    target artifact card from your graveyard to your hand. • ..."."""
    if len(lines) < 3 or lines[0].text != CALL or not all(x.text.startswith("• Target ") and x.text.endswith(" card.") for x in lines[1:]):
        return lines
    return [replace(lines[0], text="Choose up to two —"),
            *(replace(x, text=x.text[:-1].replace("• Target ", "• Return target ") + " from your graveyard to your hand.") for x in lines[1:])]


def wall_entered(plan: Any, card: Any, new_oid: str) -> None:
    """Wall of Stolen Identity: 603.12 "When you do" (it entered as a copy of a creature): the reflexive ability is about that creature (the copy's source)."""
    from app.game.rules_state import ObjectRef, TriggerEvent
    from app.rules import copying, trigger_multipliers, triggers

    d = copying.enter_definition(plan, card)
    if d is None or not d.get("reflex110d"):
        return
    eff = copying._entering_effect(plan, card)
    src = eff.copy_entry_source if eff is not None else None
    if src is None or (c := plan.state.cards.get(src.card)) is None or not c.zone.endswith(":battlefield") or plan.oid(c) != src.object_id:
        return
    triggers._add(plan, controller=card.controller, source_card=card.id, source_object=new_oid, name=card.name, index=trigger_multipliers.REFLEXIVE,
                  definition={"kind": "triggered", "trigger": "reflexive", "effects": d["reflex110d"], "optional": False},
                  event=TriggerEvent(kind="reflexive", objects=[ObjectRef(card=src.card, object_id=src.object_id, zone=c.zone)], count=1))
