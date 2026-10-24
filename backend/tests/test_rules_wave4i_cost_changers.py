"""Cost changers and alternative costs (wave 4I): app/rules/cost_changes.py, app/rules/alt_costs.py.

CR 601.2f: the total cost is the mana cost or one alternative cost (118.9, 118.9a), plus additional costs and cost
increases, minus cost reductions; it is locked in before it is paid. 118.7a-c: generic reductions touch only the
generic part, colored ones that color's symbols first. 602.2b: the same for activated abilities ("This ability costs
{1} less to activate for each legendary creature you control"). 107.3b: X is 0 for an alternative cost without X.
Real Commander cards' Oracle text; scenarios check replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import alt_costs, coverage, permissions
from app.rules.casting import activatable
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.oracle import parse_abilities
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import named
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, cost_of, find, put

EXTRA = [
    card('Force of Will', set_code='tst', number='4I00', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Instant', oracle_text="You may pay 1 life and exile a blue card from your hand rather than pay this spell's mana cost.\nCounter target spell.", colors=['U'], color_identity=['U'], keywords=[]),
    card('Snuff Out', set_code='tst', number='4I01', mana_cost='{3}{B}', cmc=4.0, type_line='Instant', oracle_text="If you control a Swamp, you may pay 4 life rather than pay this spell's mana cost.\nDestroy target nonblack creature. It can't be regenerated.", colors=['B'], color_identity=['B'], keywords=[]),
    card('Force of Negation', set_code='tst', number='4I02', mana_cost='{1}{U}{U}', cmc=3.0, type_line='Instant', oracle_text="If it's not your turn, you may exile a blue card from your hand rather than pay this spell's mana cost.\nCounter target noncreature spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.", colors=['U'], color_identity=['U'], keywords=[]),
    card('Daze', set_code='tst', number='4I03', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="You may return an Island you control to its owner's hand rather than pay this spell's mana cost.\nCounter target spell unless its controller pays {1}.", colors=['U'], color_identity=['U'], keywords=[]),
    card("Sephara, Sky's Blade", set_code='tst', number='4I04', mana_cost='{4}{W}{W}{W}', cmc=7.0, type_line='Legendary Creature — Angel', oracle_text='You may pay {W} and tap four untapped creatures you control with flying rather than pay this spell\'s mana cost.\nFlying, lifelink\nOther creatures you control with flying have indestructible. (Damage and effects that say "destroy" don\'t destroy them.)', colors=['W'], color_identity=['W'], keywords=['Flying', 'Lifelink'], power='7', toughness='7'),
    card('Jodah, Archmage Eternal', set_code='tst', number='4I05', mana_cost='{1}{U}{R}{W}', cmc=4.0, type_line='Legendary Creature — Human Wizard', oracle_text='Flying\nYou may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.', colors=['R', 'U', 'W'], color_identity=['B', 'G', 'R', 'U', 'W'], keywords=['Flying'], power='4', toughness='3'),
    card('Rooftop Storm', set_code='tst', number='4I06', mana_cost='{5}{U}', cmc=6.0, type_line='Enchantment', oracle_text='You may pay {0} rather than pay the mana cost for Zombie creature spells you cast.', colors=['U'], color_identity=['U'], keywords=[]),
    card('Darksteel Monolith', set_code='tst', number='4I07', mana_cost='{8}', cmc=8.0, type_line='Artifact', oracle_text='Indestructible\nOnce each turn, you may pay {0} rather than pay the mana cost for a colorless spell you cast from your hand.', colors=[], color_identity=[], keywords=['Indestructible']),
    card('Mindbreak Trap', set_code='tst', number='4I08', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Instant — Trap', oracle_text="If an opponent cast three or more spells this turn, you may pay {0} rather than pay this spell's mana cost.\nExile any number of target spells.", colors=['U'], color_identity=['U'], keywords=[]),
    card('Ghalta, Primal Hunger', set_code='tst', number='4I09', mana_cost='{10}{G}{G}', cmc=12.0, type_line='Legendary Creature — Elder Dinosaur', oracle_text="This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)", colors=['G'], color_identity=['G'], keywords=['Trample'], power='12', toughness='12'),
    card('Metalwork Colossus', set_code='tst', number='4I10', mana_cost='{11}', cmc=11.0, type_line='Artifact Creature — Construct', oracle_text='This spell costs {X} less to cast, where X is the total mana value of noncreature artifacts you control.\nSacrifice two artifacts: Return this card from your graveyard to your hand.', colors=[], color_identity=[], keywords=[], power='10', toughness='10'),
    card('Blasphemous Act', set_code='tst', number='4I11', mana_cost='{8}{R}', cmc=9.0, type_line='Sorcery', oracle_text='This spell costs {1} less to cast for each creature on the battlefield.\nBlasphemous Act deals 13 damage to each creature.', colors=['R'], color_identity=['R'], keywords=[]),
    card('Khalni Hydra', set_code='tst', number='4I12', mana_cost='{G}{G}{G}{G}{G}{G}{G}{G}', cmc=8.0, type_line='Creature — Hydra', oracle_text='This spell costs {G} less to cast for each green creature you control.\nTrample', colors=['G'], color_identity=['G'], keywords=['Trample'], power='8', toughness='8'),
    card("Urza's Incubator", set_code='tst', number='4I13', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='As this artifact enters, choose a creature type.\nCreature spells of the chosen type cost {2} less to cast.', colors=[], color_identity=[], keywords=[]),
    card('Defense Grid', set_code='tst', number='4I14', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text="Each spell costs {3} more to cast except during its controller's turn.", colors=[], color_identity=[], keywords=[]),
    card('Animar, Soul of Elements', set_code='tst', number='4I15', mana_cost='{G}{U}{R}', cmc=3.0, type_line='Legendary Creature — Elemental', oracle_text='Protection from white and from black\nWhenever you cast a creature spell, put a +1/+1 counter on Animar.\nCreature spells you cast cost {1} less to cast for each +1/+1 counter on Animar.', colors=['G', 'R', 'U'], color_identity=['G', 'R', 'U'], keywords=['Protection'], power='1', toughness='1'),
    card('Alabaster Leech', set_code='tst', number='4I16', mana_cost='{W}', cmc=1.0, type_line='Creature — Leech', oracle_text='White spells you cast cost {W} more to cast.', colors=['W'], color_identity=['W'], keywords=[], power='1', toughness='3'),
    card('Geyser Drake', set_code='tst', number='4I17', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Drake', oracle_text='Flying\nDuring turns other than yours, spells you cast cost {1} less to cast.', colors=['U'], color_identity=['U'], keywords=['Flying'], power='2', toughness='3'),
    card('Gravebreaker Lamia', set_code='tst', number='4I18', mana_cost='{4}{B}', cmc=5.0, type_line='Enchantment Creature — Snake Lamia', oracle_text='Lifelink\nWhen this creature enters, search your library for a card, put it into your graveyard, then shuffle.\nSpells you cast from your graveyard cost {1} less to cast.', colors=['B'], color_identity=['B'], keywords=['Lifelink'], power='4', toughness='4'),
    card('Otawara, Soaring City', set_code='tst', number='4I19', mana_cost='', cmc=0.0, type_line='Legendary Land', oracle_text="{T}: Add {U}.\nChannel — {3}{U}, Discard this card: Return target artifact, creature, enchantment, or planeswalker to its owner's hand. This ability costs {1} less to activate for each legendary creature you control.", colors=[], color_identity=['U'], keywords=['Channel']),
    card('Voldaren Estate', set_code='tst', number='4I20', mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}, Pay 1 life: Add one mana of any color. Spend this mana only to cast a Vampire spell.\n{5}, {T}: Create a Blood token. This ability costs {1} less to activate for each Vampire you control. (It\'s an artifact with "{1}, {T}, Discard a card, Sacrifice this token: Draw a card.")', colors=[], color_identity=[], keywords=[]),
    card("Hylda's Crown of Winter", set_code='tst', number='4I21', mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact', oracle_text="{1}, {T}: Tap target creature. This ability costs {1} less to activate during your turn.\n{3}, Sacrifice Hylda's Crown of Winter: Draw a card for each tapped creature your opponents control.", colors=[], color_identity=[], keywords=[]),
    card("Loreseeker's Stone", set_code='tst', number='4I22', mana_cost='{6}', cmc=6.0, type_line='Artifact', oracle_text='{3}, {T}: Draw three cards. This ability costs {1} more to activate for each card in your hand.', colors=[], color_identity=[], keywords=[]),
    card('Vadrik, Astral Archmage', set_code='tst', number='4I23', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Legendary Creature — Human Wizard', oracle_text="If it's neither day nor night, it becomes day as Vadrik enters.\nInstant and sorcery spells you cast cost {X} less to cast, where X is Vadrik's power.\nWhenever day becomes night or night becomes day, put a +1/+1 counter on Vadrik.", colors=['R', 'U'], color_identity=['R', 'U'], keywords=[], power='1', toughness='2'),
    card('Bringer of the Black Dawn', set_code='tst', number='4I24', mana_cost='{7}{B}{B}', cmc=9.0, type_line='Creature — Bringer', oracle_text="You may pay {W}{U}{B}{R}{G} rather than pay this spell's mana cost.\nTrample\nAt the beginning of your upkeep, you may pay 2 life. If you do, search your library for a card, then shuffle and put that card on top.", colors=['B'], color_identity=['B', 'G', 'R', 'U', 'W'], keywords=['Trample'], power='5', toughness='5'),
    card('Disrupting Shoal', set_code='tst', number='4I25', mana_cost='{X}{U}{U}', cmc=2.0, type_line='Instant — Arcane', oracle_text="You may exile a blue card with mana value X from your hand rather than pay this spell's mana cost.\nCounter target spell if its mana value is X.", colors=['U'], color_identity=['U'], keywords=[]),
    card("Ertai's Scorn", set_code='tst', number='4I26', mana_cost='{1}{U}{U}', cmc=3.0, type_line='Instant', oracle_text='This spell costs {U} less to cast if an opponent cast two or more spells this turn.\nCounter target spell.', colors=['U'], color_identity=['U'], keywords=[]),
    card("Herald's Horn", set_code='tst', number='4I27', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="As this artifact enters, choose a creature type.\nCreature spells you cast of the chosen type cost {1} less to cast.\nAt the beginning of your upkeep, look at the top card of your library. If it's a creature card of the chosen type, you may reveal it and put it into your hand.", colors=[], color_identity=[], keywords=[]),
    card('Tolarian Terror', set_code='tst', number='4I28', mana_cost='{6}{U}', cmc=7.0, type_line='Creature — Serpent', oracle_text='This spell costs {1} less to cast for each instant and sorcery card in your graveyard.\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)', colors=['U'], color_identity=['U'], keywords=['Ward'], power='5', toughness='5'),
    card('Shadow in the Warp', set_code='tst', number='4J00', mana_cost='{1}{R}{G}', cmc=3.0, type_line='Enchantment', oracle_text='The first creature spell you cast each turn costs {2} less to cast.\nWhenever an opponent casts their first noncreature spell each turn, this enchantment deals 2 damage to that player.', colors=['G', 'R'], color_identity=['G', 'R'], keywords=[]),
    card('Raging Battle Mouse', set_code='tst', number='4J01', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Mouse', oracle_text='The second spell you cast each turn costs {1} less to cast.\nCelebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, target creature you control gets +1/+1 until end of turn.', colors=['R'], color_identity=['R'], keywords=['Celebration'], power='2', toughness='1'),
    card('Warden of Evos Isle', set_code='tst', number='4J02', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Bird Wizard', oracle_text='Flying\nCreature spells with flying you cast cost {1} less to cast.', colors=['U'], color_identity=['U'], keywords=['Flying'], power='2', toughness='2'),
    card('Avatar of Fury', set_code='tst', number='4J03', mana_cost='{6}{R}{R}', cmc=8.0, type_line='Creature — Avatar', oracle_text='If an opponent controls seven or more lands, this spell costs {6} less to cast.\nFlying\n{R}: This creature gets +1/+0 until end of turn.', colors=['R'], color_identity=['R'], keywords=['Flying'], power='6', toughness='6'),
    card('Charix, the Raging Isle', set_code='tst', number='4J04', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Legendary Creature — Leviathan Crab', oracle_text='Spells your opponents cast that target Charix cost {2} more to cast.\n{3}: Charix gets +X/-X until end of turn, where X is the number of Islands you control.', colors=['U'], color_identity=['U'], keywords=[], power='0', toughness='17'),
    card('Killian, Ink Duelist', set_code='tst', number='4J05', mana_cost='{W}{B}', cmc=2.0, type_line='Legendary Creature — Human Warlock', oracle_text="Lifelink\nMenace (This creature can't be blocked except by two or more creatures.)\nSpells you cast that target a creature cost {2} less to cast.", colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Lifelink', 'Menace'], power='2', toughness='2'),
    card('Gloom', set_code='tst', number='4J10', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment', oracle_text='White spells cost {3} more to cast.\nActivated abilities of white enchantments cost {3} more to activate.', colors=['B'], color_identity=['B'], keywords=[]),
    card('Stalwart Valkyrie', set_code='tst', number='4J11', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Angel Warrior', oracle_text="You may pay {1}{W} and exile a creature card from your graveyard rather than pay this spell's mana cost.\nFlying", colors=['W'], color_identity=['W'], keywords=['Flying'], power='3', toughness='2'),
    card('Defiler of Vigor', set_code='tst', number='4J12', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Phyrexian Wurm', oracle_text='Trample\nAs an additional cost to cast green permanent spells, you may pay 2 life. Those spells cost {G} less to cast if you paid life this way. This effect reduces only the amount of green mana you pay.\nWhenever you cast a green permanent spell, put a +1/+1 counter on each creature you control.', colors=['G'], color_identity=['G'], keywords=['Trample'], power='6', toughness='6'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def tok(s, name, pt="2/2", pid="p1", type_line="Token Creature — Test", text="", colors=()):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t,
                                                         "text": text, "colors": list(colors)})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def roundtrip(s):
    """Replay rebuilds the same table, and a save/load round trip keeps it."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def ok(text, name="Card", type_line="Creature — Test"):
    """Is every ability line automated (coverage) on a card with that name and type?"""
    sup, types, sub = parse_type_line(type_line)
    spell = bool({"Instant", "Sorcery"} & types)
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=tuple(parse_abilities(text, spell=spell))))
    return all(f.supported for f in feats if f.id.startswith(("text:", "mana:")))


def life(s, pid="p1"):
    return s.state.players[pid].life


def decision(s):
    return s.state.rules.decision


def alt_key(s, c, pid="p1"):
    """The alternative cost the hints offer for this card (exactly one)."""
    found = hints(s.state, pid, s.cards).get("alt_castable", {}).get(c.id)
    assert found and len(found) == 1, found
    return found[0]["id"]


def refused(s, match, pid="p1", **payload):
    """Refused, and the table is exactly as it was (118.3, 601.2h)."""
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=match):
        act(s, pid, **payload)
    assert s.state.model_dump(mode="json") == before


def opponents_main(s):
    """Play on to Bob's first main phase, Bob holding priority there. Alice takes full control (she gets priority
    whenever Bob passes it, never auto-passed over)."""
    act(s, "p1", type="set_prefs", full_control=True)
    act(s, "p1", type="pass_priority")
    for _ in range(80):
        if s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.priority == "p2":
            break
        d = decision(s)
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    assert s.state.turn.active_player == "p2" and s.state.rules.priority == "p2"


def bob_casts(s, *names, target="p1"):
    """Bob casts these (one red mana each) holding priority, then passes it to Alice."""
    act(s, "p2", type="set_prefs", hold_priority=True)
    found = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.zone in ("p2:library", "p2:hand"))
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, "p2", R=1)
        act(s, "p2", type="cast_spell", card_id=c.id, targets=[target])
        found.append(s.state.cards[c.id])
    act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1"
    return found


# -- the grammar --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", [c["name"] for c in EXTRA if c["name"] not in ("Disrupting Shoal", "Herald's Horn")])
def test_the_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert ok(c["oracle_text"], name, c["type_line"]), name


@pytest.mark.parametrize("text", [
    # a cost the alternative-cost grammar can't pay, or a condition it doesn't read: refused, never guessed
    # ("You may collect evidence 10 …" and Kentaro's "You may pay {X} … where X is that spell's mana value." are read since wave 100I:
    # tests/test_rules_wave100i_activated.py)
    # ("For each {B} in a cost, you may pay 2 life …" is read now, wave 18B: K'rrik)
    # (Bruenor's "{0} rather than the equip cost of the first equip ability … each of your turns" is read since wave 48D)
    # cost changers that read something this grammar doesn't (targets, the first spell each turn, chosen names)
    # ("Spells you cast that target enchanted player cost {1} less to cast." is read since wave 53C: Infectious Curse, tests/test_rules_wave53c_block_events.py)
    "Spells with the chosen name cost {3} more to cast.",
])
def test_wordings_still_refused(text):
    assert permissions.define_static(text[0].lower() + text[1:], "static") is None
    assert permissions.define_static(text[0].lower() + text[1:], "spell") is None


@pytest.mark.parametrize("text", [
    "You may exile a blue card with mana value X from your hand rather than pay this spell's mana cost.",
    "You may discard an Island card and another card rather than pay this spell's mana cost.",
    "If you control a Forest, rather than pay this spell's mana cost, you may have each other player gain 5 life.",
])
def test_alternative_cost_wordings_now_have_native_definitions(text):
    definition = permissions.define_static(text[0].lower() + text[1:], "spell")
    assert definition is not None and definition["static"] == "alt_cost"
    assert alt_costs.parse_cost(definition["cost"]) is not None


def test_chosen_type_needs_the_enters_choice_line():
    line = "creature spells of the chosen type cost {2} less to cast"
    assert permissions.define_static(line, "static", ("As ~ enters, choose a creature type.",)) is not None
    # (a card type or a name chosen some other way isn't the creature type the engine records: refused)
    assert permissions.define_static(line, "static", ("As ~ enters, choose a card type.",)) is None


def test_target_qualified_activation_discount_is_supported():
    text = "{2}, {T}: Tap target creature. This ability costs {1} less to activate if it targets a creature with power 3 or less."
    assert ok(text, "Raft Security Officer", "Artifact Creature — Robot")


# -- alternative costs (118.9) ----------------------------------------------------------------------------------------
def bolt_on_the_stack(s):
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    return bolt


def test_force_of_will_exiles_a_blue_card_and_pays_a_life(cards):
    s = build(cards, [(1, "Force of Will"), (1, "Counterspell"), (1, "Daze"), (1, "Lightning Bolt"), (5, "Island")])
    fow, counter, daze = put(s, "Force of Will", "hand"), put(s, "Counterspell", "hand"), put(s, "Daze", "hand")
    bolt = bolt_on_the_stack(s)
    key = alt_key(s, fow)
    assert key == f"{fow.id}:0"
    act(s, "p1", type="cast_spell", card_id=fow.id, targets=[bolt.id], alt_cost=key)
    d = decision(s)  # which blue card: a private choice (the other cards in the hand are hidden)
    assert d.player == "p1" and {o.id for o in d.options} == {counter.id, daze.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    assert s.state.cards[fow.id].zone == "p1:hand" and life(s) == 40  # nothing paid yet (601.2h)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[counter.id])
    assert s.state.cards[counter.id].zone == "p1:exile" and life(s) == 39  # public in exile; 1 life paid
    assert s.state.cards[daze.id].zone == "p1:hand"
    record = s.state.rules.payments[s.state.rules.object_id(fow.id)]
    assert record.alternative == "alternative" and record.life == 1 and record.exiled == [counter.id]
    act(s, "p1", type="set_prefs", hold_priority=False)
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and life(s, "p2") == 40  # countered
    roundtrip(s)


def test_force_of_will_cant_exile_itself_and_cancel_pays_nothing(cards):
    s = build(cards, [(1, "Force of Will"), (1, "Counterspell"), (1, "Lightning Bolt"), (5, "Island")])
    fow = put(s, "Force of Will", "hand")
    bolt = bolt_on_the_stack(s)
    assert fow.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})  # no other blue card
    refused(s, "can't pay", type="cast_spell", card_id=fow.id, targets=[bolt.id], alt_cost=f"{fow.id}:0")
    counter, other = put(s, "Counterspell", "hand"), put(s, "Island", "hand")
    assert alt_key(s, fow) == f"{fow.id}:0"
    act(s, "p1", type="cast_spell", card_id=fow.id, targets=[bolt.id], alt_cost=f"{fow.id}:0")
    assert decision(s) is None  # one blue card only: it's taken without asking
    assert s.state.cards[counter.id].zone == "p1:exile"
    assert s.state.cards[other.id].zone == "p1:hand"


def test_snuff_out_needs_a_swamp(cards):
    s = build(cards, [(1, "Snuff Out"), (2, "Swamp")])
    snuff = put(s, "Snuff Out", "hand")
    victim = tok(s, "Victim", pid="p2")
    assert snuff.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})
    refused(s, "alternative cost", type="cast_spell", card_id=snuff.id, targets=[victim.id], alt_cost=f"{snuff.id}:0")
    put(s, "Swamp", "battlefield")
    act(s, "p1", type="cast_spell", card_id=snuff.id, targets=[victim.id], alt_cost=alt_key(s, snuff))
    pass_until_stack_empty(s)
    assert victim.id not in s.state.cards and life(s) == 36
    roundtrip(s)


def test_force_of_negation_only_on_another_players_turn_and_defense_grid_adds_three(cards):
    s = build(cards, [(1, "Force of Negation"), (1, "Counterspell"), (5, "Island")],
              [(1, "Defense Grid"), (1, "Lightning Bolt"), (8, "Mountain")])
    fon, counter = put(s, "Force of Negation", "hand"), put(s, "Counterspell", "hand")
    assert fon.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})  # it's Alice's turn
    act(s, "p2", type="move", card_ids=[find(s, "Defense Grid", "p2").id], to={"zone": "battlefield"})
    opponents_main(s)
    # Bob casts a noncreature spell on his turn; Alice answers for the alternative cost, plus Defense Grid's {3} (118.9d)
    (bolt,) = bob_casts(s, "Lightning Bolt")
    assert hints(s.state, "p1", s.cards).get("alt_castable", {}).get(fon.id) is None  # {3} more, no mana yet
    refused(s, "ana|pay", type="cast_spell", card_id=fon.id, targets=[bolt.id], alt_cost=f"{fon.id}:0",
            cost_choices=[{"component": 0, "cards": [counter.id]}])
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=fon.id, targets=[bolt.id], alt_cost=alt_key(s, fon))
    assert s.state.cards[counter.id].zone == "p1:exile" and s.state.players["p1"].mana == {}
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p2:exile" and life(s) == 40
    roundtrip(s)


def test_daze_returns_an_island(cards):
    s = build(cards, [(1, "Daze"), (1, "Lightning Bolt"), (5, "Island")])
    daze = put(s, "Daze", "hand")
    island = put(s, "Island", "battlefield")
    bolt = bolt_on_the_stack(s)
    act(s, "p1", type="cast_spell", card_id=daze.id, targets=[bolt.id], alt_cost=alt_key(s, daze))
    assert s.state.cards[island.id].zone == "p1:hand" and s.state.cards[daze.id].zone == "stack"
    roundtrip(s)


def test_sephara_taps_four_fliers(cards):
    s = build(cards, [(1, "Sephara, Sky's Blade")])
    sephara = put(s, "Sephara, Sky's Blade", "hand")
    birds = [tok(s, f"Bird {i}", "1/1", text="Flying") for i in range(4)]
    tok(s, "Bear", "2/2")
    mana(s, W=1)
    key = alt_key(s, sephara)
    act(s, "p1", type="cast_spell", card_id=sephara.id, alt_cost=key)
    pass_until_stack_empty(s)
    assert all(s.state.cards[b.id].tapped for b in birds) and not named(s, "Bear").tapped
    assert s.state.cards[sephara.id].zone == "p1:battlefield"
    roundtrip(s)


def test_one_alternative_cost_only(cards):
    s = build(cards, [(1, "Bringer of the Black Dawn"), (1, "Jodah, Archmage Eternal"), (5, "Swamp")])
    bringer = put(s, "Bringer of the Black Dawn", "hand")
    put(s, "Jodah, Archmage Eternal", "battlefield")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    offers = hints(s.state, "p1", s.cards)["alt_castable"][bringer.id]
    assert len(offers) == 2  # its own and Jodah's: the player picks one (118.9a)
    refused(s, "Only one alternative cost", type="cast_spell", card_id=bringer.id, alt_cost=offers[0]["id"], face_down=True)
    refused(s, "Only one alternative cost", type="cast_spell", card_id=bringer.id, alt_cost=offers[0]["id"], free=True)
    act(s, "p1", type="cast_spell", card_id=bringer.id, alt_cost=offers[1]["id"])
    pass_until_stack_empty(s)
    assert s.state.cards[bringer.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_jodah_alternative_cost_makes_x_zero(cards):
    s = build(cards, [(1, "Endless One"), (1, "Jodah, Archmage Eternal")])
    one = put(s, "Endless One", "hand")
    jodah = put(s, "Jodah, Archmage Eternal", "battlefield")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    refused(s, "107.3b", type="cast_spell", card_id=one.id, alt_cost=f"{jodah.id}:1", x_value=3)
    act(s, "p1", type="cast_spell", card_id=one.id, alt_cost=f"{jodah.id}:1")
    pass_until_stack_empty(s)
    assert s.state.cards[one.id].zone == "p1:graveyard"  # entered with no counters: a 0/0 (704.5f)
    roundtrip(s)


def test_rooftop_storm_only_for_zombie_creature_spells(cards):
    s = build(cards, [(1, "Rooftop Storm"), (1, "Dregscape Zombie"), (1, "Grizzly Bears")])
    put(s, "Rooftop Storm", "battlefield")
    zombie, bears = put(s, "Dregscape Zombie", "hand"), put(s, "Grizzly Bears", "hand")
    found = hints(s.state, "p1", s.cards).get("alt_castable", {})
    assert zombie.id in found and bears.id not in found
    act(s, "p1", type="cast_spell", card_id=zombie.id, alt_cost=found[zombie.id][0]["id"])
    pass_until_stack_empty(s)
    assert s.state.cards[zombie.id].zone == "p1:battlefield"
    roundtrip(s)


def test_darksteel_monolith_once_each_turn_from_the_hand(cards):
    s = build(cards, [(1, "Darksteel Monolith"), (2, "Sol Ring")])
    monolith = put(s, "Darksteel Monolith", "battlefield")
    ring = put(s, "Sol Ring", "hand")
    key = alt_key(s, ring)
    assert key == f"{monolith.id}:1"
    act(s, "p1", type="cast_spell", card_id=ring.id, alt_cost=key)
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    second = next(c for c in s.state.cards.values() if c.name == "Sol Ring" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    assert second.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})  # used this turn
    refused(s, "alternative cost", type="cast_spell", card_id=second.id, alt_cost=key)
    roundtrip(s)


def test_mindbreak_trap_after_three_spells(cards):
    s = build(cards, [(1, "Mindbreak Trap")], [(3, "Lightning Bolt"), (5, "Mountain")])
    trap = put(s, "Mindbreak Trap", "hand")
    assert trap.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})
    opponents_main(s)
    bolts = bob_casts(s, "Lightning Bolt", "Lightning Bolt", "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=trap.id, targets=[b.id for b in bolts], target_counts=[3],
        alt_cost=alt_key(s, trap))
    pass_until_stack_empty(s)
    assert all(s.state.cards[b.id].zone == "p2:exile" for b in bolts) and life(s) == 40
    roundtrip(s)


# -- the spell's own reductions (601.2f, 118.7) ----------------------------------------------------------------------
def test_ghalta_costs_less_by_total_power(cards):
    s = build(cards, [(1, "Ghalta, Primal Hunger")])
    ghalta = put(s, "Ghalta, Primal Hunger", "hand")
    assert cost_of(s, ghalta, s.cards) == "{10}{G}{G}"
    tok(s, "Big", "5/5"), tok(s, "Small", "2/2"), tok(s, "Theirs", "9/9", pid="p2")
    assert cost_of(s, ghalta, s.cards) == "{3}{G}{G}"
    tok(s, "Huge", "20/20")
    assert cost_of(s, ghalta, s.cards) == "{G}{G}"  # never below the colored part (118.7a)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=ghalta.id)
    pass_until_stack_empty(s)
    assert s.state.cards[ghalta.id].zone == "p1:battlefield"
    roundtrip(s)


def test_khalni_hydra_reduces_green_mana(cards):
    s = build(cards, [(1, "Khalni Hydra")])
    hydra = put(s, "Khalni Hydra", "hand")
    for i in range(3):
        tok(s, f"Elf {i}", "1/1", colors=["G"])
    tok(s, "Gray", "1/1")
    assert cost_of(s, hydra, s.cards) == "{G}{G}{G}{G}{G}"


def test_118_7c_colored_reduction_past_the_colored_part_reduces_generic():
    from app.rules import mana as M
    from app.rules.cost_changes import reduce_colored

    assert reduce_colored(M.parse_cost("{1}{U}{U}"), ("U",)).text() == "{1}{U}"
    assert reduce_colored(M.parse_cost("{2}{R}"), ("U", "U")).text() == "{R}"  # 118.7b/c
    assert reduce_colored(M.parse_cost("{G}"), ("G", "G")).text() == "{0}"


def test_blasphemous_act_counts_every_creature_and_the_total_is_locked_in(cards):
    s = build(cards, [(1, "Blasphemous Act")])
    s.state.rules.prefs_for("p1").payment = "self"  # Alice taps her own mana
    act_ = put(s, "Blasphemous Act", "hand")
    for i in range(3):
        tok(s, f"Mine {i}", "1/1")
        tok(s, f"Theirs {i}", "1/1", pid="p2")
    altar = tok(s, "Kobold", "0/1", text="Sacrifice this creature: Add {R}.")
    assert cost_of(s, act_, s.cards) == "{1}{R}"  # 9 − 7 creatures
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=act_.id)
    d = decision(s)
    assert d.display["kind"] == "tap_mana" and d.display["cost"] == "{1}{R}"
    # the Kobold is sacrificed for mana while paying: the total cost was locked in (601.2f), so {1}{R} it stays
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0)
    assert s.state.cards[act_.id].zone != "p1:hand" and s.state.players["p1"].mana == {}
    assert decision(s) is None or decision(s).display is None  # (no prompt for a {2}{R} recomputed after the sacrifice)
    pass_until_stack_empty(s)
    assert not [c for c in s.state.cards.values() if c.name.startswith(("Mine", "Theirs"))]
    roundtrip(s)


def test_tolarian_terror_counts_the_graveyard(cards):
    s = build(cards, [(1, "Tolarian Terror"), (2, "Lightning Bolt"), (1, "Counterspell")])
    terror = put(s, "Tolarian Terror", "hand")
    put(s, "Lightning Bolt", "graveyard"), put(s, "Counterspell", "graveyard")
    assert cost_of(s, terror, s.cards) == "{4}{U}"


def test_ertais_scorn_takes_a_blue(cards):
    s = build(cards, [(1, "Ertai's Scorn")], [(2, "Lightning Bolt"), (5, "Mountain")])
    scorn = put(s, "Ertai's Scorn", "hand")
    assert cost_of(s, scorn, s.cards) == "{1}{U}{U}"
    opponents_main(s)
    bob_casts(s, "Lightning Bolt", "Lightning Bolt")
    assert cost_of(s, scorn, s.cards) == "{1}{U}"


# -- the table's cost changers ----------------------------------------------------------------------------------------
def test_urzas_incubator_reads_the_chosen_type(cards):
    s = build(cards, [(1, "Urza's Incubator"), (1, "Elvish Visionary"), (1, "Grizzly Bears")])
    incubator = put(s, "Urza's Incubator", "hand")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=incubator.id)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Elf" or o.id == "Elf")])
    pass_until_stack_empty(s)
    assert s.state.cards[incubator.id].zone == "p1:battlefield"
    elf, bears = put(s, "Elvish Visionary", "hand"), put(s, "Grizzly Bears", "hand")
    assert cost_of(s, elf, s.cards) == "{G}" and cost_of(s, bears, s.cards) == "{1}{G}"
    roundtrip(s)


def test_defense_grid_only_off_turn(cards):
    s = build(cards, [(1, "Lightning Bolt"), (1, "Defense Grid")])
    put(s, "Defense Grid", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    assert cost_of(s, bolt, s.cards) == "{R}"  # Alice's own turn
    opponents_main(s)
    assert cost_of(s, bolt, s.cards) == "{3}{R}"


def test_geyser_drake_on_other_turns(cards):
    s = build(cards, [(1, "Geyser Drake"), (1, "Counterspell")])
    put(s, "Geyser Drake", "battlefield")
    counter = put(s, "Counterspell", "hand")
    assert cost_of(s, counter, s.cards) == "{U}{U}"
    s2 = build(cards, [(1, "Geyser Drake"), (1, "Mana Leak")])
    put(s2, "Geyser Drake", "battlefield")
    leak = put(s2, "Mana Leak", "hand")
    assert cost_of(s2, leak, s2.cards) == "{1}{U}"
    opponents_main(s2)
    assert cost_of(s2, leak, s2.cards) == "{U}"


def test_animar_counts_its_counters(cards):
    s = build(cards, [(1, "Animar, Soul of Elements"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    animar = put(s, "Animar, Soul of Elements", "battlefield")
    bears, bolt = put(s, "Grizzly Bears", "hand"), put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="counter", card_ids=[animar.id], kind="+1/+1", delta=2)
    assert cost_of(s, bears, s.cards) == "{G}" and cost_of(s, bolt, s.cards) == "{R}"


def test_alabaster_leech_adds_white(cards):
    s = build(cards, [(1, "Alabaster Leech"), (1, "Swords to Plowshares"), (1, "Lightning Bolt")])
    put(s, "Alabaster Leech", "battlefield")
    swords, bolt = put(s, "Swords to Plowshares", "hand"), put(s, "Lightning Bolt", "hand")
    assert cost_of(s, swords, s.cards) == "{W}{W}" and cost_of(s, bolt, s.cards) == "{R}"
    assert cost_of(s, swords, s.cards, pid="p2") == "{W}"  # "spells you cast": Bob's aren't


def test_gravebreaker_lamia_from_your_graveyard(cards):
    s = build(cards, [(1, "Gravebreaker Lamia"), (1, "Firebolt"), (1, "Grizzly Bears")])
    put(s, "Gravebreaker Lamia", "battlefield")
    firebolt = put(s, "Firebolt", "graveyard")  # flashback {4}{R}
    bears = put(s, "Grizzly Bears", "hand")
    assert cost_of(s, firebolt, s.cards) == "{3}{R}" and cost_of(s, bears, s.cards) == "{1}{G}"


def test_vadrik_reduces_by_its_power(cards):
    s = build(cards, [(1, "Vadrik, Astral Archmage"), (1, "Treasure Cruise")])
    vadrik = put(s, "Vadrik, Astral Archmage", "battlefield")
    cruise = put(s, "Treasure Cruise", "hand")
    assert cost_of(s, cruise, s.cards) == "{6}{U}"  # Vadrik is a 1/2: {1} less
    act(s, "p1", type="counter", card_ids=[vadrik.id], kind="+1/+1", delta=3)
    assert cost_of(s, cruise, s.cards) == "{3}{U}"


# -- activated abilities: "This ability costs {1} less to activate …" (602.2b) -----------------------------------------
def test_otawara_channel_costs_less_per_legend(cards):
    s = build(cards, [(1, "Otawara, Soaring City"), (1, "Jodah, Archmage Eternal")])
    otawara = put(s, "Otawara, Soaring City", "hand")
    put(s, "Jodah, Archmage Eternal", "battlefield")
    tok(s, "Legend", "1/1", type_line="Token Legendary Creature — Test")
    victim = tok(s, "Victim", pid="p2")
    mana(s, C=1, U=1)  # {3}{U} − 2 legendary creatures
    assert {"card_id": otawara.id, "ability": 1} in activatable(s.state, "p1", s.cards)
    act(s, "p1", type="activate_ability", card_id=otawara.id, ability=1, targets=[victim.id])
    assert s.state.cards[otawara.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {}
    pass_until_stack_empty(s)
    assert victim.id not in s.state.cards  # a token returned to a hand ceases to exist
    roundtrip(s)


def test_voldaren_estate_never_below_zero(cards):
    s = build(cards, [(1, "Voldaren Estate")])
    estate = put(s, "Voldaren Estate", "battlefield")
    for i in range(6):
        tok(s, f"Vampire {i}", "1/1", type_line="Token Creature — Vampire")
    act(s, "p1", type="activate_ability", card_id=estate.id, ability=2)
    pass_until_stack_empty(s)
    assert named(s, "Blood") is not None and s.state.cards[estate.id].tapped
    roundtrip(s)


def test_hyldas_crown_costs_less_during_your_turn(cards):
    s = build(cards, [(1, "Hylda's Crown of Winter")])
    crown = put(s, "Hylda's Crown of Winter", "battlefield")
    victim = tok(s, "Victim", pid="p2")
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=0, targets=[victim.id])  # {0} on Alice's turn
    pass_until_stack_empty(s)
    assert s.state.cards[victim.id].tapped
    roundtrip(s)


def test_loreseekers_stone_costs_more_per_card_in_hand(cards):
    s = build(cards, [(1, "Loreseeker's Stone"), (2, "Island")])
    stone = put(s, "Loreseeker's Stone", "battlefield")
    hand = len(s.state.zones["p1:hand"])
    mana(s, C=3 + hand - 1)
    refused(s, "mana", type="activate_ability", card_id=stone.id, ability=0)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=stone.id, ability=0)
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


def test_flashback_is_already_an_alternative_cost(cards):
    s = build(cards, [(1, "Firebolt"), (1, "Jodah, Archmage Eternal")])
    jodah = put(s, "Jodah, Archmage Eternal", "battlefield")
    firebolt = put(s, "Firebolt", "graveyard")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    assert firebolt.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})
    refused(s, "Only one alternative cost", type="cast_spell", card_id=firebolt.id, targets=["p2"], alt_cost=f"{jodah.id}:1")


# -- the first / second spell each turn, "with flying", "If …, this spell costs …", spells that target ----------------
def test_shadow_in_the_warp_first_creature_spell_only(cards):
    s = build(cards, [(1, "Shadow in the Warp"), (1, "Grizzly Bears"), (1, "Elvish Visionary"), (1, "Lightning Bolt")])
    put(s, "Shadow in the Warp", "battlefield")
    bears, elf, bolt = put(s, "Grizzly Bears", "hand"), put(s, "Elvish Visionary", "hand"), put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # a noncreature spell first: doesn't count
    pass_until_stack_empty(s)
    assert cost_of(s, bears, s.cards) == "{G}"  # {1}{G} − 2, never below the colored part
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert cost_of(s, elf, s.cards) == "{1}{G}"  # the second creature spell this turn
    roundtrip(s)


def test_raging_battle_mouse_second_spell(cards):
    s = build(cards, [(1, "Raging Battle Mouse"), (1, "Opt"), (1, "Lightning Bolt"), (1, "Treasure Cruise")])
    put(s, "Raging Battle Mouse", "battlefield")
    opt, bolt, cruise = put(s, "Opt", "hand"), put(s, "Lightning Bolt", "hand"), put(s, "Treasure Cruise", "hand")
    assert cost_of(s, cruise, s.cards) == "{7}{U}"  # the first spell this turn: no change
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert cost_of(s, cruise, s.cards) == "{6}{U}"  # it would be the second
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    pass_until_stack_empty(s)
    assert cost_of(s, cruise, s.cards) == "{7}{U}"  # the third
    roundtrip(s)


def test_warden_of_evos_isle_only_creature_spells_with_flying(cards):
    s = build(cards, [(1, "Warden of Evos Isle"), (1, "Mulldrifter"), (1, "Grizzly Bears")])
    put(s, "Warden of Evos Isle", "battlefield")
    drifter, bears = put(s, "Mulldrifter", "hand"), put(s, "Grizzly Bears", "hand")
    assert cost_of(s, drifter, s.cards) == "{3}{U}" and cost_of(s, bears, s.cards) == "{1}{G}"


def test_avatar_of_fury_when_an_opponent_has_seven_lands(cards):
    s = build(cards, [(1, "Avatar of Fury")])
    avatar = put(s, "Avatar of Fury", "hand")
    assert cost_of(s, avatar, s.cards) == "{6}{R}{R}"
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and not c.zone.endswith("battlefield")]
    act(s, "p2", type="move", card_ids=islands[:7], to={"zone": "battlefield"})
    assert cost_of(s, avatar, s.cards) == "{R}{R}"


def test_charix_taxes_spells_that_target_it(cards):
    s = build(cards, [(1, "Lightning Bolt")], [(1, "Charix, the Raging Isle"), (9, "Island")])
    charix = find(s, "Charix, the Raging Isle", "p2")
    act(s, "p2", type="move", card_ids=[charix.id], to={"zone": "battlefield"})
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    refused(s, "ana|pay", type="cast_spell", card_id=bolt.id, targets=[charix.id])  # {2}{R}: 601.2c then 601.2f
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[charix.id])
    assert s.state.players["p1"].mana == {}
    pass_until_stack_empty(s)
    roundtrip(s)


def test_killian_reduces_spells_that_target_a_creature(cards):
    s = build(cards, [(1, "Killian, Ink Duelist"), (1, "Murder"), (1, "Lightning Bolt")])
    put(s, "Killian, Ink Duelist", "battlefield")
    murder = put(s, "Murder", "hand")
    victim = tok(s, "Victim", pid="p2")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])  # {1}{B}{B} − 2 → {B}{B}
    pass_until_stack_empty(s)
    assert victim.id not in s.state.cards and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_killian_reduction_counts_in_the_castable_hint(cards):
    """-- review (Codex) -- castable only thanks to "spells that target a creature cost {2} less": the hint offers it;
    a spell without targets gets no such reduction in the hint."""
    s = build(cards, [(1, "Killian, Ink Duelist"), (1, "Murder"), (1, "Grizzly Bears")])
    put(s, "Killian, Ink Duelist", "battlefield")
    murder = put(s, "Murder", "hand")
    bears = put(s, "Grizzly Bears", "hand")
    tok(s, "Victim", pid="p2")
    mana(s, B=2)
    found = hints(s.state, "p1", s.cards)["castable"]
    assert murder.id in found and bears.id not in found  # Bears: {1}{G}, no green and no targets


def test_gloom_taxes_an_ability_with_no_mana_in_its_cost(cards):
    s = build(cards, [(1, "Gloom")])
    put(s, "Gloom", "battlefield")
    shrine = tok(s, "Shrine", "0/0", type_line="Token Enchantment — Test", text="{T}: You gain 1 life.", colors=["W"])
    refused(s, "mana", type="activate_ability", card_id=shrine.id, ability=0)  # "{T}" is "{3}, {T}" now (601.2f)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=shrine.id, ability=0)
    pass_until_stack_empty(s)
    assert life(s) == 41 and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_stalwart_valkyrie_exiles_a_creature_card_from_the_graveyard(cards):
    s = build(cards, [(1, "Stalwart Valkyrie"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    valkyrie = put(s, "Stalwart Valkyrie", "hand")
    put(s, "Lightning Bolt", "graveyard")
    mana(s, W=1, C=1)
    assert valkyrie.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})  # no creature card there
    bears = put(s, "Grizzly Bears", "graveyard")
    act(s, "p1", type="cast_spell", card_id=valkyrie.id, alt_cost=alt_key(s, valkyrie))
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:exile" and s.state.cards[valkyrie.id].zone == "p1:battlefield"
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


# -- optional additional costs on other spells (Defiler of Vigor; 601.2b, 601.2f) -------------------------------------
def test_defiler_of_vigor_pays_life_for_a_green_symbol_only(cards):
    s = build(cards, [(1, "Defiler of Vigor"), (1, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Lightning Bolt")])
    defiler = put(s, "Defiler of Vigor", "battlefield")
    bears, elves = put(s, "Grizzly Bears", "hand"), put(s, "Llanowar Elves", "hand")
    put(s, "Lightning Bolt", "hand")
    mana(s, C=1)
    found = hints(s.state, "p1", s.cards).get("optional_costs", {})
    assert found.get(bears.id) == [{"id": defiler.id, "label": "Defiler of Vigor: pay 2 life"}]
    assert set(found) <= {bears.id, elves.id}  # (green permanent spells only: never the Bolt)
    refused(s, "doesn't apply", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=["p2"], optional_costs=[defiler.id])
    act(s, "p1", type="cast_spell", card_id=bears.id, optional_costs=[defiler.id])  # {1}{G} − {G}: {1}, and 2 life
    assert life(s) == 38 and s.state.players["p1"].mana == {}
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    roundtrip(s)


def test_defiler_never_reduces_generic_mana(cards):
    from app.rules import mana as M
    from app.rules.cost_changes import reduce_only

    assert reduce_only(M.parse_cost("{2}{G}"), ("G",)).text() == "{2}"
    assert reduce_only(M.parse_cost("{3}"), ("G",)).text() == "{3}"  # (no green to reduce: nothing, not {2})
    with pytest.raises(ActionError):
        reduce_only(M.parse_cost("{1}{G/W}"), ("G",))  # which half is paid isn't known: refused
