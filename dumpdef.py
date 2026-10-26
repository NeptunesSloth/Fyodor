"""dumpdef.py "Card" "old" "new"... : pretty-print scripts.definitions of a real card (optionally with Oracle substrings replaced)."""
import sys, json
from pathlib import Path
from tools.commander_coverage import rows
from app.rules import coverage, scripts
n, *rep = sys.argv[1:]
d = next(d for d in rows(Path("/home/user/Fyodor/data/cards.sqlite"))[0] if d["name"] == n)
t = d.get("oracle_text") or ""
for i in range(0, len(rep), 2):
    assert rep[i] in t, rep[i]; t = t.replace(rep[i], rep[i + 1])
ch = coverage.printed_from_data({**d, "oracle_text": t}, 0)
print(json.dumps(scripts.definitions(ch), default=str, indent=None)[:3000])
