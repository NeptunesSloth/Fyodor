"""-- planechase walk (wave C) -- a plane's "When you planeswalk to ~" / "When you planeswalk away from ~" abilities, a phenomenon's
"When you encounter ~" (701.31d, 312.5) and a plane's step triggers, in exact Oracle wordings the ordinary grammar doesn't read
(the playbook's cheapest hook): each line is read as a native wording through ``planar.definition`` (so it is a ``planar_to`` /
``planar_from`` / ``planar_encounter`` trigger of the planar controller: 901.6, "you" is the planar controller) or ``scripts.define``,
then adjusted where the native wording differs.

* "Whenever you planeswalk here, at the beginning of your upkeep, or whenever chaos ensues, …" (Sky Deck), "Whenever you planeswalk
  here and whenever a creature enters under your control, …" (Asmoranomardicadaistinaculdacar's Kitchen), "When you planeswalk to ~
  and at the beginning of your first main phase, …" (Kilnspire District): one ability with each trigger event (603.2), read as the
  native ability of its last half with the planeswalk half added (``multi:planar_to+…``).
* Pompeii: "put an eruption counter on it" — "it" is the plane (the native "on Pompeii").
* The Maelstrom: "you may reveal …" (the native wording's optional reveal, 603.5) "If you revealed a card but didn't put it onto the
  battlefield, put it on the bottom" (the native "If you don't put it onto the battlefield, put it on the bottom").
* Time Distortion: Aeon Engine's reversal (wave110m_cards ``reverse_turn_order110m``).
* Reality Shaping: Show and Tell's "each player may put …" (put_from_hand ``each_put``: 101.4, each chooses knowing the earlier choices,
  then the cards enter at once), asked "starting with you" (the planar controller, then in turn order).
* "chaos ensues" as an instruction (311.7: a resolving ability that says chaos ensues triggers the face-up plane's chaos ability):
  ``chaos_ensues_pcw`` (``language.designation_instruction``; Oteclán, Norn's Seedcore).

* The Aether Flues: "If you do, reveal …, put …, then shuffle …" — one sentence: all of it waits on the sacrifice (608.2c).
* The Pit: each player's choice of two tokens (``token_choice_pcw``: chosen in turn order, 101.4, then made).
* Bowie Base One: "controlled by the player to your left" — the native "the opponent to your left controls" (``Plan.after``, as wave 110E).
* Prime Minister's Cabinet Room: "up to one target creature you control" (115.1: the first target group may be empty).
* City Hall: "you become the Monarch" (the monarch, 724).
* Unleash the Flux: "If you lose the flip, repeat this process." (``again_pcw``: the sacrifice and the flip run again).
* Chaotic Aether / Fixed Point in Time: ``RulesState.planar_walk_pcw`` records read by the table's die roll (a blank roll is a chaos
  roll) and by the planeswalking ability (``planar.planeswalk``: chaos ensues instead, 614.1a); they end as a player planeswalks away
  from a plane (``on_events``) / as the planar controller's next turn begins (``turn_began``, from ``delayed.turn_began``).

A phenomenon's encounter ability resolves in full, its choices included, before the planar controller planeswalks (704.6f is a
state-based action, checked only when a player would receive priority: ``planar.sba``).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules.characteristics import Characteristics
from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.rules.plan import Plan

Def = dict[str, Any]
Fix = Callable[[Def], "Def | None"]


def _effects(*effects: Def) -> Fix:
    def fix(d: Def) -> Def:
        return {**d, "effects": [dict(e) for e in effects]}
    return fix


def _trigger(name: str, *, first: str | None = None) -> Fix:
    """The native ability of the last trigger half, with the other halves added (603.2: one ability, each event triggers it)."""
    def fix(d: Def) -> Def | None:
        if first is not None and d.get("trigger") != first:
            return None
        return {**d, "trigger": name}
    return fix


def _each_put_you(d: Def) -> Def | None:
    (e,) = d["effects"]
    if e.get("do") != "each_put" or e.get("who") != "each_player":
        return None
    return {**d, "effects": [{**e, "do": "each_put_you_pcw"}]}


def _up_to_one_first(d: Def) -> Def | None:
    """"up to one target creature you control … target creature an opponent controls" (115.1, 601.2c: the first group may be empty)."""
    targets = d.get("targets") or []
    if len(targets) != 2:
        return None
    return {**d, "targets": [{**targets[0], "min": 0}, targets[1]]}


def _if_you_do_all(n: int) -> Fix:
    """"If you do, A, B, then C." (one sentence): the native wording read the condition over its first instruction only; here it covers
    all ``n`` instructions after it (608.2c)."""
    def fix(d: Def) -> Def | None:
        effects = d["effects"]
        i = next((k for k, e in enumerate(effects) if e.get("do") == "only_if"), None)
        if i is None or i == 0 or effects[i - 1].get("do") != "optional_payment" or len(effects) != i + 1 + n:
            return None
        return {**d, "effects": [*effects[:i], {**effects[i], "skip": n}, *effects[i + 1:]]}
    return fix


_ANGEL = "create a 3/3 white Angel creature token with flying."
_DEMON = ('create a 6/6 black Demon creature token with flying, trample, and "At the beginning of your upkeep, sacrifice another creature. '
          "If you can't, this token deals 6 damage to you.\"")


def _pit(d: Def) -> Def | None:
    """The Pit: each player creates their choice of the Angel or the Demon (101.4: chosen in turn order, then made) — ``token_choice_pcw``."""
    from app.rules import scripts

    tokens = []
    for text in (_ANGEL, _DEMON):
        parsed = scripts.parse_effects(text)
        if parsed is None or len(parsed[0]) != 1 or parsed[0][0].get("do") != "create_token":
            return None
        tokens.append(copy.deepcopy(parsed[0][0]["token"]))
    return {**d, "effects": [{"do": "token_choice_pcw", "tokens": tokens}]}


def _repeat_on_loss(d: Def) -> Def | None:
    """Unleash the Flux: "If you lose the flip, repeat this process." — the sacrifice and the flip again (``again_pcw``) after a lost flip."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["edict", "coin_flip", "only_if", "lose_life"] or effects[2].get("cond") != {"coin": "lose"}:
        return None
    return {**d, "effects": [*effects[:3], {"do": "again_pcw", "span": 3}]}


# exact Oracle line → (the native ability read in its place, whether planar.definition reads it (else scripts.define), the adjustment)
REWRITES: dict[str, tuple[str, bool, Fix | None]] = {
    # -- planeswalk to --
    "When you planeswalk to Pompeii and at the beginning of your upkeep, put an eruption counter on it.":
        ("When you planeswalk to Pompeii and at the beginning of your upkeep, put an eruption counter on Pompeii.", True, None),
    "When you planeswalk to The Maelstrom and at the beginning of your upkeep, you may reveal the top card of your library. If a permanent "
    "card is revealed this way, you may put it onto the battlefield. If you revealed a card but didn't put it onto the battlefield, put it "
    "on the bottom of your library.":
        ("When you planeswalk to The Maelstrom and at the beginning of your upkeep, you may reveal the top card of your library. If it's a "
         "permanent card, you may put it onto the battlefield. If you don't put it onto the battlefield, put it on the bottom of your "
         "library.", True, None),
    "When you planeswalk to Kilnspire District and at the beginning of your first main phase, put a charge counter on Kilnspire District, "
    "then add {R} for each charge counter on it.":
        ("At the beginning of your first main phase, put a charge counter on Kilnspire District, then add {R} for each charge counter on "
         "Kilnspire District.", False, _trigger("multi:planar_to+step:main1:you", first="step:main1:you")),
    "Whenever you planeswalk here, at the beginning of your upkeep, or whenever chaos ensues, put a glass counter on up to one target "
    "nonland permanent.":
        ("At the beginning of your upkeep, put a glass counter on up to one target nonland permanent.", False,
         _trigger("multi:planar_to+planar_chaos+upkeep_you", first="upkeep_you")),
    "Whenever you planeswalk here and whenever a creature enters under your control, create a Food token.":
        ("Whenever a creature enters under your control, create a Food token.", False, _trigger("multi:planar_to+event", first="event")),
    "When you planeswalk here, you become the Monarch.":  # (City Hall: the monarch, 724)
        ("When you planeswalk here, you become the monarch.", True, None),
    "When you planeswalk to The Aether Flues and at the beginning of your upkeep, you may sacrifice a creature. If you do, reveal cards "
    "from the top of your library until you reveal a creature card, put that card onto the battlefield, then shuffle all other cards "
    "revealed this way into your library.":
        ("When you planeswalk to The Aether Flues and at the beginning of your upkeep, you may sacrifice a creature. If you do, reveal cards "
         "from the top of your library until you reveal a creature card. Put that card onto the battlefield, then shuffle all other cards "
         "revealed this way into your library.", True, _if_you_do_all(3)),
    "When you planeswalk to The Pit, each player creates their choice of a 3/3 white Angel creature token with flying or a 6/6 black Demon "
    "creature token with flying, trample, and \"At the beginning of your upkeep, sacrifice another creature. If you can't, this token deals "
    "6 damage to you.\"":
        ("When you planeswalk to The Pit, each player creates a 3/3 white Angel creature token with flying.", True, _pit),
    # -- step triggers --
    "At the beginning of your end step, goad target creature controlled by the player to your left.":  # (Bowie Base One; "left": Plan.after)
        ("At the beginning of your end step, goad target creature the opponent to your left controls.", False, None),
    "At the beginning of combat on your turn, up to one target creature you control becomes a copy of target creature an opponent "
    "controls.":  # (Prime Minister's Cabinet Room)
        ("At the beginning of combat on your turn, target creature you control becomes a copy of target creature an opponent controls.",
         False, _up_to_one_first),
    # -- planeswalk away from --
    "When you planeswalk away from here, destroy all permanents with glass counters on them.":
        ("When you planeswalk away from Sky Deck, destroy all permanents with glass counters on them.", True, None),
    # -- encounter --
    "When you encounter Time Distortion, reverse the game's turn order.":
        ("When you encounter Time Distortion, you gain 1 life.", True, _effects({"do": "reverse_turn_order110m"})),
    "When you encounter Chaotic Aether, each blank roll of the planar die is a {CHAOS} roll until a player planeswalks away from a plane.":
        ("When you encounter Chaotic Aether, you gain 1 life.", True, _effects({"do": "blank_chaos_pcw"})),
    "When you encounter Fixed Point in Time, until your next turn, if a player would planeswalk as a result of rolling the planar die, "
    "chaos ensues instead.":
        ("When you encounter Fixed Point in Time, you gain 1 life.", True, _effects({"do": "fixed_point_pcw"})),
    "When you encounter Unleash the Flux, each player sacrifices a nonland permanent of their choice, then you flip a coin. If you lose "
    "the flip, repeat this process.":
        ("When you encounter Unleash the Flux, each player sacrifices a nonland permanent of their choice. Flip a coin. If you lose the "
         "flip, you lose 1 life.", True, _repeat_on_loss),
    "When you encounter Reality Shaping, starting with you, each player may put a permanent card from their hand onto the battlefield.":
        ("When you encounter Reality Shaping, each player may put a permanent card from their hand onto the battlefield.", True,
         _each_put_you),
}


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's or phenomenon's ability in one of the wordings above; else None."""
    from app.rules import planar, scripts

    if ability.kind != "triggered" or not planar.planar(ch):
        return None
    entry = REWRITES.get(ability.text.strip())
    if entry is None:
        return None
    native, planar_read, fix = entry
    new = replace(ability, text=native)
    d = planar.definition(new, ch) if planar_read else scripts.define(new, ch)
    if d is None or d.get("kind") != "triggered":
        return None
    return fix(copy.deepcopy(d)) if fix is not None else d


# -- primitives -------------------------------------------------------------------------------------------------------------------
def chaos_ensues(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """311.7: "chaos ensues": the face-up plane's chaos ability triggers (controlled by the planar controller: ``planar.on_events``).
    Outside a Planechase game there is no plane: nothing happens."""
    from app.game.handlers import planechase
    from app.game.rules_state import emit

    pc = plan.state.planechase
    if pc is None or not pc.deck or pc.face_id is None:
        plan.note("Not a Planechase game: chaos doesn't ensue (311.7)")
        return True
    plan.note("Chaos ensues (311.7)")
    emit(plan.state, "planar", counter="chaos", card=pc.face_id, player=planechase.planar_controller(plan.state) or ctx.get("controller"))
    return True


def each_put_you(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Reality Shaping: put_from_hand's ``each_put``, asked starting with "you" (the planar controller), then in turn order (101.4)."""
    from app.rules import effects, put_from_hand

    who = [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])]
    you = ctx.get("controller")
    if you in who:
        i = who.index(you)
        who = who[i:] + who[:i]
    ctx["_each_put_who"] = list(who)
    return put_from_hand._ask_each(plan, ctx, {**e, "do": "each_put"}, who, [])


def token_choice(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The Pit: each player, in turn order starting with the active player (101.4), chooses one of ``tokens``; then each creates the
    token they chose (inserted as the next instructions of this resolution)."""
    return _ask_token(plan, ctx, e, list(plan.apnap()), [])


def _ask_token(plan: Plan, ctx: dict[str, Any], e: Def, who: list[str], picks: list[list[Any]]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if not who:
        made = [{"do": "create_token", "who": f"player:{pid}", "n": 1, "token": copy.deepcopy(e["tokens"][i])} for pid, i in picks]
        i = ctx["next"]
        ctx["effects"] = [*ctx["effects"][:i], *made, *ctx["effects"][i:]]
        return True
    labels = [_label(t) for t in e["tokens"]]
    decide(plan, player=who[0], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: create your choice of token",
           options=[DecisionOption(id=str(i), label=label) for i, label in enumerate(labels)],
           resume={"step": "token_choice_pcw", "ctx": ctx, "e": e, "who": who[1:], "picks": picks})
    return False


def _label(token: Def) -> str:
    kw = ", ".join(line.lower() for line in str(token.get("text") or "").split("\n") if line and " " not in line)
    return f"{token.get('power')}/{token.get('toughness')} {token.get('name')}" + (f" with {kw}" if kw else "")


def _resume_token(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    picks = [*r["picks"], [d.player, int(chosen[0]) if chosen else 0]]
    if _ask_token(plan, r["ctx"], r["e"], r["who"], picks):
        effects.continue_effects(plan, r["ctx"])


# -- the planar die's encounter effects (Chaotic Aether, Fixed Point in Time): ``RulesState.planar_walk_pcw`` ---------------------
def blank_chaos(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Chaotic Aether: from now on each blank roll of the planar die is a chaos roll (901.9b: chaos ensues; the table's ``roll`` reads
    it), until a player planeswalks away from a plane (``on_events``; not the phenomenon's own planeswalk away, 704.6f)."""
    r = plan.rules
    if not any(x.get("kind") == "blank_chaos" for x in r.planar_walk_pcw):
        r.planar_walk_pcw = [*r.planar_walk_pcw, {"kind": "blank_chaos"}]
    plan.note("Each blank roll of the planar die is a chaos roll until a player planeswalks away from a plane")
    return True


def fixed_point(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Fixed Point in Time: until "your" (the planar controller's) next turn (500.4: ``turn_began``), a planeswalk that the planar die
    would cause (the planeswalking ability, 901.8) is replaced by chaos ensuing (614.1a: ``chaos_instead``)."""
    r = plan.rules
    r.planar_walk_pcw = [*r.planar_walk_pcw, {"kind": "fixed_point", "player": ctx["controller"], "turn": plan.state.turn.number}]
    plan.note("Until their next turn, a planeswalk caused by the planar die is chaos instead")
    return True


def chaos_instead(plan: Plan, ctx: dict[str, Any]) -> bool:
    """The planeswalking ability (rolled, 901.8) would planeswalk: under Fixed Point in Time chaos ensues instead (614.1a). True if so."""
    if not any(x.get("kind") == "fixed_point" for x in plan.rules.planar_walk_pcw):
        return False
    plan.note("Fixed Point in Time: chaos ensues instead of planeswalking (614.1a)")
    return chaos_ensues(plan, ctx, {})


def on_events(plan: Plan, events: list[Any]) -> None:
    """Chaotic Aether's effect ends as a player planeswalks away from a plane (a "from" event whose card is a plane, also one made by
    hand: the planeswalk happened all the same, 901.11); planeswalking away from a phenomenon doesn't end it."""
    r = plan.rules
    pc = plan.state.planechase
    if not r.planar_walk_pcw or pc is None:
        return
    for ev in events:
        if ev.kind == "planar" and ev.counter == "from":
            left = next((c for c in pc.deck if c.printing_id == ev.printing), None)
            if left is not None and not left.phenomenon:
                r.planar_walk_pcw = [x for x in r.planar_walk_pcw if x.get("kind") != "blank_chaos"]


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4: "until your next turn" ends as that player's next turn begins; 800.4m: for a player who left, as it would have."""
    r = plan.rules
    if not r.planar_walk_pcw:
        return
    turn, active = plan.state.turn.number, plan.active

    def ended(x: Def) -> bool:
        if x.get("kind") != "fixed_point":
            return False
        return (x["player"] == active and turn > x["turn"]) or any(x["player"] == p and n > x["turn"] for p, n in skipped or ())

    r.planar_walk_pcw = [x for x in r.planar_walk_pcw if not ended(x)]


def again(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"repeat this process": the ``span`` instructions before this one, and this one, run again next (Unleash the Flux: until a flip
    is won). A long run asks its controller to go on (as coin_flips' "flip until you lose" does) so one action's steps stay bounded."""
    i = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:i], *copy.deepcopy(ctx["effects"][i - 1 - e["span"]:i]), *ctx["effects"][i:]]
    if len(plan.steps) >= plan.max_steps - 80:
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=ctx["controller"], kind="confirm", prompt="Continue the mandatory repeated process.",
               options=[DecisionOption(id="continue", label="Continue resolving")], resume={"step": "again_pcw", "ctx": ctx})
        return False
    return True


def _resume_again(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES: dict[str, Any] = {"again_pcw": again, "chaos_ensues_pcw": chaos_ensues, "each_put_you_pcw": each_put_you, "token_choice_pcw": token_choice,
                              "blank_chaos_pcw": blank_chaos, "fixed_point_pcw": fixed_point}
RESUME: dict[str, Any] = {"token_choice_pcw": _resume_token, "again_pcw": _resume_again}
