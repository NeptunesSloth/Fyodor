/**
 * A seat link from the host (Host tools → Seat link) is `/#/game/<id>?seat_token=<token>`: the token sits after the `#`, which a browser
 * never sends to a server. It still must not stay in the address bar, history or a copied address, so it is taken off at once.
 * A hand-built `…?seat_token=<token>#/game/<id>` (a real query string) is read the same way and stripped as well.
 */
import { rememberSeat } from "./games";

export interface SeatLink {
  /** The game the link is for (the `#/game/<id>` route), null when the address is not a game's. */
  gameId: string | null;
  token: string;
  /** The same address without the token, in either position. */
  cleaned: string;
}

export function readSeatLink(loc: { pathname: string; search: string; hash: string }): SeatLink | null {
  const query = new URLSearchParams(loc.search);
  const [path = "", hashQuery = ""] = loc.hash.split("?");
  const inHash = new URLSearchParams(hashQuery);
  const token = inHash.get("seat_token") ?? query.get("seat_token");
  if (!token) return null;
  query.delete("seat_token");
  inHash.delete("seat_token");
  const [route, id] = path.replace(/^#\/?/, "").split("/");
  const search = query.toString();
  const rest = inHash.toString();
  return {
    gameId: route === "game" && id ? decodeURIComponent(id) : null,
    token,
    cleaned: `${loc.pathname}${search ? `?${search}` : ""}${path}${rest ? `?${rest}` : ""}`,
  };
}

/** Remember the seat a link carries and take the token off the address bar. `gameId`: the page's own, else the link's. */
export function adoptSeatLink(gameId?: string): void {
  const link = readSeatLink(window.location);
  if (!link) return;
  window.history.replaceState(window.history.state, "", link.cleaned);
  const id = gameId ?? link.gameId;
  if (id) rememberSeat(id, link.token);
}
