# Stage 2 (invite link): audit

Branch `internet-play-stage2`. Every statement below was read or run; the command and an excerpt of its output are given. The
owner's public addresses are replaced by `<owner public IPv4>` / `<owner public IPv6>`; nothing else in an excerpt is changed
except where marked `...` (lines left out).

## Provider verification

Task 1 of the plan (`docs/superpowers/plans/2026-11-25-internet-play-stage2-invite-link.md`), run on 2026-11-25 from the owner's
Windows 11 computer, before any Stage 2 code. It settles the three facts the plan's "Provider findings" left unverified
(WebSockets through a quick tunnel, the Host header the origin receives, whether a forged `CF-Connecting-IP` is overwritten) and
the inputs later tasks need (Host rule for Task 9, `--config` for Task 13, 429s for Task 15).

**Result: no stop condition was met.** The socket worked and survived a 10-minute idle; a forged `CF-Connecting-IP` never reaches
the origin (Cloudflare refuses the request); the hostname is available from `/quicktunnel` (and from stderr, not stdout). The
origin's `Host` is the public hostname, so Task 9's Host rule stays "equals the invite hostname".

### 1. Owner acknowledgement

Put to the owner: the "Intended use" and "Uptime" rows of Provider findings, quoting Cloudflare's "Quick Tunnels are for testing
and development." and "Quick Tunnels have no uptime guarantee."

Answer, 2026-11-25: **"i accept so start 2"**. The owner accepts both; Task 2 may start.

### 2. Terms of Use (try.cloudflare.com footer)

Command: `curl.exe -sSL -A "Mozilla/5.0" https://try.cloudflare.com` (HTTP 200), footer links listed with a regex.

The footer's **Terms of Use** link is `https://www.cloudflare.com/website-terms/` (the same page the plan's Terms row cites). The
footer excerpt:

```
...<a href="https://www.cloudflare.com/disclosure/">Report Security Issues</a><a href="https://www.cloudflare.com/website-terms/">Terms of Use</a>...
```

cloudflared itself names that page as the one governing quick tunnels, on every quick-tunnel start (stderr, cloudflared 2026.10.7):

```
INF Thank you for trying Cloudflare Tunnel. Doing so, without a Cloudflare account, is a quick way to experiment and try it out.
However, be aware that these account-less Tunnels have no uptime guarantee, are subject to the Cloudflare Online Services Terms of
Use (https://www.cloudflare.com/website-terms/), and Cloudflare reserves the right to investigate your use of Tunnels for
violations of such terms. If you intend to use Tunnels in production you should use a pre-created named tunnel by following:
https://developers.cloudflare.com/cloudflare-one/connections/connect-apps
```

Command: `curl.exe -sSL -A "Mozilla/5.0" https://www.cloudflare.com/website-terms/` (HTTP 200, 417 289 bytes), tags stripped,
searched for tunnel / automat / acceptable use / prohibit / modify or discontinue. Title: "Cloudflare Website and Online Services
Terms of Use, Effective August 1, 2025". No clause names quick tunnels or Tunnel. The clauses that apply (quoted):

- "PROHIBITED USES As a condition of your use of the Websites and Online Services, you will not use the Websites or Online
  Services for any purpose that is unlawful or prohibited by these Terms."
- "You may not use the Websites or Online Services in any manner that could damage, disable, overburden, disrupt or impair any
  Cloudflare servers or APIs, ..."
- "You may not exceed or circumvent, or try to exceed or circumvent, limitations on the Websites or Online Services, including on
  any API calls, or otherwise use the Websites or Online Services in a manner that violates any Cloudflare documentation or user
  manuals."
- "We also reserve the right to modify or discontinue the Websites and/or Online Services at any time (including, without
  limitation, by limiting or discontinuing certain features of the Websites and/or Online Services) without notice to you."
- "THE WEBSITES AND ONLINE SERVICES ARE MADE AVAILABLE TO YOU ON AN "AS IS" AND "AS AVAILABLE" BASIS, ..."
- The only "automate" clause concerns abuse reports ("If you intend to automate the process by which you submit abuse reports
  ...") and does not apply.

Reading: no prohibition of a small friends' game. The third clause ties use to Cloudflare's documentation, which says "for testing
and development" (accepted by the owner, item 1) and sets the 200 in-flight request limit: Fyodor must stay under it in normal use
(item 3.5), and must not retry 429s in a way that tries to get round it.

### 3. A real quick tunnel

#### 3.0 Version chosen, download and hash

Ruling: the newest cloudflared release that is at least 14 days old on 2026-11-25 (published on or before 2026-11-11), not the
plan's 2026.11.2.

Command: `curl.exe -sS "https://api.github.com/repos/cloudflare/cloudflared/releases?per_page=15"` (the release list; `body` is
the release-notes text verbatim, `published_at` the date):

```
2026.11.2 2026-11-23T13:10:20Z      2 days old: excluded
2026.11.1 2026-11-17T15:11:01Z      8 days: excluded
2026.11.0 2026-11-12T12:23:45Z      13 days: excluded (one day short)
2026.10.7 2026-10-30T17:11:03Z      26 days: CHOSEN
2026.10.6 2026-10-29T12:18:25Z
...
```

**Chosen: 2026.10.7** (https://github.com/cloudflare/cloudflared/releases/tag/2026.10.7), the newest release at least 14 days
old; none of these is marked pre-release.

Published SHA-256 in the 2026.10.7 release notes ("SHA256 Checksums:"), for the five assets the plan uses:

| Asset | Release notes SHA-256 | GitHub asset `digest` |
|---|---|---|
| `cloudflared-windows-amd64.exe` | `2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343` | same |
| `cloudflared-darwin-amd64.tgz` | `5c55e77da7012cebca19170357e196176c48c9647cc2ead404702fa125ddbd86` | **differs:** `02f3edfd87684dd5b705607688e4eb4b323f6e777b81e7b3a85af556aa356848` |
| `cloudflared-darwin-arm64.tgz` | `2136431d5eb467bf447d2ee514b713e192719b143aec1d9e09bf7dc290d5bb12` | **differs:** `3586ccf397e98e5f437e60e7c307ca6ac463e110580503af8bb8e6f9ebf831bd` |
| `cloudflared-linux-amd64` | `1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872` | same |
| `cloudflared-linux-arm64` | `3df43aedc9ff291d1735b5cb576cb97e0b157488796db2e32b28aecabb445775` | same |

For Task 12: the two macOS archives' release-notes hashes differ from the hashes GitHub computes for the uploaded files (the
`digest` field of the release API). Every other asset in the release agrees. Task 12 must decide which to pin for macOS (download
both archives and hash them; the downloaded bytes are what the pinned hash must match) and say why. Nothing in the Windows run
depends on it.

Download, into a new empty folder, and check (the release-notes value above was copied by hand):

```
> curl.exe -sSL --fail -o <scratch>\bin\cloudflared-windows-amd64.exe https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-windows-amd64.exe
> certutil -hashfile <scratch>\bin\cloudflared-windows-amd64.exe SHA256
SHA256 hash of ...\bin\cloudflared-windows-amd64.exe:
2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343
CertUtil: -hashfile command completed successfully.
```

Equal to the release notes. Also: size 55 390 512 bytes; `Get-AuthenticodeSignature` → `Valid`, signer `CN="Cloudflare, Inc."`;
`cloudflared --version` → `cloudflared version 2026.10.7 (built 2026-10-30T09:43 UTC)`; at start cloudflared logs its own
checksum, `Version 2026.10.7 (Checksum 2493dbc1...1343)`, the same value.

Note: the Windows process name is the file name, `cloudflared-windows-amd64`, so `Get-Process cloudflared` does not find it;
cleanup checks used `Get-Process cloudflared*`. Task 13 names the binary it installs, and whatever checks for a leftover process
must use that name.

#### 3.0a Task 12: the five pins, confirmed by hand (2026-11-25)

Each asset was downloaded with `curl.exe -sSL --fail` from `https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/<asset>`
into a new empty scratch folder (deleted afterwards, nothing executed), hashed with `certutil -hashfile <file> SHA256`, and compared with
the release notes (3.0 table) and GitHub's asset `digest` (`curl.exe https://api.github.com/repos/cloudflare/cloudflared/releases/tags/2026.10.7`).
The two `.tgz` files were extracted with `tar -xzf` and the `cloudflared` member hashed.

| Asset | certutil of the download | Release notes | GitHub digest | Matched | binary_sha256 (extracted member) |
|---|---|---|---|---|---|
| `cloudflared-windows-amd64.exe` | `2493dbc1...1343` | same | same | both | = download |
| `cloudflared-linux-amd64` | `1f99fb51...1872` | same | same | both | = download |
| `cloudflared-linux-arm64` | `3df43aed...5775` | same | same | both | = download |
| `cloudflared-darwin-amd64.tgz` | `02f3edfd87684dd5b705607688e4eb4b323f6e777b81e7b3a85af556aa356848` | `5c55e77d...bd86` (no) | `02f3edfd...6848` | **GitHub digest** | `5c55e77da7012cebca19170357e196176c48c9647cc2ead404702fa125ddbd86` |
| `cloudflared-darwin-arm64.tgz` | `3586ccf397e98e5f437e60e7c307ca6ac463e110580503af8bb8e6f9ebf831bd` | `2136431d...bb12` (no) | `3586ccf3...31bd` | **GitHub digest** | `2136431d5eb467bf447d2ee514b713e192719b143aec1d9e09bf7dc290d5bb12` |

Resolution of the macOS mismatch: the release notes list the hash of the **extracted** `cloudflared` executable, not of the `.tgz`
(the extracted members hash to exactly the release-notes values). So both are pinned in `backend/app/tunnel/pins.py`: `sha256` = the
downloaded `.tgz` (GitHub's digest, what the bytes hash to), `binary_sha256` = the executable (the release-notes value). Every pinned
value therefore matches a published source and the downloaded bytes.

#### 3.0b Re-pin to 2026.11.2 (2026-11-25, owner's decision)

**Override of the 14-day rule (Ruling 3).** The owner decided on 2026-11-25 to "move to a newer release", from 2026.10.7 to 2026.11.2
(published 2026-11-23, 2 days old), overriding the plan's "newest release at least 14 days old" supply-chain rule. Reason: 2026.11.0 fixed
VULN-170057 and 2026.11.1 fixed VULN-187395 (risk 24).

Each asset was downloaded with `curl.exe -sSL --fail` from `https://github.com/cloudflare/cloudflared/releases/download/2026.11.2/<asset>`
into a new empty scratch folder (deleted afterwards, nothing executed) and hashed with `certutil -hashfile <file> SHA256`. The release-notes
values were read from the release body (`api.github.com/repos/cloudflare/cloudflared/releases/tags/2026.11.2`, field `body`) and the GitHub
`digest` from the same response. The two `.tgz` files were extracted with `tar -xzf` and the `cloudflared` member hashed. Every download matched
at least one published source.

| Asset | Size (bytes) | certutil of the download | Release notes | GitHub digest | Matched | binary_sha256 (extracted member) |
|---|---|---|---|---|---|---|
| `cloudflared-windows-amd64.exe` | 55 470 800 | `555b46c85582461d189cac30d14ad05480d612613801be9f110b8ce08c5b2113` | same | same | both | = download |
| `cloudflared-linux-amd64` | 40 334 417 | `56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf` | same | same | both | = download |
| `cloudflared-linux-arm64` | 37 820 665 | `04a7b7f08bce85d56b26ffe1fdbfbb21a074495a363d16f0783c40e25b5c5281` | same | same | both | = download |
| `cloudflared-darwin-amd64.tgz` | 21 885 875 | `6153d9ec629174882a3adbff2f7dc5a24b4f3bdd7ccc38eaa84fba26eb890311` | `870dc209...6766` (no) | `6153d9ec...0311` | **GitHub digest** | `870dc2094f98befdd993c455234562be4eee51f8fca6e2e356df4579fa7e6766` (= release notes) |
| `cloudflared-darwin-arm64.tgz` | 19 889 939 | `f6d58eeec91ad1ec5fd1f7e4a587303772929b2625be5d24068033851c36ff55` | `8654fbdc...0d55` (no) | `f6d58eee...ff55` | **GitHub digest** | `8654fbdc9057f3e13e95f7892f417f8643113bee1b91ee2388fd0acb05210d55` (= release notes) |

As for 2026.10.7, the release notes hash the extracted macOS executable and GitHub's digest the archive; both are pinned in
`backend/app/tunnel/pins.py`. The Windows exe is 55.5 MB, so "about 55 MB" in `InternetInvite.tsx` and `docs/LAN_PLAY.md` still holds.

#### 3.1 Set-up

Owner's real data was never used. The backend ran from this worktree with `FYODOR_DATA_DIR` = a new empty scratch folder holding
only a copy of `cards.sqlite` (public card data) and, for item 3.5, 100 stand-in pictures (random bytes). Also
`FYODOR_DEV_TOOLS=1`, `FYODOR_DISCOVERY=0`, `FYODOR_ALLOW_NETWORK=0`, `FYODOR_AUTO_BACKUP_MINUTES=0`. It was wrapped in a scratch
ASGI wrapper (outside the repository) that logs each request's headers to a file (cookies and `X-Seat-Token` redacted) and points
the art-folder lookup at an empty scratch folder. Port 18573 (free), loopback only:

```
python -m uvicorn --factory wrap:factory --app-dir <scratch>\scripts --host 127.0.0.1 --port 18573 --ws websockets [--no-proxy-headers]
<scratch>\bin\cloudflared-windows-amd64.exe tunnel --no-autoupdate --metrics 127.0.0.1:20299 --url http://127.0.0.1:18573
```

Phone on mobile data: **owner's manual check (Task 16 Step 5).** Instead, every "remote" request below was sent from this
computer to the public `https://<name>.trycloudflare.com` address: it leaves the machine, crosses Cloudflare's edge (`CF-Ray ...
-ATL`) and comes back through cloudflared, as a remote player's would. The host's own set-up calls (create the table, its deck,
start) went to `http://127.0.0.1:18573` directly.

#### 3.2 Hostname: `/quicktunnel` and the console

```
> curl.exe -s -i http://127.0.0.1:20299/quicktunnel
HTTP/1.1 200 OK
Date: Wed, 25 Nov 2026 23:17:55 GMT
Content-Length: 57
Content-Type: text/plain; charset=utf-8

{"hostname":"chester-champion-org-qld.trycloudflare.com"}
```

The body is JSON with one key, `hostname`, a bare name (no scheme, no port), but the `Content-Type` is `text/plain`: Task 13's
reader must parse the body as JSON whatever the header says. It answered with the hostname within 4 s of start (polled once a second); what it
answers before that was not captured, so the reader should keep polling until it gets a non-empty `hostname`.

cloudflared wrote **nothing to stdout** (0 bytes); the banner and every log line go to **stderr**:

```
2026-11-25T23:17:46Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-11-25T23:17:50Z INF +--------------------------------------------------------------------------------------------+
2026-11-25T23:17:50Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
2026-11-25T23:17:50Z INF |  https://chester-champion-org-qld.trycloudflare.com                                        |
2026-11-25T23:17:50Z INF +--------------------------------------------------------------------------------------------+
2026-11-25T23:17:50Z INF Cannot determine default configuration path. No file [config.yml config.yaml] in [~/.cloudflared ~/.cloudflare-warp ~/cloudflare-warp]
2026-11-25T23:17:50Z INF Version 2026.10.7 (Checksum 2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343)
2026-11-25T23:17:50Z INF Settings: map[ha-connections:1 metrics:127.0.0.1:20299 no-autoupdate:true protocol:quic url:http://127.0.0.1:18573]
2026-11-25T23:17:50Z INF cloudflared will not automatically update on Windows systems.
...
2026-11-25T23:17:50Z INF Starting metrics server on 127.0.0.1:20299/metrics
...
2026-11-25T23:17:50Z INF Registered tunnel connection connIndex=0 connection=21110e70-... event=0 ip=2606:4700:a8::2 location=atl13 protocol=quic
```

(stderr also logs the computer's LAN and public IPv6 addresses for its ICMP proxy, left out here.) "Registered tunnel connection"
is the line that says the tunnel can carry traffic. A brand-new name is not resolvable at once: a lookup made a few seconds after
the banner failed (curl exit 6) and the miss was then cached by the local resolver (item 3.7); the first lookup of the main tunnel's name, 18 s after its banner,
worked.
Task 13/14 should not tell the host the link works on the strength of the hostname alone.

#### 3.3 What the origin receives (Host, Origin, client address)

First run, backend **without** the hostname in `FYODOR_EXTRA_HOSTS`, plain uvicorn CLI (its proxy headers on by default):

```
> curl.exe -s -i https://chester-champion-org-qld.trycloudflare.com/api/health
HTTP/1.1 400 Bad Request
...
CF-Ray: a6045eefbcb8b82c-ATL
Server: cloudflare
...
This address is not one Fyodor answers to. Use http://<IP>:<port>, or add the name to FYODOR_EXTRA_HOSTS.
```

Fyodor's Host guard refused it, which already shows the `Host` is not `127.0.0.1:18573`. The wrapper's log of that request
(abridged to the headers; full list as received):

```
{"type": "http", "method": "GET", "path": "/api/health", "client": ["<owner public IPv6>", 0], "server": ["127.0.0.1", 18573],
 "scheme": "https", "headers": {"host": ["chester-champion-org-qld.trycloudflare.com"], "user-agent": ["curl/8.22.0"],
 "accept": ["*/*"], "accept-encoding": ["gzip"], "cdn-loop": ["cloudflare; loops=1; subreqs=1"],
 "cf-connecting-ip": ["<owner public IPv6>"], "cf-ew-via": ["15"], "cf-ipcountry": ["US"], "cf-ray": ["a6045ef0dcdcde5c-ATL"],
 "cf-visitor": ["{\"scheme\":\"https\"}"], "cf-warp-tag-id": ["5781dcc5-..."], "cf-worker": ["trycloudflare.com"],
 "connection": ["keep-alive"], "x-forwarded-for": ["<owner public IPv6>"], "x-forwarded-proto": ["https"]}, "status": 400}
```

**`Host` = the public hostname** (`chester-champion-org-qld.trycloudflare.com`, no port). cloudflared passes the visitor's Host
through when `--http-host-header` is not set.

Note the `client` and `scheme` in that record: the uvicorn CLI's default `--proxy-headers` (trusting `127.0.0.1`) rewrote the peer
to the `X-Forwarded-For` value and the scheme to `https`. That is what the plan's `"proxy_headers": False` in `server_options`
(launcher) prevents; it is needed, as planned. All later runs used `--no-proxy-headers`, i.e. what Fyodor's launcher will see.

Second run, backend restarted with `FYODOR_EXTRA_HOSTS=chester-champion-org-qld.trycloudflare.com`,
`FYODOR_CORS_ORIGINS=https://chester-champion-org-qld.trycloudflare.com`, `--no-proxy-headers` (cloudflared left running):

```
> curl.exe -s -i https://chester-champion-org-qld.trycloudflare.com/api/health
HTTP/1.1 200 OK
...
{"status":"ok","version":"0.1.0","card_database":{"available":true,"printings":116886,...},"games_active":0,"assistant_enabled":false}
```

What the origin received, per tunnelled request (wrapper log, summarised one line each):

```
http GET  /api/health             client=127.0.0.1:62123 scheme=http status=200 | host=chester-champion-org-qld.trycloudflare.com origin=                                                   cf-connecting-ip=<owner public IPv6> xff=<owner public IPv6> xfp=https
http POST /api/join               client=127.0.0.1:52856 scheme=http status=200 | host=chester-champion-org-qld.trycloudflare.com origin=https://chester-champion-org-qld.trycloudflare.com cf-connecting-ip=<owner public IPv6> xff=<owner public IPv6> xfp=https
http POST /api/games/<id>/lobby/deck  status=403 | origin=https://evil.example  (the Origin guard refused: {"detail":"Cross-site request refused"})
websocket /ws/games/<id>          client=127.0.0.1:55218 scheme=ws status=ws-accept | host=chester-champion-org-qld.trycloudflare.com origin=https://chester-champion-org-qld.trycloudflare.com upgrade=websocket xfp=https
websocket /ws/games/<id>          close=4403 | origin=https://evil.example
```

- `Host`: the public hostname, on plain requests and on the socket upgrade.
- `Origin`: what the visitor's client sent (`https://<hostname>` from a page on that address), passed through unchanged. With
  `FYODOR_CORS_ORIGINS=https://<hostname>`, state-changing requests and the socket were accepted; a foreign Origin was refused
  (403, and the socket upgrade refused with HTTP 403 before accept).
- Peer (`client`): always `127.0.0.1` (cloudflared), as the plan assumes; `scheme` is `http`/`ws` at the origin.
- `CF-Connecting-IP`: the visitor's address as Cloudflare saw it.
- `X-Forwarded-For`: the visitor's address (see 3.4 for a forged one).
- `X-Forwarded-Proto`: `https` (also `cf-visitor: {"scheme":"https"}`).
- Also present: `cdn-loop`, `cf-ew-via`, `cf-ipcountry`, `cf-ray`, `cf-warp-tag-id` (= the cloudflared connector id),
  `cf-worker: trycloudflare.com`.

#### 3.4 Forged `CF-Connecting-IP` and `X-Forwarded-For`

Each case one request through the tunnel (`curl.exe -H ... https://<hostname>/api/health`); "origin" is what the wrapper logged.
400 = it reached Fyodor (the first, host-refusing backend); 200 = it reached Fyodor (the second backend).

| Request header(s) sent | Answer | What the origin received |
|---|---|---|
| `CF-Connecting-IP: 1.2.3.4` | **403 from Cloudflare, `error code: 1000`** | nothing: never reached cloudflared or the origin |
| `CF-Connecting-IP: 1.2.3.4` + `X-Forwarded-For: 1.2.3.4` | 403, `error code: 1000` | nothing |
| `CF-Connecting-IP: <owner's real public IPv6>` | 403, `error code: 1000` | nothing |
| `X-Forwarded-For: 1.2.3.4` | 400 / 200 (reached Fyodor) | `x-forwarded-for: 1.2.3.4,<owner public IP>`; `cf-connecting-ip: <owner public IP>` |
| `X-Forwarded-Proto: http` | reached Fyodor | `x-forwarded-proto: https` (overwritten) |
| `True-Client-IP: 1.2.3.4` | reached Fyodor | `true-client-ip: 1.2.3.4` **passed through unchanged** |
| `X-Real-IP: 1.2.3.4` | reached Fyodor | no `x-real-ip` header |
| none | reached Fyodor | `cf-connecting-ip` = `x-forwarded-for` = the visitor |

The forged-`CF-Connecting-IP` answer as received:

```
HTTP/1.1 403 Forbidden
...
Server: cloudflare
CF-RAY: a6045ef2b9fbc84c-ATL

error code: 1000
```

**The forged `CF-Connecting-IP` never reaches the origin**: Cloudflare refuses any request that carries the header at all, even
with the sender's true address. So at the origin `CF-Connecting-IP` is always Cloudflare's own value. A forged `X-Forwarded-For`
is kept and the real address appended: only its rightmost entry is trustworthy. `True-Client-IP` is not trustworthy (passed
through). `X-Forwarded-Proto` is overwritten with `https`.

For Fyodor (Task 9 and later): behind the tunnel the client address for limits is `CF-Connecting-IP` (or the rightmost
`X-Forwarded-For` entry); never `True-Client-IP` or any leftmost entry.

#### 3.5 Game socket: auth, an action, a 10-minute idle

Script `play.py` (scratch, Python `websockets` 17.4 with `ping_interval=None`, so only Fyodor's own JSON `ping`/`pong` keeps the
socket alive, as in a browser). A Sandbox LAN lobby (2 seats) was created and started by the host locally; Bob joined, sent his
deck and opened his socket **through the tunnel**. Output of the run (`play.py <hostname> 18573 <scratch data> 600`):

```
[    0.5s] claim host (local) 204
[    0.5s] create lobby (local) 201
[    1.0s] join via tunnel 200
[    1.6s] Bob's deck via tunnel 200
[    1.7s] same call with a foreign Origin via tunnel (expect refusal) 403 {"detail":"Cross-site request refused"}
[    2.1s] Alice's deck (local) 200
[    2.1s] start (local) 200
[    2.1s] Alice keeps (local) 200
[    2.1s] game 8c48370fd47d7a49
[    2.6s] foreign-Origin socket via tunnel: InvalidStatus None None server rejected WebSocket connection: HTTP 403
[    2.9s] Bob socket open via tunnel; response headers: 101 [('Date', 'Wed, 25 Nov 2026 23:22:43 GMT'), ('Connection', 'upgrade'), ('Upgrade', 'websocket'), ('Sec-WebSocket-Accept', 'dixwA3MHZS0jUmEGdH/zWP3L1Pk='), ('CF-Ray', 'a60465a6693931f9-ATL'), ('CF-Cache-Status', 'DYNAMIC'), ('Server', 'cloudflare'), ('X-Robots-Tag', 'none'), ('X-Robots-Tag', 'none')]
[    3.0s] first message: state viewer p2
[    3.0s] Bob mulligan_keep -> ack
[    3.0s] Bob's hand: ['Mountain', 'Mountain', 'Mountain', 'Mountain', 'Mountain', 'Mountain', 'Mountain']
[    3.1s] Bob plays a Mountain (move to battlefield) -> ack  | battlefield 0 -> 1 | land on battlefield: True
[    3.1s] idle 600s, answering pings only
[   93.0s] silent socket (never answers) closed after 90.1s: code=4408 reason='Idle'; pings heard 3
[   93.0s] during idle got state
[  153.6s] during idle got state
[  603.1s] idle over: 23 pings at [24.9, 49.9, 74.9, 99.9, 124.9, ..., 550.0, 575.0]; gaps [25.0, 25.0, ..., 25.0]
[  603.2s] after idle, Bob draw -> ack  | hand 7
[  603.2s] Bob socket still open: OPEN
```

- Upgrade through the tunnel: `101`, served by Cloudflare (`Server: cloudflare`, `CF-Ray`). The `auth` first message was
  accepted and the first message back was the table (`state`, viewer `p2`).
- Actions applied over the socket: `mulligan_keep`, then a Mountain played (a Sandbox table has automation off, so a land is
  played with the table tools' move to the battlefield; `play_land` answers "Rules automation is off at this table", as it
  should), then after the idle a `draw` (hand 6 → 7). Each got its `ack` and a new `state`.
- **10-minute idle (600 s)**: the socket stayed open the whole time; the server's `{"type":"ping"}` arrived every 25.0 s
  (23 pings, every gap 25.0-25.1 s), each answered with `{"type":"pong"}`. That is well past both Fyodor's 90 s idle close and
  the 100 s idle timeout Cloudflare documents for proxied connections (not measured on its own here): the JSON ping/pong is traffic enough for the edge.
- A second socket (Alice's seat, same tunnel) that never answered was closed by Fyodor after 90.1 s with **code 4408, reason
  "Idle"**, and the client saw that code (not 1006): close codes and reasons cross the tunnel intact.
- A socket with `Origin: https://evil.example` was refused before accept (HTTP 403 to the client; the wrapper logged close 4403).
- The two "during idle got state" lines are Fyodor's presence broadcasts after Alice's socket closed (at once, then after the
  reconnect grace), not traffic from Bob.

(A 5-second dry run before this one, game `24c7e687a7097e15`, gave the same results for the socket, the 4408 close and the Origin
refusal.)

#### 3.6 Four tabs opening a 100-card table: 429s

Script `burst.py` (scratch, httpx, HTTP/1.1: neither curl nor httpx here has HTTP/2). 100 real printing ids from `cards.sqlite`
were given stand-in pictures (70 KB of random bytes each) in the scratch data folder, so `/api/images/<id>?size=normal` answers
200 with a body. Each "tab" is its own client asking for all 100 pictures at once, tabs released together; between runs 10 s.

```
> python burst.py run <hostname> <scratch data> <label> <tabs> [<connections per tab>]
[realistic]                 400 requests from 4 tabs in 5.5s;  statuses {'200': 203, '429': 197}; latency ms min 1000 median 1469 max 5359
  non-200 sample: {"tab": 2, "status": 429, "ms": 1063, "bytes": 0, "cf_ray": "a604749b8fd6b072-ATL", "retry_after": null, "server": "cloudflare", "body": ""}
[one-tab-100conns]          100 requests from 1 tabs in 2.0s;  statuses {'200': 100}; latency ms min 359 median 1735 max 1921
[four-tabs-6conns]          400 requests from 4 tabs in 11.9s; statuses {'200': 400}; latency ms min 328 median 7593 max 11735
[two-tabs-100conns]         200 requests from 2 tabs in 6.0s;  statuses {'200': 200}; latency ms min 609 median 5375 max 5860
[four-tabs-100conns-repeat] 400 requests from 4 tabs in 4.3s;  statuses {'200': 212, '429': 188}; latency ms min 1062 median 1484 max 4141
  non-200 sample: {"tab": 0, "status": 429, "ms": 1172, "bytes": 0, "cf_ray": "a60476b37eed4f7b-ATL", "retry_after": null, "server": "cloudflare", "body": ""}
```

**429s appeared**: four tabs each opening the 100-card table with up to 100 requests in flight got 197 and 188 answers 429 out of
400 (about everything beyond 200 in flight), in both runs. One tab (100 in flight), two tabs (200) and four tabs limited to 6
connections each (24 in flight, a browser's HTTP/1.1 behaviour) got none. The 429 comes from Cloudflare's edge, not Fyodor:
`Server: cloudflare`, a `CF-Ray`, **no `Retry-After`**, an **empty body**; the origin never saw those requests (after the first
run the wrapper had logged 204 image requests, all 200: the 203 the run got plus one local check).

A browser talks HTTP/2 to Cloudflare and multiplexes every tab's requests on one connection, so how many are in flight at once
depends on the browser and the edge's stream limit, not on 6-per-host. The run that matters for Task 15 is the first: a burst
above 200 is refused at once, silently, without a retry time. **For Task 15: the client must keep its own image requests in
flight well under 200 for the whole table (all of a player's tabs share the tunnel's 200), and treat a 429 with no
`Retry-After` and an empty body as "retry later, with back-off", not as a missing picture.** A planned second run with a
deliberately slow origin (to force 429s) was not needed: the realistic run already produced them.

#### 3.7 `--config` and a `config.yaml` in `.cloudflared`

To keep the owner's profile untouched, each case ran cloudflared with `USERPROFILE`/`HOME` pointing at a scratch folder
(`<scratch>\cfhome`) and a planted `<scratch>\cfhome\.cloudflared\config.yaml`; that cloudflared reads that folder as `~` is shown
by its `Settings:` line, which lists the planted file's keys. Nothing listened on the `--url` port (18599), so a tunnel that
honours `--url` answers **502** (cloudflared cannot reach the origin), and one that follows the planted ingress answers **404**.
The new name was probed with `curl.exe --resolve <name>:443:104.16.230.132` (a Cloudflare edge address), because a brand-new
name is not in DNS yet. Script `cfg-case.ps1`:
`cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:<port> [--config <file>] --url http://127.0.0.1:18599`.

| Case | `config.yaml` in `~\.cloudflared` | `--config` | Quick tunnel created (`/quicktunnel`) | `Settings:` line | Probe |
|---|---|---|---|---|---|
| Baseline (item 3.2) | none | none | yes | no config keys; "Cannot determine default configuration path. No file ..." | served `--url` |
| A | `no-autoupdate: true` | none | yes | (no "Cannot determine" line: the file was read) | **502** (`--url` honoured) |
| A2 | a named tunnel's: `tunnel: <uuid>`, `credentials-file: ...`, `ingress:` (`hostname: fyodor.example.com` → `http://127.0.0.1:8000`; catch-all `http_status:404`) | none | **yes** (`{"hostname":"crest-scholars-administrators-darwin.trycloudflare.com"}`) | `map[cred-file:... credentials-file:... ha-connections:1 metrics:... no-autoupdate:true protocol:quic url:http://127.0.0.1:18599]` | **404: the quick tunnel served the planted ingress, not `--url`** |
| B | the same named-tunnel file | `<scratch>\notes\empty.yml` (0 bytes) | yes | `ERR Configuration file ...\empty.yml was empty` then `map[config:...\empty.yml ha-connections:1 metrics:... no-autoupdate:true protocol:quic url:...]` (no cred-file) | **502** (`--url` honoured) |
| C | none (real profile; `%USERPROFILE%\.cloudflared` does not exist) | the empty file | yes | as B | started (probe not resolvable in time, see 3.2) |

Findings for Task 13:

- A `config.yaml` in `.cloudflared` does **not** stop a quick tunnel from starting, and `/quicktunnel` still hands out a hostname;
  but a config with `ingress` rules silently takes over routing, so the invite link would answer 404 (or reach whatever the
  owner's named tunnel points at). This is worse than the "not supported" the plan's Config conflict row expected: it fails
  quietly.
- **`--config <an empty file Fyodor owns>` fixes it**: the default config is not read and `--url` is honoured. cloudflared logs one
  `ERR Configuration file ... was empty` line and carries on; Task 13 must not treat that line as a failure. **Decision: Task 13
  always passes `--config <empty file>`.**
- Task 13/14 should check that the tunnel reaches Fyodor (e.g. its own `/api/health` through the public name, or the first request
  arriving on the tunnel port) rather than trusting `/quicktunnel` alone.

#### 3.8 `cloudflared --help`: `--no-autoupdate` and `--metrics`

From `cloudflared tunnel --help` (2026.10.7; the top-level `--help` does not list these flags):

```
   --no-autoupdate          Disable periodic check for updates, restarting the server with the new version. (default: false) [%NO_AUTOUPDATE%]
   --autoupdate-freq value  Autoupdate frequency. Default is 24h0m0s. (default: 24h0m0s)
   --metrics value          Listen address for metrics reporting. If no address is passed cloudflared will try to bind to [localhost:20241 localhost:20242 localhost:20243 localhost:20244 localhost:20245].
  If all are unavailable, a random port will be used. Note that when running cloudflared from an virtual
  environment the default address binds to all interfaces, hence, it is important to isolate the host
   --config value           Specifies a config file in YAML format.
   --http-host-header --url Sets the HTTP Host header for the local webserver. ...
```

The flag is accepted after `tunnel` (`Settings: map[... no-autoupdate:true ...]`), and on Windows cloudflared also says
"cloudflared will not automatically update on Windows systems." Keep `--no-autoupdate` anyway (macOS/Linux). `--metrics` must
always be given an explicit `127.0.0.1:<port>` (the help warns the default can bind all interfaces in a virtual environment).

### 4. Stop conditions

| Stop condition | Result |
|---|---|
| WebSocket fails or drops before the 90 s idle close | **Not met.** Upgrade 101, auth accepted, actions applied, open after a 600 s idle with 25 s pings (3.5). |
| The origin receives the forged `CF-Connecting-IP` | **Not met.** Cloudflare answers 403 `error code: 1000` to any request carrying the header; nothing reaches cloudflared or the origin (3.4). |
| Hostname not available from `/quicktunnel` or stdout | **Not met.** `/quicktunnel` gives `{"hostname":"<name>.trycloudflare.com"}` within 4 s. (The banner is on **stderr**; stdout stays empty.) (3.2) |

Not a stop condition, recorded: the origin's `Host` **is** the public hostname (`chester-champion-org-qld.trycloudflare.com`, no
port). **Task 9's Host rule stays "equals the invite hostname"** (and Origin is compared to `https://<invite hostname>`).

What later tasks take from this section:

- **Task 9**: Host = invite hostname. Peer is always `127.0.0.1`; client address for limits from `CF-Connecting-IP` (or the
  rightmost `X-Forwarded-For` entry), never `True-Client-IP` or a leftmost XFF entry. `proxy_headers=False` is needed (3.3).
- **Task 12**: pin **2026.10.7** (newest release at least 14 days old); hashes in 3.0; resolve the two macOS archive mismatches.
- **Task 13**: always `--no-autoupdate --metrics 127.0.0.1:<port> --config <empty file> --url http://127.0.0.1:<tunnel port>`;
  read the hostname from `/quicktunnel` (JSON body, `text/plain` header); read logs from stderr; ignore the one
  `ERR Configuration file ... was empty` line; the Windows process is named after the file (3.0, 3.7, 3.8).
- **Task 15**: 429s did appear (4 tabs × 100 in flight); keep image requests in flight well under 200 and retry 429s with back-off
  (no `Retry-After` is sent) (3.6).

### 5. Cleanup

The tunnel was up from 23:17:45 to about 23:36 UTC, only while measuring. Then the backend (both its processes) and cloudflared were
stopped by process id (other Python work on the computer was left alone), and:

```
> Get-Process cloudflared* -ErrorAction SilentlyContinue      (nothing)
> Get-NetTCPConnection -State Listen -LocalPort 18573,20299   (nothing)
> curl.exe -s -o NUL -w "%{http_code}" https://chester-champion-org-qld.trycloudflare.com/api/health
530
> Test-Path <scratch>\data      -> False   (scratch data folder deleted: cards.sqlite copy, stand-in pictures, app.sqlite, host.secret)
> Test-Path <scratch>\cfhome    -> False   (planted config.yaml folder deleted)
> Test-Path <scratch>\bin       -> False   (downloaded binary deleted; Task 12 downloads its own)
> Test-Path %USERPROFILE%\.cloudflared -> False   (never created)
```

(Right after cloudflared stopped the name answered 502 once, then 530: the name is dead.) Only the scratch scripts and logs
remain, outside the repository.

## Stage gate (Task 16)

Run on 2026-11-25 at `9439005` (Stage 2 head; base `9eb1e71`, the tip of `internet-play-stage1`, plus the two plans in `3b77fbb`).
Backend tools ran from `backend/` with Fyodor-main's environment (`..\Fyodor-main\backend\.venv\Scripts\`, `PYTHONPATH` set to
this worktree's `backend`). The base counts came from a temporary `git worktree add --detach <temp> 9eb1e71`, run the same way and
removed afterwards (`git worktree remove`).

### Gate results

| Check | Command | Stage 2 head `9439005` | Base `9eb1e71` | Verdict |
|---|---|---|---|---|
| ruff | `ruff check . --output-format concise` | `Found 10 errors.` | `Found 10 errors.` | **No new error.** The two lists are identical line for line (`diff` of the two outputs is empty): I001 ×5 (`app/game/engine.py:3`, `app/game/handlers/dummy.py:98`, `app/game/views.py:9`, `tests/conftest.py:1`, `tests/test_rules_layer_whole_conditions.py:8`), SIM102 ×3 (`app/rules/costs.py:287`, `random_choice_receipts.py:261`, `taught.py:266`), F841 (`tests/test_rules_round5_additional_costs.py:189`), SIM300 (`tests/test_rules_token_batch_one_pile.py:49`). |
| mypy | `python -m mypy app tools` | `Found 303 errors in 15 files (checked 1189 source files)` | `Found 303 errors in 15 files (checked 1183 source files)` | **No new error.** The messages are identical once line numbers are removed (`sed -E 's/:[0-9]+: /: /'`, sorted, `diff` empty). The six extra files checked are the new `app/api/share.py` and `app/tunnel/*.py` (five files): none has an error. |
| Full backend suite | `python -m pytest -n 4 -q` (controller) | **FULL SUITE: PASSED** at f10604c (exit 0, 0 failed) | | The controller runs it (one run at a time on this machine, ledger Ruling 4); its result goes on this line. |
| Frontend typecheck | `npm run typecheck` (`tsc -b --noEmit`) in `frontend/` | exit 0 | | Pass. |
| Frontend tests | `npm test` in `frontend/` | `Test Files 161 passed (161)`, `Tests 1633 passed (1633)` | | Pass. |

### Security tools

**bandit** (`bandit -r app -q`; also `-f json` for the line check below): 794 findings, **8 High, 27 Medium, 759 Low**, 202,765 lines
scanned. Stage 1's run found 790 (8 High, 27 Medium, 755 Low): the only change is four Low findings. To find which findings sit on
lines this stage added, the added lines of `git diff -U0 9eb1e71..HEAD -- backend/app` (1,218 lines) were matched against each
finding's file and line (a throwaway script in the scratchpad): exactly those four.

| Finding | Where | Answer |
|---|---|---|
| B404 import subprocess | `app/tunnel/manager.py:10` | Accepted because the tunnel has to run `cloudflared` as a child process; the only call is the B603 line below. |
| B404 import subprocess | `app/tunnel/process.py:8` | Accepted: same reason (the module uses `subprocess.Popen` in types and `TimeoutExpired`). |
| B603 subprocess without shell | `app/tunnel/manager.py:112` | Accepted because the program is the pinned `cloudflared`, its SHA-256 checked (`binary.verify`) just before this call, run without a shell with a fixed argument list (`process.command`: `tunnel --no-autoupdate --config <empty file> --metrics 127.0.0.1:<port> --url http://127.0.0.1:<tunnel port>`) built from integers and Fyodor's own paths; no request text reaches it. Tests: `test_tunnel_process.py::test_command_disables_autoupdate_and_pins_metrics_to_loopback`, `::test_a_program_that_fails_verification_is_not_started`. |
| B101 assert | `app/tunnel/manager.py:74` | Accepted: `assert self._loop is not None` narrows a type for mypy after `start()` has set it. Under `python -O` it would vanish and a missing loop would raise `AttributeError` instead, which `_start` treats as a failure (state `failed`): never a grant. |

The plan expected the `ctypes` lines of `app/tunnel/process.py` among the findings; bandit 1.9.4 raises none for them. The other
790 findings are on lines from before this stage and were answered in the Stage 1 audit ("Security tools").

**pip-audit** (`pip-audit`, Fyodor-main's environment): `Found 12 known vulnerabilities in 1 package`: six advisories, each listed
twice, all in `pip` 25.0.1 (PYSEC-2026-1795 → 25.3, PYSEC-2026-1796 → 26.0, PYSEC-2026-2875 and -2876 → 26.1, PYSEC-2026-196 → 26.1.2,
PYSEC-2026-3721 → 26.2). `fyodor-backend` itself is skipped (not on PyPI). None is on a line this stage added: Stage 2 adds no Python
or npm dependency (`git diff 9eb1e71..HEAD -- backend/pyproject.toml frontend/package.json frontend/package-lock.json | wc -l` → 0).
Accepted because `pip` is the development environment's installer, not part of Fyodor; it is Stage 1's open item (Stage 1 audit, risk
11), unchanged.

**npm audit** (`npm audit` in `frontend/`): 4 vulnerabilities (2 moderate, 2 high): `vite` 8.3.0–8.3.2 (high; GHSA-698v-4r3x-3vcv,
GHSA-r825-w8mm-5pxw, GHSA-587h-7wmj-h5pm (launch-editor), GHSA-9jrq-w75r-8gcw, GHSA-rq7h-c2jc-7f22, GHSA-vfpm-58rq-9qcg (dev server)),
`source-map-js` ≤ 1.2.1 (high, GHSA-68fv-2mgg-jv7q), `vitest` and `@vitest/mocker` ≤ 5.0.2 (moderate, GHSA-qxg6-89mg-rqv8,
GHSA-xp26-3454-mjgp). `npm audit --omit=dev`: `found 0 vulnerabilities`. None is on a line this stage added (no package change).
Accepted because each is a development or build tool, never shipped; they are Stage 1's open dependency upgrades (risk 11), still
open. (The `vite` entry lists more advisories than Stage 1 recorded: new advisories against the same installed version.)

### The 13-point review gate

The spec's "Review gate (every stage)" (`docs/superpowers/specs/2026-11-21-internet-play-design.md`). File and line numbers are as
of `9439005`. Every test named is in the full backend run, which is pending (above).

1. **Met.** No new route trusts a client-supplied seat or game id: the tunnel port reuses `authorize` / `Room.seat_for_token`, and
   every host decision goes through `room_host` / `is_host_request`, both false on the tunnel port (`deps.py:79`). Tests:
   `test_tunnel_identity.py::test_host_cookie_is_not_host_on_the_tunnel_port`, `::test_room_host_token_is_not_host_on_the_tunnel_port`;
   `test_tunnel_routes.py::test_unshared_room_is_no_such_room`, `::test_an_unshared_room_cannot_be_joined_by_its_code_through_the_tunnel`,
   `::test_the_host_computer_on_the_tunnel_port_is_a_stranger`; `test_share_api.py::test_only_the_host_cookie_shares`; SR1 (`0a0cd16`):
   `test_host_seat_guard.py` (four tests, see "Stage 2 must" below).
2. **Met.** The tunnel serves the same per-viewer views; new paths: shared rooms only, codes hidden there, the invite code in no view.
   Tests: `test_shared_rooms.py::test_views_say_shared_and_never_the_invite_code` (walks a seated view, a spectator view, the lobby view
   and `GET /api/games`), `::test_discovery_never_advertises_the_invite`;
   `test_tunnel_routes.py::test_games_list_and_summary_hide_codes_on_the_tunnel_port`, `::test_shared_room_plays`;
   `test_tunnel_identity.py::test_a_seat_reconnects_from_a_new_address`; dropped spectators:
   `test_spectator_cap.py::test_33_spectators_leave_32_and_the_first_is_refused`. Accepted and documented (`netguard.py:129-135`): on a
   shared table a stranger can read its summary (no code), `GET …/result` and `GET /api/macros`. Since the final fix wave (M8) no
   lobby or table view sent to a tunnel connection or answering a tunnel request carries the LAN code
   (`test_share_api.py::test_the_lan_code_never_reaches_a_tunnel_connection`: HTTP lobby, ready, view and action replies, and the
   socket's first message, broadcasts, deltas and resync; the LAN's views keep it).
3. **Met.** `git grep -n "[?&]token=\|[?&]seat_token=" -- backend/app frontend/src ':!*.test.*'` → `games.py:1808` (the seat link,
   token after `#`), `games.py:1989` (a comment: a `?token=` is never credentials) and two comment lines in
   `frontend/src/services/seatLink.ts`. The legacy switch is gone (`git grep -n -i "legacy_ws_token\|LEGACY_WS" -- backend/app
   frontend/src` → nothing; `test_socket_auth.py::test_a_token_in_the_query_is_never_credentials`). The invite link is
   `https://<host>/#/play?code=<invite code>&join=1`: the invite code sits after `#` and it carries no seat or host token
   (`test_share_api.py::test_share_returns_the_link_with_the_invite_code`). The stage adds two log lines, both constant text
   (`manager.py`: "The tunnel could not be started", "Handling the internet link going down failed"); cloudflared's output goes to
   DEVNULL and is never read or logged.
4. **Met, one note.** The invite code is 10 characters by `secrets.choice` (`hub.py:444`), unique against every room's codes
   (`test_shared_rooms.py::test_invite_code_is_ten_characters_of_the_alphabet`, `::test_invite_code_avoids_every_room_code`), compared
   with `hmac.compare_digest` (`hub.py:476`, ASCII-guarded at `:473`; `::test_non_ascii_code_is_the_normal_refusal_on_the_lan_port`,
   `::test_non_ascii_token_matches_nothing`). The pinned hashes are compared with `hmac.compare_digest` (`binary.py`). Note (final fix
   wave, M5 and I3): the invite code is kept while the table is shared (`::test_invite_code_is_kept_once_made`) and cleared by **Stop
   sharing** (`Services._end_share`), so every new share has a new code
   (`test_share_api.py::test_every_new_share_has_a_new_invite_code`); sharing with a password replaces the table's
   (`::test_sharing_with_a_new_password_replaces_the_tables`). The hostname is new on the next share only when no other table was
   shared (the tunnel stays up while any table is). Revocation: **Stop sharing** (a new code), a new password, or closing the table
   (risk 8 below).
5. **Met.** No secret is configured or defaulted; a shared table must have a password
   (`test_share_api.py::test_sharing_needs_a_password`, `test_shared_rooms.py::test_set_password_refuses_an_empty_password`).
6. **Met.** `ShareIn.password`: 8–100 characters (`test_share_api.py::test_a_short_password_is_422`); like the other request bodies
   (`JoinIn`) it does not forbid extra fields (pydantic ignores them). Header and tool input: `CF-Connecting-IP` is parsed by
   `cf_client_key`, anything unparseable goes to one shared bucket (`test_tunnel_identity.py::test_cf_client_key`); cloudflared's
   hostname must fullmatch `[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com`
   (`test_tunnel_process.py::test_a_hostname_that_is_not_trycloudflare_fails_closed`); the download stops at 150 MB
   (`test_tunnel_binary.py::test_download_stops_at_the_size_cap`); archive members with a path or a link are refused
   (`::test_archive_member_with_a_path_is_refused`); bodies on the tunnel port are limited to 256 KB except a seat's lobby allowance
   for the shared table (final fix wave, I1: `test_body_limit.py::test_on_the_tunnel_port_a_seat_keeps_the_lobby_allowance` — a
   tunnel seat's 1,800-entry collection reaches the route, a stranger, a made-up token and another table's seat get 256 KB;
   `::test_no_host_or_any_allowance_on_the_tunnel_port`). (The earlier `test_no_allowance_on_the_tunnel_port` asserted the I1
   regression and was rewritten.) A password typed when sharing replaces a table's existing one, so the 8-100 rule can be applied
   to any table before it is shared; the panel asks the host when the table already has one (I3, risk 8).
7. **Met.** `git diff 9eb1e71..HEAD -- frontend/src | grep "^+.*\(innerHTML\|dangerouslySetInnerHTML\|javascript:\)"` → nothing; the
   link is shown in an `<input readOnly value=…>`. New log lines: two, constant text (point 3).
8. **Met in substance; deviates in letter once.** `git diff 9eb1e71..HEAD -- backend/app | grep -n "^+.*\(except\|suppress\)"`: every
   added handler refuses, fails or re-raises:
   - `except Exception as exc:` in `TunnelManager._start` (`manager.py:77`): sets `state = "failed"` and a reason, logs an error that is
     not `TunnelUnavailable`, then `raise`s. It is the one literal "new `except Exception`" the gate forbids; it swallows nothing.
     **Accepted deviation** (final review, open item 1): it is load-bearing for fail-closed (without it, any other failure in
     `_launch` would leave `state == "starting"` for ever). It carries `# noqa: BLE001` with that reason (final fix wave, M7).
   - `except BaseException:` twice (`manager.py`, ending a half-started process; `process.py`, closing the job handle): clean up and
     `raise`.
   - `contextlib.suppress(RuntimeError)` around `loop.call_soon_threadsafe` (the loop closed in between: nothing left to notify).
   - The rest are typed: `TunnelUnavailable` → 502 (`share.py`); `HTTPException` → stop an unused tunnel and `raise`; `ValueError` → the
     shared unknown bucket (`netguard.py`); `OSError` → `verify` is false / `TunnelUnavailable`; `httpx.HTTPError`, `tarfile.TarError` →
     `TunnelUnavailable`; `subprocess.TimeoutExpired` → kill; `(httpx.HTTPError, ValueError, RecursionError, AttributeError)` → keep
     polling, then time out (fails closed).
   Fail-closed routing: the tunnel allowlist is frozen (71 method/route pairs, checked both ways,
   `test_tunnel_routes.py::test_every_route_is_either_allowed_or_404_on_the_tunnel_port`); a stopped tunnel serves nothing
   (`::test_tunnel_port_serves_nothing_when_stopped`).
9. **Met.** No new Python or npm dependency (command in "Security tools" → 0 lines). One downloaded binary: **cloudflared 2026.11.2** (re-pinned from 2026.10.7, section 3.0b)
   (the newest release at least 14 days old on 2026-11-25, section 3.0), pinned in `backend/app/tunnel/pins.py` by version and SHA-256,
   verified after download and again before every launch (`binary.verify`). The five hashes (`sha256` = the download, `binary_sha256` =
   the executable):
   - `cloudflared-windows-amd64.exe` `2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343` (both)
   - `cloudflared-linux-amd64` `1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872` (both)
   - `cloudflared-linux-arm64` `3df43aedc9ff291d1735b5cb576cb97e0b157488796db2e32b28aecabb445775` (both)
   - `cloudflared-darwin-amd64.tgz` `02f3edfd87684dd5b705607688e4eb4b323f6e777b81e7b3a85af556aa356848`, executable
     `5c55e77da7012cebca19170357e196176c48c9647cc2ead404702fa125ddbd86`
   - `cloudflared-darwin-arm64.tgz` `3586ccf397e98e5f437e60e7c307ca6ac463e110580503af8bb8e6f9ebf831bd`, executable
     `2136431d5eb467bf447d2ee514b713e192719b143aec1d9e09bf7dc290d5bb12`
   The two independent checks of Task 12 Step 1 (section 3.0a): each asset was downloaded and hashed with `certutil -hashfile`, and the
   hash compared with (a) the release notes' "SHA256 Checksums:" and (b) GitHub's asset `digest` from the release API; the macOS archives
   match (b) and their extracted `cloudflared` matches (a). The Task 12 reviewer re-fetched the release API and confirmed every pin.
   (`git grep -n "2493dbc1\|02f3edfd\|3586ccf3\|1f99fb51\|3df43aed" -- backend/app/tunnel/pins.py` finds each.) Tests:
   `test_tunnel_binary.py::test_pins_are_well_formed`, `::test_a_wrong_hash_leaves_nothing_and_raises`,
   `::test_a_replaced_binary_fails_verify`, `::test_archive_whose_member_hash_differs_is_refused`,
   `test_tunnel_process.py::test_a_program_that_fails_verification_is_not_started`.
10. **Met, with the RED evidence as the ledger records it.** Each task's report holds its RED/GREEN runs; the weak ones: Task 7's RED was
    only an ImportError; Task 11's non-ASCII guard test was not seen RED (its re-review showed a 500 without the guard); two of Task 4's
    tests are regression guards that passed from the start. Negative cases: wrong seat (point 1); replaced or dropped token
    (`test_spectator_cap.py::test_the_dropped_spectators_socket_closes_4403`, Stage 1's reclaim tests); foreign Origin on the tunnel
    (`test_tunnel_routes.py::test_no_origin_post_is_refused_on_the_tunnel_port`, `::test_http_origin_is_refused_on_the_tunnel_port`) and
    for the development origins (`test_origin_guard.py::test_dev_origins_are_refused_by_default`); forged `X-Forwarded-For`
    (`test_launcher.py::test_a_real_server_ignores_forwarded_for_from_loopback` on a real uvicorn,
    `test_tunnel_identity.py::test_tunnel_client_address_is_cf_connecting_ip`, the `203.0.113.9:4711` row of `test_client_address.py`);
    oversized message (`test_body_limit.py::test_on_the_tunnel_port_a_seat_keeps_the_lobby_allowance`, `::test_a_stranger_gets_256k_on_lobby_routes`);
    repeated action id / an action in flight at unshare (`test_share_api.py::test_stop_sharing_closes_only_tunnel_sockets` asserts at
    most one log entry for its `client_action_id`; `::test_a_rest_action_queued_behind_the_unshare_is_refused`). "Timeout racing an
    action": not applicable, it belongs to Stage 3's clock.
11. **Pending (full suite); otherwise met as "no new errors".** ruff 10 = base 10, mypy 303 = base 303 (identical messages); the frontend
    typecheck and 1633 tests pass; the full backend suite is pending the controller. bandit, pip-audit and npm audit are read and
    answered above.
12. **Independent review: pending (controller).** The controller runs the security pass (ledger Ruling 6: an equivalent opus pass, as
    the `security-review` skill needs a git remote) and one fresh reviewer after this commit.
13. **Met.**
    - `git grep -n "\.is_host(" -- backend/app/api` → only `backend/app/api/deps.py:79` (`room_host`).
    - `git grep -n -i "cf-connecting-ip" -- backend/app` → only `deps.py:85,87` (`client_address`) and `netguard.py:154` (the
      `cf_client_key` docstring).
    - `git grep -n "proxy_headers" -- backend/app` → `launcher.py:329` (docstring) and `launcher.py:334` `"proxy_headers": False}`: only
      `False`.
    - One limiter class (`AttemptLimiter`, which gained `undo_last`), one Host/Origin guard (`net_guard` + `host_ok`/`origin_ok`, each with
      a tunnel branch), one body limit (`BodyLimit`, which asks `is_host_request`/`is_tunnel_request`).

### Stage 2 must (Stage 1 audit), plus NB1 and SR1

| # | Item | Task (commit) | Tests |
|---|---|---|---|
| 1 | The tunnel port filters what a stranger reads; no LAN code reaches a tunnel connection (final fix wave, M8) | 9 (`38d4a7c`, `ef34d97`); final fix wave (M8) | `test_tunnel_routes.py::test_games_list_and_summary_hide_codes_on_the_tunnel_port`, `::test_pod_stats_and_assets_list_404_on_the_tunnel_port`, `::test_health_is_trimmed_for_guests`, `::test_unshared_room_is_no_such_room`, `::test_every_route_is_either_allowed_or_404_on_the_tunnel_port`, `::test_the_tunnel_branch_is_what_refuses`. `GET …/result` of a *shared* table stays readable (accepted, gate point 2). Seated remote players' views: `test_share_api.py::test_the_lan_code_never_reaches_a_tunnel_connection`. |
| 2 | The tunnel port never passes the LAN gate | 9 (`38d4a7c`) | `test_tunnel_routes.py::test_lan_handoff_routes_404_on_the_tunnel_port` (with `CF-Connecting-IP: 192.168.1.5`) |
| 3 | Limits keyed by the provider's client address, per /64 | 8 (`b380b0e`), 11 (`4e62f5a`) | `test_tunnel_identity.py::test_tunnel_client_address_is_cf_connecting_ip`, `::test_cf_client_key`, `::test_two_phones_in_one_ipv6_64_share_a_bucket_but_other_64s_do_not`, `::test_lan_port_never_reads_cf_connecting_ip`, `::test_a_seat_reconnects_from_a_new_address`; `test_shared_rooms.py::test_wrong_password_on_the_tunnel_port_counts_against_cf_address`. The socket caps and the asset throttle read the same `client_address`. |
| 4 | A cap on spectator tokens | 7 (`3520aa4`) | `test_spectator_cap.py`: `test_33_spectators_leave_32_and_the_first_is_refused`, `test_the_dropped_spectators_socket_closes_4403`, `test_a_dropped_spectators_queued_deck_goes_with_them`, `test_restore_keeps_the_newest_32_of_40_in_order_and_round_trips`, `test_the_cap_leaves_seats_alone` |
| 5 | The `__Host-` cookie | 5 (`e4a4014`) | `test_host_auth.py::test_https_session_sets_the_host_prefixed_cookie`, `::test_either_cookie_name_is_the_host`, `::test_plain_http_keeps_the_plain_name` |
| 6 | Delete `FYODOR_LEGACY_WS_TOKEN` | 4 (`811ef22`) | `test_socket_auth.py::test_a_token_in_the_query_is_never_credentials` (also with the variable set) |
| 7 | `connect-src` to the server's own origin | 5 (`e4a4014`) | `test_security_headers.py::test_csp_pins` (no bare `ws:`/`wss:`), `::test_connect_src_names_this_host`, `::test_refused_host_gets_self_only` |
| 8 | Join hashing off the shared threadpool, counted first | 6 (`df8c531`, `62b022b`) | `test_join_limits.py::test_undo_last_removes_only_the_newest_failure`, `::test_concurrent_wrong_joins_stop_at_five`, `::test_other_routes_answer_while_joins_hash` (40 addresses), `::test_a_right_join_costs_the_address_nothing` |
| 9 | Development origins only in development | 4 (`811ef22`) | `test_origin_guard.py::test_dev_origins_are_refused_by_default`, `::test_dev_origins_with_dev_tools`, `::test_cors_origins_variable_wins` |
| 10 | An `X-Forwarded-For` entry with a port | 3 (`1b854db`) | `test_client_address.py:29`, row `(("127.0.0.1",), "127.0.0.1", "203.0.113.9:4711", "127.0.0.1")`; also `test_launcher.py::test_uvicorn_does_not_rewrite_the_client_from_headers`, `::test_a_real_server_ignores_forwarded_for_from_loopback` |
| NB1 | Large body allowances only for the host or a seat; through the tunnel only a seat's (final fix wave, I1: NB1's "never through the tunnel" overreached for seats) | 10 (`c4f0fc5`); final fix wave (I1) | `test_body_limit.py::test_a_guest_gets_256k_on_host_routes`, `::test_the_host_keeps_the_large_allowance`, `::test_a_stranger_gets_256k_on_lobby_routes`, `::test_a_seat_keeps_the_lobby_allowance`, `::test_on_the_tunnel_port_a_seat_keeps_the_lobby_allowance`, `::test_no_host_or_any_allowance_on_the_tunnel_port`, `::test_the_route_speaks_first_for_streamed_uploads` |
| SR1 (F1) | The host's own seat can't be removed; a left seat can't be claimed | 2 (`0a0cd16`) | `test_host_seat_guard.py::test_host_cannot_remove_their_own_seat`, `::test_a_left_seat_cannot_be_claimed`, `::test_join_without_a_seat_skips_left_seats`, `::test_the_exploit_from_the_review_fails` |

### Manual check through a real tunnel

**NOT DONE — owner's to do** (ledger Rulings 1, 5, 6). It needs the host computer started from the launcher, a phone on **mobile
data** (Wi-Fi off), an iPhone, and a second device on the LAN. Each line is an action and what you should see.

- [ ] Start Fyodor from its launcher. Open a LAN lobby; press **Invite** → **Invite over the internet**, type a password (8 or more
      characters), **Share with this password**. The first time it says *Starting the link… the first time downloads the tunnel
      program (about 55 MB)*; then a link
      `https://<name>.trycloudflare.com/#/play?code=…&join=1` with **Copy link**, *Send the password separately.* and **Stop sharing**.
      Copy the link.
- [ ] A phone on mobile data (not on the Wi-Fi) opens the link: it asks for the password, joins, takes a seat, plays a land; the land
      appears on the host's screen at once.
- [ ] The top bar on the host and on the phone shows the globe chip *Shared over the internet*. The phone shows no 6-character room code.
- [ ] The phone closes the tab and opens the same link again: after the password it is back in **its own** seat (no second seat in the
      lobby; mid-game no *The table is full*). The host's **⋯ → Host tools → Reclaim / assign seat** for the phone's seat shows an
      *Over the internet* link (`https://<name>.trycloudflare.com/#/game/…`) that the phone can open.
- [ ] A LAN table made with a short password (e.g. `pod`): **Invite over the internet** says *This table already has a password.*;
      **Set a new password** (8+ characters) shares it; the old password no longer joins on the LAN or the link, LAN players already
      seated play on. (And **Share with it** at a table with a long password shares at once.)
- [ ] The phone sleeps (locked) for a minute, then wakes: the same seat and hand, no *Too many connections*.
- [ ] Review Focus 1: mid-game the phone switches from Wi-Fi to mobile data: it reconnects to the same seat, with no 429 and no new join.
- [ ] On the phone, open by hand `https://<name>.trycloudflare.com/api/saves` → 404, `/api/games` → `[]`, `/api/pod/results` → 404.
- [ ] A LAN player joins by the 6-character room code as always and plays.
- [ ] Review Focus 3: the host presses **Stop sharing**: the phone's table closes with *The host stopped sharing this table.*; the LAN
      player plays on; the chip disappears.
- [ ] The host invites again: a **new** invite code (`code=` in the link), and a **new** hostname when no other table was shared
      (with another table still shared the hostname stays the same). The old link no longer opens the table.
- [ ] Review Focus 4 (optional): while shared, end `cloudflared-2026.11.2` in Task Manager: the chip goes, the invite panel says *The
      internet link went down.* and offers **Invite again**.
- [ ] The host closes Fyodor: the link stops answering (a Cloudflare error page), and Task Manager (or `Get-Process cloudflared*`) shows
      no `cloudflared-2026.11.2` left. (The program is stored as `<data folder>\tunnel\cloudflared-2026.11.2.exe`.)
- [ ] Repeat the join on an **iPhone** (Safari, mobile data): the page loads, the table's socket connects (the CSP is
      `connect-src 'self' ws://<name> wss://<name>`), a land can be played.
- [ ] Task 15's look (not done by its implementer): screenshots of the lobby's Invite popover and of Host tools → *Invite over the
      internet* in each state (button, password, starting, link, failed), and of the *Shared over the internet* chip, at 1920×1080 and at a
      phone width; an `impeccable` critique of them; fix what fits the tabletop direction.
- [ ] Task 1's open question (HTTP/2): with four tabs or devices opening one 100-card table through the link in real browsers, do card
      pictures that got a 429 come back (the page retries once after about a second)? Note any picture left broken.

### Remaining risks

Provider (Task 1, section 3):

1. Cloudflare positions quick tunnels "for testing and development" with "no uptime guarantee", and can change or end them without
   notice (website terms, section 2). The owner accepted this (section 1). If it stops, internet play stops; LAN play is unaffected.
2. A quick tunnel carries at most 200 in-flight requests; more get a 429 with no `Retry-After` and an empty body. Four tabs × 100
   pictures got 188–197 429s (3.6). The page retries a picture once (Task 15); how real browsers' HTTP/2 multiplexing meets the cap was
   not measured (owner's checklist).
3. Cloudflare sees all traffic through the link (it terminates https). A visitor's `True-Client-IP` passes through unchanged: Fyodor
   never reads it (only `CF-Connecting-IP`, which Cloudflare refuses from a visitor, 3.4).
4. A brand-new hostname is not resolvable for a few seconds; a resolver that cached the miss can keep failing a little longer (3.2).
5. A hard kill of Fyodor on macOS or Linux leaves `cloudflared` running, pointing at a closed port (the link answers an error, nothing
   is served); on Windows the job object ends it with Fyodor (`test_tunnel_process.py::test_the_child_dies_with_the_job`). Windows on
   ARM64 runs the amd64 build (Task 12; there is no arm64 Windows asset).
6. Task 12: verify-then-launch is not atomic: something able to write the user's data folder between the check and `Popen` could swap
   the program. Extraction of the macOS archive has no size bound of its own (safe: the archive's hash is checked first).

Sharing:

7. Anyone holding the link and the password can join; the host's kick and seat tools are the remedy (spec).
8. **Fixed in the final fix wave (M5, I3)**, was: neither credential rotated. Now **Stop sharing** clears the invite code (the next
   share has a new one), and sharing with a password replaces the table's. What remains: the hostname is new only when no other table
   was being shared; a shared table's code is the same while it stays shared (sharing again to set a new password keeps the link).

9. Task 14: closing a shared table (or loading a save over it) at the same instant as a share request can leave the tunnel running with
   nothing shared (`close_game`/`load_save` check `shared` before `share_lock`); `response_call.early` and an `ALREADY_APPLIED` replay
   run before the tunnel re-check; `load_save`'s `hub.close` runs without `room.lock` (older); a failing share's stop-if-unused can 502
   a concurrent second share (fails safe); tests read `asyncio.Lock._waiters`.
10. Task 13: `TunnelManager.stop()` blocks up to about 5 s (routes call it in an executor); the die-during-start test is
    timing-dependent; `main.py`'s lifespan ordering (discovery stop before services close) was noted for the final review.
11. Task 9: on a shared table a stranger without a seat can read its summary (no code), `GET …/result` and `GET /api/macros`; a seated
    remote player no longer sees the LAN code (fixed in the final fix wave, M8); `…/save//` (two slashes) still gets Starlette's 307
    (nothing exposed); a configured `FYODOR_CORS_ORIGINS` is echoed on tunnel GETs (development only); every new player-facing game
    route needs a line in the frozen allowlist test (ledger ruling).
12. Task 8: the undo display fields (`hub.py` ~875) use `viewer == host_seat`, not the connection, so a remote host-seat view may offer
    an undo the server refuses; `is_tunnel_request` matches the port only (not also `127.0.0.1`); `create_server` resolves a hand-set host
    name to IPv4 only; the sockets can leak if `create_app`/lifespan fails before start; uvicorn no longer prints its "running on" line.
13. Task 6: `undo_last` pops the newest failure (the wrong entry only if the reservation expired during a 900 s queue, or after
    `MAX_KEYS` eviction); the `hash_pool` queue is unbounded; `Services.close()` waits for the pool; a join may seat into a room closed
    during the hash (older). `/api/health`'s cost and `journal.lock` hold times were noted for the final review.
14. Task 10: `/api/lan/handoff/missing` still parses up to ~2 MB of JSON per LAN request (LAN only; 404 on the tunnel); the teach
    import's own 413 text is unreachable; stale comments above `_DECK_TEXT` and in `BodyLimit`; no HTTP test for a spectator's grant or
    for the host cookie on the tunnel; `is_host_request`/`is_tunnel_request` run on every request.
15. Task 15: the status poll gives up after 3 misses with no Retry in the page (a remount is needed) and its error is never cleared; a
    `src` change does not clear a pending picture retry (one extra load); the tunnel flag from `/api/health` is cached for the page's
    life (a transient failure on a tunnel page shows the LAN code chip); the Show-password icon is `hand`; (fixed in the final fix wave,
    M3:) the "about 40 MB" text
    understates the 55 MB Windows download (`InternetInvite.tsx:66` and `internetInvite.test.ts:55`; not changed by the gate); the
    screenshots and critique are not done (owner's checklist).
16. Tests not written (deferred minors): Task 2 (a non-host `remove_player` of the host seat, the socket path; one test ends on
    `is_host("")`), Task 3 (`thread.is_alive()` after join), Task 5 (`ws://[::1]` host-source support varies by browser; `'self'`
    covers it), Task 7 (socket reconnect with a dropped token; a duplicated case; a receive loop that could flake), Task 8 (started-game
    `HOST_ONLY_ACTIONS` on the tunnel client), Task 12 (HTTP 404/500, connect error, corrupt archive, missing or hard-link member,
    cross-host redirect). Task 1's audit lacks a "wrapper log: 0 entries" line for the forged-header cases (the 403 at the edge stands).
17. Dependency upgrades still open from Stage 1 (its risk 11): `pip` in the environment; `vite`, `source-map-js`, `vitest`,
    `@vitest/mocker` in `frontend/`.
18. Gate point 8's literal `except Exception` in `TunnelManager._start` (re-raises): accepted by the final review, marked `# noqa: BLE001`
    with its reason (final fix wave, M7). The one literal deviation of gate point 8.

19. **Fixed in the final fix wave (M4):** `docs/SECURITY.md` no longer says "never needs the Internet during play", the old
    `X-Forwarded-For` paragraph and "10 per minute" are replaced, and the tunnel port is described.

Final review and security pass (final fix wave):

20. **Fixed:** I1 (a tunnel seat keeps the lobby body allowance; `test_body_limit.py::test_on_the_tunnel_port_a_seat_keeps_the_lobby_allowance`),
    I2 (a join holding the seat's token gets that seat back, after the password; the Play page sends the token held for the code;
    Host tools adds the seat link on the internet address: `test_share_api.py::test_the_invite_link_brings_a_player_back_to_their_seat`,
    `::…_mid_game`, `frontend/src/pages/lanBits.test.ts`), I3 / security F1 / M10 (sharing with a password replaces the table's; the
    panel asks *Share with it* or *Set a new password*: `test_share_api.py::test_sharing_with_a_new_password_replaces_the_tables`,
    `frontend/src/game/internetInvite.test.ts`). What remains of I2: opening the link again finds the seat only while the table stays
    shared under the same invite code and only in the browser that joined (a re-share has a new code, M5); a seat holder opening a
    *watch* link is given their seat back; a mid-game remote player whose browser lost its token still needs the host's seat link.
    What remains of I3: **Share with it** still shares a short LAN password if the host chooses it (the server cannot measure a hash).
21. **Fixed (security F2 / M1), tunnel only:** once the per-room limiter has blocked a shared room (30 wrong passwords in 15 minutes),
    a join by its invite code is refused (429, the room's Retry-After) before any password is hashed, the right one too
    (`test_share_api.py::test_a_room_blocked_on_the_tunnel_refuses_before_hashing`, counting hash calls). Consequences: a guesser
    with many addresses can lock remote joiners out for up to 15 minutes (the LAN joins as ever; a player rejoining with their seat's
    token is let through to the password check); the room key is the LAN code, so wrong guesses on the LAN count towards the
    tunnel's pause too. Below the threshold the `hash_pool` queue is still unbounded (risk 13).
22. **M2 (recorded, not fixed):** a password holder can evict every spectator. A right password costs the address nothing, so repeated
    `spectate: true` joins through the link push the 32-token cap and drop the earliest spectators, the LAN's included
    (`hub.py`, the spectator cap in `claim_seat`); the host has no kick for spectators. Later: count successful spectator joins per
    address, or exempt the LAN's tokens from eviction by tunnel joins.
23. **M6 (recorded, not fixed):** strangers with only the hostname reach the card and image routes with no per-address budget.
    `GET /api/images/{id}` on a cache miss calls `token_art.fetch` (`cards.py:140`): a stranger can make the host download each
    token/plane picture from Scryfall once (a few thousand, cached, 4 at a time, `token_art.py:83`) and hold sync worker threads on
    that 4-slot gate; `/api/cards/search` and `/cards/batch` (2,000 ids) are unthrottled. Bounded by the token set and Cloudflare's
    200 in-flight. Later: a per-CF-address request budget (with the turn clock or after).
24. **cloudflared 2026.11.x vs 2026.10.7: FIXED 2026-11-25.** Re-pinned to 2026.11.2 on the owner's decision ("move to a newer release"), overriding the 14-day rule (Ruling 3) because of VULN-170057 and VULN-187395; hashes re-verified in section 3.0b. Original note (final review, ruling 3; read 2026-11-25):
    The GitHub release pages of 2026.11.0 (12 Nov) and 2026.11.2 (23 Nov) carry only their SHA256 checksums, no notes. The
    repository's `RELEASE_NOTES` file lists:
    - 2026.11.0: "TUN-11065: Run Windows CI on production runners", "chore: Bump golang to 1.27.4", "chore: Use correct logger",
      "**VULN-170057: Don't bypass access with matrix parameters**".
    - 2026.11.1: "TUN-11062: Reconnect on account region changes", "chore: Update base images to latest versions",
      "**VULN-187395: Bump OpenTelemetry to 1.47.0**", "fix: Allow quick tunnels to fall back to HTTP/2".
    - 2026.11.2: "TUN-11396: Bump golang.org/x/net and golang.org/x/crypto", "chore: Update Google Distroless image digests",
      "TUN-11362: Read the whole protocol version of a tunnel stream".
    So yes: 2026.11.0 fixes a security issue present in 2026.10.7 (VULN-170057, a Cloudflare Access bypass through matrix
    parameters), and 2026.11.1 (included in 2026.11.2) another (VULN-187395, a dependency). Neither note says more. VULN-170057 concerns
    Access rules on a tunnel's ingress; Fyodor runs a quick tunnel with `--config <empty>` and no Access policy, so it appears not to
    apply, but that is a reading of a one-line note, not a verification. The Go 1.27.4 and x/net/x/crypto bumps give no reason.
    2026.11.2 is 2 days old (under the plan's 14-day rule); 2026.11.0 turns 14 days old on 2026-11-26. **Owner's decision** whether
    to re-pin before merge (it needs the five hashes re-verified as in section 3.0a). **Decided: re-pin (section 3.0b).**
25. Follow-ups from the fix wave: a remote spectator taking a lobby seat uses the invite code this browser joined with (its view has no
    LAN code since M8); a browser that never stored one (storage blocked) gets the normal refusal and joins by the link instead.


### Before merging

1. **FULL SUITE: PASSED** at f10604c (2026-11-26, `-n 3`, exit 0, about 42,500 tests, 0 failed).
2. **Independent review: done** (final whole-branch review, security pass, one fix wave and a scoped re-review; see the SDD ledger).
3. **Manual check through a real tunnel:** NOT DONE — owner's to do (checklist above).
4. Merge order: Stage 1 (`internet-play-stage1`) first, then this branch. Do not merge until the owner has read this file.
