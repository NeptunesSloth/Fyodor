import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { checkCardBack } from "./cards/cardBack";
import "./styles.css";
import "./game/game.css";
import "./theme/theme.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

void checkCardBack();
