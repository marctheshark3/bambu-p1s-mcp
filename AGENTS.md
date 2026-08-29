# Agent notes

Execute [`GOAL.md`](GOAL.md). This repo is a harness-agnostic MCP server for one Bambu Lab P1S.

- Secrets stay in `.env` on the MCP host. Never commit access codes.
- Write tools need `confirm=true`. Check `printer_status` first.
- Run the MCP process where MQTT `:8883` and FTPS `:990` are reachable. Hermes on Spark should use Streamable HTTP against that host.
- Tests: `uv run pytest`. Live printer: `uv run bambu-p1s-mcp doctor`.
