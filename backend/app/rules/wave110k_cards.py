"""-- wave 110K -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's (or spell's) Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from typing import Any

Def = dict[str, Any]

# -- Library of Lat-Nam: "An opponent chooses one —" (608.2d: the mode is chosen on resolution by the player the text names) --
_LATNAM = ["An opponent chooses one —", "• You draw three cards at the beginning of the next turn's upkeep.",
           "• You search your library for a card, put that card into your hand, then shuffle."]
_LATNAM_MODES = ["Draw three cards at the beginning of the next turn's upkeep.", "Search your library for a card, put that card into your hand, then shuffle."]


def spell(ch: Any, lines: list[Any]) -> Def | None:
    """Spell definitions of whole-spell wordings: the chooser's modes are read as the native wording of each bullet."""
    from app.rules import scripts

    if [x.text for x in lines] != _LATNAM:
        return None
    modes = [scripts.parse_effects(m) for m in _LATNAM_MODES]
    if any(m is None or m[1] is not None for m in modes):
        return None
    return {"kind": "spell", "whole110k": True, "effects": [{"do": "opponent_mode110k", "modes": [m[0] for m in modes if m is not None],
                                          "labels": ["Its controller draws three cards at the beginning of the next turn's upkeep",
                                                     "Its controller searches their library for a card"]}]}


def opponent_mode(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """An opponent picks the mode; with several opponents the controller picks which one (800.4: only players still in the game)."""
    from app.rules import effects

    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    if not opponents:
        return True
    if len(opponents) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent to choose the mode",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in opponents],
                       resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e, "opponents": opponents})
        return False
    return _ask(plan, ctx, e, opponents[0])


def _ask(plan: Any, ctx: dict[str, Any], e: dict[str, Any], chooser: str) -> bool:
    from app.rules import effects

    effects.decide(plan, player=chooser, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose one'}: choose one",
                   options=[effects.DecisionOption(id=str(i), label=label) for i, label in enumerate(e["labels"])],
                   resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e})
    return False


def resume_opponent_mode(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["effect"]
    if "opponents" in d.resume:
        if chosen[0] not in d.resume["opponents"]:
            raise ValueError("not an opponent")
        _ask(plan, ctx, e, chosen[0])
        return
    if chosen[0] not in {str(i) for i in range(len(e["modes"]))}:
        raise ValueError("not a mode")
    ctx["effects"][ctx["next"]:ctx["next"]] = e["modes"][int(chosen[0])]
    effects.continue_effects(plan, ctx)


def as_controller(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The next instructions are done by the controller the bound permanent last had (a player who left the game is gone: they are skipped, 800.4a)."""
    from app.rules import effects

    owners = effects._players(plan, ctx, e["who"])
    if not owners:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
        return True
    ctx.setdefault("controllers", []).append(ctx["controller"])
    ctx["controller"] = owners[0]
    return True


def cant_phase_in(plan: Any, card_id: str) -> bool:
    """Held out of phasing in by a Teferi-style rule (phasing.untap_step)."""
    oid = plan.oid(card_id)
    return any(oid in h.objects for h in plan.rules.phase_holds110k)


def end_of_turn(plan: Any) -> None:
    """The cleanup step of the holder's next turn (a later turn than the one the hold began in) ends the holds (514.2, 611.2a)."""
    plan.rules.phase_holds110k = [h for h in plan.rules.phase_holds110k if h.player in plan.live() and not (h.player == plan.active and plan.state.turn.number > h.turn)]  # (800.4m: a departed player's duration ends with them)


def phase_out_hold(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """phasing.phase_out, then a rule on exactly the objects that phased out (702.26b: one that did not, e.g. "can't phase out", is not held) that they
    can't phase in until the cleanup step of the controller's next turn (611.2a, 514.2; phasing.untap_step reads the rule)."""
    from app.game.rules_state import PhaseHold110K
    from app.rules import effects, phasing

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield") and not phasing._held(plan, c)]
    if cards:
        plan.do({"type": "phase_shift", "card_ids": cards, "out": True}, actor=ctx["controller"])
    out = [plan.oid(c) for c in cards if plan.state.cards[c].zone.endswith(":phased")]
    if out:
        plan.rules.phase_holds110k.append(PhaseHold110K(objects=out, player=ctx["controller"], turn=plan.state.turn.number))
    return True


def extra_combat_after_first(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """500.8: an additional combat phase after the first combat phase of this turn. Before it (the precombat main phase, nothing else queued) the natural
    combat stays first and the added one follows it; during it, the phase is added directly after it; once it is over there is no phase to add it
    after, so nothing happens."""
    from app.rules import combat_rules

    r, phase = plan.rules, plan.state.turn.phase
    added = {"do": "extra_phases", "after": "phase", "then": e["then"]}
    if phase == "main1" and r.combats == 0 and not r.extra_phases:
        combat_rules.extra_phases(plan, ctx, added)
        r.extra_phases = [r.extra_phases[1], r.extra_phases[0]]  # [the natural first combat, the added one]
    elif phase in combat_rules._COMBAT and r.combats == 1:
        combat_rules.extra_phases(plan, ctx, added)
    else:
        plan.note(f"{ctx.get('name') or 'It'}: there is no first combat phase to add an additional combat phase after (500.8)")
    return True


def villain110k(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """villainous.villain for a spell: the player who faces the choice is not an event's player (a spell has no event), so the options carry a marker that
    becomes "that player" as the choice begins."""
    import json

    from app.rules import villainous

    return villainous.villain(plan, ctx, {**json.loads(json.dumps(e).replace("THAT110K", "event_player")), "do": "villain"})


def shuffle_other(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"They shuffle another creature they own into their library": the player picks one of the creatures they own on the battlefield (other than the one
    just shuffled away: it isn't there any more), nothing if they own none (701.55b)."""
    from app.rules import effects

    pid = effects._players(plan, ctx, e["who"])
    if not pid:
        return True
    mine = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.owner == pid[0] and plan.in_game(c) and plan.ch(c).is_creature]
    if not mine:
        plan.note(f"{plan.name(pid[0])} owns no other creature to shuffle into their library")
        return True
    effects.decide(plan, player=pid[0], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a creature you own to shuffle into your library",
                   min_choices=1, max_choices=1, options=[effects.DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in mine],
                   resume={"step": "shuffle_other110k", "ctx": ctx, "mine": mine})
    return False


def resume_shuffle_other(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in d.resume["mine"]:
        raise ValueError("not one of the creatures")
    # (wave 110E: queued as the next instruction, so the run loop asks 903.9b before a chosen commander moves)
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "to_library", "who": f"object:{plan.oid(chosen[0])}", "place": "shuffle"}]
    effects.continue_effects(plan, ctx)


def copies_of_revealed(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"If a creature card is revealed this way, you may have creatures you control other than this creature become copies of that card until end of
    turn": its controller decides; the copies take the card's copiable values as the effect begins (707.2, 707.9, 611.2c)."""
    from app.rules import effects, selectors

    _, looked = effects._looked(plan, ctx)
    if len(looked) != 1 or "Creature" not in plan.ch(plan.state.cards[looked[0]]).types:
        return True
    others = selectors.Selector(types=("Creature",), controller="you", other=True).key()
    if not effects._cards(plan, ctx, others):
        return True
    effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{plan.state.cards[looked[0]].name}: have your other creatures become copies of it?",
                   options=[effects.DecisionOption(id="yes", label="Yes, they become copies of it until end of turn"), effects.DecisionOption(id="no", label="No")],
                   resume={"step": "copies_of_revealed110k", "ctx": ctx, "card": looked[0], "who": others})
    return False


def resume_copies_of_revealed(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import context, copying, effects

    ctx = d.resume["ctx"]
    card = plan.state.cards.get(d.resume["card"])
    if chosen == ["yes"] and card is not None and card.zone.endswith(":library"):
        context.bind_objects(plan, ctx, "revealed110k", [card.id])
        copying.become_copy(plan, ctx, {"do": "become_copy", "who": d.resume["who"], "with": "ref:revealed110k", "duration": "end_of_turn"})
    effects.continue_effects(plan, ctx)


def control_swap(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Cruel Entertainment (723.1, 723.1a): each of the two target players controls the other during that other player's next turn. A half whose players aren't
    both still in the game does nothing (800.4)."""
    from app.game.rules_state import PlayerControl
    from app.rules import effects

    first, second = (effects._players(plan, ctx, f"target:{i}") for i in (0, 1))
    if len(first) != 1 or len(second) != 1 or first == second:
        plan.note(f"{ctx.get('name') or 'It'}: both targets are needed for the players to control each other (608.2b)")
        return True
    name = ctx.get("name") or "An effect"
    for controller, controlled in ((first[0], second[0]), (second[0], first[0])):
        old = [c for c in plan.rules.player_control if c.controlled == controlled and c.status == "pending" and not c.obj]  # 723.1a: the last one works
        plan.rules.player_control = [c for c in plan.rules.player_control if c not in old]
        plan.rules.player_control.append(PlayerControl(controlled=controlled, controller=controller, label=name, extra_after=sum(c.extra_after for c in old)))
        plan.note(f"{plan.name(controller)} will control {plan.name(controlled)} during their next turn ({name}, 723.1)", actor=ctx["controller"])
    return True


def attach_self_choose(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Attach it to a creature you control": not targeted, chosen as it resolves among the creatures it could be attached to (701.3a-b); none, it stays."""
    from app.rules import attachments, effects

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return True
    me = ctx["controller"]
    hosts = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c) and c.controller == me and plan.ch(c).is_creature
             and c.id != card.attached_to and attachments.host_problem(plan, card, c.id) is None]
    if len(hosts) == 1:
        attachments.attach(plan, card.id, hosts[0], me)
        return True
    if not hosts:
        return True
    effects.decide(plan, player=me, kind="choose_one", prompt=f"{card.name}: attach it to a creature you control",
                   options=[effects.DecisionOption(id=h, label=plan.state.cards[h].name or "Creature", card_id=h) for h in hosts],
                   resume={"step": "attach_self_choose110k", "ctx": ctx, "card": card.id, "hosts": hosts})
    return False


def resume_attach_self_choose(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments, effects

    if len(chosen) != 1 or chosen[0] not in d.resume["hosts"]:
        raise ValueError("not one of the creatures")
    attachments.attach(plan, d.resume["card"], chosen[0], d.player)
    effects.continue_effects(plan, d.resume["ctx"])


def _sorcery_damage(plan: Any, spell_oid: str) -> int:
    """The damage a spell dealt this turn, to players and to permanents (120.3; the facts keep what was actually dealt)."""
    from app.rules.history import log_for

    return sum(f.amount for f in log_for(plan).facts if (f.kind == "damage" and f.object_id == spell_oid) or (f.kind == "damaged" and f.source == spell_oid))


def backdraft(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Backdraft: its controller chooses a player who cast a sorcery spell this turn, then one of that player's sorcery spells (a spell cast, 601.2i, whether or
    not it resolved); Backdraft deals half of the damage that spell dealt, rounded down (107.1a), to that player."""
    from app.rules.history import log_for

    sorceries: dict[str, list[Any]] = {}
    for note in log_for(plan).casts:
        if "Sorcery" in note.types and note.player in plan.live():
            sorceries.setdefault(note.player, []).append(note)
    if not sorceries:
        plan.note(f"{ctx.get('name') or 'It'}: no player has cast a sorcery spell this turn")
        return True
    return _pick_player(plan, ctx, sorceries)


def _pick_player(plan: Any, ctx: dict[str, Any], sorceries: dict[str, list[Any]]) -> bool:
    from app.rules import effects

    if len(sorceries) == 1:
        return _pick_spell(plan, ctx, next(iter(sorceries)), next(iter(sorceries.values())))
    effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a player who cast a sorcery spell this turn",
                   options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in sorceries],
                   resume={"step": "backdraft110k", "ctx": ctx, "stage": "player", "spells": {p: [n.object_id for n in ns] for p, ns in sorceries.items()}})
    return False


def _pick_spell(plan: Any, ctx: dict[str, Any], pid: str, notes: list[Any]) -> bool:
    from app.rules import effects

    oids = [n.object_id for n in notes]
    if len(oids) == 1:
        return _hit(plan, ctx, pid, oids[0])
    names = {n.object_id: (n.names or ["a sorcery spell"])[0] for n in notes}
    effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose one of {plan.name(pid)}'s sorcery spells",
                   options=[effects.DecisionOption(id=o, label=f"{names[o]} ({_sorcery_damage(plan, o)} damage)") for o in oids],
                   resume={"step": "backdraft110k", "ctx": ctx, "stage": "spell", "player": pid, "oids": oids})
    return False


def _hit(plan: Any, ctx: dict[str, Any], pid: str, spell_oid: str) -> bool:
    from app.rules import effects

    half = _sorcery_damage(plan, spell_oid) // 2
    return effects.PRIMITIVES["damage"](plan, ctx, {"do": "damage", "who": f"player:{pid}", "n": half}) if half > 0 else True


def resume_backdraft(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r, ctx = d.resume, d.resume["ctx"]
    if len(chosen) != 1:
        raise ValueError("choose one")
    if r["stage"] == "player":
        if chosen[0] not in r["spells"]:
            raise ValueError("not one of the players")
        from app.rules.history import log_for

        notes = [n for n in log_for(plan).casts if n.object_id in r["spells"][chosen[0]]]
        done = _pick_spell(plan, ctx, chosen[0], notes)
    else:
        if chosen[0] not in r["oids"]:
            raise ValueError("not one of the spells")
        done = _hit(plan, ctx, r["player"], chosen[0])
    if done:
        effects.continue_effects(plan, ctx)


def aura_for_each(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors

    sel = selectors.Selector(card=True, subtypes=("Aura",), zone_owner="you", zones=("hand", "graveyard")).key()
    tokens = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    ctx["effects"][ctx["next"]:ctx["next"]] = [
        {"do": "return_choice", "to": "battlefield", "tapped": False, "under": "you", "host": f"object:{plan.oid(t)}", "sel": sel, "n": 1, "upto": True,
         "random": False, "label": "Aura card"} for t in tokens]
    return True


def double_damage_turn(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Overblaze: for the rest of this turn (611.2a), each time the permanent would deal damage, it deals double that damage instead (614.1, 120.3) — the
    object the spell targeted (a new object, 400.7, is not it)."""
    from app.rules import effects, replace

    cards = effects._cards(plan, ctx, e["who"])
    if len(cards) != 1:
        return True
    replace.add_record(plan, event="damage", match={"source": {"oids": [plan.oid(cards[0])]}, "to": {}}, op={"do": "mul", "n": 2}, controller=ctx["controller"],
                       source=ctx.get("source_object"), source_card=ctx.get("source_card"), label=ctx.get("name") or "an effect")
    return True


def return_attached_you(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    return effects.PRIMITIVES["return_card"](plan, ctx, {**e, "do": "return_card", "host": f"player:{ctx['controller']}"})


def _curses_on(plan: Any, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c) and c.attached_player == pid and "Curse" in plan.ch(c).subtypes]


def curse_to_opponent(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    me = ctx["controller"]
    curses = _curses_on(plan, me)
    if not curses or not [p for p in plan.apnap() if p != me and p in plan.live()]:
        return True
    effects.decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: you may attach a Curse attached to you to one of your opponents",
                   min_choices=0, max_choices=1, options=[effects.DecisionOption(id=c, label=plan.state.cards[c].name or "Curse", card_id=c) for c in curses],
                   resume={"step": "curse_to_opponent110k", "ctx": ctx, "stage": "curse", "curses": curses})
    return False


def _curse_hosts(plan: Any, me: str, curse: str) -> list[str]:
    from app.rules import attachments

    return [p for p in plan.apnap() if p != me and p in plan.live() and attachments.host_problem(plan, plan.state.cards[curse], p, me) is None]


def _move_curse(plan: Any, ctx: dict[str, Any], curse: str, opponent: str) -> bool:
    from app.rules import attachments, effects

    attachments.attach(plan, curse, opponent, ctx["controller"])
    if plan.state.cards[curse].attached_player == opponent:  # "if you do"
        return effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": "you", "n": 2})
    return True


def resume_curse_to_opponent(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r, ctx = d.resume, d.resume["ctx"]
    if r["stage"] == "curse":
        if not chosen:
            effects.continue_effects(plan, ctx)
            return
        if len(chosen) != 1 or chosen[0] not in r["curses"]:
            raise ValueError("not one of the Curses")
        hosts = _curse_hosts(plan, ctx["controller"], chosen[0])
        if not hosts:
            effects.continue_effects(plan, ctx)
            return
        if len(hosts) == 1:
            if _move_curse(plan, ctx, chosen[0], hosts[0]):
                effects.continue_effects(plan, ctx)
            return
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose the opponent to attach the Curse to",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in hosts],
                       resume={"step": "curse_to_opponent110k", "ctx": ctx, "stage": "opponent", "curse": chosen[0], "hosts": hosts})
        return
    if chosen[0] not in r["hosts"]:
        raise ValueError("not one of the opponents")
    if _move_curse(plan, ctx, r["curse"], chosen[0]):
        effects.continue_effects(plan, ctx)


def runesword_rules(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """614.1a, 611.2a: for the rest of the turn, by the targeted object: a creature it deals damage to can't be regenerated (damaged_unregenerable) and a
    creature it dealt damage to that would die is exiled instead (replacements._record_exile_instead, rec "dealt_by110k")."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    if len(cards) != 1:
        return True
    oid = plan.oid(cards[0])
    plan.rules.no_regen_sources110k.append(oid)
    plan.rules.replacements.append({"id": f"rs{plan.rules.timestamp}", "kind": "exile_if_dies", "turn": plan.state.turn.number, "controller": ctx["controller"],
                                    "source": ctx.get("source_object"), "label": ctx.get("name") or "", "dealt_by110k": oid})
    return True


def return_self_hand(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Return ~ to its owner's hand" from the battlefield (bounce) or from the graveyard (the same object, 400.7: if it moved since, nothing)."""
    from app.rules import effects

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or plan.oid(card) != ctx.get("source_object"):
        return True
    if card.zone.endswith(":battlefield"):
        return effects.PRIMITIVES["bounce"](plan, ctx, {"do": "bounce", "who": "self"})
    if card.zone.endswith(":graveyard"):
        return effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "to": "hand", "who": "self_gy"})
    return True


# the label delayed.apply_duration writes on the table marker
from app.rules import delayed as _delayed  # noqa: E402

_delayed.LABELS["source_tapped_power110k"] = "for as long as ~ remains tapped and its power is at most ~'s"

PRIMITIVES = {"runesword_rules110k": runesword_rules, "return_attached_you110k": return_attached_you, "curse_to_opponent110k": curse_to_opponent, "double_damage_turn110k": double_damage_turn, "aura_for_each110k": aura_for_each, "backdraft110k": backdraft, "attach_self_choose110k": attach_self_choose, "control_swap110k": control_swap, "copies_of_revealed110k": copies_of_revealed, "villain110k": villain110k, "shuffle_other110k": shuffle_other, "extra_combat_after_first110k": extra_combat_after_first, "return_self_hand110k": return_self_hand, "opponent_mode110k": opponent_mode, "as_controller110k": as_controller, "phase_out_hold110k": phase_out_hold}
RESUME = {"curse_to_opponent110k": resume_curse_to_opponent, "backdraft110k": resume_backdraft, "attach_self_choose110k": resume_attach_self_choose, "copies_of_revealed110k": resume_copies_of_revealed, "opponent_mode110k": resume_opponent_mode, "shuffle_other110k": resume_shuffle_other}


# -- spell bodies: the whole body -> (the wording the grammar reads, what to do with its effects) --
_FLOURISH = ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller exiles cards from the top of "
             "their library until they exile a nonland card, then they may cast that card without paying its mana cost.")


def _flourish(effects: list[Def]) -> list[Def] | None:
    """Transforming Flourish: the last instruction of the native "… its controller gains 2 life" is the exile-and-cast, done by that player (608.2d, 118.9)."""
    from app.rules import scripts

    gain = scripts.parse_effects("Exile cards from the top of your library until you exile a nonland card, then you may cast that card without paying its mana cost.")
    if gain is None or len(effects) != 3 or effects[2].get("do") != "gain_life" or effects[2].get("who") != "ref:e0.controller":
        return None
    rest = [{"do": "as_controller110k", "who": "ref:e0.controller", "skip": len(gain[0]) + 1}, *gain[0], {"do": "as_player_end"}]
    return [effects[0], {**effects[1], "skip": len(rest)}, *rest]


_ICE = "Destroy target land that is snow or could produce {C}."
_ENDS = ("Target creature's owner shuffles it into their library, then faces a villainous choice — They lose 5 life, or they shuffle another creature they "
         "own into their library.")
_CRUEL = ("Choose target player and another target player. The first player controls the second player during the second player's next turn, and the second "
          "player controls the first player during the first player's next turn.")
_BACKDRAFT = ("Choose a player who cast one or more sorcery spells this turn. ~ deals damage to that player equal to half the damage dealt by one of those sorcery "
              "spells this turn, rounded down.")
_EPIPHANY = ("~ deals X damage to target creature. When that creature dies this turn, exile a number of cards from the top of your library equal to its power, "
             "then choose a card exiled this way. Until the end of your next turn, you may play that card.")
_OVERBLAZE = ("Each time target permanent would deal damage to a permanent or player this turn, it deals double that damage to that permanent or player "
              "instead.")
_ICE_EACH = "Destroy each land that is snow or could produce {C}."  # (overload, 702.96a: "target" read as "each")
_SHIP = ("After the first combat phase this turn, there's an additional combat phase. At the beginning of that combat, untap all creatures that attacked "
         "this turn.")
_TEFERI = "Each creature target opponent controls phases out. Until the end of your next turn, they can't phase in."


def _teferi(effects: list[Def]) -> list[Def] | None:
    """Teferi, Timeless Voyager -8: the creatures phase out, and those same objects (they are no longer on the battlefield to be selected) can't phase in."""
    if len(effects) != 1 or effects[0].get("do") != "phase_out":
        return None
    return [{**effects[0], "do": "phase_out_hold110k"}]


def _ship(effects: list[Def]) -> list[Def] | None:
    """Swinging Ship's visit: an extra combat after the first combat phase, with its delayed untap (500.8, 603.7)."""
    if len(effects) != 1 or effects[0].get("do") != "untap":
        return None
    return [{"do": "extra_combat_after_first110k", "then": effects}]


def _epiphany() -> Any:
    """End-Blaze Epiphany: the delayed trigger (603.7c) exiles as many cards as the creature's power as it last existed (603.10a, 608.2h), its controller then chooses
    one of the exiled cards (they are public, exiled face up) and may play it until the end of their next turn."""
    from app.rules import scripts

    head = scripts.parse_effects("~ deals X damage to target creature. When that creature dies this turn, exile the top X cards of your library, where X is its power.")
    tail = scripts.parse_effects("Exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.")
    if head is None or tail is None or [e["do"] for e in head[0]] != ["damage", "delayed", "deferred:exile_top"] \
            or [e["do"] for e in tail[0]] != ["exile_top", "choose_one_of", "grant_play"]:
        return None
    exile = {**head[0][2], "as": "e0"}
    deferred = [exile, *({**e, "do": "deferred:" + e["do"]} for e in tail[0][1:])]
    return [head[0][0], {**head[0][1], "n": len(deferred)}, *deferred], head[1], head[2]


def _ends(effects: list[Def]) -> list[Def] | None:
    """This Is How It Ends: the creature's owner (as it last was, 608.2h) then faces the choice (701.55a, villainous.villain)."""
    if len(effects) != 1 or effects[0].get("do") != "to_library":
        return None
    return [{**effects[0], "as": "e0"},
            {"do": "villain110k", "who": "ref:e0.owner", "a": [{"do": "lose_life", "who": "THAT110K", "n": 5}],
             "b": [{"do": "shuffle_other110k", "who": "THAT110K"}],
             "labels": ["They lose 5 life", "They shuffle another creature they own into their library"]}]


def _snow_or_colorless() -> str:
    """"Land that is snow or could produce {C}": either property is enough (a union, not the two together)."""
    from app.rules import selectors

    return selectors.Selector(types=("Land",), either=(selectors.Selector(types=("Land",), supertypes=("Snow",)).key(),
                                                       selectors.Selector(types=("Land",), extras=("could_produce_c",)).key())).key()


_BODIES: dict[str, tuple[str, Any]] = {
    _ENDS: ("Shuffle target creature into its owner's library.", _ends),
    _ENDS.replace("Target creature's owner", "The owner of target creature"): ("Shuffle target creature into its owner's library.", _ends),  # (as define reads it)
    _SHIP: ("Untap all creatures that attacked this turn.", _ship),
    _TEFERI: ("Each creature target opponent controls phases out.", _teferi),
    _ICE_EACH: ("Destroy each land.", lambda effects: [{**effects[0], "who": _snow_or_colorless()}] if len(effects) == 1 else None),
    _ICE: ("Destroy target land.", lambda effects: effects),
    _FLOURISH: ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller gains 2 life.", _flourish),
}


def parse(body: str) -> Any:
    from app.rules import scripts

    body = body.strip()
    if body.strip() == _OVERBLAZE:
        from app.rules import scripts

        native = scripts.parse_effects("Destroy target permanent.")
        return None if native is None else ([{"do": "double_damage_turn110k", "who": "target"}], native[1], False)
    if body.replace("End-Blaze Epiphany", "~") in (_EPIPHANY, _EPIPHANY.replace("a number of cards from the top of your library equal to its power",
                                                                              "the top X cards of your library, where X is its power")):  # (as define reads it)
        return _epiphany()
    if body.replace("Backdraft", "~") == _BACKDRAFT:
        return [{"do": "backdraft110k"}], None, False
    if body[:1].upper() + body[1:] == _CRUEL:  # two different target players (115.3: "another target player")
        return [{"do": "control_swap110k"}], [{"what": "player", "min": 1, "max": 1}, {"what": "player", "min": 1, "max": 1, "distinct_from": [0]}], False
    if (built := _BODIES.get(body[:1].upper() + body[1:])) is None:  # (a trigger's effect text starts in lower case)
        return None
    native = scripts.parse_effects(built[0])
    if native is None:
        return None
    effects = built[1](native[0])
    target = _snow_or_colorless() if body[:1].upper() + body[1:] == _ICE else native[1]
    return None if effects is None else (effects, target, native[2])


# -- one-ability wordings: the whole ability text -> (the wording the grammar reads, what to change in its definition) --
def _old_man(d: Def) -> Def:
    """Old Man of the Sea: control lasts while the source stays tapped AND the creature's power stays at most the source's (611.2b; delayed.expire)."""
    from app.rules import scripts

    held = scripts.parse_effects("Gain control of target creature for as long as ~ remains tapped.")
    if held is None or len(held[0]) != 2 or held[0][0].get("duration") != "source_tapped" or d.get("effects") != [{"do": "gain_control", "who": "target"}]:
        return d
    return {**d, "effects": [{**held[0][0], "duration": "source_tapped_power110k"}, held[0][1]]}


def _stickered_target(d: Def) -> Def:
    """Scampire: the target is a creature card "with a sticker on it" (123.4: a sticker put on a card in a graveyard stays on it, selectors "sticker101:any")."""
    from app.rules import selectors

    sel = selectors.from_key(d["target"]["what"]) if d.get("target") else None
    if sel is None or "graveyard" not in sel.zones:
        return d
    return {**d, "target": {**d["target"], "what": selectors.replace(sel, extras=(*sel.extras, "sticker101:any")).key()}}


def _deceiver(d: Def) -> Def:
    """Deceiver of Form: after the reveal and before the optional bottom, a creature card revealed may be what the other creatures become copies of."""
    eff = d["effects"]
    if len(eff) != 2 or eff[0].get("do") != "look_top" or eff[1].get("do") != "pick_looked":
        return d
    return {**d, "effects": [eff[0], {"do": "copies_of_revealed110k"}, eff[1]]}


def _flip_chandra(d: Def) -> Def:
    """Chandra, Fire of Kaladesh: after the exile, the returning instruction names the exiled card, not the old object (400.7)."""
    from app.rules import scripts

    back = scripts.parse_effects("Exile ~, then return her to the battlefield transformed under her owner's control.")
    eff = d["effects"]
    if back is None or len(eff) != 3 or eff[1].get("do") != "only_if" or eff[2].get("do") != "exile":
        return d
    return {**d, "effects": [eff[0], {**eff[1], "skip": len(back[0])}, *back[0]]}


def _chandra_emblems(d: Def) -> Def:
    """Chandra, Roaring Flame -7: only the players the damage was actually dealt to (after prevention, 120.3) get the emblem."""
    eff = d["effects"]
    if len(eff) != 1 or eff[0].get("do") != "damage":
        return d
    emblem = {"do": "emblem", "who": "ref:chandra110k", "text": "At the beginning of your upkeep, this emblem deals 3 damage to you."}
    return {**d, "effects": [{**eff[0], "bind_damage_players": "chandra110k"}, emblem]}


def _vermin(d: Def) -> Def:
    """Diseased Vermin: the target is an opponent this creature has dealt damage to before, on any turn (history.py records the players, by object)."""
    from app.rules import selectors

    target = d.get("target")
    if not target or target.get("what") != "opponent":
        return d
    return {**d, "target": {**target, "what": selectors.Selector(player="opponent", extras=("previously_damaged110k",)).key()}}


def _sidequest(d: Def) -> Def:
    """Sidequest: Play Blitzball: after it transforms (it is an Equipment on its back face), it is attached to a creature its controller chooses (701.3)."""
    eff = d["effects"]
    if len(eff) != 2 or eff[0].get("do") != "only_if" or eff[1].get("do") != "transform":
        return d
    return {**d, "effects": [{**eff[0], "skip": 2}, eff[1], {"do": "attach_self_choose110k"}]}


def _livestock(d: Def) -> Def:
    """Liberated Livestock: after the three tokens, for each of them its controller may put an Aura card from their hand and/or graveyard onto the battlefield
    attached to it (303.4i: one that can't enchant it stays where it is)."""
    eff = d["effects"]
    if len(eff) != 1 or eff[0].get("do") != "create_token" or len(eff[0].get("more") or []) != 2:
        return d
    return {**d, "effects": [{**eff[0], "as": "e0"}, {"do": "aura_for_each110k", "who": "ref:e0"}]}


def _lynde_return(d: Def) -> Def:
    """Lynde: the Curse comes back attached to its controller (303.4c: a Curse enchants a player; the card goes to its owner's graveyard, "you" is the owner)."""
    eff = d["effects"]
    if len(eff) != 2 or eff[1].get("do") != "deferred:return_card":
        return d
    return {**d, "effects": [eff[0], {**eff[1], "do": "deferred:return_attached_you110k"}]}


def _lynde_move(d: Def) -> Def:
    """Lynde: at the beginning of your upkeep, you may attach a Curse attached to you to one of your opponents; if you do, draw two cards (701.3)."""
    return {**d, "effects": [{"do": "curse_to_opponent110k"}]} if d.get("trigger") == "upkeep_you" else d


def _runesword(d: Def) -> Def:
    """Runesword: after the pump and the delayed sacrifice, this turn's two rules about what the targeted creature damages (a creature it deals damage to can't be
    regenerated; one that would die is exiled instead), both tied to that object (400.7)."""
    eff = d["effects"]
    if [e.get("do") for e in eff] != ["pump", "delayed", "deferred:sacrifice"]:
        return d
    return {**d, "effects": [*eff, {"do": "runesword_rules110k", "who": "target"}]}


def _rat_roles(d: Def) -> Def:
    """Twisted Sewer-Witch: a Wicked Role token for each Rat its controller has once the token exists, each attached to its own Rat (111.1, 303.7)."""
    from app.rules import selectors

    each = {"do": "each100c", "who": selectors.Selector(subtypes=("Rat",), controller="you").key(), "then": {"do": "create_role", "role": "Wicked"}}
    return {**d, "effects": [*d["effects"], each]} if len(d["effects"]) == 1 and d["effects"][0].get("do") == "create_token" else d


_WIGHT = ("At end of combat, put a paralyzation counter on each creature blocking or blocked by this creature and tap those creatures. Each of those creatures "
          "doesn't untap during its controller's untap step for as long as it has a paralyzation counter on it. Each of those creatures gains \"{4}: Remove a "
          "paralyzation counter from this creature.\"")
_BUILD: dict[str, tuple[str, Any]] = {
    "{3}, {T}: Target attacking creature gets +2/+0 until end of turn. When that creature leaves the battlefield this turn, sacrifice this artifact. If the "
    "creature deals damage to a creature this turn, the creature dealt damage can't be regenerated this turn. If a creature dealt damage by the targeted "
    "creature would die this turn, exile that creature instead.":
        ("{3}, {T}: Target attacking creature gets +2/+0 until end of turn. When that creature leaves the battlefield this turn, sacrifice this artifact.",
         _runesword),
    "Whenever a Curse is put into your graveyard from the battlefield, return it to the battlefield attached to you at the beginning of the next end step.":
        ("Whenever a Curse is put into your graveyard from the battlefield, return it to the battlefield at the beginning of the next end step.", _lynde_return),
    "At the beginning of your upkeep, you may attach a Curse attached to you to one of your opponents. If you do, draw two cards.":
        ("At the beginning of your upkeep, draw a card.", _lynde_move),
    "When this creature dies, create a 1/1 white Cat creature token with lifelink, a 1/1 white Bird creature token with flying, and a 2/4 white Ox creature "
    "token. For each of those tokens, you may put an Aura card from your hand and/or graveyard onto the battlefield attached to it.":
        ("When this creature dies, create a 1/1 white Cat creature token with lifelink, a 1/1 white Bird creature token with flying, and a 2/4 white Ox "
         "creature token.", _livestock),
    "At the end of combat on your turn, if a player was dealt 6 or more combat damage this turn, transform this enchantment, then attach it to a creature "
    "you control.":
        ("At the end of combat on your turn, if a player was dealt 6 or more combat damage this turn, transform this enchantment.", _sidequest),
    "At the beginning of your upkeep, this creature deals X damage to target opponent previously dealt damage by it, where X is the number of infection "
    "counters on it.":
        ("At the beginning of your upkeep, this creature deals damage to target opponent equal to the number of infection counters on it.", _vermin),
    # Dread Wight: "doesn't untap during its controller's untap step for as long as it has a paralyzation counter on it" is the creatures' own granted
    # "This creature doesn't untap during your untap step if it has a paralyzation counter on it" (502.3, as Mindbender Spores: the counter is read when it untaps)
    _WIGHT: ("At end of combat, put a paralyzation counter on each creature blocking or blocked by this creature and tap those creatures. Those creatures gain "
             "\"This creature doesn't untap during your untap step if it has a paralyzation counter on it.\" Those creatures gain \"{4}: Remove a paralyzation "
             "counter from this creature.\"", lambda d: d),
    "\u22127: Chandra deals 6 damage to each opponent. Each player dealt damage this way gets an emblem with \"At the beginning of your upkeep, this emblem "
    "deals 3 damage to you.\"":
        ("\u22127: ~ deals 6 damage to each opponent.", _chandra_emblems),
    "{T}: Chandra deals 1 damage to target player or planeswalker. If Chandra has dealt 3 or more damage this turn, exile her, then return her to the "
    "battlefield transformed under her owner's control.":
        ("{T}: ~ deals 1 damage to target player or planeswalker. If ~ has dealt 3 or more damage this turn, exile ~.", _flip_chandra),
    "At the beginning of combat on your turn, reveal the top card of your library. If a creature card is revealed this way, you may have creatures you "
    "control other than this creature become copies of that card until end of turn. You may put that card on the bottom of your library.":
        ("At the beginning of combat on your turn, reveal the top card of your library. You may put that card on the bottom of your library.", _deceiver),
    "{3}{B}: Return target creature card with a sticker on it from your graveyard to the battlefield. That creature gains haste. Exile it at the beginning of "
    "the next end step. Activate only as a sorcery.":
        ("{3}{B}: Return target creature card from your graveyard to the battlefield. That creature gains haste. Exile it at the beginning of the next end "
         "step. Activate only as a sorcery.", _stickered_target),
    "{T}: Gain control of target creature with power less than or equal to this creature's power for as long as this creature remains tapped and that "
    "creature's power remains less than or equal to this creature's power.":
        ("{T}: Gain control of target creature with power less than or equal to ~'s power.", _old_man),
    'When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block." Then for each Rat you control, create a Wicked '
    'Role token attached to that Rat.':
        ('When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block."', _rat_roles),
}


_SADDLEBRUTE = "All creatures can attack your opponents and planeswalkers your opponents control as though those creatures had haste."
_NO_REGEN_DAMAGED = "Creatures dealt damage by this creature this turn can't be regenerated this turn."


def definition(ability: Any, ch: Any) -> Def | None:

    from app.rules import exact_ability

    if ability.text.strip() == _SADDLEBRUTE:  # read by combat.attack_problem / declare_attackers through sick_may_attack and sick_target_ok
        return {"kind": "static", "static": "saddlebrute110k", "effects": []}
    if ability.text.strip() == f"{{2}}{{W}}: Return {ch.name} to its owner's hand. Activate only if {ch.name} is on the battlefield or in your graveyard." \
            and ch.name == "Skyblade's Boon":
        # costs.battlefield_too110k (casting.ability_cost, ability_problem): either zone; the effect moves it from whichever it is in
        return {"kind": "activated", "cost": "{2}{W}", "effects": [{"do": "return_self_hand110k"}], "target": None, "text": ability.text}
    if ability.text.strip().replace("this permanent", "this creature") == _NO_REGEN_DAMAGED:  # Bone Shaman's granted ability: read by regeneration.shielded / regeneration_choices.options
        return {"kind": "static", "static": "no_regen_damaged110k", "effects": []}

    return exact_ability.build(ability, ch, _BUILD)


def damaged_unregenerable(plan: Any, card: Any) -> bool:
    """701.19c / 614.8: a creature dealt damage this turn by a permanent that has "Creatures dealt damage by this creature this turn can't be
    regenerated this turn" can't be regenerated (the damage as it was dealt: the facts of the turn, and the source still has the ability now)."""
    from app.rules import scripts
    from app.rules.history import log_for

    oid = plan.oid(card)
    sources = {f.source for f in log_for(plan).facts if f.kind == "damaged" and f.object_id == oid and f.amount > 0}
    if sources & set(plan.rules.no_regen_sources110k):  # Runesword: the targeted creature dealt it damage this turn (the rule isn't an ability of the source)
        return True
    return any(
        (src := plan.state.cards.get(s.rsplit(".", 1)[0])) is not None and src.zone.endswith(":battlefield") and plan.oid(src) == s
        and "no_regen_damaged110k" in {d.get("static") for d in scripts.definitions(plan.ch(src)).values()}
        for s in sources if s)


def old_man_kept(plan: Any, effect: Any) -> list[str]:
    """The objects Old Man of the Sea's control effect still holds: none once the source left or untapped (611.2b); else those whose power is still at
    most the source's (checked after every table change)."""
    from app.rules import sba

    src = plan.state.cards.get(effect.source_card or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != effect.source or not src.tapped or not plan.in_game(src):
        return []
    limit = sba.power(src, plan.ch(src))
    kept = []
    for oid in effect.affected:
        held = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
        if held is not None and (sba.power(held, plan.ch(held)) or 0) <= (limit or 0):
            kept.append(oid)
    return kept


def _saddlebrutes(state: Any, info: Any) -> list[str]:
    """The controllers of battlefield permanents with Frenzied Saddlebrute's static."""
    from app.rules import characteristics as chars
    from app.rules import scripts

    # (-- big boards -- read for every creature that could attack: only an ability with exactly the Saddlebrute's text gives the static,
    # ``definition`` above, so the cards without it are passed over before their definitions are read)
    def gives(ch: Any) -> bool:
        return any(a.text.strip() == _SADDLEBRUTE for a in ch.abilities) \
            and any(d.get("static") == "saddlebrute110k" for d in scripts.definitions(ch).values())

    return [c.controller for c in state.cards.values() if c.zone.endswith(":battlefield") and not c.phased_indirect and gives(chars.of(c, info))]


def sick_may_attack(state: Any, card: Any, info: Any) -> bool:
    """302.6, 508.1: a summoning-sick creature is still declared as an attacker when a Saddlebrute's controller has an opponent it could attack (the
    declared target is then checked by sick_target_ok)."""
    from app.rules.plan import live_players

    players = live_players(state)
    return any(p != card.controller and p != boss for boss in _saddlebrutes(state, info) for p in players)


def sick_target_ok(plan: Any, card: Any, ch: Any, target: str) -> bool:
    """A creature without haste (and not summoning-sick) attacks anything; a sick one only a player who is an opponent of a Saddlebrute's controller, or a
    planeswalker such an opponent controls."""
    from app.rules.casting import summoning_sick

    if "haste" in ch.keywords or not summoning_sick(plan.state, card):
        return True
    from app.rules import scripts

    if "attack_as_haste" in scripts.statics(ch):
        return True
    owner = target if target in plan.state.players else plan.state.cards[target].controller if target in plan.state.cards \
        and "Planeswalker" in plan.ch(plan.state.cards[target]).types else None
    return owner is not None and any(owner != boss for boss in _saddlebrutes(plan.state, plan.info))
