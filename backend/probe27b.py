"""probe: python 27b_probe.py file_with_lines  (each line: Type|oracle text with \\n as \\\\n) -> coverage level + unsupported."""
import sys
from app.rules import coverage

for i, raw in enumerate(open(sys.argv[1]).read().splitlines()):
    if not raw.strip():
        continue
    tl, text = raw.split("|", 1)
    d = {"name": f"Probe{i}", "oracle_id": f"probe-{i}-{hash(text)}", "id": f"p{i}", "type_line": tl, "oracle_text": text.replace("\\n", "\n"), "mana_cost": "{2}{B}", "cmc": 3.0,
         "colors": ["B"], "color_identity": ["B"], "keywords": [], "faces": [], "power": "2", "toughness": "2", "legalities": {"commander": "legal"}}
    cov = coverage.of_card_data(d)
    bad = [f.label for f in cov.features if not f.supported]
    print(cov.level, "|", text[:90], "|", bad if bad else "")
