import { ManaSymbol } from "../cards/ManaText";

const NAMES: Record<string, string> = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", C: "Colorless" };

/** A deck's colour identity as mana symbols (the real ones when the host has them, else letter circles); none is {C}. */
export function ColorPips({ colors }: { colors: string[] }) {
  const shown = colors.length ? colors : ["C"];
  return (
    <span className="pips">
      {shown.map((c) => <ManaSymbol key={c} sym={c.toUpperCase()} label={NAMES[c.toUpperCase()] ?? c} />)}
    </span>
  );
}
