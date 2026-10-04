"""Wave 15D: activated-ability wordings - "becomes the creature type / color of your choice", a token named like its card,
counter costs on mana abilities, "it deals" after counter costs, a player exiling a card from their graveyard, exchanging life
totals (701.12c) and spells with {X} in their mana cost. Real Oracle text, a replay and a save/load round trip each."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, counters, on_field
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"15D-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Mistform Dreamer", "{2}{U}", 3, "Creature — Illusion",
         "Flying\n{1}: This creature becomes the creature type of your choice until end of turn.", ("1", "1"), "U"),
    real("Kher Keep", "", 0, "Legendary Land",
         "{T}: Add {C}.\n{1}{R}, {T}: Create a 0/1 red Kobold creature token named Kobolds of Kher Keep.", None, ""),
    real("Relic of Progenitus", "{1}", 1, "Artifact",
         "{T}: Target player exiles a card from their graveyard.\n{1}, Exile this artifact: Exile all graveyards. Draw a card."),
    real("Graveyard Shovel", "{2}", 2, "Artifact",
         "{2}, {T}: Target player exiles a card from their graveyard. If it's a creature card, you gain 2 life."),
    real("Spitting Hydra", "{3}{R}{R}", 5, "Creature — Hydra",
         "This creature enters with four +1/+1 counters on it.\n{1}{R}, Remove a +1/+1 counter from this creature: It deals 1 "
         "damage to target creature.", ("0", "0"), "R"),
    real("Crystalline Crawler", "{5}", 5, "Artifact Creature — Construct",
         "Converge — This creature enters with a +1/+1 counter on it for each color of mana spent to cast it.\nRemove a +1/+1 "
         "counter from this creature: Add one mana of any color.", ("0", "0")),
    real("Soul Conduit", "{6}", 6, "Artifact", "{6}, {T}: Two target players exchange life totals."),
    real("Matterbending Mage", "{2}{U}", 3, "Creature — Human Wizard",
         "When this creature enters, return up to one other target creature to its owner's hand.\nWhenever you cast a spell with {X} "
         "in its mana cost, this creature can't be blocked this turn.", ("2", "2"), "U"),
    real("MJ, Rising Star", "{1}{W}", 2, "Legendary Creature — Human Citizen",
         "Vigilance\nWhenever you gain life, put a +1/+1 counter on MJ.", ("2", "2"), "W"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


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


@pytest.mark.parametrize("name", ["Mistform Dreamer", "Kher Keep", "Relic of Progenitus", "Graveyard Shovel", "Spitting Hydra",
                                  "Crystalline Crawler", "Soul Conduit", "Matterbending Mage", "MJ, Rising Star"])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_creature_type_of_your_choice_replaces_the_creature_types(cards):
    s = build(cards, "Mistform Dreamer")
    dreamer = on_field(s, "Mistform Dreamer")
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=dreamer.id, ability=ability(s, dreamer, "{1}"))
    settle(s, pick="Elf")
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[dreamer.id])
    assert "Elf" in ch.subtypes and "Illusion" not in ch.subtypes
    roundtrip(s)


def test_token_named_like_its_card(cards):
    s = build(cards, "Kher Keep")
    keep = on_field(s, "Kher Keep")
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=keep.id, ability=ability(s, keep, "{1}{R}"))
    settle(s)
    assert any(c.name == "Kobolds of Kher Keep" for c in s.state.cards.values())
    roundtrip(s)


def test_player_exiles_a_card_from_their_graveyard_and_the_life_rider(cards):
    s = build(cards, "Graveyard Shovel", p2=("Grizzly Bears",))
    shovel = on_field(s, "Graveyard Shovel")
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, "p1", C=2)
    before = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=shovel.id, ability=0, targets=["p2"])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:exile"
    assert s.state.players["p1"].life == before + 2  # it was a creature card
    roundtrip(s)


def test_remove_counter_then_it_deals_damage(cards):
    s = build(cards, "Spitting Hydra", p2=("Grizzly Bears",))
    hydra = on_field(s, "Spitting Hydra")
    bears = on_field(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_counter", card_id=hydra.id, kind="+1/+1", value=4)
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=hydra.id, ability=ability(s, hydra, "{1}{R}"), targets=[bears.id])
    settle(s)
    assert counters(s, hydra) == 3 and s.state.cards[bears.id].damage == 1
    roundtrip(s)


def test_exchange_life_totals(cards):
    s = build(cards, "Soul Conduit")
    conduit = on_field(s, "Soul Conduit")
    act(s, "p1", type="set_life", player="p1", value=10)
    mana(s, "p1", C=6)
    mine, theirs = s.state.players["p1"].life, s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=conduit.id, ability=0, targets=["p1", "p2"], target_counts=[2])
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (theirs, mine)
    roundtrip(s)
