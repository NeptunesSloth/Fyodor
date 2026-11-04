import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { checkCardBack } from "./cards/cardBack";
import { checkSymbols } from "./cards/symbols";
import { installSymbolTips } from "./cards/symbolTip";
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
void checkSymbols();
installSymbolTips();
