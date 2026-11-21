import "./polyfills"; // (first: what an older Chrome or Edge lacks)
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { CrashScreen } from "./components/CrashScreen";
import { checkCardBack } from "./cards/cardBack";
import { checkSymbols } from "./cards/symbols";
import { installSymbolTips } from "./cards/symbolTip";
import { claimHostSession } from "./services/hostSession";
import { adoptSeatLink } from "./services/seatLink";
import { startImagelessRecheck } from "./state/cardCache";
import "./styles.css";
import "./game/game.css";
import "./theme/theme.css";

(window as unknown as { __fyodorStarted?: boolean }).__fyodorStarted = true; // (index.html's too-old-browser notice stands down)
const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");

adoptSeatLink(); // a seat link's token leaves the address bar before anything renders or reads the address

// the host's own window arrives with the host secret in its address: claim it before the first API request
void claimHostSession().then(() => {
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
});
