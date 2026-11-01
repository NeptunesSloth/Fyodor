import { useEffect } from "react";
import { GameScreen } from "../game/GameScreen";
import { PracticeBar } from "../game/PracticeBar";
import { rememberSeat, seatToken } from "../services/games";
import { useGame } from "../state/gameStore";
import { LobbyScreen } from "./LobbyScreen";

export function GamePage({ id, viewer }: { id: string; viewer: string | null }) {
  useEffect(() => {
    adoptSeatLink(id);
    useGame.getState().connect(id, { token: seatToken(id), viewer });
    document.body.classList.add("in-game");
    return () => {
      useGame.getState().disconnect();
      document.body.classList.remove("in-game");
    };
  }, [id, viewer]);
  const lobby = useGame((s) => s.lobby);
  const view = useGame((s) => s.view);
  if (lobby && !view) return <LobbyScreen lobby={lobby} />;
  return (
    <>
      <GameScreen />
      <PracticeBar id={id} />
    </>
  );
}

/**
 * A seat link from the host (Host tools → Seat link) carries `?seat_token=`: remember it as this
 * browser's seat and drop it from the address bar so it isn't left in history.
 */
function adoptSeatLink(id: string): void {
  const [path, query = ""] = window.location.hash.split("?");
  const params = new URLSearchParams(query);
  const token = params.get("seat_token");
  if (!token) return;
  rememberSeat(id, token);
  params.delete("seat_token");
  const rest = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${path}${rest ? `?${rest}` : ""}`);
}
