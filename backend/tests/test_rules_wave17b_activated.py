"""Wave 17B: activated-ability wordings (CR 2026-09-25).

* "Target opponent may draw a card." (Phelddagrif): the other player decides as the ability resolves (608.2d).
* "gets -2/+2 and loses flying", "gains flying and loses trample", "loses defender and gains flying" (613.1f: one layer-6 effect).
* "Spend this mana only to cast kicked spells / spells from exile / spells with flashback from a graveyard", "This mana can't be spent
  to cast spells from your hand" (601.2h: what the spell is, where it's cast from and whether kicked are known when it's paid), and
  "Add an amount of {C} equal to Vhal's toughness".
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
from tests.test_rules_conditionals import build, on_field
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
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
FULL = ["Elfhame Druid", "Interdimensional Web Watch", "Altar of the Lost", "Vhal, Candlekeep Researcher", "Lord of the Forsaken",
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
