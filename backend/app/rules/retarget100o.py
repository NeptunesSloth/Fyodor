"""-- retarget (wave 100O) -- exact Oracle wordings about changing or choosing new targets (115.7) and copies with new targets (707.10c),
read as an equivalent native wording (scripts.define). Researched against CR 2026-09-25 and the cards' rulings. The shared primitives are in
app/rules/stack_interaction.py (change_target, choose_new_targets) and app/rules/copying.py (copy_spell + copy_new_targets).

* Captured by the Consulate: "if it has a single target" counts the targets chosen as the spell was put on the stack (115.9a; the ruling: the
  same object chosen twice is two targets) — a number no later effect changes (115.7f), so it is read as the cast trigger's "spell with a single
  target"; the new target is the enchanted creature if it is a legal target for that spell (the ruling), else nothing changes (115.7a).
* "you may copy ~ and may choose a new target for the copy" (Malicious Affliction), "copy this spell" (Bygone Marvels: the spell the cast trigger is
  about, 601.2i): a copy whose controller may choose new targets (707.10c), as "copy it. You may choose new targets for the copy."
* "When you cast this spell while you control your commander" (Ancestral Communion) / "… from your hand" (Banish into Fable): part of the trigger
  event, judged as it triggers only (not an intervening "if", 603.4); Banish's two copies each on its own condition as the trigger resolves (its
  rulings). Storm of Forms: one copy for each kind of counter among your permanents as it resolves (122.1, 608.2h).
* "copy the next [instant or sorcery] spell [with mana value 2 or less] you cast this turn when you cast it" (Flamehold Grappler, Tzaangor Shaman,
  Sea Gate Stormcaller) is a delayed triggered ability (603.7; the rulings), "When you next cast … this turn, copy that spell"; Sea Gate's "If this
  creature was kicked, copy that spell twice instead" reads its cast record (702.33d, fixed once cast). "copy the next loyalty ability you activate
  this turn when you activate it" (Jaya's Phoenix) and Repeated Reverberation's "When you next cast an instant spell, cast a sorcery spell, or
  activate a loyalty ability this turn, copy that spell or ability twice": the same, on a loyalty activation (606.3) too; copying a loyalty ability
  doesn't change loyalty (the rulings: the copy has no cost).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_AS: dict[str, str] = {
    "Whenever an opponent casts a spell, if it has a single target, change the target to enchanted creature if able.":
        "Whenever an opponent casts a spell with a single target, change the target to enchanted creature if able.",
    "When you cast this spell, if a creature died this turn, you may copy ~ and may choose a new target for the copy.":
        "When you cast this spell, if a creature died this turn, you may copy it. You may choose new targets for the copy.",
    "When you cast this spell, if there are eight or more permanent cards in your graveyard, copy this spell twice. You may choose new targets for the copies.":
        "When you cast this spell, if there are eight or more permanent cards in your graveyard, copy it twice. You may choose new targets for the copies.",
}
_COMMUNION = "When you cast this spell while you control your commander, copy this spell. You may choose a new target for the copy."
_STORM = "When you cast this spell, copy it for each kind of counter among permanents you control. You may choose new targets for the copies."
_FABLE = ("When you cast this spell from your hand, copy it if you control an artifact, then copy it if you control an enchantment. You may choose new targets "
          "for the copies.")
_NEXT = re.compile(r"(?P<head>(?:When|Whenever) [^,]+, )copy the next (?P<what>(?:instant or sorcery )?spell(?: with mana value \w+ or less)?) you cast this turn "
                   r"when you cast it\. (?P<rest>You may choose new targets for the copy\.|If ~ was kicked, copy that spell twice instead\. You may choose new "
                   r"targets for the copies\.)")
_SPINEROCK = ("Whenever you cast an instant or sorcery spell with a single target, you may copy it. If you do, those spells gain wither. You may choose new "
              "targets for the copy.")
_CHARLATAN = "{2}{U}, {T}: The controller of target instant or sorcery spell copies it. That player may choose new targets for the copy."
_MAYHEM = ("Choose target instant or sorcery spell. Each opponent may copy that spell and may choose new targets for the copy they control. You copy that "
           "spell once plus an additional time for each opponent who copied the spell this way. You may choose new targets for the copies you control.")
_REBUTTAL = ("Counter target instant or sorcery spell that targets you.",
             "If there are two or more instant and/or sorcery cards in your graveyard, you may copy the spell countered this way. You may choose new targets "
             "for the copy.")
_LOYALTY = ("Whenever ~ deals combat damage to a player or planeswalker, copy the next loyalty ability you activate this turn when you activate it. You may "
            "choose new targets for the copy.")
_REVERB = ("When you next cast an instant spell, cast a sorcery spell, or activate a loyalty ability this turn, copy that spell or ability twice. You may "
           "choose new targets for the copies.")


def _next_copy(head: dict[str, Any], n: int) -> list[dict[str, Any]]:
    """A delayed "when you next …" this turn (603.7c: once) copying that spell or ability ``n`` times, new targets allowed (707.10c)."""
    from app.rules import delayed

    out = delayed.wrap_when([{"do": "copy_event_stack", **({"n": n} if n > 1 else {})}, {"do": "copy_new_targets", "optional": True}], head, this_turn=True)
    out[0]["once"] = True
    return out


def _loyalty() -> dict[str, Any]:
    from app.rules import activated_copy_effects

    return {**activated_copy_effects.activation_cond(), "loyalty": True}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import conditions, scripts, selectors, values

    text = scripts.self_text(ability.text, ch.name)
    if text == _COMMUNION:  # (Ancestral Communion: "while" is part of the trigger event, not rechecked as it resolves, unlike an "if": 603.4)
        native = scripts.define(replace(ability, text="When you cast this spell, copy it. You may choose new targets for the copy."), ch)
        return None if native is None else {**native, "while": conditions.parse("you control your commander")}
    if text == _FABLE:  # (Banish into Fable: each copy on its own condition, judged as the trigger resolves: the rulings)
        native = scripts.define(replace(ability, text="When you cast this spell, copy it. If you control an artifact, copy that spell. If you control an "
                                                      "enchantment, copy that spell. You may choose new targets for the copies."), ch)
        return None if native is None else {**native, "effects": native["effects"][1:], "while": conditions.parse("you cast this spell from your hand", objects=True)}
    if text == _STORM:  # (Storm of Forms: 122.1, the kinds counted as the trigger resolves, 608.2h)
        native = scripts.define(replace(ability, text="When you cast this spell, copy it. You may choose new targets for the copies."), ch)
        n = values.parse_count("different kinds of counters among permanents you control")
        return None if native is None or n is None else {**native, "effects": [{**native["effects"][0], "n": n}, *native["effects"][1:]]}
    if (m := _NEXT.fullmatch(text)) is not None:
        what = m["what"]
        when = f"{m['head']}when you next cast {'an' if what[0] in 'aeiou' else 'a'} {what} this turn, copy that spell"
        if not m["rest"].startswith("If"):
            return scripts.define(replace(ability, text=f"{when}. You may choose new targets for the copy."), ch)
        twice = scripts.define(replace(ability, text=f"{when} twice. You may choose new targets for the copies."), ch)
        once = scripts.define(replace(ability, text=f"{when}. You may choose new targets for the copy."), ch)
        kicked = conditions.parse("~ was kicked", objects=True)
        if twice is None or once is None or kicked is None or twice.get("if") or once.get("if") or twice.get("target") or once.get("target"):
            return None
        return {**once, "effects": [{"do": "only_if", "cond": kicked, "skip": len(twice["effects"])}, *twice["effects"],
                                    {"do": "only_if", "cond": {"not": kicked}, "skip": len(once["effects"])}, *once["effects"]]}
    if text == _LOYALTY:  # (Jaya's Phoenix)
        native = scripts.define(replace(ability, text="Whenever ~ deals combat damage to a player or planeswalker, draw a card."), ch)
        return None if native is None else {**native, "effects": _next_copy({"kind": "watch", "cond": _loyalty(), "text": "you next activate a loyalty ability"}, 1)}
    if text == _REVERB and ability.kind == "spell":  # (Repeated Reverberation)
        cast = {"event": "cast", "subject": "player", "player": "you", "spell": selectors.Selector(zones=("stack",), types=("Instant", "Sorcery")).key()}
        head = {"kind": "watch", "cond": {"event": "either", "subject": "player", "conds": [cast, _loyalty()]},
                "text": "you next cast an instant or sorcery spell or activate a loyalty ability"}
        return {"kind": "spell", "effects": _next_copy(head, 2), "target": None}
    if text == _SPINEROCK:  # (Spinerock Tyrant: "those spells" — the copy (copy_gain) and the spell it copied, while each is that object on the stack)
        native = scripts.define(replace(ability, text="Whenever you cast an instant or sorcery spell with a single target, you may copy it. You may choose new "
                                                      "targets for the copy. The copy gains wither."), ch)
        return None if native is None else {**native, "effects": [*native["effects"], {"do": "grant", "who": "event_spell", "keywords": ["wither"]}]}
    if text == _CHARLATAN and ability.kind == "activated":  # (Meletis Charlatan: the copy is the target spell's controller's, and so is the choice: the rulings)
        native = scripts.define(replace(ability, text="{2}{U}, {T}: Copy target instant or sorcery spell. You may choose new targets for the copy."), ch)
        return None if native is None or native["effects"][0].get("do") != "copy_spell" else \
            {**native, "effects": [{**native["effects"][0], "by": "target"}, *native["effects"][1:]]}
    if text == _MAYHEM and ability.kind == "spell":  # (Tempt with Mayhem: each opponent in turn order, then you, 1 + that many times: the ruling)
        native = scripts.define(replace(ability, text="Copy target instant or sorcery spell. You may choose new targets for the copies."), ch)
        if native is None or [x.get("do") for x in native["effects"]] != ["copy_spell", "copy_new_targets"] or native["effects"][0].get("who") != "target":
            return None
        return {**native, "effects": [{"do": "copy_players100o", "who": "target", "players": "opponents", "may": True, "bind_amount": "tempted100o"},
                                      {**native["effects"][0], "n": {"plus": [1, {"ref_amount": "tempted100o"}]}}, native["effects"][1]]}
    lines = [scripts.self_text(a.text, ch.name) for a in ch.abilities if a.kind == "spell"]
    if ability.kind == "spell" and lines == list(_REBUTTAL) and text in _REBUTTAL:  # (Psychic Rebuttal: one resolution, the second line merged into the first)
        if text == _REBUTTAL[1]:
            return {"kind": "spell", "effects": [], "target": None, "merged_into": next(a.index for a in ch.abilities if a.kind == "spell")}
        native = scripts.define(replace(ability, text=f"{_REBUTTAL[0]} If there are two or more instant and/or sorcery cards in your graveyard, you may draw a card."), ch)
        if native is None or [x.get("do") for x in native["effects"]] != ["counter", "only_if", "may_rest", "draw"]:
            return None
        counter, gate, may = native["effects"][:3]  # (the spell countered this way: only one that left the stack — its ruling: one that can't be countered gives no copy)
        return {**native, "effects": [{**counter, "as": "rebutted"}, {**gate, "skip": 3}, may, {"do": "copy_spell", "who": "ref:rebutted"},
                                      {"do": "copy_new_targets", "optional": True}]}
    if (players := _PLAYERS.get(text)) is not None:  # (Hive Mind, Curse of Echoes)
        native = scripts.define(replace(ability, text=players[0]), ch)
        return None if native is None else {**native, "effects": [{"do": "copy_players100o", **({"may": True} if players[1] else {})}]}
    same = _AS.get(text)
    return None if same is None else scripts.define(replace(ability, text=same), ch)


# -- each other player copies (Hive Mind, Curse of Echoes) --
_PLAYERS: dict[str, tuple[str, bool]] = {
    "Whenever a player casts an instant or sorcery spell, each other player copies that spell. Each of those players may choose new targets for their copy.":
        ("Whenever a player casts an instant or sorcery spell, you draw a card.", False),
    "Whenever enchanted player casts an instant or sorcery spell, each other player may copy that spell and may choose new targets for the copy they control.":
        ("Whenever enchanted player casts an instant or sorcery spell, you draw a card.", True),
}


def copy_players(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Each player other than the caster copies the spell (707.10: under their control), in turn order from the active player (101.4; the
    rulings), each choosing new targets for their own copy (707.10c); "may": each asked in turn. ``who`` "target" (Tempt with Mayhem: the target spell,
    each opponent; ``bind_amount``: how many copied, for "an additional time for each opponent who copied the spell this way")."""
    from app.rules import context, effects

    if e.get("bind_amount"):
        context.bind_amount(ctx, e["bind_amount"], 0)
    skip = ctx["controller"] if e.get("players") == "opponents" else next(iter(effects._players(plan, ctx, "event_player")), None)  # (each opponent / other player)
    return _players_next(plan, ctx, e, [p for p in plan.apnap() if p != skip and p in plan.live()])


def _players_next(plan: Any, ctx: dict[str, Any], e: dict[str, Any], order: list[str], agreed: bool = False) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import copying
    from app.rules.plan import decide

    while order:
        pid, rest = order[0], order[1:]
        who = e.get("who") or "event_spell"
        objects = [(sid, oid, 1) for sid, oid in copying._copy_sources(plan, ctx, who)]
        if not objects:  # (never silently no copy: a spell that left the stack with nothing kept is copied by hand)
            if who != "event_spell" or not copying._event_object_left(ctx, "event_spell"):
                return True
            copying._manual(plan, {**copying.new_job(None, controller=pid, objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                                   "after100o": {"ctx": ctx, "e": e, "order": rest}},
                            f"{ctx.get('name') or 'Copy'}: the spell to copy left the stack, so its copy isn't automated: make the copy by hand, then press Done")
            return False
        if e.get("may") and not agreed:
            name = plan.ch(plan.state.cards[objects[0][0]]).name or "that spell"
            decide(plan, player=pid, kind="confirm", prompt=f"{ctx.get('name') or 'Copy'}: copy {name}?",
                   options=[DecisionOption(id="yes", label="Copy it"), DecisionOption(id="no", label="Don't copy it")],
                   resume={"step": "copy_players100o", "ctx": ctx, "e": e, "order": order})
            return False
        agreed = False
        if e.get("bind_amount"):
            from app.rules import context

            context.bind_amount(ctx, e["bind_amount"], context.amount(ctx, e["bind_amount"]) + 1)
        job = copying.new_job(None, controller=pid, objects=objects, retarget=True, label=ctx.get("name") or "Copy")
        job["after100o"] = {"ctx": ctx, "e": e, "order": rest}
        if not copying.run(plan, job):
            return False
        order = rest
    return True


def after_copy(plan: Any, after: dict[str, Any]) -> None:
    """A copy is on the stack (copying.go_on): the next player, then the resolving ability goes on."""
    from app.rules.effects import continue_effects

    if _players_next(plan, after["ctx"], after["e"], list(after["order"])):
        continue_effects(plan, after["ctx"])


def resume_players(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    order = list(r["order"])
    if _players_next(plan, r["ctx"], r["e"], order if chosen == ["yes"] else order[1:], agreed=chosen == ["yes"]):
        continue_effects(plan, r["ctx"])


PRIMITIVES = {"copy_players100o": copy_players}
RESUME = {"copy_players100o": resume_players}
