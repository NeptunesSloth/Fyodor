export function ColorPips({ colors }: { colors: string[] }) {
  if (!colors.length) return <span className="mana c">C</span>;
  return (
    <span className="pips">
      {colors.map((c) => (
        <span key={c} className={`mana ${c.toLowerCase()}`}>{c}</span>
      ))}
    </span>
  );
}
