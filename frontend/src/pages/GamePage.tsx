import { useEffect } from "react";
import { GameScreen } from "../game/GameScreen";
import { seatToken } from "../services/games";
import { useGame } from "../state/gameStore";

export function GamePage({ id, viewer }: { id: string; viewer: string | null }) {
  useEffect(() => {
    useGame.getState().connect(id, { token: seatToken(id), viewer });
    document.body.classList.add("in-game");
    return () => {
      useGame.getState().disconnect();
      document.body.classList.remove("in-game");
    };
  }, [id, viewer]);
  return <GameScreen />;
}
