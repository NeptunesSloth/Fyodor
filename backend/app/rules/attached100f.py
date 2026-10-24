"""Attached objects and control (wave 100F), researched against CR 2026-09-25.

**Losing control.** "When you lose control of the creature, tap it." (Ray of Command; "the artifact": Magus of the Unseen), "When you lose
control of that Equipment, unattach it." (Ogre Geargrabber): a delayed triggered ability (603.7) the resolving ability creates on the object it
just took (603.7c: that object, bound now). It triggers once (603.7b) when its controller loses control of that object: another player gains
control of it — the "until end of turn" effect ending in cleanup (514.2, 613.1b) or another control-changing effect — or it leaves the
battlefield (603.10d looks back in time; the official rulings of Ray of Command / Magus of the Unseen, and of Khârn the Betrayer and Gustha's
Scepter: "You lose control of [it] when it leaves the battlefield or another player gains control of it"). If its controller doesn't control
the object as the ability resolves, there is nothing to lose: no delayed trigger. A trigger in the cleanup step gives priority and another
cleanup step follows (514.3a, engine).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import DelayedTrigger, Event, ObjectRef, ObjectSnapshot
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Context = dict[str, Any]

LOSE_CONTROL = {"kind": "event", "event": "lose_control", "open": True}
_LOSE = re.compile(r"^when you lose control of (?:the creature|the artifact|that equipment), (?P<clause>tap it|unattach it)$", re.I)


def _lose(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed

    inner = [{"do": "tap", "who": "it"}] if m["clause"] == "tap it" else [{"do": "unattach_it100f", "who": "it"}]
    return delayed.wrap_when(inner, LOSE_CONTROL, who="it"), None


def watching(plan: Plan, ctx: Context, watched: list[str]) -> list[str]:
    """The watched objects the creating ability's controller controls now (one it doesn't control can't be lost)."""
    return [c for c in watched if plan.state.cards[c].controller == ctx["controller"]]


def lost(plan: Plan, t: DelayedTrigger, events: list[Event]) -> list[ObjectRef]:
    """The watched objects ``t``'s controller lost control of in ``events`` (as they were then)."""
    from app.game.rules_state import ObjectRef
    from app.rules.triggers import _zone

    oids = {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []}
    out: list[ObjectRef] = []
    for e in events:
        if e.manual or e.object_id is None or e.object_id not in oids or not e.card:
            continue
        if e.kind == "designation" and e.counter == "control" and e.from_zone == t.controller and e.player != t.controller:
            out.append(ObjectRef(card=e.card, object_id=e.object_id))
        elif e.kind == "zone_change" and _zone(e.from_zone) == "battlefield" and _zone(e.to_zone) != "battlefield":
            snap = plan.rules.lki.get(e.object_id or "")
            if snap is not None and snap.controller == t.controller:
                out.append(ObjectRef(card=e.card, object_id=e.object_id, snapshot=snap))
    return out


def unattach_it(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.3d: "unattach it": the Equipment stays on the battlefield attached to nothing (nothing if it isn't attached or is gone)."""
    from app.rules import effects

    loose = [c for c in effects._cards(plan, ctx, str(e.get("who") or "it"))
             if plan.state.cards[c].zone.endswith(":battlefield") and plan.state.cards[c].attached_to]
    if loose:
        plan.do({"type": "detach", "card_ids": loose}, actor=ctx["controller"])
    return True


def _clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import scripts

    return scripts._clause(text)


# -- one grant, two subjects -- "it and Zombies you control gain deathtouch until end of turn" (Wand of Orcus): the one object and the group, each
# granted the keywords until end of turn (611.2a; the group is read as the ability resolves, 611.2c); a creature that is both is simply granted them
_AND_GROUP = re.compile(r"^(?P<a>it|~|equipped creature|enchanted creature) and (?P<b>(?!target\b)[^,.\"]+? you control) gain (?P<kw>[a-z ,]+?) until end of turn$")


def _and_group(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    left, right = _clause(f"{m['a']} gains {m['kw']} until end of turn"), _clause(f"{m['b']} gain {m['kw']} until end of turn")
    if left is None or right is None or left[1] is not None or right[1] is not None or len(left[0]) != 1 or len(right[0]) != 1 \
            or {e["do"] for e in (*left[0], *right[0])} != {"grant"}:
        raise _NoMatch
    return left[0] + right[0], None


# "Each equipped creature and Equipment you control gains deathtouch until end of turn." (Hemlock Vial): one group, either kind (the ruling: the set is
# fixed as the ability resolves, 611.2c — a creature equipped later doesn't gain it)
_EQUIPPED_AND_EQUIPMENT = re.compile(r"^each equipped creature and equipment you control gains (?P<kw>[a-z ,]+?) until end of turn$", re.I)


def _equipped_and_equipment(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import selectors
    from app.rules.scripts import _NoMatch

    halves = [selectors.parse(p) for p in ("equipped creatures you control", "Equipment you control")]
    found = _clause(f"creatures you control gain {m['kw']} until end of turn")
    if any(h is None for h in halves) or found is None or found[1] is not None or [e["do"] for e in found[0]] != ["grant"]:
        raise _NoMatch
    return [{**found[0][0], "who": selectors.Selector(either=tuple(h.key() for h in halves if h is not None)).key()}], None


# -- the host deals damage -- "enchanted creature deals 1 damage to its owner" (Enslave), "Enchanted creature deals 1 damage to target creature with flying."
# (Dizzying Gaze): the creature the source is attached to is the source of the damage (120.3; its lifelink / deathtouch count, 702.15b, 702.2b). 608.2h: the
# creature is read as the effect happens — what the Aura enchants now, or what it enchanted as it last existed if the Aura has left — and if that creature has
# left the battlefield too, as it last existed (it still deals the damage). "Its owner" is that creature's owner (108.3).
HOST = "host100f"
_HOST_DAMAGE = re.compile(r"^(?:enchanted|equipped) creature deals (?P<n>\d+) damage to (?P<o>its owner|its controller|target [^,.\"]+|any target)$")


def _host_damage(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language
    from app.rules.scripts import _NoMatch

    n, o = int(m["n"]), m["o"]
    if o in ("its owner", "its controller"):
        who, group = f"ref:{HOST}.{o.split()[1]}", None
    else:
        try:
            group = language.target_group(o)
        except language._Fail:
            raise _NoMatch from None
        if group is None or group.get("min") != 1 or group.get("max") != 1 or "another" in group:
            raise _NoMatch
        who = "target"
    return [{"do": "bind_host100f", "as": HOST}, {"do": "damage", "who": who, "n": n, "src": f"ref:{HOST}"}], group


def bind_host(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """608.2h: bind (``as``) the object the source is attached to — now, or as the source last existed — as it is, or as it last existed."""
    from app.game.rules_state import ObjectRef
    from app.rules import context

    r = plan.rules
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        host_id = src.attached_to
        host_oid = plan.oid(host_id) if host_id in plan.state.cards else None
    else:
        snap = r.lki.get(ctx.get("source_object") or "")
        host_id, host_oid = (snap.attached_to, snap.attached_object) if snap is not None else (None, None)
    found: list[dict[str, Any]] = []
    card = plan.state.cards.get(host_id or "")
    if host_id and host_oid:
        if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == host_oid:
            found.append(ObjectRef(card=host_id, object_id=host_oid, zone=card.zone).model_dump(mode="json"))
        elif (was := r.lki.get(host_oid)) is not None:
            found.append(ObjectRef(card=host_id, object_id=host_oid, zone=was.zone, snapshot=was).model_dump(mode="json"))
    context.refs(ctx)[str(e["as"])] = {"kind": "objects", "objects": found}
    return True


# -- bounces -- "Return enchanted creature and this Aura to their owners' hands." (Disappear), "When enchanted creature attacks, return it and this Aura to their owners'
# hands at end of combat." (Contempt: a delayed trigger, 603.7, 511.2; "it" is the attacking creature the trigger is about, the Aura the source — each only while still
# that object, 400.7): both in one move (one event, 603.2c); "Return enchanted creature and all Auras attached to that creature to their owners' hands." (Mark of
# Eviction): the creature and every Aura on it as the ability resolves, at once
_BOUNCE_BOTH = re.compile(r"^return (?:(?P<host>enchanted creature) and ~ to their owners' hands|(?P<it>it) and ~ to their owners' hands at end of combat"
                          r"|(?P<all>enchanted creature and all auras attached to that creature) to their owners' hands)$", re.I)


def _bounce_both(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed

    if m["host"]:
        return [{"do": "bounce", "who": "union:host+self"}], None
    if m["all"]:
        return [{"do": "bounce_host_auras100f"}], None
    return delayed.wrap_when([{"do": "bounce", "who": "union:event+self"}], delayed.END_OF_COMBAT), None


def bounce_host_auras(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    hosts = effects._cards(plan, ctx, "host")
    auras = [c.id for c in plan.state.cards.values() if hosts and c.attached_to == hosts[0] and c.zone.endswith(":battlefield")
             and "Aura" in plan.ch(c).subtypes]
    if hosts:
        plan.do({"type": "move", "card_ids": [*hosts, *auras], "to": {"zone": "hand"}}, actor=ctx["controller"])
    return True


# "unattach it" (Tamiyo's Compleation: "If it's an Equipment, unattach it." — 701.3d)
_UNATTACH = re.compile(r"^unattach it$")


def _unattach(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "unattach_it100f", "who": "it"}], None


# "target player sacrifices a creature of their choice other than enchanted creature" (Sporogenic Infection): 701.21a, the player chooses among their own; the
# enchanted creature (as the ability resolves, or as the Aura last existed: 608.2h) isn't among the choices
_EDICT_NOT_HOST = re.compile(r"^(?P<who>target player|target opponent|each opponent|each player) sacrifices an? (?P<sel>[a-z ]+?) of their choice other than enchanted creature$")


def _edict_not_host(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    found = _clause(f"{m['who']} sacrifices a {m['sel']} of their choice")
    if found is None or len(found[0]) != 1 or found[0][0]["do"] != "edict":
        raise _NoMatch
    return [{"do": "bind_host100f", "as": HOST}, {**found[0][0], "except_ref": HOST}], found[1]


# "you may have enchanted creature fight target creature an opponent controls" (Cartouche of Strength): the optional instruction "enchanted creature fights …"
# (701.14; the rulings: with the target gone or the creature gone, no one fights; with the Aura gone, the creature it last enchanted still fights, 608.2h)
_HAVE_FIGHT = re.compile(r"^have (?P<s>enchanted creature|equipped creature) fight (?P<o>target [^,.\"]+)$")


def _have_fight(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    found = _clause(f"{m['s']} fights {m['o']}")
    if found is None or [e["do"] for e in found[0]] != ["fight"]:
        raise _NoMatch
    return found




# -- control (wave 100F, part 3) ----------------------------------------------------------------------------------------------------------------------------
# "Sacrifice it at the beginning of the next end step if it has mana value 3 or less." (Angrath, the Flame-Chained −3): a delayed trigger (603.7) on the creature
# taken (603.7c: that object, bound now); the ruling: its mana value is checked only as the delayed ability resolves (202.3) — then it is sacrificed (701.21a)
_SAC_IF_MV = re.compile(r"^sacrifice it at the beginning of the next end step if it has mana value (?P<n>\d+) or less$")


def _sac_if_mv(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed

    return delayed.wrap_when([{"do": "sacrifice_if_mv100f", "who": "it", "mv": int(m["n"])}], delayed.WHEN["the next end step"]), None


def sacrifice_if_mv(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    who = str(e["who"])
    found = effects._cards(plan, ctx, who)
    if not found or any(plan.ch(plan.state.cards[c]).mana_value > int(e["mv"]) for c in found):
        plan.note(f"{ctx.get('name') or 'It'}: nothing is sacrificed (gone, or mana value greater than {e['mv']})", actor=ctx["controller"])
        return True
    return bool(effects.PRIMITIVES["sacrifice"](plan, ctx, {"do": "sacrifice", "who": who}))


# "You and target opponent each gain control of all creatures the other controls until end of turn. Untap those creatures. Those creatures gain haste until end
# of turn." (Twist Allegiance), "Untap all creatures you control and all creatures target opponent controls. You and that opponent each gain control of …"
# (Reins of Power): both sets are fixed at once as the effect begins (611.2c) — the creatures each of the two players controls then — and each player's
# layer-2 effect takes the other's (613.1b), both ending in cleanup (514.2). "Those creatures" are all of them (bound as SWAPPED). A third player is untouched.
SWAPPED = "swap100f"
_TWIST = ("you and target opponent each gain control of all creatures the other controls until end of turn. untap those creatures. "
          "those creatures gain haste until end of turn.")
_REINS = ("untap all creatures you control and all creatures target opponent controls. you and that opponent each gain control of all creatures "
          "the other controls until end of turn. those creatures gain haste until end of turn.")


def swap_all(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects, keyword_actions, layers

    me = ctx["controller"]
    them = effects._players(plan, ctx, "target")
    if len(them) != 1 or them[0] == me:
        context.bind_objects(plan, ctx, str(e["as"]), [])
        return True
    opp = them[0]
    side = {p: [c.id for c in plan.state.cards.values() if c.zone == f"{p}:battlefield" and plan.in_game(c) and plan.ch(c).is_creature] for p in (me, opp)}
    every = [*side[me], *side[opp]]
    context.bind_objects(plan, ctx, str(e["as"]), every)

    def untap() -> None:
        tapped = keyword_actions.untap_stunned(plan, [c for c in every if plan.state.cards[c].tapped], me)
        if tapped:
            plan.do({"type": "tap", "card_ids": tapped, "tapped": False}, actor=me)
    if e.get("untap") == "before":
        untap()
    effects._control_effect(plan, ctx, side[opp], me, "end_of_turn")
    effects._control_effect(plan, ctx, side[me], opp, "end_of_turn")
    layers.control_sync(plan)
    if e.get("untap") == "after":
        untap()
    return True


def _swap_body(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    low = body.strip().lower()
    if low not in (_TWIST, _REINS):
        return None
    when = "after" if low == _TWIST else "before"
    return [{"do": "swap_all100f", "untap": when, "as": SWAPPED}, {"do": "grant", "who": f"ref:{SWAPPED}", "keywords": ["haste"]}], "opponent", False


# "Gain control of target Equipment, then create a 0/0 black Phyrexian Germ creature token and attach that Equipment to it." (Grip of Phyresis): 613.1b (no
# duration: for the game), 111.1, 701.3a — the Equipment moves onto the Germ if it could be attached there (701.3b); the rulings: the Germ is a 0/0 for a moment,
# and dies afterwards if the Equipment gives no toughness (704.5f), the Equipment staying yours
_GRIP = "gain control of target equipment, then create a 0/0 black phyrexian germ creature token and attach that equipment to it."


def _grip_body(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip().lower() != _GRIP:
        return None
    took, made = scripts._clause("gain control of target Equipment"), scripts._clause("create a 0/0 black Phyrexian Germ creature token")
    if took is None or made is None or len(made[0]) != 1 or made[0][0]["do"] != "create_token":
        return None
    return [*took[0], {**made[0][0], "as": "germ100f"}, {"do": "attach_to", "src": "target", "who": "ref:germ100f"}], took[1], False


# "Whenever equipped creature dies, you may put a creature card from your hand onto the battlefield and attach this Equipment to it." (Deathrender): the card
# enters (put_from_hand: a private choice, 400.2), then the Equipment moves onto it if it could be attached there (701.3b; the ruling: else the creature
# enters and the Equipment stays unattached). "Whenever equipped creature deals combat damage, you may put an Aura card from your hand onto the battlefield
# attached to it." (Holy Avenger): the effect names what the Aura enchants (303.4f); one that couldn't legally enchant it (the ruling), or with the creature
# gone, stays in the hand (303.4g)
_PUT_ATTACH = "you may put a creature card from your hand onto the battlefield and attach ~ to it."
_PUT_ATTACHED = "you may put an aura card from your hand onto the battlefield attached to it."


def _put_body(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    low = re.sub(r"\bthis equipment\b", "~", body.strip().lower())
    if low == _PUT_ATTACH:
        return scripts.parse_effects("You may put a creature card from your hand onto the battlefield. Attach ~ to it.")
    if low == _PUT_ATTACHED and (put := scripts.parse_effects("You may put an Aura card from your hand onto the battlefield.")) is not None:
        return [{**put[0][0], "host": "event"}], put[1], put[2]  # ("it": the trigger event's creature)
    return None


# "When this Aura enters, remove enchanted creature from combat. Then draw a card for each tapped creature its controller controls." (Observed Stasis): 506.4;
# "its controller" is the enchanted creature's, its tapped creatures counted as the draw happens (608.2h; the ruling: removing it from combat doesn't untap it)
_STASIS = "remove enchanted creature from combat. then draw a card for each tapped creature its controller controls."


def _stasis_body(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip().lower() != _STASIS or (got := scripts.parse_effects("Remove enchanted creature from combat. Then draw a card for each tapped creature "
                                                                         "that player controls.")) is None:
        return None
    effects = [dict(e) for e in got[0]]
    effects[-1]["n"] = {**effects[-1]["n"], "for_player": "host_controller"}
    return effects, got[1], got[2]


# Same meaning, wording the grammar reads: "choose up to one target creature. That creature …" (Atomic Microsizer) is the target of the ability (115.1, 601.2c);
# "Enchanted creature's owner shuffles it into their library." (Watery Grasp): into its owner's library, which that player shuffles (401.3, 701.24)
_SAME = {"choose up to one target creature. that creature can't be blocked this turn and has base power and toughness 1/1 until end of turn.":
         "Up to one target creature can't be blocked this turn. It has base power and toughness 1/1 until end of turn.",
         "enchanted creature's owner shuffles it into their library.": "Shuffle enchanted creature into its owner's library."}


# "At the beginning of each player's upkeep, that player may pay {R}{R} or 2 life. If the player does, they gain control of this creature." (Emberwilde
# Djinn): the upkeep's player chooses one cost or neither (118.3: only one payable in full), then takes it for the game (613.1b, no duration)
_DJINN = "that player may pay {r}{r} or 2 life. if the player does, they gain control of ~."


def _djinn_body(low: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if low != _DJINN or (got := scripts.parse_effects("That player may pay {R}{R}. If the player does, that player gains control of ~.", event_player=True)) is None:
        return None
    return [{**got[0][0], "alts": ["{R}{R}", "Pay 2 life"]}, *got[0][1:]], got[1], got[2]


# "For each Aura and Equipment you control, you may attach it to a creature you control." (Inventory Management): one at a time (608.2c), each to a creature
# its controller chooses among those it could be attached to (701.3a-b; 303.4: an Aura only where its enchant ability allows), or left where it is.
# "Gain control of target Aura that's attached to a permanent. Attach it to another permanent it can enchant." (Aura Graft; ``who``/``any``): any permanent
# but the one it's on, chosen as it resolves (not targeted); with none it stays, still yours (the ruling of 2004-10-04)
_EACH_ATTACH = "for each aura and equipment you control, you may attach it to a creature you control."
_GRAFT = "gain control of target aura that's attached to a permanent. attach it to another permanent it can enchant."
EACH_STEP = "attach_each100f"


def attach_each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects
    from app.rules.plan import decide

    me, anywhere = ctx["controller"], bool(e.get("who"))
    left = e.get("left")
    if left is None:
        left = effects._cards(plan, ctx, e["who"]) if anywhere else [c.id for c in plan.state.cards.values() if c.zone == f"{me}:battlefield" and plan.in_game(c)
                                                                     and {"Aura", "Equipment"} & plan.ch(c).subtypes]
    for i, cid in enumerate(left):
        card = plan.state.cards[cid]
        hosts = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c) and (anywhere or c.controller == me and plan.ch(c).is_creature)
                 and c.id != card.attached_to and attachments.host_problem(plan, card, c.id) is None] if card.zone.endswith(":battlefield") else []
        if hosts:
            decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: {'attach' if anywhere else 'you may attach'} {card.name} to "
                   + ("another permanent" if anywhere else "a creature you control"),
                   options=[*(DecisionOption(id=h, label=plan.state.cards[h].name or "Permanent", card_id=h) for h in hosts),
                            *([] if anywhere else [DecisionOption(id="none", label="Leave it")])],
                   resume={"step": EACH_STEP, "ctx": ctx, "e": {**e, "left": left[i + 1:]}, "card": cid})
            return False
    return True


def resume_attach_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments
    from app.rules.effects import continue_effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose a creature or leave it")
    if chosen[0] != "none":
        attachments.attach(plan, d.resume["card"], chosen[0], d.player)
    if attach_each(plan, d.resume["ctx"], d.resume["e"]):
        continue_effects(plan, d.resume["ctx"])


# "Whenever an enchantment you control enters, create a 2/2 white Cat creature token. If that enchantment is an Aura, you may attach it to the token." (Ajani's
# Chosen): checked as it resolves (608.2c); the Aura moves only if both are still there and it could enchant the token (701.3b; the rulings of 2013-07-01)
_CAT = "create a 2/2 white cat creature token. if that enchantment is an aura, you may attach it to the token."


def _cat_body(low: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    if low != _CAT or (made := scripts.parse_effects("Create a 2/2 white Cat creature token.")) is None:
        return None
    aura = selectors.Selector(subtypes=("Aura",)).key()
    return [{**made[0][0], "as": "cat100f"}, {"do": "only_if", "cond": {"object": "event", "is": aura}, "skip": 2}, {"do": "may_rest"},
            {"do": "attach_to", "src": "event", "who": "ref:cat100f"}], None, False


# "At the beginning of your end step, clash with an opponent. If you win, gain control of enchanted creature. Otherwise, that player gains control of enchanted
# creature." (Captivating Glance): "that player" is the opponent clashed with (701.30b), who takes it whenever you don't win (the rulings of 2007-10-01)
_GLANCE = "clash with an opponent. if you win, gain control of enchanted creature. otherwise, that player gains control of enchanted creature."


def _glance_body() -> tuple[list[dict[str, Any]], Any, bool]:
    from app.rules import clash

    return [{"do": "clash"}, {"do": "only_if", "cond": {"coin": "win", "of": "clash"}, "skip": 1, "bind": "cond0"}, {"do": "gain_control", "who": "host"},
            {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": 1}, {"do": "gain_control", "who": "host", "to": f"ref:{clash.CLASHED}"}], None, False


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The exact bodies this module reads whole (scripts.parse_effects)."""
    from app.rules import scripts

    low = re.sub(r"\bthis creature\b", "~", body.strip().lower())
    if (same := _SAME.get(low)) is not None:
        return scripts.parse_effects(same)
    if low == _EACH_ATTACH:
        return [{"do": EACH_STEP}], None, False
    if low == _GRAFT and (took := scripts.parse_effects("Gain control of target Aura that's attached to a permanent.")) is not None:
        return [*took[0], {"do": EACH_STEP, "who": "target"}], took[1], False
    return _swap_body(body) or _grip_body(body) or _put_body(body) or _stasis_body(body) or _djinn_body(low) or _cat_body(low) or (_glance_body() if low == _GLANCE else None)


# "At the beginning of the next end step, target land deals 3 damage to that creature." (Swooping Pteranodon): a delayed trigger (603.7) whose own target, the
# land, is chosen as it triggers (the ruling; 603.3d) and is the source of the damage (120.3); "that creature" is the creature taken, bound now (603.7c)
_LAND_DROP = re.compile(r"^at the beginning of the next end step, target land deals (?P<n>\d+) damage to that creature$")


def _land_drop(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed, selectors

    land = selectors.parse("land")
    if land is None:
        raise _no()
    effects = delayed.wrap_when([{"do": "damage", "who": "it", "n": int(m["n"]), "src": delayed.WATCH_TARGET}], delayed.WHEN["the next end step"])
    effects[0]["target"] = {"what": land.key()}
    return effects, None


# "this Aura deals 1 damage to that player or a planeswalker that player controls" (Curse of the Pierced Heart): not a target — as it resolves its controller
# chooses that player or one of that player's planeswalkers (the Vial Smasher ruling for the same wording), the damage then dealt to it (120.3)
_PLAYER_OR_PW = re.compile(r"^~ deals (?P<n>\d+) damage to that player or a planeswalker that player controls$")
PICKED = "pick100f"


def _player_or_pw(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "player_or_pw100f", "of": "event_player", "as": PICKED}, {"do": "damage", "who": f"ref:{PICKED}", "n": int(m["n"])}], None


def player_or_pw(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.plan import decide

    who = effects._players(plan, ctx, str(e["of"]))
    context.bind_players(ctx, str(e["as"]), who[:1])
    if len(who) != 1:
        return True
    walkers = _walkers(plan, who[0])
    if not walkers:
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: deal the damage to {plan.name(who[0])} or a planeswalker they control",
           options=[DecisionOption(id=who[0], label=plan.name(who[0])),
                    *(DecisionOption(id=c, label=plan.state.cards[c].name or "Planeswalker", card_id=c) for c in walkers)],
           resume={"step": "player_or_pw100f", "ctx": ctx, "e": e, "player": who[0]})
    return False


def _walkers(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]


def resume_player_or_pw(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context
    from app.rules.effects import continue_effects

    ctx, e, pid = d.resume["ctx"], d.resume["e"], d.resume["player"]
    if chosen[0] != pid:
        if chosen[0] not in _walkers(plan, pid):
            raise ValueError("not that player's planeswalker")
        context.refs(ctx)[str(e["as"])] = {"kind": "objects", "objects": []}
        context.bind_objects(plan, ctx, str(e["as"]), [chosen[0]])
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name if chosen[0] != pid else plan.name(pid)}")
    continue_effects(plan, ctx)


# "Whenever an enchanted creature dies, draw a card for each Aura you controlled that was attached to it." (Hateful Eidolon): the Auras attached to the creature
# as it last existed (603.10a; the rulings: one destroyed at the same time counts), each counted if you controlled it then (its own last information, 608.2h)
_EIDOLON = re.compile(r"^draw a card for each aura you controlled that was attached to it$", re.I)


def _eidolon(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "draw_per_aura100f"}], None


def was_attached(plan: Plan, snap: ObjectSnapshot | None) -> list[tuple[str, Characteristics]]:
    """(controller, characteristics) of what was attached to a departed permanent as it last existed (603.10a): each as it is now while still that
    object on the battlefield, else as it last existed (608.2h)."""
    from app.rules.triggers import _lki_characteristics

    out = []
    for cid, oid in (snap.attached_objects if snap is not None else {}).items():
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == oid:
            out.append((card.controller, plan.ch(card)))
        elif (was := plan.rules.lki.get(oid)) is not None:
            out.append((was.controller, _lki_characteristics(plan, was)))
    return out


def draw_per_aura(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    me = ctx["controller"]
    refs = context._object_refs(ctx, context.EVENT, was=True)[:1]
    n = sum(1 for ref in refs for who, ch in was_attached(plan, plan.rules.lki.get(ref.object_id)) if "Aura" in ch.subtypes and who == me)
    if n:
        return bool(effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": "you", "n": n}))
    return True


# 701.60: "If it's suspected, it's no longer suspected." (Airtight Alibi): the designation is removed (it may be suspected again later, unless something says
# it can't: "can't become suspected", keyword_actions.suspect); 722.3b: "It becomes unprepared." (Infinite Coursework): the prepared designation is removed (the
# copy in exile no longer remains: 722.3c, 704.5e)
_NO_LONGER = re.compile(r"^(?:if it's suspected, )?it's no longer suspected$")
_UNPREPARED = re.compile(r"^it becomes unprepared$")


def _no_longer(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "unsuspect100f", "who": "it"}], None


def _unprepared(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "unprepare100f", "who": "it"}], None


def unsuspect(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    for cid in effects._cards(plan, ctx, str(e["who"])):
        card = plan.state.cards[cid]
        if plan.oid(card) not in plan.rules.suspected:
            continue
        plan.rules.suspected[:] = [o for o in plan.rules.suspected if o != plan.oid(card)]
        for marker in [x for x in card.effects if x.name == "Suspected"]:
            plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=ctx["controller"])
        plan.note(f"{card.name} is no longer suspected", [card.id], actor=ctx["controller"])
    return True


def unprepare(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    for cid in effects._cards(plan, ctx, str(e["who"])):
        oid = plan.oid(cid)
        if oid in plan.rules.prepared:
            del plan.rules.prepared[oid]
            plan.note(f"{plan.state.cards[cid].name} becomes unprepared", [cid], actor=ctx["controller"])
    return True


def _no() -> Exception:
    from app.rules.scripts import _NoMatch

    return _NoMatch()


TEMPLATES = [(_LOSE, _lose), (_AND_GROUP, _and_group), (_EQUIPPED_AND_EQUIPMENT, _equipped_and_equipment), (_HOST_DAMAGE, _host_damage),
             (_BOUNCE_BOTH, _bounce_both), (_UNATTACH, _unattach), (_EDICT_NOT_HOST, _edict_not_host), (_HAVE_FIGHT, _have_fight),
             (_SAC_IF_MV, _sac_if_mv), (_LAND_DROP, _land_drop), (_PLAYER_OR_PW, _player_or_pw), (_EIDOLON, _eidolon), (_NO_LONGER, _no_longer),
             (_UNPREPARED, _unprepared)]
PRIMITIVES = {"unattach_it100f": unattach_it, "bind_host100f": bind_host, "bounce_host_auras100f": bounce_host_auras, "sacrifice_if_mv100f": sacrifice_if_mv,
              "swap_all100f": swap_all, "player_or_pw100f": player_or_pw, "draw_per_aura100f": draw_per_aura, "unsuspect100f": unsuspect,
              "unprepare100f": unprepare, EACH_STEP: attach_each}
RESUME: dict[str, Any] = {"player_or_pw100f": resume_player_or_pw, EACH_STEP: resume_attach_each}
