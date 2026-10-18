"""Shared helpers of the wave 53B scenario tests: the real-Oracle fixture cards (tests/fixtures/wave53b_cards.json, from data/cards.sqlite) plus a few
synthetic probe cards (plain bodies with known types and colors) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave53b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}


def probe(name: str, types: str, colors: str = "", text: str = "", pt: tuple[str, str] | None = None, cost: str = "{1}", cmc: int = 1,
          keywords: tuple[str, ...] = ()) -> dict[str, Any]:
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="p53b", number=f"P-{name[:9]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=list(keywords), **extra)


PROBES = [
    probe("Probe Elf", "Creature — Elf Druid", "G", pt=("1", "1")),
    probe("Probe Elf Two", "Creature — Elf Warrior", "G", pt=("2", "2"), cost="{1}{G}", cmc=2),
    probe("Probe Bird", "Creature — Bird", "W", text="Flying", pt=("1", "1"), keywords=("Flying",)),
    probe("Probe Goblin", "Creature — Goblin", "R", pt=("1", "1")),
    probe("Probe Knight", "Creature — Human Knight", "W", pt=("3", "3"), cost="{2}{W}", cmc=3),
    probe("Probe Bolt", "Instant", "R", cost="{R}"),
    probe("Probe Gain", "Instant", "R", text="You gain 1 life.", cost="{R}"),
    probe("Probe Relic", "Artifact"),
    probe("Probe Rock", "Artifact Creature — Golem", "", pt=("2", "2"), cost="{2}", cmc=2),
    probe("Probe Land", "Land", cost="", cmc=0),
    probe("Probe Charm", "Enchantment", "U", cost="{U}"),
    probe("Probe Gem", "Artifact", cost="{4}", cmc=4),
    probe("Probe Pinger", "Artifact", text="{T}: Probe Pinger deals 1 damage to any target.\n{T}: Add {C}.", cost="{1}"),
    probe("Probe Zapper", "Artifact", text="{T}: Probe Zapper deals 1 damage to any target.", cost="{1}"),
    probe("Probe Wagon", "Artifact Creature — Vehicle", pt=("2", "2"), cost="{2}", cmc=2),
    probe("Probe Hex", "Enchantment — Aura", "R", text="Enchant creature", cost="{R}"),
    probe("Probe Freeze", "Sorcery", "U", text="Tap target land.", cost="{U}"),
    probe("Probe Swamp", "Basic Land — Swamp", text="({T}: Add {B}.)", cost="", cmc=0),
]
EXTRA = [card(c["name"], set_code="w53b", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN] + PROBES


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()
