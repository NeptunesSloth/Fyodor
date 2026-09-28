import { useEffect } from "react";
import { GameScreen } from "../game/GameScreen";
import { seatToken } from "../services/games";
import { useGame } from "../state/gameStore";
import { LobbyScreen } from "./LobbyScreen";

export function GamePage({ id, viewer }: { id: string; viewer: string | null }) {
  useEffect(() => {
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
  return <GameScreen />;
}
