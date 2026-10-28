"""Snipe-IT MCP server (Mojood Connect demo): ask about assets in plain words, and check them out or in with a
confirmation step.

Run:  uv run --env-file .env snipeit-mcp          → http://127.0.0.1:8002/mcp (Streamable HTTP)
      uv run --env-file .env snipeit-mcp --stdio  → for Claude Desktop's config file

Settings (environment, written to .env by scripts/up.sh):
  SNIPEIT_URL     the Snipe-IT instance (default http://127.0.0.1:8088)
  SNIPEIT_TOKEN   a Snipe-IT API token; the server acts as that token's user
  SNIPEIT_SAMPLE  "1" (default) says in every session that the data is SAMPLE
  SNIPEIT_MCP_PORT  default 8002
"""

import logging
import os
import sys
from typing import Annotated

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from snipeit_mcp import tools
from snipeit_mcp.client import SnipeIT

SAMPLE = os.environ.get("SNIPEIT_SAMPLE", "1") != "0"
_api: SnipeIT | None = None


def api() -> SnipeIT:
    global _api
    if _api is None:
        _api = SnipeIT()
    return _api


INSTRUCTIONS = f"""\
Snipe-IT asset tracking: laptops, monitors, phones, scanners and printers, who has each one, where it is, audits,
warranties, loans, and consumables and accessories in stock.
{"This is a demo with SAMPLE data for a made-up company, Harbor Trading. " if SAMPLE else ""}\
Answer only from these tools; never guess a tag, a serial or who holds something. Asset tags look like LAP-0142.
check_out_asset and check_in_asset change real records. Call one without `confirmation` first: it changes nothing
and returns what it would do plus a code. Show the user that summary and ask them to confirm. Only after they say
yes, call again with the same arguments and the code. Never confirm on the user's behalf. If a tool returns
`problem`, nothing changed: tell the user why."""

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
CHANGE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

server = MCPServer(
    name="snipeit-mcp",
    title="Snipe-IT",
    description="Asset tracking in Snipe-IT: find assets, who holds what, what needs attention, low stock, check out and in.",
    instructions=INSTRUCTIONS,
    website_url="https://mojood.app/connect",
    version="0.1.0",
)


@server.tool(title="Find an asset", annotations=READ)
def find_asset(
    query: Annotated[str, Field(description='an asset tag ("LAP-0142"), serial, model ("ThinkPad") or a person\'s name')],
) -> tools.Found:
    """Find assets by tag, serial, model or the name of whoever holds them. Returns status, who has each one,
    where it is, its next audit and warranty end."""
    return tools.find_asset(api(), query)


@server.tool(title="What a person holds", annotations=READ)
def whats_assigned_to(
    person: Annotated[str, Field(description='a name, e.g. "Sara" or "Sara Al-Qahtani"')],
) -> tools.Holdings:
    """Everything checked out to one person: assets and accessories. If the name matches several people,
    returns them as candidates: ask which one."""
    return tools.whats_assigned_to(api(), person)


@server.tool(title="What needs attention", annotations=READ)
def needs_attention(
    days: Annotated[int, Field(ge=1, le=365, description="how far ahead to look for returns and warranties")] = 30,
) -> tools.Attention:
    """Audits overdue and due, loans overdue and due back soon, warranties ending soon, and assets out of service."""
    return tools.needs_attention(api(), days)


@server.tool(title="Low stock", annotations=READ)
def low_stock() -> list[tools.StockLine]:
    """Consumables and accessories below their minimum quantity, with how many are left."""
    return tools.low_stock(api())


@server.tool(title="Check out an asset", annotations=CHANGE)
def check_out_asset(
    asset_tag: Annotated[str, Field(description='e.g. "LAP-0160"')],
    person: Annotated[str, Field(description="who it goes to")],
    note: Annotated[str | None, Field(description="optional, kept in Snipe-IT's history")] = None,
    confirmation: Annotated[str | None, Field(description="leave empty first; pass the code only after the user confirms")] = None,
) -> tools.Change:
    """Assign an asset to a person. The first call changes nothing and returns a summary and a confirmation code;
    the change happens only on a second call with the code, after the user has said yes."""
    return tools.check_out_asset(api(), asset_tag, person, note, confirmation)


@server.tool(title="Check in an asset", annotations=CHANGE)
def check_in_asset(
    asset_tag: Annotated[str, Field(description='e.g. "LAP-0162"')],
    note: Annotated[str | None, Field(description="optional, kept in Snipe-IT's history")] = None,
    confirmation: Annotated[str | None, Field(description="leave empty first; pass the code only after the user confirms")] = None,
) -> tools.Change:
    """Return an asset from whoever holds it. The first call changes nothing and returns a summary and a
    confirmation code; the change happens only on a second call with the code, after the user has said yes."""
    return tools.check_in_asset(api(), asset_tag, note, confirmation)


def app():
    security = TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
    )
    # Stateful sessions: a confirmation code must reach the same server process that issued it.
    return server.streamable_http_app(json_response=True, transport_security=security)


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Snipe-IT call is noise in a client's log
    if "--stdio" in sys.argv:
        server.run("stdio")
        return
    uvicorn.run(app(), host="127.0.0.1", port=int(os.environ.get("SNIPEIT_MCP_PORT", "8002")), log_level="info",
                timeout_graceful_shutdown=5)
