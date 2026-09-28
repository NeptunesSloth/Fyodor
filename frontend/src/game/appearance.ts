/** Sleeves (card backs) and playmats: purely visual, looked up from the table view. */
import type { CSSProperties } from "react";
import { useGame } from "../state/gameStore";
import type { Playmat } from "../types/game";

/** URL of a player's sleeve image, or undefined for the default back. */
export function useSleeve(owner: string | null | undefined): string | undefined {
  return useGame((s) => {
    const v = s.view;
    if (!v || !owner) return undefined;
    const id = v.players.find((p) => p.id === owner)?.sleeve;
    return id ? v.game.assets?.[id]?.url : undefined;
  });
}

export function sleeveStyle(url: string | undefined): CSSProperties | undefined {
  return url ? { backgroundImage: `url("${url}")`, backgroundSize: "cover", backgroundPosition: "center" } : undefined;
}

/** CSS for a playmat layer (non-destructive: fit, scale, offset, rotation, opacity). */
export function playmatStyle(mat: Playmat | null | undefined, url: string | undefined): CSSProperties | undefined {
  if (!mat || !url) return undefined;
  const size = mat.fit === "stretch" ? "100% 100%" : mat.fit;
  return {
    backgroundImage: `url("${url}")`,
    backgroundSize: mat.scale === 1 || mat.fit === "stretch" ? size : `${mat.scale * 100}%`,
    backgroundRepeat: "no-repeat",
    backgroundPosition: `calc(50% + ${mat.offset_x}%) calc(50% + ${mat.offset_y}%)`,
    opacity: mat.opacity,
    transform: mat.rotation ? `rotate(${mat.rotation}deg)` : undefined,
  };
}

export function usePlaymat(player: string | null): { mat: Playmat | null; url: string | undefined } {
  const mat = useGame((s) => {
    const v = s.view;
    if (!v) return null;
    return player ? v.players.find((p) => p.id === player)?.playmat ?? null : v.table.playmat ?? null;
  });
  const url = useGame((s) => (mat ? s.view?.game.assets?.[mat.asset_id]?.url : undefined));
  return { mat, url };
}
