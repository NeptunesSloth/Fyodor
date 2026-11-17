import { playerName, useGame } from "../../state/gameStore";

/** -- resolving progress -- the words of the indicator (also its tests'). */
export function resolvingText(resolved: number, left: number): string {
  return `${resolved.toLocaleString()} resolved${left > 0 ? ` · ${left.toLocaleString()} left` : ""}`;
}

/**
 * -- resolving progress -- over the turn dial while the server works out a long automatic chain inside one action (200 end-step
 * sacrifices): how far it got, so the table never looks hung. The server sends the count with each interim view (gameStore
 * `resolving`); the action's own update clears it. A quiet brass plaque: no spinner, no looping animation (the bar only fills).
 */
export function ResolvingIndicator() {
  const progress = useGame((s) => s.resolving);
  const view = useGame((s) => s.view);
  if (!progress || !view) return null;
  const total = progress.resolved + progress.left;
  const share = total > 0 ? Math.min(1, progress.resolved / total) : 0;
  const by = playerName(view, progress.by);
  return (
    <section className="resolving plaque" data-testid="resolving" aria-label="Resolving">
      <header className="resolving-head" role="status" aria-live="polite">Resolving…{by ? <span className="resolving-by"> {by}'s action</span> : null}</header>
      <p className="resolving-count" aria-hidden="true" data-testid="resolving-count">{resolvingText(progress.resolved, progress.left)}</p>
      {total > 0 && (
        <div className="resolving-bar" aria-hidden="true">
          <span style={{ transform: `scaleX(${share})` }} />
        </div>
      )}
    </section>
  );
}
