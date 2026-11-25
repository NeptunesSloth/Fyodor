import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { HOST_ONLY_NOTE } from "../services/hostSession";
import { GuestDoor } from "./PlayPage";

// The Play page shows GuestDoor when the host's own routes refuse this browser (no host cookie: a player's device, or the host
// computer opened by hand at http://127.0.0.1:8000). The host in the second case must read how to get the host tools back.
describe("the Play page for a browser without the host cookie", () => {
  it("says games are made on the host computer and how to open it as the host", () => {
    const html = renderToStaticMarkup(createElement(GuestDoor));
    expect(html).toContain("You&#x27;re connected to a host");
    expect(html).toContain(HOST_ONLY_NOTE);
  });
});
