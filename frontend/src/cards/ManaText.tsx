import { Fragment, memo } from "react";
import { symbolInfo, symbolUrl, useSymbols } from "./symbols";

const SYMBOL = /\{([^}]+)\}/g;
const COLOR_CLASS: Record<string, string> = { W: "w", U: "u", B: "b", R: "r", G: "g", C: "c", S: "c" };

function symbolClass(sym: string): string {
  const upper = sym.toUpperCase();
  if (upper === "T" || upper === "Q") return "tap";
  const parts = upper.split("/");
  const colors = parts.map((p) => COLOR_CLASS[p]).filter(Boolean);
  if (colors.length === 1) return colors[0]!;
  if (colors.length > 1) return `hybrid ${colors.join("-")}`;
  return "generic";
}

function symbolLabel(sym: string): string {
  const upper = sym.toUpperCase();
  if (upper === "T") return "⟳";
  if (upper === "Q") return "⟲";
  return upper.replace("/P", "ᵖ").replace("/", "");
}

/**
 * One mana or card symbol, by its text without braces ("W", "2/U", "T"): the real symbol when the host has it
 * (cards/symbols.ts), else a letter circle in its colour. `label` names it for screen readers instead of its meaning.
 */
export function ManaSymbol({ sym, label }: { sym: string; label?: string }) {
  const info = symbolInfo(useSymbols(), sym);
  if (info) {
    const words = label ?? (info.english || `{${sym}}`);
    return <img className="mana mana-sym" src={symbolUrl(info)} alt={words} title={words} draggable={false} decoding="async" />;
  }
  return (
    <span className={`mana ${symbolClass(sym)}`} title={label ?? `{${sym}}`} {...(label ? { role: "img", "aria-label": label } : {})}>
      {symbolLabel(sym)}
    </span>
  );
}

/** Renders `{2}{U}{U}` and oracle text with inline mana symbols. */
export const ManaText = memo(function ManaText({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(SYMBOL)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    nodes.push(<ManaSymbol key={index} sym={match[1] ?? ""} />);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes.map((n, i) => (typeof n === "string" ? <Fragment key={`t${i}`}>{n}</Fragment> : n))}</>;
});

export function OracleText({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <>
      {text.split("\n").map((line, i) => (
        <p key={i}>
          <ManaText text={line} />
        </p>
      ))}
    </>
  );
}
