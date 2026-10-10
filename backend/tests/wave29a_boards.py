"""The boards of the wave 29A hint checks. Each builder returns a session in which p1 has priority (unless it says otherwise) over a table that
makes the hint code do real work: many permanents, spells on the stack, cards in every zone a permission can reach, cost changers, casting
restrictions, copy effects and layer-changing statics. Builders are deterministic: same table every run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tests.game_helpers import act
from tests.wave29a_kit import cast, lands, put, snapshot, table, token


def stack_and_anthems(cards):
    """The 28C review's table: 80 permanents, 3 spells on the stack, 7 cards in hand, grants to spells."""
    s = table(cards, {"hand": [("Lightning Bolt", 5), "Fireblast", "Sol Ring", "Fire // Ice", "Opt", "Counterspell"],
                      "battlefield": ["Radiant Scrollwielder", ("Mountain", 6)]})
    token(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    token(s, "p1", "Knight", "2/2", "Other creatures you control have first strike.")
    token(s, "p1", "Warden", "0/4", "Creatures you control get +2/+2 as long as you control three or more artifacts.")
    for i in range(33):
        token(s, "p1", f"A{i}", "2/2")
    for i in range(36):
        token(s, "p2", f"B{i}", "2/2")
    token(s, "p2", "Cumber", "0/4", "Creatures your opponents control get -1/-0.")
    for _ in range(3):
        lands(s, R=1)
        cast(s, "Lightning Bolt", targets=["p2"])
    lands(s, R=3)
    return s


def permissions(cards):
    """Casting and playing from the graveyard, exile, the top of the library and the command zone, with several permission sources."""
    s = table(cards, {
        "battlefield": ["Lurrus of the Dream-Den", "Muldrotha, the Gravetide", "Karador, Ghost Chieftain", "Future Sight", "Vizier of the Menagerie",
                        "Bolas's Citadel", "Oracle of Mul Daya", "Underworld Breach", "Snapcaster Mage", ("Mountain", 4), ("Island", 3), ("Swamp", 2),
                        "Sol Ring", "Mind Stone", "Arcane Signet"],
        "graveyard": ["Faithless Looting", "Think Twice", "Treasure Cruise", "Eternal Witness", "Birds of Paradise", "Llanowar Elves", "Reanimate",
                      "Animate Dead", "Mountain", "Lightning Bolt", "Counterspell", "Kor Cartographer", "Sphere of Resistance"],
        "exile": ["Rift Bolt", "Rampant Growth", "Wrath of God"],
        "hand": ["Fireblast", "Force of Will", "Dream Halls", "Mountain", "Swords to Plowshares", "Cyclonic Rift"],
        "library": ["Eternal Witness"],
        "command": [],
    })
    lands(s, R=3, U=2, B=1, W=1, G=1)
    return s


def top_of_library(cards):
    """A land on top of the library with Courser, Oracle and Future Sight on the table; then a spell on top."""
    s = table(cards, {"battlefield": ["Courser of Kruphix", "Oracle of Mul Daya", ("Mountain", 3), ("Forest", 3)],
                      "hand": ["Mountain", "Llanowar Elves", "Cultivate"], "library": ["Forest"]})
    return s


def cost_changers(cards):
    s = table(cards, {
        "battlefield": ["Ruby Medallion", "Jet Medallion", "Helm of Awakening", "Thorn of Amethyst", "Sphere of Resistance", "Foundry Inspector",
                        "Goblin Warchief", "Etherium Sculptor", "Training Grounds", "Heartstone", "Trinisphere", "Goblin Electromancer",
                        "Herald's Horn", "Defiler of Vigor", "Defiler of Faith", "Jhoira, Weatherlight Captain", "Baral, Chief of Compliance",
                        ("Mountain", 6), ("Swamp", 3), ("Forest", 3), "Cryptolith Rite", "Llanowar Elves", "Birds of Paradise"],
        "hand": ["Lightning Bolt", "Sol Ring", "Mind Stone", "Wrath of God", "Treasure Cruise", "Bloodbraid Elf", "Cultivate", "Kor Cartographer",
                 "Mulldrifter", "Goblin Warchief", "Vampire Nighthawk"],
    }, {"battlefield": ["Sphere of Resistance", "Thorn of Amethyst", ("Island", 4)], "hand": ["Counterspell", "Sol Ring"]})
    lands(s, R=4, B=2, G=2, U=1, W=1)
    return s


def alternative_costs(cards):
    s = table(cards, {
        "battlefield": [("Mountain", 5), ("Island", 4), ("Plains", 2), ("Swamp", 2), "Frogmite", "Sol Ring", "Mind Stone", "Llanowar Elves"],
        "hand": ["Fireblast", "Force of Will", "Daze", "Snuff Out", "Gush", "Dream Halls", "Misdirection", "Fury", "Endurance", "Grief", "Subtlety",
                 "Cyclonic Rift", "Chord of Calling", "Treasure Cruise", "Mulldrifter", "Counterspell", "Solitude", "Bloodbraid Elf",
                 "Eternal Dragon", "Fiery Temper", "Terminus", "Ninja of the Deep Hours", "Bonecrusher Giant // Stomp",
                 "Rift Bolt", "Fire // Ice", "Lightning Bolt", "Swords to Plowshares"],
        "graveyard": ["Faithless Looting", "Think Twice", "Fiery Temper", "Mulldrifter"],
        "library": ["Terminus"],
    })
    lands(s, R=3, U=3, B=1)
    return s


def free_casts(cards):
    s = table(cards, {"battlefield": ["Omniscience", "Dream Halls", ("Island", 7), ("Mountain", 3), "Fires of Invention"],
                      "hand": ["Cyclonic Rift", "Wrath of God", "Bloodbraid Elf", "Lightning Bolt", "Mulldrifter", "Prismari Command",
                               "Thousand-Year Storm", "Wilderness Reclamation", "Rhystic Study"]})
    return s


def mayhem_and_grants(cards):
    s = table(cards, {"battlefield": ["Norman Osborn // Green Goblin", "Radiant Scrollwielder", "Pestilent Spirit", "Samut, Tyrant of Naktamun",
                                      ("Mountain", 5), ("Swamp", 3)],
                      "graveyard": ["Lightning Bolt", "Kolaghan's Command", "Doom Blade", "Vampire Nighthawk", "Mountain", "Cabal Coffers"],
                      "hand": ["Lightning Bolt", "Doom Blade", "Kolaghan's Command", "Vampire Nighthawk", "Sol Ring"]})
    lands(s, R=3, B=2)
    return s


def restrictions(cards):
    """Opponent's casting and activation restrictions, once Alice has cast a spell this turn (one spell per turn, no abilities of artifacts, ...)."""
    s = table(cards, {
        "battlefield": ["Sol Ring", "Mind Stone", "Arcane Signet", "Cursed Scroll", "Skullclamp", "Llanowar Elves", "Birds of Paradise",
                        ("Mountain", 5), ("Forest", 3), ("Island", 3), "Vedalken Orrery", "Leyline of Anticipation", "Yeva, Nature's Herald"],
        "hand": ["Lightning Bolt", "Counterspell", "Wrath of God", "Llanowar Elves", "Cultivate", "Fireblast", "Swords to Plowshares", "Bloodbraid Elf"],
    }, {"battlefield": ["Grand Abolisher", "Teferi, Time Raveler", "Rule of Law", "Archon of Emeria", "Hushbringer", "Aven Mindcensor",
                        "Cursed Totem", "Collector Ouphe", "Static Orb", "Winter Orb", "Thalia, Guardian of Thraben", "Narset, Parter of Veils",
                        ("Island", 4)]})
    lands(s, R=3, G=2, U=2)
    return s


def restrictions_after_a_spell(cards):
    s = restrictions(cards)
    cast(s, "Lightning Bolt", targets=["p2"])
    act(s, "p1", type="set_prefs", hold_priority=False)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    lands(s, R=3, G=2, U=2)
    return s


def layers_and_copies(cards):
    s = table(cards, {
        "battlefield": ["Blood Moon", "Urborg, Tomb of Yawgmoth", "Humility", "Opalescence", "Painter's Servant", "Crusade", "Honor of the Pure",
                        "Glorious Anthem", "Clone", "Phyrexian Metamorph", "Swiftfoot Boots", "Lightning Greaves", "Rancor", "Doubling Season",
                        "Cryptolith Rite", "Gaea's Cradle", "Mana Reflection", "Hardened Scales", "Anointed Procession", "Kess, Dissident Mage",
                        "Mizzix of the Izmagnus", ("Mountain", 4), ("Forest", 3), "Llanowar Elves", "Birds of Paradise", "Sol Ring"],
        "hand": ["Lightning Bolt", "Cultivate", "Vampire Nighthawk", "Wrath of God", "Counterspell"],
        "graveyard": ["Lightning Bolt", "Faithless Looting"],
    })
    for i in range(20):
        token(s, "p1", f"T{i}", "1/1")
    for i in range(20):
        token(s, "p2", f"U{i}", "1/1")
    lands(s, R=3, G=3)
    return s


def opponents_turn(cards):
    """Bob's turn: he casts a spell and passes priority; Alice has instants, flash and counterspells."""
    s = table(cards, {"battlefield": [("Island", 5), ("Mountain", 3), ("Forest", 2), "Leyline of Anticipation", "Vedalken Orrery", "Yeva, Nature's Herald"],
                      "hand": ["Counterspell", "Force of Will", "Lightning Bolt", "Swords to Plowshares", "Mulldrifter", "Daze", "Snuff Out"],
                      "graveyard": ["Misdirection", "Cyclonic Rift", "Llanowar Elves", "Wrath of God"]},
              {"battlefield": [("Mountain", 4)], "hand": ["Lightning Bolt", "Sol Ring"]}, active="p2")
    lands(s, "p2", R=3)
    cast(s, "Lightning Bolt", "p2", targets=["p1"])
    act(s, "p2", type="pass_priority")
    lands(s, "p1", U=3, R=2, G=1)
    return s


def split_and_modal(cards):
    s = table(cards, {"battlefield": [("Mountain", 4), ("Island", 3), "Sol Ring"],
                      "hand": ["Fire // Ice", "Bonecrusher Giant // Stomp", "Valakut Awakening // Valakut Stoneforge", "Eternal Dragon",
                               "Ninja of the Deep Hours", "Rift Bolt", "Terminus"]})
    lands(s, R=3, U=2)
    return s


def activations(cards):
    """Activated abilities (mana and not), loyalty abilities, equip, crew, X spells and sacrifice costs."""
    s = table(cards, {"battlefield": ["Walking Ballista", "Hangarback Walker", "Mother of Runes", "Sensei's Divining Top", "Cursed Scroll", "Skullclamp",
                                      "Smuggler's Copter", "Jace, the Mind Sculptor", "Liliana of the Veil", "Chandra, Torch of Defiance", "Wasteland",
                                      "Reliquary Tower", "Mana Crypt", "Mox Diamond", "Springleaf Drum", "Swiftfoot Boots", "Lightning Greaves",
                                      "Stoneforge Mystic", "Kor Cartographer", "Llanowar Elves", ("Mountain", 4), ("Forest", 4), ("Island", 2)],
                      "hand": ["Fireball", "Banefire", "Walking Ballista", "Lightning Helix", "Pyroblast", "Mental Misstep", "Remand", "Mountain"]})
    token(s, "p1", "Goblin A", "1/1", "{T}: Add {R}.")
    token(s, "p1", "Goblin B", "1/1")
    lands(s, R=3, G=2, U=1)
    return s


def second_player(cards):
    """Bob's own main phase: his hints, with Alice's permanents on the table."""
    s = table(cards, {"battlefield": [("Mountain", 2), "Thorn of Amethyst", "Static Orb"]},
              {"battlefield": [("Island", 4), ("Mountain", 2), "Sol Ring", "Ruby Medallion", "Future Sight"],
               "hand": ["Counterspell", "Lightning Bolt", "Mulldrifter", "Daze", "Fireblast", "Fireball"],
               "graveyard": ["Faithless Looting", "Think Twice", "Treasure Cruise"]}, active="p2")
    lands(s, "p2", U=3, R=2)
    return s


def hidden_information(cards):
    """Cards nobody may see (a face-down exile nobody looked at, both libraries, the opponent's hand) next to ones that are shown (the top card
    under Future Sight): hints may offer only what their viewer can see (400.2, 401.5, 406.3)."""
    s = table(cards, {"battlefield": [("Mountain", 4), ("Island", 2), "Future Sight"], "hand": [("Lightning Bolt", 2), "Counterspell"],
                      "library": ["Fire // Ice", "Fireball"]},
              {"battlefield": [("Island", 3), "Future Sight"], "hand": ["Counterspell", "Daze", "Lightning Bolt"], "library": ["Mulldrifter", "Daze"]})
    for pid in ("p1", "p2"):  # an effect exiled each library's top card face down: nobody has looked at it (406.3)
        act(s, pid, type="mill", player=pid, count=1, to="exile", face_down=True, blind=True)
    lands(s, R=2, U=2)
    return s


def play_through(cards) -> list[dict[str, Any]]:
    """A turn and a half of play with a view after every step: a land, a creature and a Bolt cast and resolved, then priority passed through
    Alice's phases into Bob's turn. Each view is taken on a table the previous step changed (a cache that outlived its call would show)."""
    s = table(cards, {"battlefield": [("Mountain", 3), ("Forest", 2), "Sol Ring", "Ruby Medallion", "Pestilent Spirit", "Lurrus of the Dream-Den"],
                      "hand": ["Mountain", "Lightning Bolt", "Llanowar Elves", "Cultivate", "Fireblast", "Faithless Looting"],
                      "graveyard": ["Mind Stone", "Kor Cartographer", "Think Twice"], "library": ["Forest"]},
              {"battlefield": [("Island", 3), "Thorn of Amethyst"], "hand": ["Counterspell", "Daze"]})
    out = [snapshot(s)]
    mountain = next(c for c in s.state.cards.values() if c.name == "Mountain" and c.zone == "p1:hand")
    act(s, "p1", type="play_land", card_id=mountain.id)
    out.append(snapshot(s))
    lands(s, R=2, G=1)
    cast(s, "Llanowar Elves")
    out.append(snapshot(s))
    for _ in range(4):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    out.append(snapshot(s))
    lands(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])
    out.append(snapshot(s))
    for _ in range(4):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    out.append(snapshot(s))
    act(s, "p1", type="set_prefs", hold_priority=False)
    for _ in range(24):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        out.append(snapshot(s))
    return out


SEQUENCES: dict[str, Callable[[Any], list[dict[str, Any]]]] = {"play_through": play_through}


def golden_snapshots(cards) -> dict[str, Any]:
    """Everything the golden file holds: board name -> both players' views (a sequence: a list of them)."""
    return {**{name: snapshot(build(cards)) for name, build in BOARDS.items()}, **{name: seq(cards) for name, seq in SEQUENCES.items()}}


BOARDS: dict[str, Callable[[Any], Any]] = {
    "stack_and_anthems": stack_and_anthems,
    "permissions": permissions,
    "top_of_library": top_of_library,
    "cost_changers": cost_changers,
    "alternative_costs": alternative_costs,
    "free_casts": free_casts,
    "mayhem_and_grants": mayhem_and_grants,
    "restrictions": restrictions,
    "restrictions_after_a_spell": restrictions_after_a_spell,
    "layers_and_copies": layers_and_copies,
    "opponents_turn": opponents_turn,
    "split_and_modal": split_and_modal,
    "activations": activations,
    "second_player": second_player,
    "hidden_information": hidden_information,
}

__all__ = ["BOARDS", "put"]
