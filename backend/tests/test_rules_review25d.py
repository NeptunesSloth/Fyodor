"""Review of wave 25D (attached events, X-sized costs, reanimation). Real Oracle text; each scenario replays and round-trips."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import attachments
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_wave25d_attached import EXTRA, FODDER, cast_on, make, roundtrip, settle
from tests.test_rules_wave25d_x_costs import EXTRA as X_EXTRA

MORE = [
    card("Stone Rain", set_code="r25d", number="R01", mana_cost="{2}{R}", cmc=3.0, type_line="Sorcery", oracle_text="Destroy target land.",
         colors=["R"], color_identity=["R"]),
    card("Shatter", set_code="r25d", number="R02", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", oracle_text="Destroy target artifact.",
         colors=["R"], color_identity=["R"]),
    card("Viridian Harvest", set_code="r25d", number="R03", mana_cost="{G}", cmc=1.0, type_line="Enchantment — Aura",
         oracle_text="Enchant artifact\nWhen enchanted artifact is put into a graveyard, you gain 6 life.", colors=["G"], color_identity=["G"]),
    card("Crown of Vigor", set_code="r25d", number="R04", mana_cost="{1}{G}", cmc=2.0, type_line="Enchantment — Aura",
         oracle_text="Enchant creature\nEnchanted creature gets +1/+1.\nSacrifice this Aura: Enchanted creature and other creatures that share a "
                     "creature type with it get +1/+1 until end of turn.", colors=["G"], color_identity=["G"]),
    card("Changeling Outcast", set_code="r25d", number="R05", mana_cost="{B}", cmc=1.0, type_line="Creature — Shapeshifter",
         oracle_text="Changeling (This card is every creature type.)\nThis creature can't block and can't be blocked.", power="1", toughness="1",
         colors=["B"], color_identity=["B"]),
    card("Probe Trinket", set_code="r25d", number="R06", mana_cost="{1}", cmc=1.0, type_line="Artifact", oracle_text="", colors=[], color_identity=[]),
    card("Probe Red Aura", set_code="r25d", number="R07", mana_cost="{R}", cmc=1.0, type_line="Enchantment — Aura", oracle_text="Enchant creature",
         colors=["R"], color_identity=["R"]),
    card("Thought Scour", set_code="r25d", number="R08", mana_cost="{U}", cmc=1.0, type_line="Instant",
         oracle_text="Target player mills two cards.\nDraw a card.", colors=["U"], color_identity=["U"]),
    card("Revitalize", set_code="r25d", number="R09", mana_cost="{1}{W}", cmc=2.0, type_line="Instant", oracle_text="You gain 3 life.\nDraw a card.",
         colors=["W"], color_identity=["W"]),
    card("Creeping Chill", set_code="r25d", number="R10", mana_cost="{3}{B}", cmc=4.0, type_line="Sorcery",
         oracle_text="Creeping Chill deals 3 damage to each opponent and you gain 3 life.\nWhen Creeping Chill is put into your graveyard from your "
                     "library, you may exile it. If you do, Creeping Chill deals 3 damage to each opponent and you gain 3 life.",
         colors=["B"], color_identity=["B"]),
    card("Punishing Fire", set_code="r25d", number="R11", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Punishing Fire deals 2 damage to any target.\nWhenever an opponent gains life, you may pay {R}. If you do, return this card "
                     "from your graveyard to your hand.", colors=["R"], color_identity=["R"]),
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    names = {c["name"] for c in EXTRA}
    build_database([*fixture_cards(), *EXTRA, *[c for c in X_EXTRA if c["name"] not in names], *FODDER, *MORE], settings.cards_db_path,
                   meta={"bulk_type": "test"})
    return settings.cards_db_path


def yes_all(s, limit=30):
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            choose(s, next((o.id for o in d.options if o.label == "Yes"), d.options[0].id))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_genju_returns_when_its_unanimated_forest_is_destroyed(cards):
    s = build(cards, "Genju of the Cedars", "Stone Rain")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    genju = cast_on(s, "Genju of the Cedars", forest, G=1)
    rain = to_hand(s, "Stone Rain")
    pay(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=rain.id, targets=[forest.id])
    yes_all(s)
    assert s.state.cards[forest.id].zone == "p1:graveyard" and s.state.cards[genju.id].zone == "p1:hand"
    roundtrip(s)


def test_viridian_harvest_on_a_noncreature_artifact(cards):
    s = build(cards, "Viridian Harvest", "Probe Trinket", "Shatter")
    trinket = on_battlefield(s, "Probe Trinket")
    cast_on(s, "Viridian Harvest", trinket, G=1)
    life = s.state.players["p1"].life
    shatter = to_hand(s, "Shatter")
    pay(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=shatter.id, targets=[trinket.id])
    yes_all(s)
    assert s.state.players["p1"].life == life + 6
    roundtrip(s)


def test_spectra_ward_only_excuses_auras_already_attached(cards):
    """702.16n: the Auras aren't put into the graveyard as a state-based action; protection still keeps a red Aura from becoming attached
    (702.16c) when it is put onto the battlefield or moved onto the creature."""
    s = build(cards, "Spectra Ward", "Probe Red Aura", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    cast_on(s, "Spectra Ward", beast, W=2, C=3)
    red = on_battlefield(s, "Probe Red Aura")
    plan = Plan(s.state, "p1", s.cards, None)
    assert beast.id not in attachments.legal_hosts(plan, s.state.cards[red.id])
    assert attachments.host_problem(plan, s.state.cards[red.id], beast.id, sba=True) is None
    roundtrip(s)


def _crown(s, host, name="Crown of Vigor"):
    cast_on(s, name, host, G=1, C=1)
    crown = next(c for c in s.state.cards.values() if c.name == name)
    index = next(a.index for a in ch(s, crown).abilities if a.kind == "activated")
    return crown, index


def test_a_crown_on_a_changeling_reaches_every_creature(cards):
    s = build(cards, "Crown of Vigor", "Changeling Outcast", "Probe Beast")
    outcast = on_battlefield(s, "Changeling Outcast")
    beast = on_battlefield(s, "Probe Beast")
    crown, index = _crown(s, outcast)
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=index)
    settle(s)
    assert ch(s, outcast).pt == (2, 2) and ch(s, beast).pt == (4, 4)
    roundtrip(s)


def test_a_crown_reads_a_dead_changeling_host_as_it_last_existed(cards):
    s = build(cards, "Crown of Vigor", "Changeling Outcast", "Probe Beast", "Lightning Bolt")
    outcast = on_battlefield(s, "Changeling Outcast")
    beast = on_battlefield(s, "Probe Beast")
    crown, index = _crown(s, outcast)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=index)
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    act(s, "p2", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "hand"})
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[outcast.id])  # in response: the host dies first
    settle(s)
    assert s.state.cards[outcast.id].zone.endswith(":graveyard") and ch(s, beast).pt == (4, 4)  # found by what it was (608.2h)
    roundtrip(s)


def test_firestorm_discards_exactly_x(cards):
    s = build(cards, "Firestorm", "Probe Beast", "Probe Spell Book")
    beast = on_battlefield(s, "Probe Beast")
    book = to_hand(s, "Probe Spell Book")
    storm = to_hand(s, "Firestorm")
    pay(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=storm.id, targets=[beast.id, "p2"], target_counts=[2], x_value=2,
            cost_choices=[{"component": 0, "cards": [book.id]}])


def test_screams_from_within_stays_in_the_graveyard_with_nothing_to_enchant(cards):
    s = build(cards, "Screams from Within", "Changeling Outcast")
    outcast = on_battlefield(s, "Changeling Outcast")
    screams = cast_on(s, "Screams from Within", outcast, B=2, C=1)
    yes_all(s)
    assert s.state.cards[outcast.id].zone == "p1:graveyard" and s.state.cards[screams.id].zone == "p1:graveyard"
    roundtrip(s)


def test_screams_from_within_returns_attached_to_another_creature(cards):
    s = build(cards, "Screams from Within", "Changeling Outcast", "Probe Beast")
    outcast = on_battlefield(s, "Changeling Outcast")
    beast = on_battlefield(s, "Probe Beast")
    screams = cast_on(s, "Screams from Within", outcast, B=2, C=1)
    yes_all(s)
    assert s.state.cards[outcast.id].zone == "p1:graveyard" and s.state.cards[screams.id].attached_to == beast.id  # 303.4f
    assert ch(s, beast).pt == (2, 2)
    roundtrip(s)


def test_lingering_death_spares_a_creature_its_controller_no_longer_controls(cards):
    """701.21a: "that player sacrifices that creature" — a player can't sacrifice a permanent they don't control."""
    s = build(cards, "Lingering Death")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    cast_on(s, "Lingering Death", ogre, B=1, C=1)
    act(s, "p1", type="pass_priority", until="next_turn")
    moved = False
    for _ in range(120):
        if s.state.turn.number >= 3:  # (on Alice's own end step it is hers to sacrifice)
            break
        if s.state.zones.get("stack") and not moved and s.state.turn.active_player == "p2":
            act(s, "p1", type="set_controller", card_ids=[ogre.id], player="p1")  # (by hand, with the trigger waiting)
            moved = True
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id) if d.kind not in ("declare_attackers", "declare_blockers") else \
                act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blockers": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert moved and s.state.cards[ogre.id].zone == "p1:battlefield"
    roundtrip(s)


def test_two_cragflames_meet_the_legend_rule(cards):
    s = build(cards, "Mabel, Heir to Cragflame")
    mabel = to_hand(s, "Mabel, Heir to Cragflame")
    for _ in range(2):
        pay(s, R=1, W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=mabel.id)
        yes_all(s)
        act(s, "p1", type="move", card_ids=[mabel.id], to={"zone": "hand"})
    flames = [c for c in s.state.cards.values() if c.name == "Cragflame" and c.zone == "p1:battlefield"]
    assert len(flames) == 1  # 704.5j
    roundtrip(s)


def test_creeping_chill_milled_deals_its_damage(cards):
    s = build(cards, "Creeping Chill", "Thought Scour")
    chill = next(c for c in s.state.cards.values() if c.name == "Creeping Chill")
    act(s, "p1", type="move", card_ids=[chill.id], to={"zone": "library"}, position="top")
    scour = to_hand(s, "Thought Scour")
    life = s.state.players["p2"].life
    pay(s, U=1)
    act(s, "p1", type="cast_spell", card_id=scour.id, targets=["p1"])
    yes_all(s)
    assert s.state.cards[chill.id].zone == "p1:exile" and s.state.players["p2"].life == life - 3  # 113.6m / 603.6a
    roundtrip(s)


def test_punishing_fire_returns_when_an_opponent_gains_life(cards):
    s = build(cards, "Punishing Fire", "Revitalize")
    fire = next(c for c in s.state.cards.values() if c.name == "Punishing Fire")
    act(s, "p1", type="move", card_ids=[fire.id], to={"zone": "graveyard"})
    revit = next(c for c in s.state.cards.values() if c.name == "Revitalize")
    act(s, "p2", type="move", card_ids=[revit.id], to={"player": "p2", "zone": "hand"})
    act(s, "p2", type="add_mana", player="p2", mana={"W": 1, "C": 1})
    pay(s, R=1)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=revit.id)
    yes_all(s)
    assert s.state.cards[fire.id].zone == "p1:hand"
    roundtrip(s)


def test_vampire_hexmage_removes_every_kind_of_counter(cards):
    s = build(cards, "Vampire Hexmage", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    act(s, "p1", type="counter", card_ids=[beast.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[beast.id], kind="stun", delta=1)
    hexmage = on_battlefield(s, "Vampire Hexmage")
    index = next(a.index for a in ch(s, hexmage).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=hexmage.id, ability=index, targets=[beast.id])
    settle(s)
    assert not any(s.state.cards[beast.id].counters.values()) and ch(s, beast).pt == (3, 3)
    roundtrip(s)


def test_tattoo_ward_keeps_itself_but_not_another_aura(cards):
    s = build(cards, "Tattoo Ward", "Probe Curse", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    curse = cast_on(s, "Probe Curse", beast, B=1)
    ward = cast_on(s, "Tattoo Ward", beast, W=1, C=2)
    assert s.state.cards[ward.id].attached_to == beast.id and s.state.cards[curse.id].zone == "p1:graveyard"  # 702.16n / 704.5m
    roundtrip(s)


def test_apathy_the_enchanted_creatures_controller_discards_at_random(cards):
    s = build(cards, "Apathy")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    act(s, "p2", type="tap", card_ids=[ogre.id], tapped=True)
    cast_on(s, "Apathy", ogre, U=1)
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "hand"})
    act(s, "p1", type="pass_priority", until="next_turn")
    asked = []
    for _ in range(40):
        if s.state.turn.number >= 2 and s.state.turn.phase not in ("untap", "upkeep"):
            break
        d = decision(s)
        if d is not None:
            asked.append(d.player)
            choose(s, next((o.id for o in d.options if o.label == "Yes"), d.options[0].id))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert asked == ["p2"] and not s.state.cards[ogre.id].tapped and s.state.cards[island.id].zone == "p2:graveyard"  # its only card, at random
    roundtrip(s)
