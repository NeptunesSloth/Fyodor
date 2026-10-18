"""levels_diff.py BASE NEW: gained / lost FULL, commanders gained, and cards whose parsed definitions changed (same level)."""
import json, sys
b, n = (json.load(open(p)) for p in sys.argv[1:3])
gained = sorted(k for k in n if n[k][0] == "FULL" and b.get(k, ["?"])[0] != "FULL")
lost = sorted(k for k in b if b[k][0] == "FULL" and n.get(k, ["?"])[0] != "FULL")
changed = sorted(k for k in n if k in b and n[k][0] == b[k][0] and n[k][2] != b[k][2])
fb, fn = sum(v[0] == "FULL" for v in b.values()), sum(v[0] == "FULL" for v in n.values())
print(f"BASE FULL {fb}  NEW FULL {fn}  GAINED {len(gained)}  LOST {len(lost)}  NET {fn - fb}  FULL% {100 * fn / len(n):.2f}")
print(f"COMMANDERS FULL base {sum(v[0]=='FULL' and v[1] for v in b.values())} new {sum(v[0]=='FULL' and v[1] for v in n.values())}")
print("GAINED:", *gained, sep="\n  ")
print("LOST:", *lost, sep="\n  ")
print(f"DEFINITIONS CHANGED, SAME LEVEL ({len(changed)}):", *changed[:200], sep="\n  ")
