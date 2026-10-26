"""-- lines (wave 110D) -- whole abilities read as an equivalent native wording (same meaning, citations at each entry; CR 2026-09-25)."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from app.rules import wave110d_chef, wave110d_fire, wave110d_mech, wave110d_meld

# the Oracle line (the card's name as ~) -> the wording the grammar already reads, with the same meaning
_AS: dict[str, str] = {
    # Liege of the Tangle: "Each of those lands" = each of them (the targets); 613.1d/613.1f, 205.1b the lands stay lands
    "Whenever ~ deals combat damage to a player, you may choose any number of target lands you control and put an awakening counter on each of them. Each of those lands is an 8/8 green Elemental creature for as long as it has an awakening counter on it. They're still lands.":  # noqa: E501
        "Whenever ~ deals combat damage to a player, you may choose any number of target lands you control and put an awakening counter on each of them. Each of them becomes an 8/8 green Elemental creature for as long as it has an awakening counter on it. They're still lands.",
    # Last Night Together: the restriction is the extra combat's own tag (combat_rules.extra_phases "only110d", combat.attack_problem)
    "Choose two target creatures. Untap them. Put two +1/+1 counters on each of them. They gain vigilance, indestructible, and haste until end of turn. After this main phase, there is an additional combat phase. Only the chosen creatures can attack during that combat phase.":  # noqa: E501
        "Choose two target creatures. Untap them. Put two +1/+1 counters on each of them. They gain vigilance, indestructible, and haste until end of turn. After this main phase, there is an additional combat phase.",
    # Call for Aid: 701.21 "you can't sacrifice those creatures" = they can't be sacrificed (only you control them this turn, 611.2c); the attack ban is appended
    "Gain control of all creatures target opponent controls until end of turn. Untap those creatures. They gain haste until end of turn. You can't attack that player this turn. You can't sacrifice those creatures this turn.":  # noqa: E501
        "Gain control of all creatures target opponent controls until end of turn. Untap those creatures. They gain haste and \"This creature can't be sacrificed\" until end of turn.",
    # Resplendent Marshal: 205.3m the creatures that share a creature type with the exiled card are picked by a primitive (patched in definition)
    "When ~ enters or dies, you may exile another creature card from your graveyard. When you do, put a +1/+1 counter on each creature you control other than ~ that shares a creature type with the exiled card.":
        "When ~ enters or dies, you may exile another creature card from your graveyard. When you do, put a +1/+1 counter on each creature you control other than ~.",
    # Growing Dread: 702.37e, 701.40b any permanent, turned up by you (the special action's player or the effect's controller; patched in definition)
    "Whenever you turn a permanent face up, put a +1/+1 counter on it.":
        "Whenever a permanent is turned face up, put a +1/+1 counter on it.",
    # Yes Man: 603.12 the reflexive trigger of the control change ("When they do" = when that happens, for the ability's controller); 111.2 the owner makes
    # the tokens, 608.2h from the quest counters it last had (the owner patched in definition)
    "{T}: Target opponent gains control of ~. When they do, you draw two cards and put a quest counter on ~. Activate only during your turn.":
        "{T}: Target opponent gains control of ~. When you do, draw two cards and put a quest counter on ~. Activate only during your turn.",
    "When ~ leaves the battlefield, its owner creates a tapped 1/1 white Soldier creature token for each quest counter on it.":
        "When ~ leaves the battlefield, create a tapped 1/1 white Soldier creature token for each quest counter on it.",
    # Frodo, Sauron's Bane (the quoted ability, 113.10): 701.54c the count of times the Ring tempted its controller decides which sentence is followed
    # (the conditional "loses the game if" / "Otherwise" is built in definition)
    "Whenever ~ deals combat damage to a player, that player loses the game if the Ring has tempted you four or more times this game. Otherwise, the Ring tempts you.":
        "Whenever ~ deals combat damage to a player, that player loses the game.",
    # Holy Frazzle-Cannon: 205.3m the attacker gets its counter first, then the other creatures sharing a creature type with it (share_counters110d)
    "Whenever equipped creature attacks, put a +1/+1 counter on that creature and each other creature you control that shares a creature type with it.":
        "Whenever equipped creature attacks, put a +1/+1 counter on that creature.",
    # Gutter Grime: the token's quoted CDA counts the counters on the enchantment that made it (the one named in the quote)
    "Whenever a nontoken creature you control dies, put a slime counter on ~, then create a green Ooze creature token with \"This token's power and toughness are each equal to the number of slime counters on ‹granter›.\"":
        "Whenever a nontoken creature you control dies, put a slime counter on this enchantment, then create a green Ooze creature token with \"This token's power and toughness are each equal to the number of slime counters on its creator.\"",
    # Shallow Grave: 404.1 the top card of a graveyard is the last one put there; it is not a target (patched in definition)
    "Return the top creature card of your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step.":
        "Return target creature card from your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step.",
    # Coveted Falcon: 608.2b only the legal targets are given away; the draw below counts the ones the opponent now controls (any number: a group of 0-N, patched in definition)
    "When ~ is turned face up, target opponent gains control of any number of target permanents you control. Draw a card for each one they gained control of this way.":
        "When ~ is turned face up, target opponent gains control of target permanent you control. Draw a card.",
    # Oft-Nabbed Goat: 611.2 the activator gains control (the same "you" as the draw); the dies trigger counts the -1/-1 counters it last had (608.2h)
    "{1}: Draw a card. Gain control of ~ and put a -1/-1 counter on it. Only your opponents may activate this ability and only as a sorcery.":
        "{1}: Draw a card. Put a -1/-1 counter on ~. Gain control of ~. Only your opponents may activate this ability and only as a sorcery.",
    "When ~ dies, if it had one or more -1/-1 counters on it, its owner draws that many cards and each other player loses that much life.":
        "When ~ dies, if it had one or more -1/-1 counters on it, its owner draws X cards and each opponent loses X life, where X is the number of -1/-1 counters on it.",
    '{2}: If ~ isn\'t a creature, it becomes a 0/0 Construct Hero artifact creature with flying and "~ gets +1/+1 for each artifact you control" until end of turn.':
        "{2}: If ~ isn't a creature, it becomes a 0/0 Construct Hero artifact creature with flying until end of turn.",
    # Sorin, Ravenous Neonate: "a white permanent other than that creature or Sorin" (here ~) = other than Sorin (the native "another") and not the stolen creature (patched below)
    "−6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control a white permanent other than that creature or ~.":
        "−6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control another white permanent.",
    # Sheltering Prayers: 613.7 each basic land is checked against its own controller's land count (a controller-relative selector extra)
    "Basic lands each player controls have shroud as long as that player controls three or fewer lands.":
        "Basic lands controlled by a player who controls three or fewer lands have shroud.",
    # One with the Kami: the enchanted creature is itself modified (700.9: this Aura, which its controller controls, is attached), so "enchanted creature or
    # another modified creature you control" is every modified creature you control
    "Whenever enchanted creature or another modified creature you control dies, create X 1/1 colorless Spirit creature tokens, where X is that creature's power.":
        "Whenever a modified creature you control dies, create X 1/1 colorless Spirit creature tokens, where X is that creature's power.",
    # Hand of Vecna: a single object named Vecna per player under the legend rule (704.5j), so "a creature named Vecna" = "each"; X is the same for both
    "At the beginning of combat on your turn, equipped creature or a creature you control named Vecna gets +X/+X until end of turn, where X is the number of cards in your hand.":
        "At the beginning of combat on your turn, equipped creature gets +X/+X until end of turn, where X is the number of cards in your hand. Each creature you control named Vecna gets +X/+X until end of turn, where X is the number of cards in your hand.",
    # Common Cause: "they" are the nonartifact creatures the line names (statics._condition "share_color110d", 105.4: one color all of them have)
    "Nonartifact creatures get +2/+2 as long as they all share a color.":
        "Nonartifact creatures get +2/+2 as long as all nonartifact creatures share a color.",
    # Summoner's Grimoire (granted trigger): 508.4, 614.12 only an enchantment card enters tapped and attacking (put_from_hand.resume, tap_atk110d)
    "Whenever ~ attacks, you may put a creature card from your hand onto the battlefield. If that card is an enchantment card, it enters tapped and attacking.":
        "Whenever ~ attacks, you may put a creature card from your hand onto the battlefield.",
    # Thelon of Havenwood: "each Fungus on the battlefield" is each permanent with the Fungus subtype (a selector reads permanents on the battlefield; 109.2)
    "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus on the battlefield.":
        "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus.",
    # Jeska, Thrice Reborn: a loyalty counter "for each time" = a number of counters equal to the number of times (122.6, 903.8)
    "~ enters with a loyalty counter on it for each time you've cast a commander from the command zone this game.":
        "~ enters with a number of loyalty counters on it equal to the number of times you've cast a commander from the command zone this game.",
    # Heliod's Punishment: "It" is the enchanted creature, so one sentence with the same three parts (613.1f, 508.1c, 509.1b)
    'Enchanted creature can\'t attack or block. It loses all abilities and has "{T}: Remove a task counter from ‹granter›. Then if it has no task counters on it, destroy ‹granter›."':
        'Enchanted creature can\'t attack or block, loses all abilities, and has "{T}: Remove a task counter from ‹granter›. Then if it has no task counters on it, destroy ‹granter›."',
    # Infantry Shield: the granted keyword is the triggered ability it stands for (702.181a, X read as it resolves, 107.3c)
    "Equipped creature has menace and mobilize X, where X is its power.":
        'Equipped creature has menace and "Whenever this creature attacks, create X tapped and attacking 1/1 red Warrior creature tokens, '
        'where X is its power. Sacrifice them at the beginning of the next end step."',
    # Unable to Scream: a creature that is not face down can't be turned face up anyway (708.2), so the condition changes nothing
    "As long as enchanted creature is face down, it can't be turned face up.": "Enchanted creature can't be turned face up.",
    # Mjölnir: doubling all of a source's damage is "it deals double that damage instead" to any recipient (120.1, 614.1)
    "Double all damage equipped creature would deal.":
        "If equipped creature would deal damage to a permanent or player, it deals double that damage instead.",
    # The Millennium Calendar: untapping in the untap step happens to every permanent at once (502.3), one batch (603.2c); the count is read below
    "Whenever you untap one or more permanents during your untap step, put that many time counters on ~.":
        "Whenever one or more permanents you control become untapped, put that many time counters on this artifact.",
    # "1,000" is the number 1000 (107.1)
    "When there are 1,000 or more time counters on ~, sacrifice it and each opponent loses 1,000 life.":
        "When there are 1000 or more time counters on this artifact, sacrifice it and each opponent loses 1000 life.",
    # Tourach's / Thelon's Chant: the player who puts a land onto the battlefield is the one it enters under (400.7, 110.2); an exact text only
    "Whenever a player puts a Forest onto the battlefield, ~ deals 3 damage to that player unless they put a -1/-1 counter on a creature they control.":
        "Whenever a Forest enters, ~ deals 3 damage to its controller unless they put a -1/-1 counter on a creature they control.",
    "Whenever a player puts a Swamp onto the battlefield, ~ deals 3 damage to that player unless the player puts a -1/-1 counter on a creature they control.":
        "Whenever a Swamp enters, ~ deals 3 damage to its controller unless they put a -1/-1 counter on a creature they control.",
    # Mind Whip: the same unless-payment (118.12); the tap is the second consequence of not paying (patched in below)
    "At the beginning of the upkeep of enchanted creature's controller, that player may pay {3}. If they don't, ~ deals 2 damage to that player and you tap that creature.":
        "At the beginning of the upkeep of enchanted creature's controller, ~ deals 2 damage to that player unless they pay {3}.",
    # Yarus: 708.9 a face-down creature that dies is revealed as its card; only a permanent card (110.4) can return (read as "if it's a permanent card")
    "Whenever a face-down creature you control dies, return it to the battlefield face down under its owner's control if it's a permanent card, then turn it face up.":  # noqa: E501
        "Whenever a face-down creature you control dies, return it to the battlefield face down under its owner's control, then turn it face up.",
    # Archnemesis: "that player" is the enchanted player; the second ability moves the Aura (303.4, 701.3) with an own primitive (patched in definition)
    "Whenever you attack enchanted player, that player loses 2 life. You draw a card and gain 2 life.":
        "Whenever you attack enchanted player, enchanted player loses 2 life. You draw a card and gain 2 life.",
    "Whenever a player attacks you, you may attach ~ to that player.":
        "Whenever a player attacks you, you may draw a card.",
}


_KALDRA = "{1}: If you control Equipment named Helm of Kaldra, Sword of Kaldra, and Shield of Kaldra, create Kaldra, a legendary 4/4 colorless Avatar creature token. Attach those Equipment to it."
_PYXIS = "{7}, {T}, Sacrifice ~: Each player turns face up all cards they own exiled with ~, then puts all permanent cards among them onto the battlefield."
_ETRATA = "{2}{U}{B}: Turn ~ face up. If you can't, exile it, then you may cast the exiled card without paying its mana cost."
_GIFT = "As ~ is turned face up, you may attach it to a creature."
_SAME_MV = "Whenever you cast a spell, your opponents can't cast spells with the same mana value as that spell until your next turn."


def same_mv_limit(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Living Breakthrough: 117.1, 202.3: opponents can't cast spells with the cast spell's mana value (as it is on the stack) until your next turn."""
    from app.rules import cast_limits, selectors, values

    key = selectors.Selector(compare=(("mv", "==", values.evaluate(plan, ctx, {"mana_value": "event"})),), zones=("stack",)).key()
    return cast_limits.cast_limit(plan, ctx, {"who": "each_opponent", "until": "next_turn", "filter": key})


_SURVEIL = "At the beginning of enchanted player's upkeep, any number of target players other than that player each draw cards equal to the number of Curses attached to that player."


def draw_per_curse(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Curse of Surveillance: each target player draws a card per Curse attached to the enchanted player (303.4, 702.5d), counted as it resolves (608.2h)."""
    from app.rules import effects

    host = effects._players(plan, ctx, "event_player")
    n = sum(c.zone.endswith(":battlefield") and c.attached_player in host and "Curse" in plan.ch(c).subtypes for c in plan.state.cards.values())
    return all(effects.draw(plan, ctx, {"do": "draw", "who": f"player:{p}", "n": n}) for p in effects._players(plan, ctx, "target:0")) if n else True


_ATTACKS_ME = "+2: Up to one target creature an opponent controls attacks ~ during its controller's next turn if able."


def attack_me_next_turn(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Gideon, Battle-Forged: 508.1d, 508.1c requirement on the target for its controller's next turn (like attack_destinations.attack_window)."""
    from app.rules import effects, layers

    for cid in effects._cards(plan, ctx, "target:0"):
        layers.add_effect(plan, affected=[plan.oid(cid)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="permanent",
                          imposes=(f"attack_object:{ctx.get('source_object')}",), declaration_window="next_turn", declaration_player=plan.state.cards[cid].controller)
    return True


_KYTHEON = "At end of combat, if ~ and at least two other creatures attacked this combat, exile ~, then return it to the battlefield transformed under its owner's control."
_CANT_DRAW = " If you can't, draw a card."
_NIKO = ("{2}, {T}: Exile target nonlegendary creature you control. Shards you control become copies of it until the next end step. "
         "Return it to the battlefield under its owner's control at the beginning of the next end step.")
_CAPRI = ("{2}: Put a +1/+1 counter on ~, then you may reselect which player ~ is attacking. "
          "Only the player ~ is attacking may activate this ability and only during the declare attackers step.")


def draw_if_none(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Draw a card when the earlier "return" moved nothing (the instruction could not be carried out)."""
    from app.rules import effects

    return bool(effects._cards(plan, ctx, "ref:" + e["ref"])) or effects.draw(plan, ctx, {"do": "draw", "who": "you", "n": 1})


_HORDE = "{3}{R/W}{R/W}: Creatures your opponents control block this turn if able, and you choose how those creatures block."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == wave110d_meld.LINE:
        return wave110d_meld.definition(ability, ch)
    if text == wave110d_mech.LINE:  # Mechtitan Core
        return wave110d_mech.definition(ability, ch)
    if text == wave110d_chef.LINE:
        return wave110d_chef.definition(ability, ch)
    if text == wave110d_fire.LINE:  # Firebender Ascension: read by wave110d_fire.triggers, not by an event pass
        return {"kind": "static", "static": "firebender110d", "effects": []}
    if text == _HORDE:  # Brutal Hordechief: "block if able" changes no characteristic, so it is not locked (611.2c): it binds every creature opponents control at blocks, so the whole declaration (509.1a) is yours
        d = scripts.define(replace(ability, text="{3}{R/W}{R/W}: Creatures your opponents control block this turn if able."), ch)
        if d is not None:
            d["effects"].append({"do": "declare_chooser110a", "kind": "block", "combat": False})
        return d
    if text == WARD_XP:
        return {"kind": "static", "static": "ward_xp110d", "effects": []}
    native = _AS.get(text)
    if text == _KYTHEON:  # the conditional parse loses the exile binding ("return him" would find nothing): define it plain, then add the intervening if (603.4)
        d = scripts.define(replace(ability, text="At end of combat, exile ~, then return it to the battlefield transformed under its owner's control."), ch)
        if d is not None:
            d["if"] = {"history": "self_attacked", "object": "self", "combat": True, "others": 2}  # (508.1, 500.8: conditions "and at least two other creatures")
        return d
    if text == _ATTACKS_ME:
        d = scripts.define(replace(ability, text="+2: Up to one target creature an opponent controls gains flying until end of turn."), ch)
        if d is not None:
            d["effects"] = [{"do": "attack_me110d"}]
        return d
    if text == _SURVEIL:
        d = scripts.define(replace(ability, text="At the beginning of enchanted player's upkeep, any number of target players each draw a card."), ch)
        if d is not None:
            from app.rules import selectors

            d["targets"][0]["what"] = selectors.Selector(player="any", player_exclude=selectors.THAT_PLAYER).key()
            d["effects"] = [{"do": "draw_per_curse110d"}]
        return d
    if text == _KALDRA:  # Helm of Kaldra: 701.3a attach each of the three named Equipment to the new token (a plain create parse, then the checks and attach by hand)
        d = scripts.define(replace(ability, text="{1}: Create Kaldra, a legendary 4/4 colorless Avatar creature token."), ch)
        if d is not None:
            from app.rules import selectors

            names = ("Helm of Kaldra", "Sword of Kaldra", "Shield of Kaldra")
            one = [selectors.Selector(controller="you", subtypes=("Equipment",), extras=("name:" + n,)).key() for n in names]
            allk = selectors.Selector(either=tuple(one)).key()
            conds = [{"value": {"count": k}, "op": ">=", "n": 1} for k in one]
            d["effects"] = [{"do": "only_if", "cond": c, "skip": 4 - i} for i, c in enumerate(conds)] + [{**d["effects"][0], "as": "kaldra110d"}]
            d["effects"].append({"do": "attach_to", "src": allk, "who": "ref:kaldra110d"})
        return d
    if text == _NIKO:  # Niko, Light of Hope: 707.9 the Shards copy the exiled creature as it last existed (608.2h), until the end step begins (611.2a)
        d = scripts.define(replace(ability, text=text.replace(" Shards you control become copies of it until the next end step.", "")), ch)
        if d is not None and d["effects"][0].get("do") == "exile":
            from app.rules import selectors

            shards = selectors.Selector(subtypes=("Shard",), controller="you").key()
            d["effects"].insert(1, {"do": "become_copy", "who": shards, "with": "ref:" + d["effects"][0]["as"], "last_known": True, "duration": "next_end_step110d"})
            return d
        return None
    if text == _CAPRI:  # Capricopian: 602.2 the defending player activates it (so "you" is them), 508.7c they may reselect whom it attacks
        d = scripts.define(replace(ability, text=text.replace(", then you may reselect which player ~ is attacking", "")), ch)
        if d is not None:
            d["effects"].append({"do": "attacker_reselect73", "mode": "self_player110d"})
        return d
    if text == _PYXIS:  # Pyxis of Pandemonium: 406.3 the cards turn face up in exile (public), then each permanent card enters under its owner's control (400.3)
        d = scripts.define(replace(ability, text="{7}, {T}, Sacrifice ~: Each player returns to the battlefield all cards they own exiled with ~."), ch)
        if d is not None:
            from app.rules import selectors

            perm = selectors.parse("permanent card")
            assert perm is not None
            d["effects"] = [{"do": "turn_up_linked100g", "who": "exiled_with", "as": "pyxis110d"}, {**d["effects"][0], "who": "exiled_with:" + perm.key()}]
        return d
    if text == _ETRATA:  # the fallback runs only when the turn-up failed (608.2c); a chosen-form permanent (chosen_forms95) is not met here
        d = scripts.define(replace(ability, text="{2}{U}{B}: Exile this creature, then you may cast the exiled card without paying its mana cost."), ch)
        if d is not None:
            d["effects"] = [{"do": "turn_up_or_not110d", "bind": "up110d"}, {"do": "only_if", "cond": {"not": {"succeeded": "up110d"}}, "skip": len(d["effects"])}, *d["effects"]]
        return d
    if text == _GIFT:
        return {"kind": "replacement", "replacement": "turned_up_attach110d", "effects": []}
    if text == _SAME_MV:
        d = scripts.define(replace(ability, text="Whenever you cast a spell, you gain life equal to that spell's mana value."), ch)
        if d is not None:
            d["effects"] = [{"do": "same_mv_limit110d"}]
        return d
    if text.endswith(_CANT_DRAW):  # Inventive Iteration: the graveyard pick is not a target, so "can't" = no artifact card to return (701.21, 608.2c)
        d = scripts.define(replace(ability, text=text[: -len(_CANT_DRAW)]), ch)
        if d is not None:
            d["effects"][0]["as"] = "back110d"
            d["effects"].append({"do": "draw_if_none110d", "ref": "back110d"})
        return d
    d = None if native is None else scripts.define(replace(ability, text=native), ch)
    if d is not None and text.startswith("−6: Gain control of target creature. It becomes a Vampire"):
        # the stolen creature is now yours: it counts in "another white permanent" when white, so it needs one more
        old = d["effects"][-2]["cond"]  # (the "only_if" before the counter)
        d["effects"][-2]["cond"] = {"any": [{"all": [{"not": {"object": "target", "is": 'sel:{"colors":["W"]}'}}, old]}, {**old, "n": 2}]}
    if d is not None and text.startswith("Whenever you untap one or more"):  # (own_untap: only the untap step of its controller, triggers.py)
        d = json.loads(json.dumps(d, default=str).replace('{"event_amount": 1}', '{"event_count": 1}'))
        d["cond"]["own_untap"] = True
    if d is not None and text.endswith("and you tap that creature."):  # (Mind Whip: both consequences follow a failed payment)
        d["effects"][1]["skip"] = 2
        d["effects"].append({"do": "tap", "who": "host"})
    if d is not None and text.startswith("{2}: If ~ isn't a creature, it becomes a 0/0 Construct Hero"):  # (Iron Man Armor: quoted static, 613.1f)
        d["effects"][-1]["abilities"] = ["This creature gets +1/+1 for each artifact you control."]
    if d is not None and text.startswith("When ~ dies, if it had one or more -1/-1 counters on it, its owner draws"):  # (Oft-Nabbed Goat: other than the owner)
        d["effects"][-1]["who"] = "each_other_than_source_owner110d"
    if d is not None and text.startswith("When ~ is turned face up, target opponent gains control of any number"):
        d["targets"][1] = {**d["targets"][1], "min": 0, "max": 250}  # (language.MAX_TARGETS)
        d["effects"][-1] = {"do": "draw_gained110d"}
    if d is not None and text.startswith("When ~ enters or dies, you may exile another creature card"):
        d["effects"][1]["lki"] = "pay0"  # (the reflexive ability's event: the card the cost exiled)
        d["effects"][1]["ability"]["effects"][0] = {"do": "share_counters110d"}
    if d is not None and text.startswith("Return the top creature card of your graveyard"):
        d.pop("target")
        d["effects"][0]["who"] = "ref:top110d"
        d["effects"].insert(0, {"do": "top_creature110d", "bind": "top110d"})
    if d is not None and text.startswith("Whenever you turn a permanent face up"):
        d["cond"]["turner110d"] = "you"  # (triggers.py)
    if d is not None and text.startswith("When ~ leaves the battlefield, its owner creates a tapped"):
        d["effects"][0]["who"] = "ref:event.owner"  # (as the native "its owner creates")
    if d is not None and text.endswith("Otherwise, the Ring tempts you."):  # (Frodo: lose the game at the fourth temptation or after, else tempt)
        lose = d["effects"][0]
        d["effects"] = [{"do": "only_if", "cond": {"ring110d": 4}, "skip": 1}, lose,
                        {"do": "only_if", "cond": {"not": {"ring110d": 4}}, "skip": 1}, {"do": "ring_tempts", "who": "you"}]
    if d is not None and text.startswith("Whenever equipped creature attacks, put a +1/+1 counter on that creature and each other"):
        d["effects"].append({"do": "share_counters110d"})
    if d is not None and text.startswith("Gain control of all creatures target opponent controls until end of turn. Untap"):
        # 508.1c, 611.2c: every creature you control, also one that arrives later this turn, can't attack that player
        d["effects"].append({"do": "restrict", "who": 'controlled:you|sel:{"types":["Creature"]}', "rules": ["cant_attack_player:@that"], "player": "target"})
    if d is not None and text.startswith("Choose two target creatures. Untap them. Put two +1/+1"):
        d["effects"][-1]["only110d"] = "target:0"
    if d is not None and text.endswith("if it's a permanent card, then turn it face up."):  # (Yarus: the permanent-card test gates both steps)
        sel = 'sel:{"card":true,"types":["Artifact","Creature","Enchantment","Land","Planeswalker","Battle"],"zones":[]}'
        d["effects"].insert(0, {"do": "only_if", "cond": {"object": "event", "is": sel}, "skip": 2})
    if d is not None and text.startswith("Whenever a player attacks you, you may attach ~"):
        d["effects"] = [{"do": "attach_event_player110d"}]
    if d is not None and text.endswith("it enters tapped and attacking."):
        d["effects"][0]["tap_atk110d"] = "Enchantment"
    return d


# Minthara, Merciless Soul: ward {X} (702.21a) with X the experience counters its controller has as the ward ability triggers (122.1, 608.2h); read in
# triggers.targeted. Zero counters is ward {0}: nothing to pay, so no trigger.
WARD_XP = "~ has ward {X}, where X is the number of experience counters you have."


def ward_xp(plan: Any, card: Any) -> list[str]:
    from app.rules import permissions

    if not any(src.id == card.id for src, _, _ in permissions._table_statics(plan.state, plan.info, {"ward_xp110d"})):
        return []
    n = int(plan.state.players[card.controller].resources.get("experience", 0))
    return [f"{{{n}}}"] if n > 0 else []


def draw_gained(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Coveted Falcon: draw a card for each permanent of the second target group that the first target player now controls (608.2c)."""
    from app.rules import effects

    owners = effects._players(plan, ctx, "target:0")
    n = sum(1 for c in effects._cards(plan, ctx, "target:1") if plan.state.cards[c].controller in owners) if owners else 0
    return effects.draw(plan, ctx, {"do": "draw", "who": "you", "n": n}) if n else True


def top_creature(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Shallow Grave: bind the top creature card of its controller's graveyard (404.1; the last card put there), if any."""
    from app.rules import context

    pile = plan.state.zones[f"{ctx['controller']}:graveyard"]
    top = [c for c in pile if "Creature" in plan.ch(plan.state.cards[c]).types][-1:]
    context.bind_objects(plan, ctx, e["bind"], top)
    return True


def share_counters(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Resplendent Marshal: a +1/+1 counter on each other creature its controller controls that shares a creature type with the exiled card (205.3m,
    as the card last was: 608.2h)."""
    from app.rules import context, effects
    from app.rules.creature_types import CREATURE_TYPES

    found = context.info(plan, ctx, context.EVENT)
    if found is None:
        return True
    types = found[1].subtypes & CREATURE_TYPES
    ids = [c.id for c in plan.state.cards.values()
           if c.zone == f"{ctx['controller']}:battlefield" and c.id not in (ctx.get("source_card"), found[0].id) and "Creature" in plan.ch(c).types
           and plan.ch(c).subtypes & types]
    context.bind_objects(plan, ctx, "share110d", ids)
    return effects.add_counters(plan, ctx, {"do": "add_counters", "who": "ref:share110d", "kind": "+1/+1", "n": 1})


def attach_event_player(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Archnemesis: attach the Aura to the attacking player (701.3a, 303.4f; an illegal host leaves it where it is)."""
    from app.rules import attachments, effects

    src = plan.state.cards.get(ctx.get("source_card") or "")
    who = effects._players(plan, ctx, "event_player")
    if src is not None and who and plan.in_game(src) and attachments.host_problem(plan, src, who[0]) is None:
        attachments.attach(plan, src.id, who[0], ctx["controller"])
    return True


def turn_up_or_not(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Etrata: "Turn this creature face up. If you can't, ..." — 701.40g/701.58g a manifested or cloaked instant or sorcery card can't be (it is only
    revealed), nor can one an effect bars (static_perm100d.face_up_barred); the result is bound for the fallback."""
    from app.rules import chosen_forms95, context, effects, facedown

    cards = effects._cards(plan, ctx, "self")
    card = plan.state.cards.get(cards[0]) if cards else None
    if card is not None and card.face_down and any(
            chosen_forms95.form(a.text.replace("this creature", "~")) for a in plan.ch(card.model_copy(update={"face_down": False})).abilities):  # (its "as it is turned face up" choice: the ordinary effect asks it)
        context.bind_payment(ctx, e["bind"], True)
        return facedown.turn_face_up(plan, ctx, {"who": "self"})
    ok = bool(cards) and facedown._turn_up(plan, cards[0], ctx["controller"])
    context.bind_payment(ctx, e["bind"], ok)
    return True


PRIMITIVES = {"turn_up_or_not110d": turn_up_or_not, "attack_me110d": attack_me_next_turn, "draw_per_curse110d": draw_per_curse, "same_mv_limit110d": same_mv_limit, "draw_if_none110d": draw_if_none, "attach_event_player110d": attach_event_player, "share_counters110d": share_counters, "draw_gained110d": draw_gained, "top_creature110d": top_creature}


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """701.54c: the Ring has tempted the ability's controller N or more times."""
    from app.rules import designations

    return designations.ring_level(plan, ctx["controller"]) >= cond["ring110d"]
