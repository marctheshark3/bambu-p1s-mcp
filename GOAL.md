# Goal: harness-agnostic P1S MCP

**Status:** implement in this repo. Do not wrap a Claude-only or Grok-only plugin.
**Printer:** Bambu Lab P1S on LAN. MQTT `:8883`, implicit FTPS `:990`, camera TLS `:6000`.
**Handoff:** execute this file. Do not rediscover Bambu cloud APIs.

Paste for the next agent:

> Execute `GOAL.md`. Keep this MCP harness-agnostic (stdio + Streamable HTTP). The process must run on a host that can reach the P1S. Hermes on Spark should connect over HTTP; Grok on the LAN box may use stdio. Tools: doctor, status, AMS, files, pause/resume/stop, upload, print, slice. Write tools require `confirm=true`. No access codes in git.

---

## Job

Give any MCP client (Hermes, Grok, Claude Code, Cursor) the same tools against one P1S:

1. Is the printer reachable, idle, or printing something?
2. What is on the bed / in AMS?
3. Slice a model with the local Bambu Studio CLI when present.
4. Upload a sliced `.gcode.3mf` and start/pause/resume/stop a job.

This is **not** a slicer GUI, not Bambu Handy, and not a cloud integration.

## Where the process runs

The MCP process must have L3 reachability to the printer. Harness location is independent.

```
P1S  --MQTT/FTPS-->  MCP host (this LAN machine is the default)
                       | stdio   --> Grok / Hermes if they run here
                       | HTTP    --> Hermes on DGX Spark, Grok elsewhere
```

| Setup | Run MCP here | Client config |
|---|---|---|
| Grok on the LAN box | stdio subprocess | `command = "bambu-p1s-mcp"` |
| Hermes on Spark, printer on LAN | HTTP daemon on the LAN box | `url: http://<lan-or-tailscale>:8765/mcp` |
| Spark itself can reach `:8883` and `:990` | stdio on Spark | same as Grok |

Do **not** run stdio MCP on Spark if Spark cannot open printer `:8883`. That fails closed and looks like a "broken MCP".

## Done means

All of these hold:

1. `python -m bambu_p1s_mcp doctor` reports MQTT connected without printing the access code.
2. MCP tools exist for status, AMS, files, pause, resume, stop, speed, upload, print, slice, doctor.
3. Write tools no-op unless `confirm=true`.
4. `stdio` and Streamable HTTP both work. HTTP `/health` is unauthenticated; `/mcp` honors `BAMBU_MCP_TOKEN` when set.
5. Harness snippets live in `configs/` for Hermes (`config.yaml`) and Grok (`config.toml`). No secrets in those files.
6. Unit tests pass without a printer (`pytest`).
7. Slice delegates to `bambu-studio` / `orca-slicer`. If the CLI is missing, the tool returns a clear error instead of pretending.

## Non-goals

- Cloud MQTT / Bambu Handy account login
- Multi-printer fleet
- Vendoring Bambu Connect X.509 material
- Starting a print while `gcode_state` is `RUNNING`

## Camera extension

The requested camera extension adds read-only `printer_camera_snapshot` and
`printer_camera_stream` tools. Snapshots return native MCP images over either
transport. The HTTP daemon serves `/camera`, `/camera/snapshot.jpg`, and
`/camera/stream.mjpg`; camera data uses the same bearer authentication as `/mcp`.
The viewer shell is public but contains no printer data or credentials. Keep the
access code on the MCP host and share one camera connection per process.
See the README for setup and the P1S camera's low frame rate.

## Printer prep

On the P1S screen: LAN mode, note IP + access code + serial. Enable Developer Mode if `project_file` is rejected on current firmware.

## Secrets

`BAMBU_ACCESS_CODE` lives in `.env` on the MCP host or the harness env block. Never commit it. Tool errors must redact it.
