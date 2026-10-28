# Snipe-IT MCP server

Ask Claude about your assets in plain words: who has laptop LAP-0142, what needs auditing this month, what's
running low. Check assets out and in from the same chat, with a confirmation step before anything changes.

Built by [Mojood Connect](https://mojood.app/connect) as a working demo for [Snipe-IT](https://snipeitapp.com).
It runs against any Snipe-IT through its REST API. This repository includes a local Snipe-IT with **SAMPLE data**
for a made-up company, Harbor Trading, so you can try it without touching a real instance.

## Tools

| Tool | What it does | Changes anything? |
| --- | --- | --- |
| `find_asset` | Find assets by tag, serial, model or holder: status, who has it, where, next audit, warranty end | No |
| `whats_assigned_to` | Everything checked out to one person; asks which person when a name matches several | No |
| `needs_attention` | Audits overdue and due, loans overdue and due back soon, warranties ending, assets out of service | No |
| `low_stock` | Consumables and accessories below their minimum quantity | No |
| `check_out_asset` | Assign an asset to a person | Yes, after confirmation |
| `check_in_asset` | Return an asset from whoever holds it | Yes, after confirmation |

**How changes are made safe.** A call to `check_out_asset` or `check_in_asset` without a `confirmation` changes
nothing: it returns a plain summary ("Check out LAP-0160 (ThinkPad T14 Gen 5) to Sara Al-Qahtani, Finance, Dammam
HQ.") and a one-time code. The change happens only when the same request comes back with that code, within 10
minutes. A code works once, and only for the request it was issued for. The server's instructions tell the model to
show the summary and wait for the user's yes. Every change goes through Snipe-IT's own checkout and check-in
endpoints with the note "via Claude (Mojood Connect demo)", so it appears in the asset's history like any change a
person makes.

The server acts as the user who owns the API token, with that user's Snipe-IT permissions.

## Try it locally

Needs Docker (with Compose), [uv](https://docs.astral.sh/uv/) and Python 3.13.

```
scripts/reset.sh                         # local Snipe-IT on http://localhost:8088, filled with the SAMPLE company
uv run --env-file .env snipeit-mcp       # MCP server on http://127.0.0.1:8002/mcp (Streamable HTTP)
```

`scripts/reset.sh` generates every password and the API token itself and keeps them in the git-ignored files
`docker/.env` and `.env`; nothing is printed. Run it again any time to start over from fresh SAMPLE data. Everything
listens on 127.0.0.1 only. `scripts/up.sh` starts it again after a restart without touching the data.

**Claude Desktop:** add this to `claude_desktop_config.json` (Settings › Developer), with the path to this folder:

```json
{
  "mcpServers": {
    "snipe-it": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/snipeit-mcp", "--env-file", "/path/to/snipeit-mcp/.env", "snipeit-mcp", "--stdio"]
    }
  }
}
```

Then ask: "Who has LAP-0142, and what else do they hold?", "What needs attention this month?", "What's running
low?", "Check the spare ThinkPad out to Sara."

**Your own Snipe-IT:** set `SNIPEIT_URL` and `SNIPEIT_TOKEN` (a personal API key from your Snipe-IT profile) and
`SNIPEIT_SAMPLE=0`.

## The SAMPLE company

Harbor Trading: three sites (Dammam HQ, Riyadh office, Jeddah warehouse), 15 people, 48 assets (laptops, monitors,
phones, warehouse scanners, printers) and 7 stock items. Dates are set relative to the day it is seeded, so there
are always audits overdue and due, one loaner laptop 12 days late, one due back in 4 days, warranties ending, a
laptop out for repair and three items below their minimum. The people, serials and prices are made up.

## Tests

```
uv run pytest                            # unit tests (a fake Snipe-IT API), plus live tests when the local Snipe-IT runs
```

## What a production version adds

This demo signs in with one API token. A production server for Snipe-IT customers would add sign-in with each
person's own Snipe-IT account, so Claude sees exactly what they may see; hosting with an audit log of every tool
call; and more of the API (licenses, components, maintenance, requests). That is what
[Mojood Connect](https://mojood.app/connect) builds.

## License

Apache 2.0. Snipe-IT is a trademark of Grokability, Inc.; this project is not made or endorsed by Grokability.
