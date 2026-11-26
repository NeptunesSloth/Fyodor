import { Icon } from "../components/Icon";
import type { PlayerView } from "../types/game";

/**
 * -- playtest (nov 17) -- what a seat's round portrait or chip shows: a person's initial, a bot's robot glyph (Bob and the bot both
 * showed "B", told apart by colour alone). `size`: the glyph's size in px for a bot.
 */
export function PlayerInitial({ p, name, size = 16 }: { p?: Pick<PlayerView, "name" | "bot"> | null; name?: string; size?: number }) {
  if (p?.bot) return <Icon name="bot" size={size} label="Bot" className="player-bot-glyph" />;
  return <>{(p?.name ?? name ?? "").slice(0, 1).toUpperCase()}</>;
}
