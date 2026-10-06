"""probe27c: python probe27c.py file -- each line "cond ||| body" or full text; report which half fails."""
import re
import sys

from app.rules import events, scripts

for raw in open(sys.argv[1]).read().splitlines():
    raw = raw.strip()
    if not raw:
        continue
    m = re.match(r"^(?:when|whenever) (?P<c>.+?), (?P<b>.+)$", raw, re.I)
    if not m:
        print("NOSPLIT", raw[:80])
        continue
    c, b = m["c"], m["b"]
    cond = events.parse_condition(c)
    try:
        eff = scripts.parse_effects(b, "~" if "~" in c else None)
    except Exception as e:  # noqa
        eff = f"EXC {e}"
    print(("COND-FAIL " if cond is None else "cond-ok   ") + ("BODY-FAIL " if eff is None else "body-ok   "), "|", c[:70], "|", b[:80])
