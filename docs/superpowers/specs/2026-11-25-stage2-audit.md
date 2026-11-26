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
