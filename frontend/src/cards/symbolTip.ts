/**
 * The mana symbols' tooltip: a small plaque over the symbol pointed at, naming it ("Green or White", "White"). One
 * delegated listener for the whole page (symbols carry `data-sym-tip`, cards/ManaText.tsx), shown after a short rest and
 * gone as soon as the pointer leaves, the page scrolls or a key is pressed. Screen readers read the symbol's own label.
 * -- keyword help -- keywords in card text carry it too (cards/ManaText.tsx): focusable, so the tip also shows on keyboard focus
 * (and is their description); a long reminder wraps.
 */
const DELAY_MS = 260;

export function installSymbolTips(doc: Document = document): () => void {
  const tip = doc.createElement("div");
  tip.className = "sym-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  tip.id = "sym-tip";
  doc.body.appendChild(tip);
  let timer = 0;
  let current: Element | null = null;
  const hide = () => {
    window.clearTimeout(timer);
    current?.removeAttribute("aria-describedby");
    current = null;
    tip.hidden = true;
    tip.classList.remove("on");
  };
  const show = (el: Element) => {
    tip.textContent = el.getAttribute("data-sym-tip");
    tip.classList.toggle("long", (tip.textContent?.length ?? 0) > 40);
    if (el.classList.contains("kw")) el.setAttribute("aria-describedby", tip.id);
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const below = r.top - h - 8 < 4; // no room above: under it
    tip.dataset.side = below ? "below" : "above";
    tip.style.left = `${Math.round(Math.min(Math.max(4, r.left + r.width / 2 - w / 2), window.innerWidth - w - 4))}px`;
    tip.style.top = `${Math.round(below ? r.bottom + 8 : r.top - h - 8)}px`;
    tip.style.setProperty("--caret", `${Math.round(r.left + r.width / 2 - parseFloat(tip.style.left))}px`);
    requestAnimationFrame(() => tip.classList.add("on"));
  };
  const over = (e: Event) => {
    const el = (e.target as Element | null)?.closest?.("[data-sym-tip]") ?? null;
    if (el === current) return;
    hide();
    if (!el) return;
    current = el;
    timer = window.setTimeout(() => current === el && el.isConnected && show(el), DELAY_MS);
  };
  const out = (e: PointerEvent) => !e.relatedTarget && hide(); // left the window
  const focus = (e: FocusEvent) => {
    const el = (e.target as Element | null)?.closest?.(".kw[data-sym-tip]") ?? null;
    if (!el || el === current) return;
    hide();
    current = el;
    timer = window.setTimeout(() => current === el && el.isConnected && show(el), 60);
  };
  const blur = (e: FocusEvent) => (e.target as Element | null) === current && hide();
  doc.addEventListener("pointerover", over);
  doc.addEventListener("pointerout", out);
  doc.addEventListener("focusin", focus);
  doc.addEventListener("focusout", blur);
  doc.addEventListener("pointerdown", hide, true);
  doc.addEventListener("keydown", hide, true);
  window.addEventListener("scroll", hide, true);
  return () => {
    hide();
    doc.removeEventListener("pointerover", over);
    doc.removeEventListener("pointerout", out);
    doc.removeEventListener("focusin", focus);
    doc.removeEventListener("focusout", blur);
    doc.removeEventListener("pointerdown", hide, true);
    doc.removeEventListener("keydown", hide, true);
    window.removeEventListener("scroll", hide, true);
    tip.remove();
  };
}
