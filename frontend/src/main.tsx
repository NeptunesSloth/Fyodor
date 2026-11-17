import "./polyfills"; // (first: what an older Chrome or Edge lacks)
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { CrashScreen } from "./components/CrashScreen";
import { checkCardBack } from "./cards/cardBack";
import { checkSymbols } from "./cards/symbols";
import { installSymbolTips } from "./cards/symbolTip";
import { startImagelessRecheck } from "./state/cardCache";
import "./styles.css";
import "./game/game.css";
import "./theme/theme.css";

(window as unknown as { __fyodorStarted?: boolean }).__fyodorStarted = true; // (index.html's too-old-browser notice stands down)
const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");
createRoot(root).render(
  <StrictMode>
    <CrashScreen>
      <App />
    </CrashScreen>
  </StrictMode>,
);

void checkCardBack();
void checkSymbols();
installSymbolTips();
startImagelessRecheck();
