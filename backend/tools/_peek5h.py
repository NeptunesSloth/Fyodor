"""Scratch helper (wave 5H, not committed): show definitions of named cards."""
import json
import sqlite3
import sys

from app.rules import coverage
from app.rules import scripts as templates
from app.rules.characteristics import printed_from_data

db = sqlite3.connect("file:/home/user/Fyodor/data/cards.sqlite?mode=ro", uri=True)
db.row_factory = sqlite3.Row
for name in sys.argv[1:]:
    r = db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.name = ?", (name,)).fetchone()
    if r is None:
        print("??", name)
        continue
    d = dict(r)
    for key in ("colors", "color_identity", "keywords"):
        d[key] = json.loads(d[key] or "[]")
    d["faces"] = json.loads(d.pop("card_faces") or "null") or []
    cov = coverage.of_card_data(d)
    print("==", name, cov.level)
    ch = printed_from_data(d, 0)
    defs = templates.definitions(ch)
    for ab in ch.abilities:
        print("  ", ab.index, ab.kind, "|", ab.text[:150])
        if ab.index in defs:
            print("      ->", json.dumps(defs[ab.index], default=str)[:600], coverage.definition_supported(defs[ab.index]))
    if ch.is_instant_or_sorcery:
        print("   spell ->", json.dumps(templates.spell_definition(ch), default=str)[:800])
