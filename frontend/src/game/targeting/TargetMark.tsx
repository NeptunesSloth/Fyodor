import { pickNumber, useTargeting } from "./store";

/**
 * The board half of targeting on a candidate card (TableCard renders it while the card is a legal choice): its brass
 * ring, brighter while its tray thumbnail is hovered, a focus ring while that thumbnail has keyboard focus, and the
 * order it was chosen in. Styles: game/targeting.css.
 */
export function TargetMark({ id }: { id: string }) {
  const n = useTargeting((s) => pickNumber(s.picked, id));
  const hot = useTargeting((s) => s.hot === id);
  const focus = useTargeting((s) => s.focus === id);
  return (
    <span className="tgt-mark" data-n={n || undefined} data-hot={hot ? "" : undefined} data-focus={focus ? "" : undefined} aria-hidden>
      {n > 0 && <b className="tgt-mark-n">{n}</b>}
    </span>
  );
}
