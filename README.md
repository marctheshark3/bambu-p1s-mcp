# bambu-p1s-mcp

Harness-agnostic [MCP](https://modelcontextprotocol.io) server for a **Bambu Lab P1S** on the local network.

Any MCP client can use it: **Hermes**, **Grok**, Claude Code, Cursor. The server speaks **stdio** (local subprocess) and **Streamable HTTP** (remote harness).

It does not talk to Bambu Cloud. It talks to the printer:

- MQTT over TLS, port **8883** — status and print commands
- Implicit FTPS, port **990** — list / upload files
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
```

User systemd unit: `contrib/bambu-p1s-mcp.service`.

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
| `printer_doctor` | no | Env, ports, MQTT, FTPS, slicer |
| `printer_status` | no | Idle/printing, job, %, layers, temps, remaining |
| `printer_ams` | no | AMS / external trays |
| `printer_files` | no | SD card listing |
| `printer_pause` / `resume` / `stop` | yes | Job control |
| `printer_speed` | yes | silent / standard / sport / ludicrous |
| `printer_upload` | yes | Push a sliced file over FTPS |
| `printer_print` | yes | Upload if local path, then start |
| `slice_model_file` | yes | Bambu Studio CLI → `.gcode.3mf` |

Write tools require `confirm=true`. `printer_print` refuses if the printer is already `RUNNING`.

Ask an agent:

- “What’s on the P1S right now?”
- “Anything in the AMS?”
- “Slice `~/Documents/lamp/stls/base.stl` for the P1S.”
- “Upload that 3mf and print plate 1.”

## Slice notes

`BAMBU_SLICER` should point at the `bambu-studio` binary (this machine has `/home/whaleshark/.local/bin/bambu-studio`).

Project `.3mf` files that already contain printer settings can be sliced as-is. Bare STL/STEP needs machine + process + filament JSON. The server auto-discovers P1S 0.4 / `0.20mm Standard @BBL X1C` / `Bambu PLA Basic @BBL P1S 0.4 nozzle` from `~/.config/BambuStudio/system/BBL` when present.

## Security

- LAN access code is the MQTT/FTPS password. Keep it in `.env`, not in git.
- HTTP without `BAMBU_MCP_TOKEN` is only for localhost. When Spark (or anything off-box) connects, set a token and bind `BAMBU_MCP_HOST=0.0.0.0`.
- Do not port-forward this to the public internet.
- This is not affiliated with Bambu Lab.

## Goal

Agent brief: [`GOAL.md`](GOAL.md).
