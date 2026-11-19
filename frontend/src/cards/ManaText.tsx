import { Fragment, memo } from "react";
import { splitKeywords, useGlossary } from "./glossary";
import { symbolInfo, symbolUrl, useSymbols } from "./symbols";

const SYMBOL = /\{([^}]+)\}/g;
const FILL: Record<string, string> = { W: "w", U: "u", B: "b", R: "r", G: "g" };
/** A part's disc: its colour's official fill, else the colourless grey (generic, X, colourless, snow…). */
const fillOf = (part: string) => FILL[part] ?? "c";

const WORD: Record<string, string> = {
  W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", C: "Colorless", S: "Snow", X: "X", Y: "Y", Z: "Z", T: "Tap", Q: "Untap", E: "Energy",
};

/** A symbol in words, for its tooltip and screen readers: "Green or White", "2 generic or Blue", "Black or 2 life". */
export function symbolWords(sym: string): string | null {
  const parts = sym.toUpperCase().split("/");
  const phyrexian = parts.length > 1 && parts[parts.length - 1] === "P";
  const words = (phyrexian ? parts.slice(0, -1) : parts).map((p) => WORD[p] ?? (/^\d+$/.test(p) ? `${p} generic` : null));
  if (!words.length || words.some((w) => w === null)) return null;
  const text = words.join(" or ");
  return phyrexian ? `${text} or 2 life` : words.length === 1 && /^\d+$/.test(parts[0]!) ? `${text} mana` : text;
}

/** The tap and untap arrows, drawn (no font has them reliably): a curved arrow, turned for untap. */
function TapArrow({ untap }: { untap: boolean }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={untap ? "untap" : undefined}>
      <path d="M15 11a5 5 0 1 1-5-5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M8.6 2.2 13 6l-4.4 3.8z" fill="currentColor" />
    </svg>
  );
}

/**
 * A symbol the host hasn't (offline before the first download, a brand-new one), drawn as one family with the real ones:
 * a disc in the symbol's official fill with its letter or number centred in the UI font; a hybrid split on the diagonal
 * with a letter in each half; Phyrexian mana as its colour with the Φ mark; tap and untap as a drawn arrow.
 */
function DrawnSymbol({ sym, label }: { sym: string; label?: string }) {
  const upper = sym.toUpperCase();
  const words = label ?? symbolWords(sym) ?? `{${sym}}`;
  // (data-sym-tip: the table's own tooltip, cards/symbolTip.ts)
  const a11y = { role: "img", "aria-label": words, "data-sym-tip": words };
  if (upper === "T" || upper === "Q") {
    return <span className="mana c drawn-tap" {...a11y}><TapArrow untap={upper === "Q"} /></span>;
  }
  const parts = upper.split("/");
  const phyrexian = parts.length > 1 && parts[parts.length - 1] === "P";
  const body = phyrexian ? parts.slice(0, -1) : parts;
  if (body.length === 2) {
    const [a, b] = body as [string, string];
    const style = { "--c1": `var(--sym-${fillOf(a)})`, "--c2": `var(--sym-${fillOf(b)})` } as React.CSSProperties;
    return (
      <span className="mana split" style={style} {...a11y}>
        {phyrexian ? <i className="mid">Φ</i> : <><i>{a}</i><i>{b}</i></>}
      </span>
    );
  }
  const one = body[0] ?? "";
  const text = phyrexian ? "Φ" : one;
  return <span className={`mana ${fillOf(one)}`} {...a11y}>{text.length > 1 ? <i className="sm">{text}</i> : text}</span>;
}

/**
 * One mana or card symbol, by its text without braces ("W", "2/U", "T"): the real symbol when the host has it
 * (cards/symbols.ts), else the drawn one. `label` names it for screen readers instead of its meaning.
 */
export function ManaSymbol({ sym, label }: { sym: string; label?: string }) {
  const info = symbolInfo(useSymbols(), sym);
  if (info) {
    const words = label ?? symbolWords(sym) ?? (info.english || `{${sym}}`);
    return <img className="mana mana-sym" src={symbolUrl(info)} alt={words} data-sym-tip={words} draggable={false} decoding="async" />;
  }
  return <DrawnSymbol sym={sym} label={label} />;
}

/** A keyword in card text: a dotted underline, its reminder on hover or focus (the table's tooltip, cards/symbolTip.ts). */
function Keywords({ text, own }: { text: string; own: readonly string[] | true }) {
  const parts = splitKeywords(text, useGlossary(), own === true ? undefined : own);
  return <>{parts.map((p, i) => (typeof p === "string" ? <Fragment key={i}>{p}</Fragment> : <span key={i} className="kw" tabIndex={0} data-sym-tip={p.tip}>{p.word}</span>))}</>;
}

/**
 * Renders `{2}{U}{U}` and oracle text with inline mana symbols. `keywords` marks keywords with their reminders: the card's
 * own keyword list, or `true` for text without one (an ability on the stack, a prompt), where only a keyword at the start
 * of a clause counts (cards/glossary.ts). Not inside a button: the marks are focusable.
 */
export const ManaText = memo(function ManaText({ text, keywords }: { text: string | null | undefined; keywords?: readonly string[] | true }) {
  if (!text) return null;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  const plain = (s: string, at: number) => nodes.push(keywords ? <Keywords key={`t${at}`} text={s} own={keywords} /> : <Fragment key={`t${at}`}>{s}</Fragment>);
  for (const match of text.matchAll(SYMBOL)) {
    const index = match.index ?? 0;
    if (index > last) plain(text.slice(last, index), last);
    nodes.push(<ManaSymbol key={index} sym={match[1] ?? ""} />);
    last = index + match[0].length;
  }
  if (last < text.length) plain(text.slice(last), last);
  return <>{nodes}</>;
});

export function OracleText({ text, keywords }: { text: string | null | undefined; keywords?: readonly string[] | true }) {
  if (!text) return null;
  return (
    <>
      {text.split("\n").map((line, i) => (
        <p key={i}>
          <ManaText text={line} keywords={keywords} />
        </p>
      ))}
    </>
  );
}
