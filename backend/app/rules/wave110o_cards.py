"""-- wave 110O -- exact Oracle wordings of single cards, read as native instructions or built from parts of them.

Each entry matches one whole ability's (or spell body's) Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

# spell body (exact) -> the native wording
REWRITES: dict[str, str] = {}


_REMEMBRANCE = "Shuffle Serene Remembrance and up to three target cards from a single graveyard into their owners' libraries."


_THRALL = ("Gain control of target creature until end of turn. If you control a Villain with greater mana value than that creature, gain control of that "
           "creature until the end of your next turn instead. Untap that creature. It gains haste until end of turn.")


_PORTENT = ("Reveal the top X cards of your library. For each card type, you may exile a card of that type from among them. Put the rest into your graveyard. "
            "You may cast a spell from among the exiled cards without paying its mana cost if you exiled four or more cards this way. Then put the rest of "
            "the exiled cards into your hand.")
_SANDS = "Redistribute any number of players' life totals."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _PORTENT:
        # 701.20a (reveal), 608.2c: one card of each type at most (each exiled card stands for one type), the rest to the graveyard, then the free cast
        # gated on the number exiled (603.4-style count, judged as it is read), then what is still exiled goes to the hand
        look = scripts.parse_effects("Reveal the top X cards of your library. For each card type, you may put a card of that type from among them into your hand. "
                                     "Put the rest into your graveyard.")
        cast = scripts.parse_effects("Exile the top four cards of your library. You may cast a spell from among them without paying its mana cost.")
        assert look and cast and look[0][1]["do"] == "pick_looked" and cast[0][1]["do"] == "free_cast"
        looked, pick, rest = look[0]
        free = {**cast[0][1], "who": "ref:portent110o"}
        return [looked, {**pick, "to": "exile", "as": "portent110o"}, rest, {"do": "only_if", "cond": {"w110o": "portent_four"}, "skip": 1}, free,
                {"do": "portent_hand110o"}], None, False
    if body.strip() == _SANDS:
        return [{"do": "redistribute110o"}], None, False
    if body.strip() == _PURE:  # 603.7a, 701.9, 603.2c: a turn-long trigger on the opponents' discards, one trigger for the batch; the cards, as they now are in the graveyard
        from app.rules import delayed, events

        cond = events.parse_condition("a spell or ability an opponent controls causes you to discard cards")
        if cond is None or not cond.get("aggregate") or cond.get("cause") != "opponent":
            return None
        head = {"kind": "watch", "cond": cond, "text": "a spell or ability an opponent controls causes you to discard cards"}
        wrapped = delayed.wrap_when([{"do": "bounce", "who": "event.new"}], head, this_turn=True)
        wrapped[0]["once"] = False
        return wrapped, None, False
    if body.strip() == _NAHIRI.replace("Nahiri's Sacrifice", "~"):  # 115.6, 601.2d: "any number of" allows none (X may be 0, and nothing is divided then)
        found = scripts.parse_effects("~ deals X damage divided as you choose among one, two, or three target creatures.")
        assert found is not None and isinstance(found[1], list) and found[1][0]["divide"]["total"] == {"x": 1}
        groups = [{**found[1][0], "min": 0, "max": 250, "divide": {**found[1][0]["divide"], "allow_zero_targets": True}}]
        return found[0], groups, found[2]
    if body.strip() == _HEROIC:  # 614.9, 611.2a, 603.7a: the redirection record (target 0 is the chosen creature); the delayed trigger has a target of its own (603.7d)
        from app.rules import damage_redirection_effects, delayed

        mine = damage_redirection_effects.key("creature you control")
        watch_target = delayed.WATCH_TARGET + ":0"
        return ([{"do": "heroic110o"},
                 {"do": "delayed", "when": {"kind": "event", "event": "die"}, "n": 2, "who": "target", "this_turn": True,
                  "targets": [{"what": mine, "min": 0, "max": 1}]},
                 {"do": "deferred:lki_counters", "from": "event", "who": watch_target}, {"do": "deferred:draw", "who": "you", "n": 1}], mine, False)
    if body.strip() == _TIDAL:
        return [{"do": "tidal110o"}], None, False
    if body.strip() == _CLEANSING:
        return [{"do": "cleansing110o"}], None, False
    if body.strip() == _UNDER_COST:  # 601.2b: the optional additional cost is announced as the spell is cast (costs.kicker_cost reads it); this line does nothing itself
        return [], None, False
    if body.strip() == _UNDER_PREVENT:  # 615.1, 608.2c: the exception is read when the spell resolves; the red creatures are those of that moment
        from app.rules import selectors

        non_red = selectors.parse("nonred creature").key()  # type: ignore[union-attr]
        paid = {"object": "self", "cast": {"kicked": True}}
        return ([{"do": "only_if", "cond": {"not": paid}, "skip": 1, "bind": "under110o"},
                 {"do": "prevent_all", "scope": {"combat": True, "any_target": True}},
                 {"do": "only_if", "cond": {"flag": "under110o", "negate": True}, "skip": 1},
                 {"do": "prevent_all", "scope": {"combat": True, "any_target": True, "by_objects": non_red}}], None, False)

    if body.strip() == _THRALL:  # 608.2c: the "instead" duration replaces the first one, so exactly one control effect is made
        short = scripts.parse_effects("Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.")
        long = scripts.parse_effects("Gain control of target creature until the end of your next turn.")
        assert short and long
        (control, *others), (until, long_control) = short[0], long[0]
        bigger = {"w110o": "villain_bigger"}
        return [{"do": "only_if", "cond": bigger, "skip": 2}, until, long_control, {"do": "only_if", "cond": {"not": bigger}, "skip": 1}, control, *others], short[1], False

    if body.strip() == _REMEMBRANCE.replace("Serene Remembrance", "~"):  # 701.24a: the spell and the cards are shuffled in, each owner's library shuffled
        own = scripts.parse_effects("Shuffle ~ into its owner's library.")
        pile = scripts.parse_effects("Shuffle up to three target cards from a single graveyard into their owner's library.")
        assert own and pile
        return [*own[0], *pile[0]], pile[1], False
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


_PURE = ("Whenever a spell or ability an opponent controls causes you to discard cards this turn, return those cards from your graveyard to your hand.")
_NAHIRI = "Nahiri's Sacrifice deals X damage divided as you choose among any number of target creatures."
# (the parenthetical "(if it's still on the battlefield)" is reminder text, dropped before parsing; the redirection is anyway only to the chosen object, 614.9)
_HEROIC = ("Choose target creature you control. Until end of turn, all damage that would be dealt to you and creatures you control is dealt to the chosen "
           "creature instead. When that creature dies this turn, put its counters on up to one target creature you control and "
           "draw a card.")
_TIDAL = ("For each attacking creature without flying, its controller may pay {1}. If that player doesn't, creatures you control blocking that creature "
          "gain first strike until end of turn.")
_SOUL_ECHO = ("At the beginning of your upkeep, sacrifice ~ if there are no echo counters on it. Otherwise, target opponent may choose that for each 1 damage that would "
              "be dealt to you until your next upkeep, you remove an echo counter from ~ instead.")
_SECRET = ("When ~ enters, exile up to one target creature other than enchanted creature until ~ leaves the battlefield. Enchanted creature becomes "
           "a copy of that creature until ~ leaves the battlefield.")
_MILEVA = ("{2}{W}, Collect evidence 4: If ~ is a Detective, it becomes a legendary creature named Mileva, the Stalwart, it has base power and toughness 5/5, and it "
           "gains \"Other creatures you control have indestructible.\"")
# Names originally printed in the Arabian Nights expansion (their first printing, 1993-12-17; the card database's ARN names without Mountain, first printed in Alpha)
ARABIAN_NIGHTS = frozenset({
    "Abu Ja'far", 'Aladdin', "Aladdin's Lamp", "Aladdin's Ring", 'Ali Baba', 'Ali from Cairo', 'Army of Allah', 'Bazaar of Baghdad', 'Bird Maiden',
    'Bottle of Suleiman', 'Brass Man', 'Camel', 'City in a Bottle', 'City of Brass', 'Cuombajj Witches', 'Cyclone', 'Dancing Scimitar', 'Dandân',
    'Desert', 'Desert Nomads', 'Desert Twister', 'Diamond Valley', 'Drop of Honey', 'Ebony Horse', 'El-Hajjâj', 'Elephant Graveyard', 'Erg Raiders',
    'Erhnam Djinn', 'Eye for an Eye', 'Fishliver Oil', 'Flying Carpet', 'Flying Men', 'Ghazbán Ogre', 'Giant Tortoise', 'Guardian Beast',
    'Hasran Ogress', 'Hurr Jackal', 'Ifh-Bíff Efreet', 'Island Fish Jasconius', 'Island of Wak-Wak', "Jandor's Ring", "Jandor's Saddlebags",
    'Jeweled Bird', 'Jihad', 'Junún Efreet', 'Juzám Djinn', 'Khabál Ghoul', 'King Suleiman', 'Kird Ape', 'Library of Alexandria',
    'Magnetic Mountain', 'Merchant Ship', 'Metamorphosis', 'Mijae Djinn', 'Moorish Cavalry', 'Nafs Asp', 'Oasis', 'Old Man of the Sea', 'Oubliette',
    'Piety', 'Pyramids', 'Repentant Blacksmith', "Ring of Ma'rûf", 'Rukh Egg', 'Sandals of Abdallah', 'Sandstorm', 'Serendib Djinn',
    'Serendib Efreet', 'Shahrazad', 'Sindbad', 'Singing Tree', 'Sorceress Queen', 'Stone-Throwing Devils', 'Unstable Mutation', 'War Elephant',
    'Wyluli Wolf', 'Ydwen Efreet',
})

EXILE_WHAT = "exile110o"
_LORE_ENTER = "As ~ enters, exile an instant or sorcery card from your graveyard."
_LORE_CDA = "~'s power and toughness are each equal to the exiled card's mana value."
_LORE_TRIGGER = ("Whenever ~ deals combat damage, you may sacrifice it. If you do, you may cast the exiled card without paying its mana cost.")
_EVELYN_TRIGGER = "Whenever ~ or another Vampire you control enters, exile the top card of each player's library with a collection counter on it."
_EVELYN_PERMISSION = ("Once each turn, you may play a card from exile with a collection counter on it if it was exiled by an ability you controlled, and you may spend mana as "
                      "though it were mana of any color to cast it.")
_CITY_STATIC = "Players can't cast spells or play lands with a name originally printed in the Arabian Nights expansion."
_CITY_TRIGGER = ("Whenever one or more other nontoken permanents with a name originally printed in the Arabian Nights expansion are on the battlefield, their controllers "
                 "sacrifice them.")
_VOLO_NOTE = "Whenever you cast a creature spell, note one of its creature types that hasn't been noted for ~."
_VOLO_DRAW = "{2}, {T}: Draw a card for each creature type noted for target permanent you control named Volo's Journal."
_TOMB_ACTIVATED = ("{2}, {T}: Put a mire counter on target non-Swamp land. That land is a Swamp for as long as it has a mire counter on it. Activate only during your upkeep.")
_TOMB_TRIGGER = ("When ~ is put into a graveyard from the battlefield, at the beginning of each of your upkeeps for the rest of the game, remove all mire counters from a land "
                 "that a mire counter was put onto with ~ but that a mire counter has not been removed from with ~.")
_ALTERATION = "Attach target Aura attached to a creature or land to another permanent of that type."
_ARMOR_PREVENT = "Prevent all damage that would be dealt to enchanted creature by sources of the last chosen color."
_ARMOR_COUNTER = "{X}: Put a sleight counter on ~ and choose a color. X is the number of sleight counters on ~."
_PYRAMIDS_MODE = "• The next time target land would be destroyed this turn, remove all damage marked on it instead."
_CLEANSING = "For each land, destroy that land unless any player pays 1 life."
_UNDER_COST = "As an additional cost to cast this spell, you may pay {2}{R}."
_UNDER_PREVENT = ("Prevent all combat damage that would be dealt this turn. If this spell's additional cost was paid, this effect doesn't affect "
                  "combat damage that would be dealt by red creatures.")
_HELM = ("{X}, {T}: Target opponent mills a card, then repeats this process until a creature card or X cards have been put into their graveyard this way, "
         "whichever comes first. If one or more creature cards were put into that graveyard this way, sacrifice ~ and put one of them onto the "
         "battlefield under your control. X can't be 0.")
_WITCH = ("Whenever ~ deals combat damage to a player, look at the top two cards of your library, then exile them face down. Then you may cast a Hero or "
          "noncreature spell from among cards exiled with ~ without paying its mana cost.")
_RINOA = ("Whenever one or more attacking creatures you control die, you may return one of them to the battlefield tapped under its owner's control with a "
          "flying counter on it. Do this only once each turn.")
_SYRIX_END = ("At the beginning of each end step, if a creature card left your graveyard this turn, target Phoenix you control deals damage equal to its "
              "power to any target.")
_SYRIX_DIES = "Whenever another Phoenix you control dies, you may cast this card from your graveyard."
_LAZAV = ("Whenever you commit a crime, put a +1/+1 counter on ~. Then you may exile a card from a graveyard. If a creature card was exiled this way, you may have "
          "~ become a copy of that card until end of turn. This ability triggers only once each turn.")
_STRIP = ("{3}, {T}: Until end of turn, you may cast instant and sorcery spells from the top of your graveyard. If a spell cast this way would be put into a "
          "graveyard, exile it instead.")
_WITCHES = "{T}: ~ deals 1 damage to any target and 1 damage to any target of an opponent's choice."
_MAGUS = ("{3}, {T}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other.")
_MINOTAUR = "Whenever you lose a coin flip, ~ deals 1 damage to any target of an opponent's choice."
_WORM = ("Whenever you attack with creatures with total power 12 or greater for the first time each turn, untap all attacking creatures. After this phase, "
         "there is an additional combat phase.")
_PHANTASM = "When ~ enters, if you guessed correctly for a card named Spire Phantasm, draw a card."
_CODIE = "{W}{U}{B}{R}{G}, {T}: Each creature you control becomes prepared."
_LIEGE = ("As long as ~ isn't attacking, its power and toughness are each equal to the number of Forests you control. As long as ~ is attacking, its power and "
          "toughness are each equal to the number of Forests defending player controls.")
_LIEGE_LAND = "{T}: Target land becomes a Forest until ~ leaves the battlefield."
_PROFANER = ("When ~ exploits a creature, return to their owners' hands all creatures your opponents control with toughness less than the exploited creature's "
             "toughness.")
_VINDICATOR = ("When ~ is turned face up, exile up to X other target creatures from the battlefield and/or creature cards from graveyards.")
_HERALD = "When ~ leaves the battlefield, each player gains control of each land they own that you control."
_KALDRA = ("{1}: If you control Equipment named Helm of Kaldra, Sword of Kaldra, and Shield of Kaldra, create Kaldra, a legendary 4/4 colorless Avatar "
           "creature token. Attach those Equipment to it.")
_MYSTERIO = ("When ~ enters, create a 3/3 blue Illusion Villain creature token for each nontoken Villain you control. Exile those tokens when ~ leaves the "
             "battlefield.")
_OKO_TYPES = "+2: Up to one target creature gains all creature types."
_OKO_EMBLEM = ('−6: Choose a creature type. You get an emblem with "Creatures you control of the chosen type get +3/+3 and have vigilance and '
               'hexproof."')


def modal_swap(ab: Any, ch: Any) -> tuple[Any, int, list[dict[str, Any]]] | None:
    """Pyramids: the second mode is read as a stand-in sentence (a destroy of a land); its effect is this module's shield, 614.1a. (characteristics, the mode's index, its effects)"""
    import dataclasses

    if ab.kind != "activated" or ab.text != "{2}: Choose one —" or len(ch.abilities) <= ab.index + 2 or ch.abilities[ab.index + 2].text != _PYRAMIDS_MODE:
        return None
    swapped = tuple(replace(a, text="• Destroy target land.") if a.index == ab.index + 2 else a for a in ch.abilities)
    return dataclasses.replace(ch, abilities=swapped), 1, [{"do": "wipe_shield110o", "who": "target"}]


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "loyalty" and text == _OKO_TYPES:  # Oko: 613.1d layer 4, "(This effect doesn't end.)": a permanent effect on the object
        native = scripts.define(replace(ability, text="+2: Up to one target creature gets +0/+0 until end of turn."), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "become", "who": "target", "types": [], "all_creature_types": True, "duration": "permanent"}]}
    if ability.kind == "loyalty" and text == _OKO_EMBLEM:
        native = scripts.define(replace(ability, text="−6: You get an emblem with \"Elf creatures you control get +3/+3 and have vigilance and hexproof.\""), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "type_emblem110o"}]}
    if ability.kind == "triggered" and text == _MYSTERIO:  # 603.7a, 603.7c: the delayed trigger watches Mysterio (if it already left, nothing is made to leave later)
        native = scripts.define(replace(ability, text="When ~ enters, create a 3/3 blue Illusion Villain creature token for each nontoken Villain you control."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["create_token"]:
            return None
        return {**native, "effects": [{**native["effects"][0], "as": "mysterio110o"},
                                      {"do": "delayed", "when": {"kind": "event", "event": "leave", "open": True}, "n": 1, "who": "self"},
                                      {"do": "deferred:exile", "who": "ref:mysterio110o"}]}
    if ability.kind == "triggered" and text == _SOUL_ECHO:  # 614.1a: the opponent's choice is made as it resolves; the shield lasts until its controller's next turn begins
        native = scripts.define(replace(ability, text="At the beginning of your upkeep, sacrifice ~ if there are no echo counters on it."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["only_if", "sacrifice"]:
            return None
        has_counters = {"value": {"counters": "echo", "on": "self"}, "op": ">=", "n": 1}
        return {**native, "target": {"what": "opponent"},
                "effects": [*native["effects"], {"do": "only_if", "cond": has_counters, "skip": 1}, {"do": "echo_offer110o"}]}
    if ability.kind == "triggered" and text == _SECRET:  # 707.2, 611.2b: the creature enchanted becomes a copy of the exiled one for as long as this Aura stays
        native = scripts.define(replace(ability, text="When this Aura enters, exile up to one target creature other than enchanted creature until this Aura leaves the battlefield. "
                                                      "~ becomes a copy of that creature."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["exile_until", "become_copy"]:
            return None
        return {**native, "effects": [native["effects"][0], {**native["effects"][1], "do": "secret_copy110o", "who": "host"}]}
    if ability.kind == "static" and text == _ARMOR_PREVENT:  # 614.1a: each "choose a color" replaces the one before, so the last chosen color is the color the Aura holds
        return scripts.define(replace(ability, text=text.replace("the last chosen color", "the chosen color")), ch)
    if ability.kind == "activated" and text == _ARMOR_COUNTER:  # one sentence, two actions in order: the same as two sentences
        native = scripts.define(replace(ability, text=text.replace("on ~ and choose a color.", "on ~. Choose a color.")), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["add_counters", "choose_value"]:
            return None  # (the choice is written on the Aura like the one it entered with: "the last chosen color" is what it holds)
        return {**native, "effects": [native["effects"][0], {**native["effects"][1], "remember": True}]}
    if ability.kind == "activated" and text == _MILEVA:  # 613.1d, 613.1c, 613.4b, 613.1f: one effect with a part in each layer, for good ("legendary creature named …")
        native = scripts.define(replace(ability, text="{2}{W}, Collect evidence 4: If ~ is a Detective, it becomes a creature with base power and toughness 5/5 and gains vigilance."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["only_if", "become"]:
            return None
        become = {k: v for k, v in native["effects"][1].items() if k not in ("keywords", "types")}
        return {**native, "effects": [{**native["effects"][0], "skip": 3}, {**become, "types": [], "legendary": True},
                                      {"do": "named100g", "who": "self", "name": "Mileva, the Stalwart"},
                                      {"do": "grant", "who": "self", "abilities": ["Other creatures you control have indestructible."], "duration": "permanent"}]}
    if text == _LORE_ENTER:  # 614.12a: "as it enters" the controller picks the card (a replacement, made before it enters), after_entry exiles it linked to the new permanent
        from app.rules import selectors

        sel = selectors.parse("instant or sorcery card in your graveyard")
        assert sel is not None
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": EXILE_WHAT, "pick110a": sel.key()}]}
    if text == _LORE_CDA:  # 604.3, 613.4a: the exiled card's mana value, 0 while nothing is exiled with it
        return {"kind": "static", "static": "cda", "effects": [], "p": {"exiled_mv110o": 1}, "t": {"exiled_mv110o": 1}}
    if ability.kind == "triggered" and text == _LORE_TRIGGER:  # 603.7, 608.2d: sacrificed first (a payment), then the linked card, which stays exiled if it isn't cast
        native = scripts.define(replace(ability, text="Whenever ~ deals combat damage, you may sacrifice it. If you do, draw a card."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["optional_payment", "only_if", "draw"]:
            return None
        return {**native, "effects": [native["effects"][0], {**native["effects"][1], "skip": 2}, {"do": "lore_bind110o"},
                                      {"do": "free_cast", "zone": "ref:lore110o", "filter": None, "optional": True, "mv": None, "n": 1, "who": "ref:lore110o"}]}
    if ability.kind == "triggered" and text == _EVELYN_TRIGGER:  # 122.1, 406.3: each exiled card gets a collection counter (a counter on a card in exile), remembering whose ability exiled it
        native = scripts.define(replace(ability, text="Whenever ~ or another Vampire you control enters, exile the top card of each player's library."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["exile_top"]:
            return None
        return {**native, "effects": [{**native["effects"][0], "as": "evelyn110o"}, {"do": "collect110o"}]}
    if ability.kind == "static" and text == _EVELYN_PERMISSION:  # 601.3, 305.1: once each turn (any turn), one such card; mana of any color for the cast (609.4b)
        return {"kind": "static", "static": "permission", "zone": "exile", "filter": None, "self": False, "play": True, "cast": True, "once": True, "once_any": True,
                "flash": False, "spend": "color", "exile_counter": "collection", "exiled_by110o": True, "effects": []}
    if ability.kind == "static" and text == _CITY_STATIC:  # 101.2: a prohibition (spells and lands) by name, for names in the fixed set
        from app.rules import selectors

        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "from": None, "act": None, "max": None, "effects": [], "arn_lands110o": True,
                "filter": selectors.Selector(zones=("stack",), extras=("arn_name110o",)).key()}
    if ability.kind in ("triggered", "static") and text == _CITY_TRIGGER:  # 603.8: a state trigger; 701.21: their controllers sacrifice them
        return {"kind": "triggered", "trigger": "state", "optional": False, "target": None, "state": {"w110o": "arn_permanents"}, "effects": [{"do": "arn_sacrifice110o"}]}
    if ability.kind == "triggered" and text in (_VOLO_NOTE, _VOLO_NOTE.replace("noted for ~", "noted for Volo's Journal")):  # 700.? a note is a memory kept for the object (the token); the type is the controller's choice among the unnoted ones
        native = scripts.define(replace(ability, text="Whenever you cast a creature spell, copy that spell."), ch)  # (the event-type trigger: it keeps the cast spell, "event_spell")
        if native is None or [e["do"] for e in native["effects"]] != ["copy_spell"]:
            return None
        return {**native, "effects": [{"do": "note110o"}]}
    if ability.kind == "activated" and text == _VOLO_DRAW:
        from app.rules import selectors

        sel = selectors.parse("permanent you control named Volo's Journal")
        draw = scripts.define(replace(ability, text="{2}, {T}: Draw a card."), ch)
        if sel is None or draw is None or [e["do"] for e in draw["effects"]] != ["draw"]:
            return None
        return {**draw, "target": {"what": sel.key()}, "effects": [{"do": "draw", "who": "you", "n": {"noted110o": "target"}}]}
    if ability.kind == "activated" and text == _TOMB_ACTIVATED:  # 122.1, 611.2b: a counter, and the land is a Swamp for as long as it has one; the lands are remembered for the second ability (607.2a-like)
        native = scripts.define(replace(ability, text="{2}, {T}: Put a mire counter on target non-Swamp land. Activate only during your upkeep."), ch)
        swamp = scripts.define(replace(ability, text="{2}, {T}: Target land becomes a Swamp for as long as it has a mire counter on it."), ch)
        if native is None or swamp is None or [e["do"] for e in native["effects"]] != ["add_counters"] or [e["do"] for e in swamp["effects"]] != ["until", "become"]:
            return None
        return {**native, "effects": [*native["effects"], {"do": "tomb_put110o"}, *swamp["effects"]]}
    if ability.kind == "triggered" and text == _TOMB_TRIGGER:  # 603.7a: a delayed trigger for the rest of the game, made as this resolves
        native = scripts.define(replace(ability, text="When ~ is put into a graveyard from the battlefield, you gain 1 life."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["gain_life"]:
            return None
        return {**native, "effects": [{"do": "tomb_delay110o"}]}
    if ability.kind == "spell" and text == _ALTERATION:  # 701.3, 115.1: the Aura is the one target; the permanent it goes to is chosen as this resolves (not targeted)
        from app.rules import selectors

        mine = [selectors.Selector(subtypes=("Aura",), extras=(x,)).key() for x in ("attached_creature", "attached_land")]
        return {"kind": "spell", "effects": [{"do": "alter_aura110o", "who": "target"}], "target": {"what": selectors.Selector(zones=("battlefield",), either=tuple(mine)).key()}}
    if ability.kind == "activated" and text == _KALDRA:  # 603.4-style "if" judged as it resolves (608.2c); every Equipment so named is attached
        from app.rules import conditions, selectors

        native = scripts.define(replace(ability, text="{1}: Create Kaldra, a legendary 4/4 colorless Avatar creature token."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["create_token"]:
            return None
        names = ("Helm of Kaldra", "Sword of Kaldra", "Shield of Kaldra")
        keys = [selectors.parse(f"Equipment named {n} you control").key() for n in names]  # type: ignore[union-attr]
        conds = [conditions.parse(f"you control an Equipment named {n}") for n in names]
        if any(c is None for c in conds):
            return None
        make = {**native["effects"][0], "as": "kaldra110o"}
        return {**native, "effects": [{"do": "only_if", "cond": {"all": conds}, "skip": 4}, make,
                                      *({"do": "attach_to", "src": k, "who": "ref:kaldra110o"} for k in keys)]}
    if ability.kind == "triggered" and text == _HERALD:  # 108.3: each owner takes back their lands; the ones its controller owns stay (nothing to give back)
        from app.rules import selectors

        native = scripts.define(replace(ability, text="When ~ leaves the battlefield, draw a card."), ch)
        return None if native is None else {**native, "effects": [{"do": "gain_control", "to": "owner", "who": selectors.parse("land you control").key()}]}  # type: ignore[union-attr]
    if ability.kind == "triggered" and text == _VINDICATOR:  # 107.3a: X is the X paid to turn it face up; 607.2a: the exile is the link the leave trigger returns
        by_x = scripts.define(replace(ability, text=_VINDICATOR.split(" from the battlefield")[0] + "."), ch)
        by_two = scripts.define(replace(ability, text=_VINDICATOR.replace("up to X", "up to two")), ch)
        if by_x is None or by_two is None or len(by_x.get("targets") or []) != 1 or len(by_two.get("targets") or []) != 1 \
                or [e["do"] for e in by_x["effects"]] != ["exile"] or by_x["targets"][0].get("x_count") != "upto":
            return None
        return {**by_x, "targets": [{**by_x["targets"][0], "what": by_two["targets"][0]["what"]}], "effects": [{**by_x["effects"][0], "link": True}]}
    if ability.kind == "triggered" and text == _PROFANER:  # 702.110b, 608.2h: the exploited creature's toughness as it last existed
        native = scripts.define(replace(ability, text="When ~ exploits a creature, draw a card."), ch)
        return None if native is None else {**native, "effects": [{"do": "profaner110o"}]}
    if ability.kind == "static" and text == _LIEGE:
        # 604.3a(5): each sentence sets power and toughness only if its condition holds, so neither is a characteristic-defining ability: two ordinary statics
        # (611.3a, 613.4b layer 7b) that exclude each other; "defending player" is the player it attacks (506.2)
        first, second = _LIEGE.split(" As long as ")
        a = scripts.define(replace(ability, text=first.replace("its power and toughness are each equal to", "it has base power and toughness X/X, where X is")), ch)
        b = scripts.define(replace(ability, text="As long as " + second.replace("its power and toughness are each equal to", "it has base power and toughness X/X, where X is")), ch)
        return None if a is None or b is None or a.get("also") or b.get("also") else {**a, "also": [b]}
    if ability.kind == "activated" and text == _LIEGE_LAND:  # 611.2b: for as long as the creature remains on the battlefield
        return scripts.define(replace(ability, text=_LIEGE_LAND.replace("until ~ leaves the battlefield", "for as long as ~ remains on the battlefield")), ch)
    if ability.kind == "activated" and text == _CODIE:  # 722.3a: each creature that has a prepare spell gains the designation (the effect skips the others)
        from app.rules import selectors

        native = scripts.define(replace(ability, text="{W}{U}{B}{R}{G}, {T}: Target creature becomes prepared."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["prepare"]:
            return None
        return {**native, "target": None, "effects": [{**native["effects"][0], "who": selectors.parse("creature you control").key()}]}  # type: ignore[union-attr]
    if ability.kind == "triggered" and text == _PHANTASM:  # 905.2: a guess is made only during a draft, and a game here has none
        native = scripts.define(replace(ability, text="When ~ enters, draw a card."), ch)
        return None if native is None else {**native, "if": {"w110o": "guessed"}}
    if ability.kind == "triggered" and text == _WORM:  # "for the first time each turn": it triggers only the first time the attack is that strong, 603.2h
        return scripts.define(replace(ability, text=_WORM.replace(" for the first time each turn", "") + " This ability triggers only once each turn."), ch)
    if ability.kind == "triggered" and text == _MINOTAUR:  # "of an opponent's choice": the controller picks the opponent, who announces the target (115.1d-style)
        native = scripts.define(replace(ability, text="Whenever you lose a coin flip, ~ deals 1 damage to any target."), ch)
        return None if native is None else {**native, "target_choice": "opponent110o"}
    if ability.kind == "activated" and text == _WITCHES:  # 115.1d-style delegation: an opponent (the activator's choice) announces the second target
        native = scripts.define(replace(ability, text="{T}: ~ deals 1 damage to any target and 1 damage to any target."), ch)
        if native is None or len(native.get("targets") or []) != 2:
            return None
        return {**native, "delegated_target": "opponent_second"}
    if ability.kind == "activated" and text == _MAGUS:
        native = scripts.define(replace(ability, text="{3}, {T}: Tap target creature you control and target creature an opponent controls."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["tap", "tap"] or len(native.get("targets") or []) != 2:
            return None
        return {**native, "delegated_target": "opponent_second", "delegated_controls110d": True,
                "effects": [*native["effects"], {"do": "fight", "who": "target:0", "with": "target:1"}]}
    if ability.kind == "activated" and text == _STRIP:  # 404.1: only the top card (the last one put there) may be cast, judged as each cast is announced
        native = scripts.define(replace(ability, text=_STRIP.replace("from the top of your graveyard", "from your graveyard")), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["grant_play"]:
            return None
        from app.rules import selectors

        top = selectors.Selector(zones=("graveyard",), card=True, extras=("top_graveyard110o",)).key()
        return {**native, "effects": [{**native["effects"][0], "card_filter": top}]}
    if ability.kind == "triggered" and text == _LAZAV:
        native = scripts.define(replace(ability, text="Whenever you commit a crime, put a +1/+1 counter on ~. This ability triggers only once each turn."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["add_counters"]:
            return None
        return {**native, "effects": [*native["effects"], {"do": "lazav110o"}]}
    if ability.kind == "triggered" and text == _SYRIX_DIES:  # 113.6k: it triggers from the graveyard; 601.2: a normal (paid) cast
        native = scripts.define(replace(ability, text="Whenever another Phoenix you control dies, return this card from your graveyard to the battlefield."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["return_card"]:
            return None
        return {**native, "optional": False, "effects": [{"do": "free_cast", "zone": "that", "who": "self_gy", "filter": None, "optional": True, "mv": None,
                                                           "n": 1, "paid": True}]}
    if ability.kind == "triggered" and text == _SYRIX_END:
        native = scripts.define(replace(ability, text=_SYRIX_END.split(", if ")[0] + ", " + _SYRIX_END.split("this turn, ")[1]), ch)
        if native is None or native.get("if") is not None:
            return None
        return {**native, "if": conditions.parse("a creature card left your graveyard this turn")}
    if ability.kind == "triggered" and text == _RINOA:
        # 700.4: "dies" is the batch that went to the graveyard together; 603.10a looks back at which were attacking (the base trigger); 603.2h the "once"
        base = scripts.define(replace(ability, text=_RINOA.replace(" return one of them to the battlefield tapped under its owner's control with a flying "
                                                                   "counter on it.", " draw a card.")), ch)
        back = scripts.parse_effects("Return target creature card from a graveyard to the battlefield tapped under its owner's control with a flying counter on it.")
        if base is None or back is None or len(back[0]) != 1 or [e["do"] for e in base["effects"]] != ["draw"]:
            return None
        return {**base, "effects": [{"do": "rinoa_pick110o"}, {**back[0][0], "who": "ref:rinoa110o"}]}
    if ability.kind == "triggered" and text == _WITCH:
        # 607.2a: the cards exiled with it by every resolution so far (accumulating link), this resolution's two among them; 406.3b: a face-down card is
        # cast only by a player allowed to look at it (she looked at these two as she exiled them, 406.3)
        native = scripts.define(replace(ability, text=_WITCH.split(" Then")[0] + " Then you may cast a Hero or noncreature spell from among them without paying "
                                                      "its mana cost."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["look_top", "pick_looked", "free_cast"]:
            return None
        look, exile, cast = native["effects"]
        return {**native, "accumulating_link": True,
                "effects": [look, {**exile, "link": True}, {"do": "linked_cards", "as": "witch110o"}, {**cast, "who": "ref:witch110o"}]}
    if ability.kind == "activated" and text == _HELM:
        native = scripts.define(replace(ability, text="{X}, {T}: Target opponent mills a card. X can't be 0."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["mill"] or native.get("x_min") != 1:
            return None
        mill = {**native["effects"][0], "as": "helm110o"}
        # 701.17a, 608.2c: one card at a time, each its own mill (616.1 replacements ask as usual); the process stops with a creature card or X cards
        # in the graveyard (the total counts cards that really went there)
        return {**native, "effects": [mill, {"do": "helm_test110o"}, {"do": "helm_again110o", "rewind": 3},
                                      {"do": "only_if", "cond": {"w110o": "helm_creature"}, "skip": 2}, {"do": "sacrifice", "who": "self"},
                                      {"do": "helm_pick110o"}]}
    return None


def type_emblem(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Oko, Shadowmoor Scion: the creature type is chosen as the ability resolves (the loyalty ability's controller, 608.2d); the emblem (114.1) then
    names that type, since an emblem keeps no "chosen" value of its own (114.2: it has no source)."""
    from app.game.rules_state import DecisionOption
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature type",
           options=[DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)], resume={"step": "type_emblem110o", "ctx": ctx, "e": e})
    return False


def resume_type_emblem(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import designations, effects
    from app.rules.creature_types import CREATURE_TYPES

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in CREATURE_TYPES:
        raise ActionError("Choose one creature type")
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]}", actor=d.player)
    designations.emblem(plan, ctx, {"who": "you", "text": f"{chosen[0]} creatures you control get +3/+3 and have vigilance and hexproof."})
    effects.continue_effects(plan, ctx)


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """Evil's Thrall: you control a Villain whose mana value is greater than the target creature's (the target as it is now, 608.2b)."""
    from app.rules import effects, selectors, stack_interaction

    if cond["w110o"] == "land_upkeep":  # Herald of Leshrac: a land the controller does not control for each age counter (each is gained once)
        src = plan.state.cards.get(ctx.get("source_card") or "")
        age = src.counters.get("age", 0) if src is not None else 0
        return len(_others_lands(plan, ctx["controller"])) >= age
    if cond["w110o"] == "defender_no_snow":  # a defending player now: one an attacking creature attacks or whose planeswalker one attacks (508.5); the choice among them is the controller's (508.5a)
        defenders = {d for c in plan.state.cards.values() if c.attacking is not None and (d := selectors._defender(plan, c.attacking))}
        return any(not any("Snow" in plan.ch(x).supertypes and "Land" in plan.ch(x).types for x in plan.state.cards.values()
                           if x.zone.endswith(":battlefield") and x.controller == p) for p in defenders)
    if cond["w110o"] == "arn_permanents":
        return bool(arn_permanents(plan, ctx))
    if cond["w110o"] == "guessed":
        return False  # Spire Phantasm: no draft, no guess, so no correct guess (905.2b: the information is noted during the draft)
    if cond["w110o"] == "portent_four":

        return len(_bound(plan, ctx, "portent110o")) >= 4
    if cond["w110o"] == "helm_creature":
        return bool(ctx.get("helm_creatures110o"))
    assert cond["w110o"] == "villain_bigger"
    target = [stack_interaction.mana_value(plan.state.cards[c], plan.ch(plan.state.cards[c])) for c in effects._cards(plan, ctx, "target")]
    return bool(target) and any(
        "Villain" in plan.ch(c).subtypes and stack_interaction.mana_value(c, plan.ch(c)) > target[0]
        for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"])



# -- Reverse the Sands: "Redistribute any number of players' life totals." (119.7-8) ------------------------------------------------------------
def _allowed(plan: Plan, pid: str, total: int) -> bool:
    """119.7-8: a player who can't gain life can't receive a higher total, one who can't lose life no lower one."""
    from app.rules import cant_gain, life_lock

    now = plan.state.players[pid].life
    return not ((total > now and cant_gain.why_not(plan, pid)) or (total < now and life_lock.why_not(plan, pid, "lose")))


def _completable(plan: Plan, players: list[str], totals: dict[str, int], left: list[str], given: dict[str, str]) -> bool:
    """Can the players not yet given a total still all be given one of the totals left (each source once)?"""
    todo = [p for p in players if p not in given]
    if not todo:
        return True
    p = todo[0]
    return any(_allowed(plan, p, totals[src]) and _completable(plan, players, totals, [x for x in left if x != src], {**given, p: src}) for src in left)


def redistribute(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    live = [p for p in plan.apnap() if p in plan.live()]
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose any number of players whose life totals are redistributed",
           options=[DecisionOption(id=p, label=f"{plan.name(p)} ({plan.state.players[p].life} life)") for p in live], min_choices=0, max_choices=len(live),
           resume={"step": "redistribute_players110o", "ctx": ctx, "e": e})
    return False


def resume_redistribute_players(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    live = [p for p in plan.apnap() if p in plan.live()]
    if len(set(chosen)) != len(chosen) or any(p not in live for p in chosen):
        raise ActionError("Choose players still in the game")
    players = [p for p in live if p in chosen]
    if len(players) < 2:  # one player given back their own total, or none: nothing changes
        effects.continue_effects(plan, ctx)
        return
    totals = {p: plan.state.players[p].life for p in players}  # (the totals as the choice is made, 608.2h)
    _next_assignment(plan, ctx, players, totals, {})


def _next_assignment(plan: Plan, ctx: Context, players: list[str], totals: dict[str, int], given: dict[str, str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    todo = [p for p in players if p not in given]
    left = [p for p in players if p not in given.values()]
    p = todo[0]
    options = [src for src in left if _allowed(plan, p, totals[src])
               and _completable(plan, players, totals, [x for x in left if x != src], {**given, p: src})]
    if len(todo) == 1:  # the last total goes to the last player
        _finish(plan, ctx, players, totals, {**given, p: options[0]})
        return
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: which life total does {plan.name(p)} get?",
           options=[DecisionOption(id=src, label=f"{totals[src]} (was {plan.name(src)}'s)") for src in options],
           resume={"step": "redistribute_give110o", "ctx": ctx, "players": players, "totals": totals, "given": given})


def resume_redistribute_give(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError

    r = d.resume
    players, totals, given = r["players"], r["totals"], r["given"]
    p = [x for x in players if x not in given][0]
    left = [x for x in players if x not in given.values()]
    if len(chosen) != 1 or chosen[0] not in left or not _allowed(plan, p, totals[chosen[0]]):
        raise ActionError("Choose one of the life totals offered")
    plan.note(f"{plan.name(p)} gets {totals[chosen[0]]}", actor=d.player)
    _next_assignment(plan, r["ctx"], players, totals, {**given, p: chosen[0]})


def _finish(plan: Plan, ctx: Context, players: list[str], totals: dict[str, int], given: dict[str, str]) -> None:
    """An exchange of every chosen player's total (119.7-8, life_changes44.change: replacements, 616.1, are applied there)."""
    from app.rules import effects, life_changes44, replace

    request = {"mode": "exchange", "participants": players, "changes": [[p, totals[given[p]] - plan.state.players[p].life] for p in players],
               "actor": ctx["controller"], "bind": None, "operation": replace._life_operation(plan, None)}
    if life_changes44.change(plan, request, then={"do": "continue", "ctx": ctx}, ctx=ctx):
        effects.continue_effects(plan, ctx)


# -- Helm of Obedience ------------------------------------------------------------------------------------------------------------------------
def helm_test(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """After each mill: the cards that really reached the graveyard count (a replacement may have sent it elsewhere); stop (skip the "repeat") with a
    creature card among them, with X cards in all, or when nothing could be milled (an empty library: the process can't go on)."""
    from app.rules import context

    milled = [c for c in context.objects(plan, ctx, "helm110o") if plan.state.cards[c].zone.endswith(":graveyard")]
    ctx["helm_total110o"] = int(ctx.get("helm_total110o", 0)) + len(milled)
    ctx["helm_creatures110o"] = [*ctx.get("helm_creatures110o", []), *(c for c in milled if "Creature" in plan.ch(plan.state.cards[c]).types)]
    if ctx["helm_creatures110o"] or ctx["helm_total110o"] >= int(ctx.get("x") or 0) or not context.objects(plan, ctx, "helm110o"):
        ctx["next"] += 1
    return True


def helm_again(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    ctx["next"] -= e["rewind"]
    return True


def helm_pick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put one of them onto the battlefield under your control": the only creature card, else the controller picks one (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    found = [c for c in ctx.get("helm_creatures110o", []) if plan.state.cards[c].zone.endswith(":graveyard")]
    if len(found) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature card to put onto the battlefield",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in found],
               resume={"step": "helm_pick110o", "ctx": ctx})
        return False
    return _put_onto_battlefield(plan, ctx, found[0]) if found else True


def _put_onto_battlefield(plan: Plan, ctx: Context, cid: str) -> bool:
    from app.rules import context, effects

    context.bind_objects(plan, ctx, "helm_pick110o", [cid])
    return bool(effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "ref:helm_pick110o", "to": "battlefield", "tapped": False, "under": "you"}))


def resume_helm_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in ctx.get("helm_creatures110o", []):
        raise ActionError("Choose one of the creature cards offered")
    if _put_onto_battlefield(plan, ctx, chosen[0]):
        effects.continue_effects(plan, ctx)


def _bound(plan: Plan, ctx: Context, name: str) -> list[str]:
    """The objects of the binding called ``name`` (a spell's lines get the line number as a prefix, scripts.rename_bindings: l0_name)."""
    from app.rules import context

    return [c for key in context.refs(ctx) if key == name or key.endswith("_" + name) for c in context.objects(plan, ctx, key)]


def portent_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Portent of Calamity: what is still exiled of the cards exiled this way goes into the controller's hand (a cast one is on the stack, or beyond)."""
    rest = [c for c in _bound(plan, ctx, "portent110o") if plan.state.cards[c].zone.endswith(":exile")]
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": ctx["controller"], "zone": "hand"}}, actor=ctx["controller"])
    return True


# -- Rinoa, Angel Wing -------------------------------------------------------------------------------------------------------------------------
def rinoa_pick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Return one of them": the controller picks one of the creature cards that died together and are still in a graveyard (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    found = [c for c in context.objects(plan, ctx, context.EVENT_NEW) if plan.state.cards[c].zone.endswith(":graveyard")]
    if len(found) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature to return",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in found],
               resume={"step": "rinoa_pick110o", "ctx": ctx})
        return False
    context.bind_objects(plan, ctx, "rinoa110o", found)
    return True


def resume_rinoa_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in context.objects(plan, ctx, context.EVENT_NEW):
        raise ActionError("Choose one of the creatures that died")
    context.bind_objects(plan, ctx, "rinoa110o", chosen)
    effects.continue_effects(plan, ctx)


# -- Lazav, Familiar Stranger --------------------------------------------------------------------------------------------------------------
def lazav(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Then you may exile a card from a graveyard" (not a target: any graveyard, chosen as the ability resolves, 608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":graveyard") and plan.in_game(c)]
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: exile a card from a graveyard?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in cards], min_choices=0, max_choices=1,
           resume={"step": "lazav110o", "ctx": ctx})
    return False


def resume_lazav(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects
    from app.rules.plan import decide

    ctx = d.resume["ctx"]
    if len(chosen) > 1 or any(not plan.state.cards[c].zone.endswith(":graveyard") for c in chosen):
        raise ActionError("Choose at most one card from a graveyard")
    if chosen:
        card = plan.state.cards[chosen[0]]
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": card.owner, "zone": "exile"}}, actor=ctx["controller"])
        context.bind_objects(plan, ctx, "lazav110o", chosen)
        if "Creature" in plan.ch(plan.state.cards[chosen[0]]).types:
            from app.game.rules_state import DecisionOption

            decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: become a copy of {card.name}?",
                   options=[DecisionOption(id="yes", label="Become a copy"), DecisionOption(id="no", label="Don't")],
                   resume={"step": "lazav_copy110o", "ctx": ctx})
            return
    effects.continue_effects(plan, ctx)


def resume_lazav_copy(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen == ["yes"] and not effects.PRIMITIVES["become_copy"](plan, ctx, {"do": "become_copy", "who": "self", "with": "ref:lazav110o", "duration": "end_of_turn"}):
        return
    effects.continue_effects(plan, ctx)


def profaner(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects, selectors

    got = context.info(plan, ctx, context.EVENT_OTHER)
    if got is None or got[1].pt is None:
        return True  # (no exploited creature to measure: nothing is less than it)
    small = selectors.Selector(types=("Creature",), controller="opponent", compare=(("toughness", "<", int(got[1].pt[1])),)).key()
    return bool(effects.PRIMITIVES["bounce"](plan, ctx, {"do": "bounce", "who": small}))


# -- Herald of Leshrac --------------------------------------------------------------------------------------------------------------------------
def _others_lands(plan: Plan, you: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller != you and plan.in_game(c) and "Land" in plan.ch(c).types]


def gain_land(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Gain control of a land you don't control" as a cost (cumulative upkeep, 702.24a): chosen as it is paid, not targeted (115.1), kept for good (no duration)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    lands = _others_lands(plan, ctx["controller"])
    if not lands:
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a land you don't control",
           options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({plan.name(plan.state.cards[c].controller)})", card_id=c) for c in lands],
           resume={"step": "gain_land110o", "ctx": ctx})
    return False


def resume_gain_land(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in _others_lands(plan, ctx["controller"]):
        raise ActionError("Choose a land you don't control")
    context.bind_objects(plan, ctx, "herald110o", chosen)
    if effects.PRIMITIVES["gain_control"](plan, ctx, {"do": "gain_control", "who": "ref:herald110o"}):
        effects.continue_effects(plan, ctx)


def heroic(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """614.9: damage to the controller and their creatures goes to the chosen creature, while it is still that creature on the battlefield (the record keeps its
    object id, source_shields.redirect_target); damage to the chosen creature itself is not redirected."""
    from app.rules import damage_redirection_effects, source_shields

    dest = source_shields._destination(plan, ctx, "target")
    if dest is None:
        return True
    damage_redirection_effects.record(plan, ctx, {"to": {"players": "you", "objects": {"sel": damage_redirection_effects.key("creatures you control")}}}, dest)
    return True


def tidal(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """608.2c: the attacking creatures without flying as the instruction starts, each with its controller's own optional {1} (118.12); a creature whose controller does
    not pay is given its blockers first strike as that step is reached (the creatures I control that block it then)."""
    from app.rules import context, effects

    order = {p: i for i, p in enumerate(plan.apnap())}
    attackers = sorted((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.is_attacking and "flying" not in plan.ch(c).keywords),
                       key=lambda c: order.get(c.controller, len(order)))
    added: list[dict[str, Any]] = []
    for i, c in enumerate(attackers):
        context.bind_objects(plan, ctx, f"tidal{i}_110o", [c.id])
        added += [{"do": "optional_payment", "who": f"player:{c.controller}", "cost": "{1}", "bind": f"tidal{i}_paid110o", "for110o": f"{c.name} (attacking)"},
                  {"do": "only_if", "cond": {"succeeded": f"tidal{i}_paid110o", "negate": True}, "skip": 1},
                  {"do": "tidal_grant110o", "attacker": f"tidal{i}_110o", "index": i}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    effects.continue_effects(plan, ctx)
    return False


def tidal_grant(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    found = context.objects(plan, ctx, e["attacker"])
    if not found or not plan.state.cards[found[0]].is_attacking:
        return True
    blockers = [c.id for c in plan.state.cards.values() if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and c.blocks(found[0])]
    if blockers:
        context.bind_objects(plan, ctx, f"tidal_blockers{e['index']}_110o", blockers)
        at = ctx["next"]
        ctx["effects"][at:at] = [{"do": "grant", "who": f"ref:tidal_blockers{e['index']}_110o", "keywords": ["first strike"]}]
    return True


def _echo_holder(plan: Any, op: dict[str, Any]) -> Any:
    return next((x for x in plan.state.cards.values() if x.zone.endswith(":battlefield") and plan.oid(x) == op["oid"]), None)


def echo_left(plan: Any, c: Any, sim: dict[str, Any]) -> int:
    """The counters Soul Echo's replacement can still remove in this damage batch (the permanent only while it is that object on the battlefield, 400.7)."""
    holder = _echo_holder(plan, c.op)
    return 0 if holder is None else holder.counters.get(c.op["kind"], 0) - sim.get("shields", {}).get(f"echo110o:{c.op['oid']}:{c.op['kind']}", 0)


def echo_apply(plan: Any, c: Any, ev: dict[str, Any], sim: dict[str, Any]) -> list[dict[str, Any]]:
    """614.1a: "for each 1 damage that would be dealt to you … you remove an echo counter instead": that many counters are removed (as many as there are), the rest is dealt."""
    used = min(int(ev["amount"]), max(0, echo_left(plan, c, sim)))
    key = f"echo110o:{c.op['oid']}:{c.op['kind']}"
    shields = sim.setdefault("shields", {})
    shields[key] = shields.get(key, 0) + used
    return [{**ev, "amount": int(ev["amount"]) - used}]


def echo_commit(plan: Any, key: str, n: int) -> None:
    _, oid, kind = key.split(":", 2)
    holder = next((x for x in plan.state.cards.values() if x.zone.endswith(":battlefield") and plan.oid(x) == oid), None)
    if holder is not None and holder.counters.get(kind, 0) > 0:
        taken = min(n, holder.counters[kind])
        plan.do({"type": "counter", "card_ids": [holder.id], "kind": kind, "delta": -taken}, actor=holder.controller)
        plan.note(f"{holder.name}: {taken} {kind} counter(s) removed instead of damage", [holder.id], actor=holder.controller)


def echo_offer(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Target opponent may choose that …": the opponent targeted decides, privately, as the ability resolves (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    opponents = effects._players(plan, ctx, "target")
    if len(opponents) != 1 or opponents[0] not in plan.live():
        return True
    decide(plan, player=opponents[0], kind="choose_one",
           prompt=f"{ctx.get('name') or 'It'}: for each 1 damage that would be dealt to {plan.name(ctx['controller'])} until their next upkeep, they remove an echo counter instead?",
           options=[DecisionOption(id="yes", label="Choose that"), DecisionOption(id="no", label="Don't")],
           resume={"step": "echo_offer110o", "ctx": ctx})
    return False


def resume_echo_offer(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, replace

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in ("yes", "no"):
        raise ActionError("Choose yes or no")
    if chosen[0] == "yes" and ctx.get("source_object") is not None:
        replace.add_record(plan, event="damage", match={"to": {"players": "you"}}, op={"do": "remove_counters110o", "kind": "echo", "oid": ctx["source_object"]},
                           controller=ctx["controller"], source=ctx.get("source_object"), source_card=ctx.get("source_card"),
                           label=ctx.get("name") or "an effect", until="next_turn", until_player=ctx["controller"])
    effects.continue_effects(plan, ctx)


def secret_copy(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """611.2b: the copy effect (layer 1, made by the ordinary ``become_copy``) lasts for as long as the Aura (the source) stays on the battlefield."""
    from app.rules import copying

    before = len(plan.rules.effects)
    done = copying.become_copy(plan, ctx, {**e, "do": "become_copy"})
    for made in plan.rules.effects[before:]:
        if made.layer == "1" and made.copy_recipe is not None:
            made.duration, made.source, made.source_card, made.until_player = "source_on_battlefield", ctx.get("source_object"), ctx.get("source_card"), ctx["controller"]
    return done


def entered(plan: Any, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
    """614.12a: the card picked as the permanent entered is exiled (406.3) and linked to it, 607.2a (the new object's id: ``exiled_with``)."""
    from app.rules import exiled_with

    picked = (choices or {}).get(EXILE_WHAT)
    card = plan.state.cards.get(card_id)
    if card is None or picked is None or picked not in plan.state.cards or not plan.state.cards[picked].zone.endswith(":graveyard"):
        return
    plan.do({"type": "move", "card_ids": [picked], "to": {"zone": "exile"}}, actor=controller)
    exiled_with.record(plan, {"source_object": plan.oid(card), "source_card": card_id, "controller": controller}, [picked])


def exiled_mv(plan: Any, ctx: dict[str, Any]) -> int:
    from app.rules import exiled_with

    return sum(int(plan.ch(plan.state.cards[c]).mana_value) for c in exiled_with.cards(plan, ctx))


def lore_bind(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with

    context.bind_objects(plan, ctx, "lore110o", exiled_with.cards(plan, ctx))
    return True


def collect(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The cards the ability just exiled get a collection counter and are remembered as exiled by an ability its controller controlled."""
    from app.rules import context

    for cid in context.objects(plan, ctx, "evelyn110o"):
        if plan.state.cards[cid].zone.endswith(":exile"):
            plan.do({"type": "counter", "card_ids": [cid], "kind": "collection", "delta": 1}, actor=ctx["controller"])
            plan.rules.collection110o[plan.oid(cid)] = ctx["controller"]
    return True


def named_arn(name: str | None) -> bool:
    return any(part in ARABIAN_NIGHTS for part in (name or "").split(" // "))


def arn_permanents(plan: Any, ctx: dict[str, Any]) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.is_token and c.id != ctx.get("source_card")
            and plan.in_game(c) and named_arn(plan.ch(c).name)]


def arn_sacrifice(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.21a: each controller sacrifices their own (they are sacrificed together)."""
    from app.rules import context

    found = arn_permanents(plan, ctx)
    if found:
        context.bind_objects(plan, ctx, "arn110o", found)
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "sacrifice", "who": "ref:arn110o", "by": "controller"}]
    return True


def note(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Note one of its creature types that hasn't been noted for ~": the cast spell's creature types not yet kept for this object; one left is noted, several are the controller's choice."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    spells = effects._cards(plan, ctx, "event_spell")
    card = plan.state.cards.get(spells[0]) if spells else None
    if card is None or ctx.get("source_object") is None:
        return True
    noted = plan.rules.notes110o.get(ctx["source_object"], [])
    options = sorted(t for t in plan.ch(card).subtypes & CREATURE_TYPES if t not in noted)
    if len(options) == 1:
        plan.rules.notes110o[ctx["source_object"]] = [*noted, options[0]]
        plan.note(f"{ctx.get('name') or 'It'}: {options[0]} is noted", actor=ctx["controller"])
    elif options:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: note one of {card.name}'s creature types",
               options=[DecisionOption(id=t, label=t) for t in options], resume={"step": "note110o", "ctx": ctx})
        return False
    return True


def resume_note(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the creature types")
    noted = plan.rules.notes110o.get(ctx["source_object"], [])
    plan.rules.notes110o[ctx["source_object"]] = [*noted, chosen[0]]
    plan.note(f"{ctx.get('name') or 'It'}: {chosen[0]} is noted", actor=ctx["controller"])
    effects.continue_effects(plan, ctx)


def noted_count(plan: Any, ctx: dict[str, Any], who: str) -> int:
    from app.rules import effects

    return sum(len(plan.rules.notes110o.get(plan.oid(c), [])) for c in effects._cards(plan, ctx, who))


def tomb_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    record = plan.rules.tomb110o.setdefault(ctx["source_object"], {"put": [], "removed": []})
    for cid in effects._cards(plan, ctx, "target"):
        if plan.state.cards[cid].counters.get("mire", 0) > 0 and plan.oid(cid) not in record["put"]:
            record["put"].append(plan.oid(cid))
    return True


def tomb_delay(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """603.7: the delayed trigger belongs to the controller of the ability when it resolved, and goes on for the rest of the game (once: False)."""
    from app.rules import delayed

    delayed.create_plain(plan, ctx["controller"], ctx["source_card"], ctx["source_object"], ctx.get("name") or "Cyclopean Tomb",
                         {"kind": "step", "step": "upkeep", "whose": "you"}, [{"do": "tomb_remove110o", "tomb": ctx["source_object"]}])
    plan.rules.delayed[-1].once = False
    return True


def tomb_remove(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Remove all mire counters from a land the Tomb put one onto and has not removed one from (the controller picks if there are several)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    record = plan.rules.tomb110o.get(e["tomb"]) or {"put": [], "removed": []}
    options = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in record["put"] and plan.oid(c) not in record["removed"]]
    if len(options) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a land to remove the mire counters from",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Land", card_id=c) for c in options],
               resume={"step": "tomb_remove110o", "ctx": ctx, "tomb": e["tomb"]})
        return False
    if options:
        _tomb_take(plan, ctx, e["tomb"], options[0])
    return True


def _tomb_take(plan: Any, ctx: dict[str, Any], tomb: str, land: str) -> None:
    card = plan.state.cards[land]
    n = card.counters.get("mire", 0)
    if n > 0:
        plan.do({"type": "counter", "card_ids": [land], "kind": "mire", "delta": -n}, actor=ctx["controller"])
        plan.rules.tomb110o.setdefault(tomb, {"put": [], "removed": []})["removed"].append(plan.oid(card))


def resume_tomb_remove(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the lands")
    _tomb_take(plan, ctx, d.resume["tomb"], chosen[0])
    effects.continue_effects(plan, ctx)


def alter_aura(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Enchantment Alteration: "that type" is the type of the permanent the Aura is attached to as this resolves (a creature, a land, or both); the caster picks the
    other permanent of it that the Aura can enchant (701.3b), nothing if there is none."""
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects
    from app.rules.plan import decide
    from app.rules.targets import label

    found = effects._cards(plan, ctx, e["who"])
    aura = plan.state.cards[found[0]] if found else None
    host = plan.state.cards.get(aura.attached_to or "") if aura is not None else None
    if aura is None or host is None or not host.zone.endswith(":battlefield"):
        return True
    types = plan.ch(host).types & {"Creature", "Land"}
    options = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.id != host.id and types & plan.ch(c).types
               and attachments.host_problem(plan, aura, c.id) is None]
    if not options:
        return True
    if len(options) == 1:
        attachments.attach(plan, aura.id, options[0], ctx["controller"])
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: attach {aura.name} to which permanent?",
           options=[DecisionOption(id=c, label=label(plan, c), card_id=c) for c in options], resume={"step": "alter_aura110o", "ctx": ctx, "aura": aura.id})
    return False


def resume_alter_aura(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments, effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the permanents")
    attachments.attach(plan, d.resume["aura"], chosen[0], d.player)
    effects.continue_effects(plan, d.resume["ctx"])


def divide_x_to_event(target: Any) -> Any:
    """A reflexive ability's divided group whose total is X: the total becomes the amount of its event (the X paid), read as it goes on the stack (targets.divide_x);
    any other X in the target definition is not read (None)."""
    groups = target if isinstance(target, list) else [target]
    out = []
    for g in groups:
        if not isinstance(g, dict) or (g.get("divide") or {}).get("total") != {"x": 1} or "value" in g["divide"]:
            return None
        out.append({**g, **({"min": 0} if g["max"] >= 250 else {}), "divide": {**g["divide"], "value": {"event_amount": 1}}})  # (115.6: "any number of" allows none)
    return out if isinstance(target, list) else out[0]


def wipe_shield(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """614.1a: a shield for this turn on each target land (the object, 400.7): the next time it would be destroyed, the damage marked on it is removed instead."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"]):
        oid = plan.oid(cid)
        plan.rules.wipe_shields110o[oid] = plan.rules.wipe_shields110o.get(oid, 0) + 1
        effects._mark(plan, [cid], "Damage-removal shield")
    return True


def use_wipe(plan: Any, card: Any) -> None:
    """The shield is used up: all damage marked on the permanent is removed and it is not destroyed (614.1a; a deathtouch mark goes with the damage)."""
    oid = plan.oid(card)
    left = plan.rules.wipe_shields110o.get(oid, 0) - 1
    if left > 0:
        plan.rules.wipe_shields110o[oid] = left
    else:
        plan.rules.wipe_shields110o.pop(oid, None)
        for marker in [m for m in card.effects if m.name == "Damage-removal shield"]:
            plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=card.controller)
    plan.note(f"{card.name}: all damage marked on it is removed instead of being destroyed", [card.id], actor=card.controller)
    if card.damage:
        plan.do({"type": "set_damage", "card_ids": [card.id], "value": 0}, actor=card.controller)
    plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != card.id]


def cleansing(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """608.2c, 118.12a: "For each land, destroy that land unless any player pays 1 life": the lands there are as the instruction starts, each with its own
    round of payments (every player decides in turn order, 101.4, then pays; a land is destroyed if nobody paid for it)."""
    from app.rules import context, effects

    lands = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and "Land" in plan.ch(c).types]
    added: list[dict[str, Any]] = []
    for i, cid in enumerate(lands):
        context.bind_objects(plan, ctx, f"cleansing{i}_110o", [cid])
        added += [{"do": "each_may", "who": "each_player", "cost": "Pay 1 life", "verdict": f"cleansing{i}_paid110o",
                   "for110o": f"{plan.state.cards[cid].name} ({plan.name(plan.state.cards[cid].controller)}'s)"},
                  {"do": "only_if", "cond": {"flag": f"cleansing{i}_paid110o", "negate": True}, "skip": 1},
                  {"do": "destroy", "who": f"ref:cleansing{i}_110o"}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    effects.continue_effects(plan, ctx)
    return False


PRIMITIVES: dict[str, Any] = {"alter_aura110o": alter_aura, "tomb_put110o": tomb_put, "tomb_delay110o": tomb_delay, "tomb_remove110o": tomb_remove, "note110o": note, "arn_sacrifice110o": arn_sacrifice, "collect110o": collect, "lore_bind110o": lore_bind, "secret_copy110o": secret_copy, "echo_offer110o": echo_offer, "wipe_shield110o": wipe_shield, "tidal110o": tidal, "tidal_grant110o": tidal_grant, "heroic110o": heroic, "cleansing110o": cleansing, "type_emblem110o": type_emblem, "redistribute110o": redistribute,
              "helm_test110o": helm_test, "helm_again110o": helm_again, "helm_pick110o": helm_pick, "portent_hand110o": portent_hand, "rinoa_pick110o": rinoa_pick, "lazav110o": lazav, "profaner110o": profaner, "gain_land110o": gain_land}
RESUME: dict[str, Any] = {"alter_aura110o": resume_alter_aura, "tomb_remove110o": resume_tomb_remove, "note110o": resume_note, "echo_offer110o": resume_echo_offer, "type_emblem110o": resume_type_emblem, "redistribute_players110o": resume_redistribute_players,
                          "redistribute_give110o": resume_redistribute_give, "helm_pick110o": resume_helm_pick, "rinoa_pick110o": resume_rinoa_pick, "lazav110o": resume_lazav, "lazav_copy110o": resume_lazav_copy, "gain_land110o": resume_gain_land}
