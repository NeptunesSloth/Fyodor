"""probe27d: python probe27d.py file -- each line a body; flags: lines starting with 'E:' use event_player, 'S:' it=self."""
import sys

from app.rules import scripts

for raw in open(sys.argv[1]).read().splitlines():
    raw = raw.strip()
    if not raw:
        continue
    kw = {}
    if raw.startswith("E:"):
        raw, kw = raw[2:], {"event_player": True}
    elif raw.startswith("S:"):
        raw, kw = raw[2:], {"it": "self"}
    try:
        eff = scripts.parse_effects(raw, **kw)
    except Exception as e:  # noqa
        eff = f"EXC {e!r}"
    print("FAIL" if eff is None else "ok  ", "|", raw[:110], "" if eff is None or isinstance(eff, str) else str(eff[0])[:150])
