# bambu-p1s-mcp

Harness-agnostic [MCP](https://modelcontextprotocol.io) server for a **Bambu Lab P1S** on the local network.

Any MCP client can use it: **Hermes**, **Grok**, Claude Code, Cursor. The server speaks **stdio** (local subprocess) and **Streamable HTTP** (remote harness).

It does not talk to Bambu Cloud. It talks to the printer:

- MQTT over TLS, port **8883** — status and print commands
- Implicit FTPS, port **990** — list / upload files
- JPEG over TLS, port **6000** — live chamber camera and snapshots
- Optional **Bambu Studio CLI** — slice STL/3MF to a printable `.gcode.3mf`

## Where to run it

The MCP process has to reach the printer. The agent harness does not.

If Hermes is on a DGX Spark that is **not** on the printer LAN, run this server on the LAN machine (or any box that can open `192.168.x.x:8883` and `:990`) and point Hermes at the HTTP URL. Grok on that same LAN box can use stdio.

This clone lives at `/home/whaleshark/Documents/bambu-p1s-mcp`. On the current LAN box the printer-facing IPs are typically:

- LAN: `192.168.1.195`
- Tailscale: `100.123.149.116`

Spark should use whichever of those it can route to, on port `8765`.

```
P1S  <--- MQTT/FTPS ---  MCP host
                           |-- stdio --> harness on this host
                           |-- HTTP  --> Hermes on Spark / any remote MCP client
```

## Install

```bash
cd /home/whaleshark/Documents/bambu-p1s-mcp
uv sync --extra dev
cp .env.example .env
# fill BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL from the printer screen
uv run bambu-p1s-mcp doctor
```

Printer screen: **Settings → Network** for IP and access code, **Settings → Device** for serial. Turn on LAN mode. Developer Mode if local `project_file` start is rejected.

## Run

Stdio (Grok / Hermes on this machine):

```bash
uv run bambu-p1s-mcp
```

HTTP daemon (Hermes on Spark, or any remote client):

```bash
# bind LAN/Tailscale; set BAMBU_MCP_TOKEN in .env
BAMBU_MCP_HOST=0.0.0.0 uv run bambu-p1s-mcp --http
# health: http://<host>:8765/health
# mcp:    http://<host>:8765/mcp
# camera: http://<host>:8765/camera
```

User systemd unit: `contrib/bambu-p1s-mcp.service`. It defaults to localhost;
set the bind address and token in the host's `.env` for remote clients.
Startup refuses a non-loopback bind without `BAMBU_MCP_TOKEN`.

## Point a harness at it

Grok (`~/.grok/config.toml`), stdio:

```toml
[mcp_servers.bambu]
command = "/home/whaleshark/Documents/bambu-p1s-mcp/.venv/bin/bambu-p1s-mcp"
startup_timeout_sec = 45
```

Grok, HTTP (after the daemon is up):

```toml
[mcp_servers.bambu]
url = "http://127.0.0.1:8765/mcp"
headers = { Authorization = "Bearer ${BAMBU_MCP_TOKEN}" }
```

Hermes (`~/.hermes/config.yaml`) on Spark:

```yaml
mcp_servers:
  bambu:
    url: "http://192.168.1.195:8765/mcp"
    headers:
      Authorization: "Bearer ${BAMBU_MCP_TOKEN}"
    timeout: 180
```

If Spark is only on Tailscale, use `http://100.123.149.116:8765/mcp`. Reload with `/reload-mcp`.

Ready-to-copy snippets: [`configs/`](configs/).

## Tools

| Tool | Write? | What it does |
|---|---|---|
| `printer_doctor` | no | Env, ports (including camera), MQTT, FTPS, slicer |
| `printer_status` | no | Idle/printing, job, %, layers, temps, remaining |
| `printer_ams` | no | AMS / external trays |
| `printer_files` | no | SD card listing |
| `printer_camera_snapshot` | no | New chamber JPEG as native MCP image content |
| `printer_camera_stream` | no | HTTP viewer and stream connection instructions |
| `printer_pause` / `resume` / `stop` | yes | Job control |
| `printer_speed` | yes | silent / standard / sport / ludicrous |
| `printer_upload` | yes | Push a sliced file over FTPS |
| `printer_print` | yes | Upload if local path, then start |
| `slice_model_file` | yes | Bambu Studio CLI → `.gcode.3mf` |

Write tools require `confirm=true`. `printer_print` refuses if the printer is already `RUNNING`.

Ask an agent:

- “What’s on the P1S right now?”
- “Anything in the AMS?”
- “Show me the P1S camera.”
- “Slice `~/Documents/lamp/stls/base.stl` for the P1S.”
- “Upload that 3mf and print plate 1.”

## Live camera

Run the HTTP daemon on the printer LAN host and open
[`http://127.0.0.1:8765/camera`](http://127.0.0.1:8765/camera).
For another machine, use the MCP host's reachable LAN/Tailscale address and set
`BAMBU_MCP_TOKEN` before binding to that interface. The host also needs access to
printer TCP **6000** (`BAMBU_CAMERA_PORT` overrides the default).

The browser shows the native JPEG feed as MJPEG. The stock P1S camera is
[1280 × 720 at approximately 0.5 fps](https://au.store.bambulab.com/products/p1s):
expect a new image roughly every two seconds. A separate camera is needed for
smooth video; converting this feed to WebRTC will not add captured frames.

| Endpoint | Purpose |
|---|---|
| `/camera` | Browser viewer with Start/Stop and reconnects |
| `/camera/snapshot.jpg` | Wait for a new JPEG and return it |
| `/camera/stream.mjpg` | Continuous `multipart/x-mixed-replace` JPEG stream |

The viewer shell is public and contains no camera data or credentials. When
`BAMBU_MCP_TOKEN` is set, camera data requires `Authorization: Bearer <token>`,
just like `/mcp`. Enter the **server token** in the viewer; the printer access
code stays on the MCP host. The viewer holds the token only in memory and sends
it in request headers, never in a URL or browser storage. Use Tailscale or HTTPS
for remote access so bearer tokens are protected in transit.

One camera connection is shared by all viewers and snapshot calls in a server
process. It reconnects after failures, retains only the latest frame, and closes
after viewers stop requesting frames (normally about ten seconds; stalled reads
can take up to another fifteen seconds). Separate stdio/HTTP processes each
have their own connection; prefer one HTTP daemon when sharing the camera.

`printer_camera_snapshot` works over **both stdio and HTTP** and returns an MCP
image that a vision-capable client can inspect. `printer_camera_stream` returns
the paths above; continuous video is served over HTTP, not in an MCP tool result.
Camera reads do not enable the chamber light, start a print, or change settings.
The image helps check the bed but does not establish that it is safe to print.

If the feed is unavailable, run `uv run bambu-p1s-mcp doctor` to check camera port
reachability, then request a snapshot to verify authentication and actual frames.
Check the printer IP/access code, LAN/Developer Mode, and other camera clients.
A reachable TCP port alone does not prove the camera has authenticated.

## Local operation and source code

Camera, status/AMS, file transfer, and job commands use the printer's LAN
interfaces. Bambu documents
[Developer Mode for local MQTT, FTP, and live streaming](https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/)
when firmware authorization would otherwise restrict third-party clients.
Enable it on the printer if needed; no firmware decompilation or Bambu Connect
certificate extraction is needed for this workflow.

[Bambu Studio is open source and has build instructions](https://github.com/bambulab/BambuStudio).
Use its installed CLI for slicing, or build its published source if slicer changes
are needed. Its optional proprietary networking plugin is a separate component;
this server uses the LAN interfaces directly. This does not imply that every
Bambu Handy/cloud feature or firmware function is exposed here.

The remaining setup for a remote client is a reachable HTTP host, a server token,
and a client configured for `/mcp`. Machine/process/filament profiles are needed
for bare models. Model paths refer to files on the MCP host, so stage remote
models there (for example, with SFTP or a shared folder) before slicing/uploading.
Check printer status and the bed before sending a confirmed
print command; live viewing alone does not authorize printing.

## Slice notes

`BAMBU_SLICER` should point at the `bambu-studio` binary (this machine has `/home/whaleshark/.local/bin/bambu-studio`).

Project `.3mf` files that already contain printer settings can be sliced as-is. Bare STL/STEP needs machine + process + filament JSON. The server auto-discovers P1S 0.4 / `0.20mm Standard @BBL X1C` / `Bambu PLA Basic @BBL P1S 0.4 nozzle` from `~/.config/BambuStudio/system/BBL` when present.

## Security

- LAN access code authenticates MQTT, FTPS, and the camera. Keep it in `.env`, not in git.
- HTTP without `BAMBU_MCP_TOKEN` is only for localhost. When Spark (or anything off-box) connects, set a token and bind `BAMBU_MCP_HOST=0.0.0.0`.
- Token-free listeners reject non-loopback Host headers and foreign browser Origins to guard against DNS rebinding and cross-origin requests.
- Do not port-forward this to the public internet.
- This is not affiliated with Bambu Lab.

### Operation without Bambu Cloud

This MCP implements local MQTT, FTPS, and camera connections directly. It does
not load Bambu's proprietary networking plugin or log into Bambu Cloud. Slicing
uses the local CLI and local profiles. This describes the MCP's behavior, not a
guarantee about other programs on the host or the printer's own outbound traffic.

For a setup controlled by your own infrastructure:

1. Enable LAN Only Mode on the printer. Enable Developer Mode if its firmware
   requires it for third-party local control. Developer Mode exposes local
   interfaces; it is not a security boundary.
2. Reserve the printer's address and place it on an isolated printer/IoT VLAN
   where possible. Allow the MCP host to reach it, including FTPS passive data
   connections as well as ports 8883, 990, and 6000. Allow return traffic for
   those connections and any explicitly required local infrastructure services.
3. Deny printer access to the internet, covering **both IPv4 and IPv6**, and deny
   unsolicited access to the printer from other networks. Blocking only Bambu
   domains or DNS does not establish isolation. Devices on the same subnet can
   communicate without passing through the router, so use VLANs or suitable
   switch/AP isolation to restrict that path as well.
4. Expose the MCP only to trusted clients. For fully self-hosted remote access,
   use an SSH tunnel or your own WireGuard VPN. Bind to localhost for an SSH
   tunnel, or to the private VPN interface with `BAMBU_MCP_TOKEN` set. Do not
   forward printer ports or the MCP port from the public internet. Bearer auth
   alone does not encrypt HTTP traffic.
5. Verify router rules/counters and repeat status, camera, file listing, and a
   deliberately confirmed print while printer WAN access is blocked. A successful
   `doctor` check establishes LAN connectivity, **not** internet isolation.

The MQTT, FTPS, and camera clients currently accept the printer's self-signed
TLS certificate without verifying its identity. Restricting access to the
printer network therefore matters even though those connections are encrypted.
Keep access codes and server tokens in the host's `.env`, restrict its permissions
to the service user, and run the service without root privileges.

Bambu cloud-dependent workflows will need local replacements; this repository
covers camera viewing, status/AMS, slicing, uploads, and job control. Plan separate
maintenance for firmware updates. Router isolation does not replace the stock
firmware or establish that the device is invulnerable.

## Goal

Agent brief: [`GOAL.md`](GOAL.md).
