import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ShareStatus } from "../services/share";
import { InternetInviteView, inviteStep } from "./InternetInvite";

const base: ShareStatus = { shared: false, state: "stopped", reason: null, link: null, has_password: false, available: true };
const st = (over: Partial<ShareStatus> = {}): ShareStatus => ({ ...base, ...over });
const render = (status: ShareStatus, pressed = false) =>
  renderToStaticMarkup(createElement(InternetInviteView, { status, pressed, password: "", busy: false, onPress: () => undefined, onPassword: () => undefined, onStart: () => undefined, onStop: () => undefined }));

describe("inviteStep", () => {
  it("maps the status and whether the button was pressed to a step", () => {
    expect(inviteStep(st({ available: false, reason: "Network play is off." }), false)).toBe("unavailable");
    expect(inviteStep(st(), false)).toBe("button");
    expect(inviteStep(st(), true)).toBe("password");
    expect(inviteStep(st({ has_password: true }), false)).toBe("button");
    expect(inviteStep(st({ has_password: true }), true)).toBe("existing");
    expect(inviteStep(st({ has_password: true }), true, true)).toBe("password");
    expect(inviteStep(st({ state: "starting" }), false)).toBe("starting");
    expect(inviteStep(st({ shared: true, state: "running", link: "https://x.trycloudflare.com/#/play?code=AB" }), true)).toBe("link");
    expect(inviteStep(st({ state: "failed", reason: "no" }), false)).toBe("failed");
    expect(inviteStep(st({ state: "failed", reason: "no" }), true)).toBe("password");
    // (a failed share at a table with a password: "Invite again" asks again which password, as it asks for one at a table without)
    expect(inviteStep(st({ state: "failed", reason: "no", has_password: true }), false)).toBe("failed");
    expect(inviteStep(st({ state: "failed", reason: "no", has_password: true }), true)).toBe("existing");
  });
});

describe("InternetInvite", () => {
  it("shows the reason and no button when it isn't available", () => {
    const html = render(st({ available: false, reason: "Fyodor was not started from the launcher." }));
    expect(html).toContain("Invite over the internet");
    expect(html).toContain("Fyodor was not started from the launcher.");
    expect(html).not.toContain("<button");
  });
  it("offers one button when not shared", () => {
    const html = render(st());
    expect(html.match(/<button/g)).toHaveLength(1);
    expect(html).toContain(">Invite over the internet</button>");
  });
  it("asks for a password first when the table has none", () => {
    const html = render(st(), true);
    expect(html).toContain("Table password (friends need it to join)");
    expect(html).toContain('minLength="8"');
    expect(html).toContain('maxLength="100"');
  });
  it("offers Show password on the field, and shows the text when revealed", () => {
    expect(render(st(), true)).toContain("Show password");
    const shown = renderToStaticMarkup(createElement(InternetInviteView, { status: st(), pressed: true, password: "", busy: false, reveal: true, onPress: () => undefined, onPassword: () => undefined, onStart: () => undefined, onStop: () => undefined }));
    expect(shown).toContain("Hide password");
    expect(shown).toContain('type="text"');
  });
  it("says a status read kept failing while starting", () => {
    const html = renderToStaticMarkup(createElement(InternetInviteView, { status: st({ state: "starting" }), pressed: false, password: "", busy: false, error: "Can't read the link's status: offline", onPress: () => undefined, onPassword: () => undefined, onStart: () => undefined, onStop: () => undefined }));
    expect(html).toContain("Can&#x27;t read the link&#x27;s status: offline");
  });
  it("says the tunnel program may download while starting", () => {
    expect(render(st({ state: "starting" }))).toContain("Starting the link… the first time downloads the tunnel program (about 55 MB).");
  });
  it("shows the link, Copy link, the password line and Stop sharing when running", () => {
    const html = render(st({ shared: true, state: "running", link: "https://x.trycloudflare.com/#/play?code=AB", has_password: true }));
    expect(html).toContain('value="https://x.trycloudflare.com/#/play?code=AB"');
    expect(html).toContain("readOnly");
    expect(html).toContain("Copy link");
    expect(html).toContain("Send the password separately.");
    expect(html).toContain("Stop sharing");
  });
  it("asks whether to share with the table's password or set a new one", () => {
    const html = render(st({ has_password: true }), true);
    expect(html).toContain("This table already has a password.");
    expect(html).toContain(">Share with it</button>");
    expect(html).toContain(">Set a new password</button>");
    expect(html).toContain("A new password is needed by everyone who joins from now on, on this network too. Players already seated keep their seats.");
    expect(html).not.toContain("<input");
  });
  it("asks for the new password when replacing the table's", () => {
    const html = renderToStaticMarkup(createElement(InternetInviteView, { status: st({ has_password: true }), pressed: true, replacing: true, password: "", busy: false, onPress: () => undefined, onPassword: () => undefined, onStart: () => undefined, onStop: () => undefined }));
    expect(html).toContain("New table password (friends need it to join)");
    expect(html).toContain('minLength="8"');
    expect(html).toContain("A new password is needed by everyone who joins from now on, on this network too. Players already seated keep their seats.");
  });
  it("shows the reason and Invite again when it failed", () => {
    const html = render(st({ state: "failed", reason: "The tunnel did not start." }));
    expect(html).toContain("The tunnel did not start.");
    expect(html).toContain("Invite again");
  });
});
