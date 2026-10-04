"""Wave 17B: activated-ability wordings (CR 2026-09-25).

* "Target opponent may draw a card." (Phelddagrif): the other player decides as the ability resolves (608.2d).
* "gets -2/+2 and loses flying", "gains flying and loses trample", "loses defender and gains flying" (613.1f: one layer-6 effect).
* "Spend this mana only to cast kicked spells / spells from exile / spells with flashback from a graveyard", "This mana can't be spent
  to cast spells from your hand" (601.2h: what the spell is, where it's cast from and whether kicked are known when it's paid), and
  "Add an amount of {C} equal to Vhal's toughness".
* "Untap two tapped creatures you control" as a cost (Halo Fountain, Crackleburr: 701.26b) and "It deals 1 damage" after "Exert this
  creature" (701.43: the exerted creature is the source).
* Mana abilities whose cost exerts the source ("{T}, Exert this creature"), untaps it ("{2}, {Q}") or forages: paid by hand like a
  sacrifice cost, 605.3a (Oasis Ritualist, Pili-Pala, Thornvault Forager).
* "Remove X storage counters from this land: Add X mana in any combination of {U} and/or {B}" (the storage lands), "…X mana of any one
  color" (Petalmane Baku, Haruspex), "…an amount of {C} equal to X plus one" (Kyren Toy) and "Tap X untapped tokens you control: Add X mana
  in any combination of colors" (Hazel of the Rootbloom): X is announced as the cost is paid (107.3a), 605.3a. A mana ability that is
  activated by hand with a spending restriction (Crucible of the Spirit Dragon) stays manual: the pool carries no restriction.
* "Sacrifice an artifact: Add an amount of {B} equal to the sacrificed artifact's mana value" (Priest of Yawgmoth): the mana value of
  what the cost sacrificed (608.2h), a mana ability activated by hand (the sacrifice is the payer's choice).
* "Choose a color of a permanent you control. Add one mana of that color." (Meteor Crater; 105.2: never colorless) and "Choose a color.
  Add one mana of that color for each different power among creatures you control." (Selvala, Eager Trailblazer): counted as it's
  activated, 605.3b.
* "Target creature gains flanking / battle cry / dethrone / toxic 1 until end of turn": the keyword line itself is granted (613.1f), so its
  triggered ability exists for as long as the grant does (702.25a flanking).
* "…target creature blocking it / blocking this creature" in an activated ability of the attacker (509.1, 506.3d): only a creature
  blocking the source is a legal target (115.2).
* "{X}, Sacrifice this enchantment: Destroy each artifact, creature, and enchantment with mana value X or less." (Pernicious Deed) and
  "…Destroy each artifact with mana value X." (Dauntless Dismantler): the X announced as the ability is activated (107.3a, 107.3f).
* "Add X mana in any combination of colors, where X is the number of creatures you control with defender" (Axebane Guardian) and "…of {U}
  and/or {R}, where X is Vivi Ornitier's power": X as the ability is activated (605.3b); "Activate only during your turn / an opponent's
  turn" on a mana ability (602.5b).
* "Waterbend {2}: …" as an activation cost (701.67a): {2}, and for each generic mana in it the payer may tap an untapped artifact or
  creature they control instead of paying that mana (not a {T} cost: summoning sickness doesn't matter, 302.6); the permanent that
  taps itself for the ability can't also help pay.
* "…deals damage equal to that spell's mana value to any target that isn't a commander" (Lozhan, Dragons' Legacy) and "…that isn't a
  Dragon" (Wrathful Red Dragon): any target (115.1), but not a permanent that is one.
* "has base power 4 and gains trample" (613.4b: layer 7b, power only).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting, coverage
from app.rules import mana as M
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, creature, on_field
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"17B-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real('Phelddagrif', '{1}{G}{W}{U}', 4, 'Legendary Creature — Phelddagrif',
         "{G}: Phelddagrif gains trample until end of turn. Target opponent creates a 1/1 green Hippo creature token.\n{W}: Phelddagrif gains flying until end of turn. Target opponent gains 2 life.\n{U}: Return Phelddagrif to its owner's hand. Target opponent may draw a card.", ('4', '4'), 'GUW'),
    real('Leering Gargoyle', '{1}{W}{U}', 3, 'Creature — Gargoyle',
         'Flying\n{T}: This creature gets -2/+2 and loses flying until end of turn.', ('2', '2'), 'UW'),
    real('Canopy Dragon', '{4}{G}{G}', 6, 'Creature — Dragon',
         'Trample\n{1}{G}: This creature gains flying and loses trample until end of turn.', ('4', '4'), 'G'),
    real('Turtle-Duck', '{G}', 1, 'Creature — Turtle Bird',
         '{3}: Until end of turn, this creature has base power 4 and gains trample.', ('0', '4'), 'G'),
    real('Gargoyle Sentinel', '{3}', 3, 'Artifact Creature — Gargoyle',
         "Defender (This creature can't attack.)\n{3}: Until end of turn, this creature loses defender and gains flying.", ('3', '3'), ''),
    real('Singing Tree', '{3}{G}', 4, 'Creature — Plant',
         '{T}: Target attacking creature has base power 0 until end of turn.', ('0', '3'), 'G'),
    real('Island of Wak-Wak', '', 0, 'Land',
         '{T}: Target creature with flying has base power 0 until end of turn.', None, ''),
    real('Elfhame Druid', '{1}{G}', 2, 'Creature — Elf Druid',
         '{T}: Add {G}.\n{T}: Add {G}{G}. Spend this mana only to cast kicked spells.', ('0', '2'), 'G'),
    real('Saproling Migration', '{1}{G}', 2, 'Sorcery',
         'Kicker {4} (You may pay an additional {4} as you cast this spell.)\nCreate two 1/1 green Saproling creature tokens. If this spell was kicked, create four of those tokens instead.', None, 'G'),
    real('Interdimensional Web Watch', '{4}', 4, 'Artifact',
         'When this artifact enters, exile the top two cards of your library. Until the end of your next turn, you may play those cards.\n{T}: Add two mana in any combination of colors. Spend this mana only to cast spells from exile.', None, ''),
    real('Altar of the Lost', '{3}', 3, 'Artifact',
         'This artifact enters tapped.\n{T}: Add two mana in any combination of colors. Spend this mana only to cast spells with flashback from a graveyard.', None, ''),
    real('Vhal, Candlekeep Researcher', '{3}{U}', 4, 'Legendary Creature — Human Wizard',
         "Vigilance\n{T}: Add an amount of {C} equal to Vhal's toughness. This mana can't be spent to cast spells from your hand.\nChoose a Background (You can have a Background as a second commander.)", ('2', '3'), 'U'),
    real('Lord of the Forsaken', '{4}{B}{B}', 6, 'Creature — Demon',
         'Flying, trample\n{B}, Sacrifice another creature: Target player mills three cards.\nPay 1 life: Add {C}. Spend this mana only to cast a spell from your graveyard.', ('6', '6'), 'B'),
    real('Volshe Tideturner', '{1}{U}', 2, 'Creature — Merfolk Wizard',
         '{T}: Add {U}. Spend this mana only to cast an instant or sorcery spell or a kicked spell.', ('1', '3'), 'U'),
    real('Faithless Looting', '{R}', 1, 'Sorcery',
         'Draw two cards, then discard two cards.\nFlashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', None, 'R'),
    real('Halo Fountain', '{2}{W}', 3, 'Artifact',
         '{W}, {T}, Untap a tapped creature you control: Create a 1/1 green and white Citizen creature token.\n{W}{W}, {T}, Untap two tapped creatures you control: Draw a card.\n{W}{W}{W}{W}{W}, {T}, Untap fifteen tapped creatures you control: You win the game.', None, 'W'),
    real('Fervent Paincaster', '{2}{R}', 3, 'Creature — Human Wizard',
         "{T}: This creature deals 1 damage to target player or planeswalker.\n{T}, Exert this creature: It deals 1 damage to target creature. (An exerted creature won't untap during your next untap step.)", ('3', '1'), 'R'),
    real('Crackleburr', '{1}{U/R}{U/R}', 3, 'Creature — Elemental',
         "{U/R}{U/R}, {T}, Tap two untapped red creatures you control: This creature deals 3 damage to any target.\n{U/R}{U/R}, {Q}, Untap two tapped blue creatures you control: Return target creature to its owner's hand. ({Q} is the untap symbol.)", ('2', '2'), 'RU'),
    real('Oasis Ritualist', '{3}{G}', 4, 'Creature — Snake Druid',
         "{T}: Add one mana of any color.\n{T}, Exert this creature: Add two mana of any one color. (An exerted creature won't untap during your next untap step.)", ('2', '4'), 'G'),
    real('Pili-Pala', '{2}', 2, 'Artifact Creature — Scarecrow',
         'Flying\n{2}, {Q}: Add one mana of any color. ({Q} is the untap symbol.)', ('1', '1'), ''),
    real('Thornvault Forager', '{1}{G}', 2, 'Creature — Squirrel Ranger',
         '{T}: Add {G}.\n{T}, Forage: Add two mana in any combination of colors. (To forage, exile three cards from your graveyard or sacrifice a Food.)\n{3}{G}, {T}: Search your library for a Squirrel card, reveal it, put it into your hand, then shuffle.', ('2', '2'), 'G'),
    real('Dreadship Reef', '', 0, 'Land',
         '{T}: Add {C}.\n{1}, {T}: Put a storage counter on this land.\n{1}, Remove X storage counters from this land: Add X mana in any combination of {U} and/or {B}.', None, ''),
    real('Petalmane Baku', '{1}{G}', 2, 'Creature — Spirit',
         'Whenever you cast a Spirit or Arcane spell, you may put a ki counter on this creature.\n{1}, Remove X ki counters from this creature: Add X mana of any one color.', ('1', '2'), 'G'),
    real('Kyren Toy', '{3}', 3, 'Artifact',
         '{1}, {T}: Put a charge counter on this artifact.\n{T}, Remove X charge counters from this artifact: Add an amount of {C} equal to X plus one.', None, ''),
    real('Hazel of the Rootbloom', '{2}{B}{G}', 4, 'Legendary Creature — Squirrel Druid',
         "{T}, Pay 2 life, Tap X untapped tokens you control: Add X mana in any combination of colors.\nAt the beginning of your end step, create a token that's a copy of target token you control. If that token is a Squirrel, instead create two tokens that are copies of it.", ('3', '5'), 'BG'),
    real('Priest of Yawgmoth', '{1}{B}', 2, 'Creature — Phyrexian Human Cleric',
         "{T}, Sacrifice an artifact: Add an amount of {B} equal to the sacrificed artifact's mana value.", ('1', '2'), 'B'),
    real('Meteor Crater', '', 0, 'Land',
         '{T}: Choose a color of a permanent you control. Add one mana of that color.', None, ''),
    real('Selvala, Eager Trailblazer', '{2}{G}{W}', 4, 'Legendary Creature — Elf Scout',
         'Vigilance\nWhenever you cast a creature spell, create a 1/1 red Mercenary creature token with "{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery."\n{T}: Choose a color. Add one mana of that color for each different power among creatures you control.', ('4', '5'), 'GW'),
    real('Corrupted Grafstone', '{2}', 2, 'Artifact',
         'This artifact enters tapped.\n{T}: Choose a color of a card in your graveyard. Add one mana of that color.', None, ''),
    real("Jabari's Banner", '{2}', 2, 'Artifact',
         '{1}, {T}: Target creature gains flanking until end of turn. (Whenever a creature without flanking blocks this creature, the blocking creature gets -1/-1 until end of turn.)', None, ''),
    real('Reckless Pyrosurfer', '{1}{R}', 2, 'Creature — Human Scout',
         'Haste\nLandfall — Whenever a land you control enters, this creature gains battle cry until end of turn. (Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn. Each instance of battle cry triggers separately.)', ('2', '2'), 'R'),
    real("Godo's Irregulars", '{R}', 1, 'Creature — Human Warrior',
         '{R}: This creature deals 1 damage to target creature blocking it.', ('1', '1'), 'R'),
    real('Knight of Dusk', '{1}{B}{B}', 3, 'Creature — Human Knight',
         '{B}{B}: Destroy target creature blocking this creature.', ('2', '2'), 'B'),
    real('Pernicious Deed', '{1}{B}{G}', 3, 'Enchantment',
         '{X}, Sacrifice this enchantment: Destroy each artifact, creature, and enchantment with mana value X or less.', None, 'BG'),
    real('Dauntless Dismantler', '{1}{W}', 2, 'Creature — Human Artificer',
         'Artifacts your opponents control enter tapped.\n{X}{X}{W}, Sacrifice this creature: Destroy each artifact with mana value X.', ('1', '4'), 'W'),
    real('Axebane Guardian', '{2}{G}', 3, 'Creature — Human Druid',
         'Defender\n{T}: Add X mana in any combination of colors, where X is the number of creatures you control with defender.', ('0', '3'), 'G'),
    real('Vivi Ornitier', '{1}{U}{R}', 3, 'Legendary Creature — Wizard',
         "{0}: Add X mana in any combination of {U} and/or {R}, where X is Vivi Ornitier's power. Activate only during your turn and only once each turn.\nWhenever you cast a noncreature spell, put a +1/+1 counter on Vivi Ornitier and it deals 1 damage to each opponent.", ('0', '3'), 'RU'),
    real('Lavinia, Foil to Conspiracy', '{1}{W/U}{W/U}', 3, 'Legendary Creature — Human Detective',
         'Vigilance\nWhenever you cast your second spell each turn, investigate. (Create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")\n{T}: Add {C}{C}. Activate only during an opponent\'s turn.', ('2', '3'), 'UW'),
    real('Ruthless Waterbender', '{1}{B}', 2, 'Creature — Human Soldier Ally',
         'Waterbend {2}: This creature gets +1/+1 until end of turn. Activate only during your turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)', ('1', '3'), 'B'),
    real('North Pole Patrol', '{2}{U}', 3, 'Creature — Human Soldier Ally',
         '{T}: Untap another target permanent you control.\nWaterbend {3}, {T}: Tap target creature an opponent controls. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)', ('2', '3'), 'U'),
    real('Katara, Bending Prodigy', '{2}{U}', 3, 'Legendary Creature — Human Warrior Ally',
         'At the beginning of your end step, if Katara is tapped, put a +1/+1 counter on her.\nWaterbend {6}: Draw a card. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)', ('2', '3'), 'U'),
    real('Geyser Leaper', '{4}{U}', 5, 'Creature — Human Warrior Ally',
         'Flying\nWaterbend {4}: Draw a card, then discard a card. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)', ('4', '3'), 'U'),
    real('Giant Koi', '{4}{U}{U}', 6, 'Creature — Fish',
         "Waterbend {3}: This creature can't be blocked this turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)", ('5', '7'), 'U'),
    real('Flexible Waterbender', '{3}{U}', 4, 'Creature — Human Warrior Ally',
         'Vigilance\nWaterbend {3}: This creature has base power and toughness 5/2 until end of turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)', ('2', '5'), 'U'),
    real('Disembowel', '{X}{B}', 1, 'Instant',
         'Destroy target creature with mana value X.', None, 'B'),
    real("Lozhan, Dragons' Legacy", '{3}{U}{R}', 5, 'Legendary Creature — Dragon Shaman',
         "Flying\nWhenever you cast an Adventure or Dragon spell, Lozhan deals damage equal to that spell's mana value to any target that isn't a commander.", ('4', '2'), 'RU'),
    real('Shivan Dragon', '{4}{R}{R}', 6, 'Creature — Dragon',
         'Flying\n{R}: This creature gets +1/+0 until end of turn.', ('5', '5'), 'R'),
    real('Wrathful Red Dragon', '{3}{R}{R}', 5, 'Creature — Dragon',
         "Flying\nWhenever a Dragon you control is dealt damage, it deals that much damage to any target that isn't a Dragon.", ('5', '5'), 'R'),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
FULL = ["Lozhan, Dragons' Legacy", "Wrathful Red Dragon", "Disembowel", "Ruthless Waterbender", "North Pole Patrol", "Katara, Bending Prodigy", "Geyser Leaper", "Giant Koi",
        "Flexible Waterbender", "Axebane Guardian", "Vivi Ornitier", "Lavinia, Foil to Conspiracy", "Pernicious Deed", "Dauntless Dismantler", "Godo's Irregulars", "Knight of Dusk", "Jabari's Banner", "Reckless Pyrosurfer", "Meteor Crater", "Selvala, Eager Trailblazer", "Corrupted Grafstone", "Priest of Yawgmoth", "Dreadship Reef", "Petalmane Baku", "Kyren Toy", "Hazel of the Rootbloom", "Oasis Ritualist", "Pili-Pala", "Thornvault Forager", "Halo Fountain", "Crackleburr", "Fervent Paincaster", "Elfhame Druid", "Interdimensional Web Watch", "Altar of the Lost", "Vhal, Candlekeep Researcher", "Lord of the Forsaken",
        "Volshe Tideturner", "Phelddagrif", "Leering Gargoyle", "Canopy Dragon", "Turtle-Duck", "Gargoyle Sentinel", "Singing Tree", "Island of Wak-Wak"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def settle(s, pick=None, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [pick] if pick and pick in [o.id for o in d.options] else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def ability(s, c, start):
    return next(i for i, a in enumerate(s.cards.resolve(c.name).get("oracle_text", "").split("\n")) if a.startswith(start))


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("name", FULL)
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_target_opponent_may_draw_a_card(cards, answer):
    s = build(cards, "Phelddagrif", p2=("Grizzly Bears",))
    phel = on_field(s, "Phelddagrif")
    mana(s, "p1", U=1)
    before = len(zone(s.state, "p2", "hand"))
    act(s, "p1", type="activate_ability", card_id=phel.id, ability=ability(s, phel, "{U}"), targets=["p2"])
    settle(s, pick=answer)
    assert s.state.cards[phel.id].zone == "p1:hand"  # (returned to its owner's hand first)
    assert len(zone(s.state, "p2", "hand")) == before + (1 if answer == "yes" else 0)
    roundtrip(s)


def test_gets_and_loses_flying(cards):
    s = build(cards, "Leering Gargoyle")
    c = on_field(s, "Leering Gargoyle")
    s.state.rules.controlled_since[c.id].turn = 0  # (it has been there since before this turn began: 302.6)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{T}"))
    settle(s)
    ch = chars(s, c)
    assert ch.pt == (0, 4) and "flying" not in ch.keywords
    roundtrip(s)


def test_gains_flying_and_loses_trample(cards):
    s = build(cards, "Canopy Dragon")
    c = on_field(s, "Canopy Dragon")
    mana(s, "p1", G=2)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{1}{G}"))
    settle(s)
    ch = chars(s, c)
    assert "flying" in ch.keywords and "trample" not in ch.keywords
    roundtrip(s)


def test_loses_defender_and_gains_flying(cards):
    s = build(cards, "Gargoyle Sentinel")
    c = on_field(s, "Gargoyle Sentinel")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{3}"))
    settle(s)
    ch = chars(s, c)
    assert "flying" in ch.keywords and "defender" not in ch.keywords
    roundtrip(s)


def test_base_power_only_and_gains_trample(cards):
    s = build(cards, "Turtle-Duck")
    c = on_field(s, "Turtle-Duck")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{3}"))
    settle(s)
    ch = chars(s, c)
    assert ch.pt == (4, 4) and "trample" in ch.keywords  # (base toughness stays 4)
    roundtrip(s)


def lands(s, n):
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})


def with_druid(cards, n):
    s = build(cards, "Elfhame Druid", "Saproling Migration")
    druid = on_field(s, "Elfhame Druid")
    s.state.rules.controlled_since[druid.id].turn = 0
    lands(s, n)
    return s


def test_kicked_only_mana_pays_for_a_kicked_spell(cards):
    s = with_druid(cards, 4)  # {G}{G} (kicked spells only) + four Forests pay {5}{G}
    spell = next(c for c in s.state.cards.values() if c.name == "Saproling Migration")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1)
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p1:battlefield") == 4
    roundtrip(s)


def test_kicked_only_mana_cannot_pay_for_an_unkicked_spell(cards):
    s = with_druid(cards, 0)  # without the restriction its {G}{G} would pay {1}{G}
    spell = next(c for c in s.state.cards.values() if c.name == "Saproling Migration")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id)


@pytest.mark.parametrize(("sentence", "zone", "player", "ok"), [
    ("Spend this mana only to cast spells from exile.", "p1:exile", "p1", True),
    ("Spend this mana only to cast spells from exile.", "p1:graveyard", "p1", False),
    ("Spend this mana only to cast a spell from your graveyard.", "p1:graveyard", "p1", True),
    ("Spend this mana only to cast a spell from your graveyard.", "p2:graveyard", "p1", False),
    ("This mana can't be spent to cast spells from your hand.", "p1:hand", "p1", False),
    ("This mana can't be spent to cast spells from your hand.", "p1:exile", "p1", True),
])
def test_spend_only_by_where_the_spell_is_cast_from(cards, sentence, zone, player, ok):
    s = build(cards, "Saproling Migration")
    kind = M.parse_spend(sentence)
    assert kind is not None
    spell = chars(s, next(c for c in s.state.cards.values() if c.name == "Saproling Migration"))
    assert casting.spend_allowed(kind, casting.Purpose(spell=spell, zone=zone, player=player)) is ok
    assert casting.spend_allowed(kind, None) is False  # (a cost that isn't a spell or ability: refused)


def test_spend_only_for_a_spell_with_flashback_from_a_graveyard(cards):
    s = build(cards, "Saproling Migration", "Faithless Looting")
    kind = M.parse_spend("Spend this mana only to cast spells with flashback from a graveyard.")
    by_name = {c.name: chars(s, c) for c in s.state.cards.values() if c.name in ("Saproling Migration", "Faithless Looting")}
    assert casting.spend_allowed(kind, casting.Purpose(spell=by_name["Faithless Looting"], zone="p1:graveyard", player="p1"))
    assert not casting.spend_allowed(kind, casting.Purpose(spell=by_name["Faithless Looting"], zone="p1:hand", player="p1"))
    assert not casting.spend_allowed(kind, casting.Purpose(spell=by_name["Saproling Migration"], zone="p1:graveyard", player="p1"))


def test_untap_tapped_creatures_you_control_as_a_cost(cards):
    s = build(cards, "Halo Fountain")
    fountain = on_field(s, "Halo Fountain")
    bears = [creature(s, "p1", "Bear A"), creature(s, "p1", "Bear B")]
    act(s, "p1", type="tap", card_ids=[b.id for b in bears], tapped=True)
    mana(s, "p1", W=3)
    act(s, "p1", type="activate_ability", card_id=fountain.id, ability=ability(s, fountain, "{W}{W}, {T}"))
    settle(s)  # (both are untapped; the fountain tapped)
    assert [s.state.cards[b.id].tapped for b in bears] == [False, False] and s.state.cards[fountain.id].tapped
    assert s.state.players["p1"].mana == {"W": 1}
    roundtrip(s)


def test_untap_a_tapped_creature_cost_needs_one_and_makes_a_token(cards):
    s = build(cards, "Halo Fountain")
    fountain = on_field(s, "Halo Fountain")
    a, b = creature(s, "p1", "Bear A"), creature(s, "p1", "Bear B")
    mana(s, "p1", W=1)
    with pytest.raises(ActionError):  # (no tapped creature to untap: 118.3)
        act(s, "p1", type="activate_ability", card_id=fountain.id, ability=ability(s, fountain, "{W}, {T}"))
    act(s, "p1", type="tap", card_ids=[a.id], tapped=True)
    act(s, "p1", type="activate_ability", card_id=fountain.id, ability=ability(s, fountain, "{W}, {T}"))
    settle(s)
    assert not s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    assert any(c.name == "Citizen" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_exert_as_a_cost_then_it_deals_damage(cards):
    s = build(cards, "Fervent Paincaster", p2=("Grizzly Bears",))
    c = on_field(s, "Fervent Paincaster")
    s.state.rules.controlled_since[c.id].turn = 0
    bears = on_field(s, "Grizzly Bears", "p2")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{T}, Exert"), targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].damage == 1 and s.state.cards[c.id].tapped
    assert s.state.rules.exerted  # (701.43a: it won't untap during its controller's next untap step)
    roundtrip(s)


def test_exert_as_a_mana_ability_cost(cards):
    s = build(cards, "Oasis Ritualist")
    c = on_field(s, "Oasis Ritualist")
    s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{T}, Exert"))
    settle(s)
    assert sum(s.state.players["p1"].mana.values()) == 2 and len(s.state.players["p1"].mana) == 1  # (two of one color)
    assert s.state.cards[c.id].tapped and s.state.rules.exerted
    roundtrip(s)


def test_untap_symbol_as_a_mana_ability_cost(cards):
    s = build(cards, "Pili-Pala")
    c = on_field(s, "Pili-Pala")
    s.state.rules.controlled_since[c.id].turn = 0
    mana(s, "p1", C=2)
    with pytest.raises(ActionError):  # ({Q}: it has to be tapped, 107.6)
        act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{2}, {Q}"))
    act(s, "p1", type="tap", card_ids=[c.id], tapped=True)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{2}, {Q}"))
    settle(s)
    assert not s.state.cards[c.id].tapped and sum(s.state.players["p1"].mana.values()) == 1
    roundtrip(s)


def test_forage_as_a_mana_ability_cost(cards):
    s = build(cards, "Thornvault Forager")
    c = on_field(s, "Thornvault Forager")
    s.state.rules.controlled_since[c.id].turn = 0
    forests = [x for x in s.state.cards.values() if x.name == "Forest" and x.zone == "p1:library"][:3]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{T}, Forage"))
    d = s.state.rules.decision  # (the three graveyard cards to exile)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id in {f.id for f in forests}])
    settle(s)
    assert all(s.state.cards[f.id].zone.endswith(":exile") for f in forests)  # (701.61a: three cards from the graveyard)
    assert sum(s.state.players["p1"].mana.values()) == 2 and s.state.cards[c.id].tapped
    roundtrip(s)


def test_storage_land_adds_x_mana_in_any_combination(cards):
    s = build(cards, "Dreadship Reef")
    reef = on_field(s, "Dreadship Reef")
    act(s, "p1", type="set_counter", card_id=reef.id, kind="storage", value=3)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=reef.id, ability=ability(s, reef, "{1}, Remove"))
    d = s.state.rules.decision  # one option per number of counters, and per mix of {U} and {B}: 1: U, B; 2: UU, UB, BB; 3: …
    assert [o.label for o in d.options][:5] == ["{U}", "{B}", "{U}{U}", "{U}{B}", "{B}{B}"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["3"])
    assert s.state.players["p1"].mana == {"U": 1, "B": 1} and s.state.cards[reef.id].counters.get("storage", 0) == 1
    roundtrip(s)


def test_x_mana_of_any_one_color_and_x_plus_one(cards):
    s = build(cards, "Petalmane Baku", "Kyren Toy")
    baku = on_field(s, "Petalmane Baku")
    toy = on_field(s, "Kyren Toy")
    act(s, "p1", type="set_counter", card_id=baku.id, kind="ki", value=2)
    act(s, "p1", type="set_counter", card_id=toy.id, kind="charge", value=2)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=baku.id, ability=ability(s, baku, "{1}, Remove"))
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label == "{G}{G}"])
    assert s.state.players["p1"].mana == {"G": 2} and s.state.cards[baku.id].counters.get("ki", 0) == 0
    act(s, "p1", type="activate_ability", card_id=toy.id, ability=ability(s, toy, "{T}, Remove"))
    d = s.state.rules.decision  # 1 + X colorless: X = 0, 1 or 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label == "{C}{C}{C}"])
    assert s.state.players["p1"].mana == {"G": 2, "C": 3} and s.state.cards[toy.id].counters.get("charge", 0) == 0
    roundtrip(s)


def test_tap_x_untapped_tokens_for_x_mana(cards):
    s = build(cards, "Hazel of the Rootbloom")
    hazel = on_field(s, "Hazel of the Rootbloom")
    s.state.rules.controlled_since[hazel.id].turn = 0
    tokens = [creature(s, "p1", f"Squirrel {i}", pt="1/1") for i in range(3)]
    with pytest.raises(ActionError):  # (X isn't said)
        act(s, "p1", type="activate_ability", card_id=hazel.id, ability=0)
    act(s, "p1", type="activate_ability", card_id=hazel.id, ability=0, x_value=2)
    d = s.state.rules.decision  # which two tokens to tap
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[tokens[0].id, tokens[1].id])
    d = s.state.rules.decision  # the two mana: 15 mixes of five colors
    assert len(d.options) == 15
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0"])
    assert [s.state.cards[t.id].tapped for t in tokens] == [True, True, False]
    assert sum(s.state.players["p1"].mana.values()) == 2 and s.state.players["p1"].life == 38
    roundtrip(s)


def test_sacrifice_an_artifact_for_mana_equal_to_its_mana_value(cards):
    s = build(cards, "Priest of Yawgmoth", "Kyren Toy")
    priest = on_field(s, "Priest of Yawgmoth")
    s.state.rules.controlled_since[priest.id].turn = 0
    toy = on_field(s, "Kyren Toy")  # (mana value 3)
    act(s, "p1", type="activate_ability", card_id=priest.id, ability=0)
    settle(s)
    assert s.state.cards[toy.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {"B": 3}
    roundtrip(s)


def test_choose_a_color_of_a_permanent_you_control(cards):
    s = build(cards, "Meteor Crater", "Selvala, Eager Trailblazer")
    crater = on_field(s, "Meteor Crater")
    on_field(s, "Selvala, Eager Trailblazer")
    act(s, "p1", type="activate_ability", card_id=crater.id, ability=ability(s, crater, "{T}"))
    d = s.state.rules.decision
    assert sorted(o.label for o in d.options) == ["{G}", "{W}"]  # (Selvala's colors; a land has none)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "{G}")])
    assert s.state.players["p1"].mana == {"G": 1}
    roundtrip(s)


def test_one_mana_of_the_chosen_color_for_each_different_power(cards):
    s = build(cards, "Selvala, Eager Trailblazer")
    selvala = on_field(s, "Selvala, Eager Trailblazer")  # (power 4)
    s.state.rules.controlled_since[selvala.id].turn = 0
    creature(s, "p1", "Mouse", pt="1/1")
    creature(s, "p1", "Bear", pt="2/2")
    creature(s, "p1", "Other Bear", pt="2/3")  # (the same power as the Bear)
    act(s, "p1", type="activate_ability", card_id=selvala.id, ability=ability(s, selvala, "{T}"))
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "{G}{G}{G}")])
    assert s.state.players["p1"].mana == {"G": 3}  # (powers 4, 1 and 2)
    roundtrip(s)


def test_granted_flanking_shrinks_the_blocker(cards):
    s = build(cards, "Jabari's Banner")
    banner = on_field(s, "Jabari's Banner")
    knight = creature(s, "p1", "Knight", pt="2/2")
    s.state.rules.controlled_since[knight.id].turn = 0  # (not summoning sick: 302.6)
    guard = creature(s, "p2", "Guard", pt="2/2")
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=banner.id, ability=0, targets=[knight.id])
    settle(s)
    for _ in range(8):  # → combat
        if s.state.rules.decision is None and s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": knight.id, "target": "p2"}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": knight.id}])
    for _ in range(6):
        if s.state.rules.decision is None and s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
        if guard.id not in s.state.cards:
            break
    assert guard.id not in s.state.cards  # (a 1/1 after flanking: the Knight's 2 damage kills it)
    assert s.state.cards[knight.id].zone == "p1:battlefield"  # (a 2/2 Guard would have killed the 2/2 Knight too)
    roundtrip(s)


def test_target_creature_blocking_this_creature(cards):
    s = build(cards, "Godo's Irregulars", p2=("Grizzly Bears", "Grizzly Bears"))
    godo = on_field(s, "Godo's Irregulars")
    s.state.rules.controlled_since[godo.id].turn = 0
    bear, other = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in (bear, other):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    for _ in range(8):
        if s.state.rules.decision is None and s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="create_token", player="p1", token={"name": "Hill", "type_line": "Token Land — Mountain"})  # (R to pay with)
    act(s, "p1", type="set_prefs", stops_my_turn=["declare_blockers"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": godo.id, "target": "p2"}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": godo.id}])
    with pytest.raises(ActionError):  # (the other Bear isn't blocking it)
        act(s, "p1", type="activate_ability", card_id=godo.id, ability=0, targets=[other.id])
    act(s, "p1", type="activate_ability", card_id=godo.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].damage == 1 and s.state.cards[other.id].damage == 0
    roundtrip(s)


def test_destroy_each_artifact_creature_and_enchantment_with_mana_value_x_or_less(cards):
    s = build(cards, "Pernicious Deed", "Kyren Toy", "Priest of Yawgmoth", p2=("Grizzly Bears",))
    deed = on_field(s, "Pernicious Deed")
    toy = on_field(s, "Kyren Toy")  # (mana value 3)
    priest = on_field(s, "Priest of Yawgmoth")  # (2)
    bears = on_field(s, "Grizzly Bears", "p2")  # (2)
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=deed.id, ability=0, x_value=2)
    settle(s)
    zones = {c.name: s.state.cards[c.id].zone for c in (deed, toy, priest, bears)}
    assert zones == {"Pernicious Deed": "p1:graveyard", "Kyren Toy": "p1:battlefield", "Priest of Yawgmoth": "p1:graveyard",
                     "Grizzly Bears": "p2:graveyard"}
    roundtrip(s)


def test_destroy_each_artifact_with_mana_value_exactly_x(cards):
    s = build(cards, "Dauntless Dismantler", "Kyren Toy", "Pili-Pala")
    dismantler = on_field(s, "Dauntless Dismantler")
    toy = on_field(s, "Kyren Toy")  # (3)
    pili = on_field(s, "Pili-Pala")  # (2)
    mana(s, "p1", W=1, C=6)
    act(s, "p1", type="activate_ability", card_id=dismantler.id, ability=ability(s, dismantler, "{X}{X}{W}"), x_value=3)
    settle(s)
    assert s.state.cards[toy.id].zone == "p1:graveyard" and s.state.cards[pili.id].zone == "p1:battlefield"
    assert s.state.cards[dismantler.id].zone == "p1:graveyard"
    roundtrip(s)


def test_x_mana_in_any_combination_where_x_is_a_count(cards):
    s = build(cards, "Axebane Guardian", "Pili-Pala")
    guardian = on_field(s, "Axebane Guardian")
    s.state.rules.controlled_since[guardian.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=guardian.id, ability=ability(s, guardian, "{T}"))
    d = s.state.rules.decision  # X = 1 (only the Guardian has defender): one mana of any color
    assert sorted(o.label for o in d.options) == ["{B}", "{G}", "{R}", "{U}", "{W}"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "{R}")])
    assert s.state.players["p1"].mana == {"R": 1}
    roundtrip(s)


def test_x_mana_of_two_colors_where_x_is_power_once_each_turn(cards):
    s = build(cards, "Vivi Ornitier")
    vivi = on_field(s, "Vivi Ornitier")
    act(s, "p1", type="set_counter", card_id=vivi.id, kind="+1/+1", value=2)  # (power 2)
    act(s, "p1", type="activate_ability", card_id=vivi.id, ability=0)
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["{U}{U}", "{U}{R}", "{R}{R}"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["1"])
    assert s.state.players["p1"].mana == {"U": 1, "R": 1}
    with pytest.raises(ActionError):  # (once each turn)
        act(s, "p1", type="activate_ability", card_id=vivi.id, ability=0)
    roundtrip(s)


def test_mana_ability_only_during_an_opponents_turn(cards):
    s = build(cards, "Lavinia, Foil to Conspiracy")
    lavinia = on_field(s, "Lavinia, Foil to Conspiracy")
    s.state.rules.controlled_since[lavinia.id].turn = 0
    with pytest.raises(ActionError):  # (it's Alice's turn)
        act(s, "p1", type="activate_ability", card_id=lavinia.id, ability=ability(s, lavinia, "{T}"))


def waterbend_ruthless(cards, helpers, mana_c, pick):
    s = build(cards, "Ruthless Waterbender")
    c = on_field(s, "Ruthless Waterbender")
    tokens = [creature(s, "p1", f"Helper {i}", pt="1/1") for i in range(helpers)]
    if mana_c:
        mana(s, "p1", C=mana_c)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "Waterbend"))
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[tokens[i].id for i in pick])
    settle(s)
    return s, c, tokens


def test_waterbend_taps_artifacts_and_creatures_for_generic_mana(cards):
    s, c, tokens = waterbend_ruthless(cards, 2, 1, [0])  # {2}: one Helper taps, {1} of mana
    assert chars(s, c).pt == (2, 4) and s.state.players["p1"].mana == {}
    assert [s.state.cards[t.id].tapped for t in tokens] == [True, False]
    roundtrip(s)


def test_waterbend_paid_with_mana_alone(cards):
    s, c, tokens = waterbend_ruthless(cards, 1, 2, [])  # none tapped: {2} of mana
    assert chars(s, c).pt == (2, 4) and s.state.players["p1"].mana == {} and not s.state.cards[tokens[0].id].tapped
    roundtrip(s)


def test_waterbend_needs_all_of_the_cost_paid(cards):
    s = build(cards, "Ruthless Waterbender")
    c = on_field(s, "Ruthless Waterbender")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "Waterbend"))
    d = s.state.rules.decision  # (the only helper is the Waterbender itself)
    with pytest.raises(ActionError):  # ({1} of the cost is left and there's no mana for it)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[c.id])
    assert not s.state.cards[c.id].tapped


def test_waterbend_with_tap_symbol_cannot_tap_itself_to_help(cards):
    s = build(cards, "North Pole Patrol", p2=("Grizzly Bears",))
    patrol = on_field(s, "North Pole Patrol")
    s.state.rules.controlled_since[patrol.id].turn = 0
    bears = on_field(s, "Grizzly Bears", "p2")
    helpers = [creature(s, "p1", f"Helper {i}", pt="1/1") for i in range(3)]
    act(s, "p1", type="activate_ability", card_id=patrol.id, ability=ability(s, patrol, "Waterbend"), targets=[bears.id])
    d = s.state.rules.decision
    assert sorted(o.card_id for o in d.options) == sorted(h.id for h in helpers)  # (the Patrol itself taps for {T})
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[h.id for h in helpers])
    settle(s)
    assert s.state.cards[bears.id].tapped and s.state.cards[patrol.id].tapped
    assert all(s.state.cards[h.id].tapped for h in helpers)
    roundtrip(s)


def test_target_creature_with_mana_value_exactly_x(cards):
    """"Destroy target creature with mana value X." (Disembowel): the X announced with the spell (107.3f, 202.3e) is the mana value the
    target must have, read for a permanent as for a card in a graveyard."""
    s = build(cards, "Disembowel", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears", "p2")  # (mana value 2)
    spell = next(c for c in s.state.cards.values() if c.name == "Disembowel")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    mana(s, "p1", B=1, C=3)
    with pytest.raises(ActionError):  # (X = 3: the Bears' mana value is 2)
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    roundtrip(s)


def test_any_target_that_isnt_a_commander(cards):
    s = build(cards, "Lozhan, Dragons' Legacy", "Shivan Dragon", p2=("Grizzly Bears",))
    on_field(s, "Lozhan, Dragons' Legacy")
    bears = on_field(s, "Grizzly Bears", "p2")
    atraxa = on_field(s, "Atraxa, Praetors' Voice", "p2")  # (Bob's commander on the battlefield)
    spell = next(c for c in s.state.cards.values() if c.name == "Shivan Dragon")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    mana(s, "p1", R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = s.state.rules.decision  # Lozhan's trigger: damage equal to the spell's mana value (6)
    ids = {o.id for o in d.options}
    assert bears.id in ids and "p2" in ids and atraxa.id not in ids
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[atraxa.id].damage == 0
    roundtrip(s)
